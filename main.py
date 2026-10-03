import os
import io
import csv
import json
import secrets
import base64
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from flask import (
    Flask, render_template_string, request, redirect, url_for,
    flash, session, jsonify
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

# ============================================================
# GLOBALROUTE AI — B2B SaaS
# Direct USDC / Solana payment verification
# ============================================================

app = Flask(__name__)

# Secrets are the only important Render variables.
app.secret_key = os.getenv("SECRET_KEY", secrets.token_hex(32))

# Admin password is intentionally read from Render.
ADMIN_SECRET_PASSWORD = os.getenv("ADMIN_SECRET_PASSWORD", "CHANGE-ME")

# ------------------------------------------------------------
# FIXED PUBLIC CONFIGURATION
# These values are safe to keep in code.
# ------------------------------------------------------------

APP_NAME = "GlobalRoute AI"

# Public Solana wallet supplied for receiving payments.
SOLANA_RECEIVING_WALLET = "22BzBEYLewJkKe2FXD6EHJYqX4NNshMw9roNw9qFxV9d"

# Mainnet USDC mint.
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

# Solana mainnet RPC. For high traffic, replace later with a
# dedicated RPC provider, but no secret is needed for this basic setup.
SOLANA_RPC_URL = "https://api.mainnet.solana.com"

# Subscription catalogue.
PLANS = {
    "standard": {
        "name": "Standard",
        "monthly_price": 29.00,
        "annual_price": 290.00,
        "route_limit": 500,
    },
    "pro": {
        "name": "Pro",
        "monthly_price": 59.00,
        "annual_price": 590.00,
        "route_limit": 2500,
    },
    "business": {
        "name": "Business",
        "monthly_price": 99.00,
        "annual_price": 990.00,
        "route_limit": 10000,
    },
    "enterprise": {
        "name": "Enterprise",
        "monthly_price": None,
        "annual_price": None,
        "route_limit": 50000,
    },
}

# Enterprise is quoted manually. Other plans can be purchased for
# 30/90/180/365 days; the annual price is discounted.
DURATIONS = (30, 90, 180, 365)

# ------------------------------------------------------------
# DATABASE
# ------------------------------------------------------------

database_url = os.getenv("DATABASE_URL")

if database_url:
    if database_url.startswith("postgres://"):
        database_url = database_url.replace(
            "postgres://", "postgresql+psycopg2://", 1
        )
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace(
            "postgresql://", "postgresql+psycopg2://", 1
        )
else:
    database_url = "sqlite:///globalroute.db"

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.getenv("COOKIE_SECURE", "0") == "1"

db = SQLAlchemy(app)


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(160), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)

    address = db.Column(db.String(250), default="")
    city = db.Column(db.String(100), default="")
    country = db.Column(db.String(100), default="")

    plan = db.Column(db.String(30), default="standard")
    subscription_started_at = db.Column(db.DateTime, nullable=True)
    subscription_expires_at = db.Column(db.DateTime, nullable=True)

    credits = db.Column(db.Integer, default=0)
    unlimited = db.Column(db.Boolean, default=False)
    active = db.Column(db.Boolean, default=True)
    route_limit = db.Column(db.Integer, default=0)
    routes_used = db.Column(db.Integer, default=0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    api_keys = db.relationship(
        "ApiKey",
        backref="owner",
        lazy=True,
        cascade="all, delete-orphan"
    )

    deliveries = db.relationship(
        "DeliveryRoute",
        backref="company",
        lazy=True,
        cascade="all, delete-orphan"
    )

    payments = db.relationship(
        "PaymentOrder",
        backref="customer",
        lazy=True,
        cascade="all, delete-orphan"
    )


class ApiKey(db.Model):
    __tablename__ = "api_keys"

    id = db.Column(db.Integer, primary_key=True)
    key_string = db.Column(db.String(255), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=True)
    revoked = db.Column(db.Boolean, default=False)


class PaymentOrder(db.Model):
    __tablename__ = "payment_orders"

    id = db.Column(db.Integer, primary_key=True)

    order_code = db.Column(
        db.String(80), unique=True, nullable=False, index=True
    )

    # A unique Solana reference is generated for every order.
    reference = db.Column(
        db.String(64), unique=True, nullable=False, index=True
    )

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    plan = db.Column(db.String(30), nullable=False)
    duration_days = db.Column(db.Integer, nullable=False)

    amount_usdc = db.Column(db.Float, nullable=False)
    asset = db.Column(db.String(20), default="USDC")
    network = db.Column(db.String(30), default="Solana")

    status = db.Column(db.String(20), default="pending")

    transaction_signature = db.Column(
        db.String(160), unique=True, nullable=True
    )

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    paid_at = db.Column(db.DateTime, nullable=True)


class DeliveryRoute(db.Model):
    __tablename__ = "delivery_routes"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False
    )

    driver_name = db.Column(db.String(100), nullable=False)
    route_name = db.Column(db.String(150), default="Tournée")
    access_code = db.Column(
        db.String(80), unique=True, nullable=False
    )
    stops_data = db.Column(db.Text, nullable=False)
    stops_count = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default="En cours")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(120), nullable=False)
    details = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


def _column_type_sql(column):
    """Return a portable SQL type for the lightweight startup migration."""
    try:
        return column.type.compile(dialect=db.engine.dialect)
    except Exception:
        return str(column.type)


def migrate_existing_database():
    """
    Add columns introduced by newer versions without deleting existing data.

    db.create_all() creates missing tables, but it deliberately does not alter
    tables that already exist. The previous GlobalRoute database therefore
    could keep the old `users` schema and make /admin-panel fail when the new
    code selected credits/unlimited/active. This small migration closes that
    gap for the current one-file deployment.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(db.engine)
    existing_tables = set(inspector.get_table_names())

    for table_name, model in (
        ("users", User),
        ("api_keys", ApiKey),
        ("payment_orders", PaymentOrder),
        ("delivery_routes", DeliveryRoute),
        ("audit_logs", AuditLog),
    ):
        if table_name not in existing_tables:
            continue

        existing_columns = {
            col["name"] for col in inspector.get_columns(table_name)
        }

        for column in model.__table__.columns:
            if column.name in existing_columns or column.primary_key:
                continue

            type_sql = _column_type_sql(column)

            # New columns are deliberately nullable during migration. This
            # lets old customer rows survive even when no historical value
            # exists. Application-level defaults handle new records.
            sql = (
                f'ALTER TABLE "{table_name}" '
                f'ADD COLUMN "{column.name}" {type_sql}'
            )

            db.session.execute(text(sql))

        db.session.commit()


with app.app_context():
    # Creates new tables and then upgrades older existing tables in place.
    db.create_all()
    migrate_existing_database()
    try:
        from sqlalchemy import text
        # Backfill fields added to existing installations.
        db.session.execute(text('UPDATE users SET route_limit = 0 WHERE route_limit IS NULL'))
        db.session.execute(text('UPDATE users SET routes_used = 0 WHERE routes_used IS NULL'))
        db.session.execute(text('UPDATE delivery_routes SET stops_count = 0 WHERE stops_count IS NULL'))
        db.session.commit()
    except Exception:
        db.session.rollback()


# ============================================================
# HELPERS
# ============================================================

ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def base58_encode(raw: bytes) -> str:
    number = int.from_bytes(raw, "big")
    result = ""

    while number:
        number, remainder = divmod(number, 58)
        result = ALPHABET[remainder] + result

    leading_zeroes = 0
    for byte in raw:
        if byte == 0:
            leading_zeroes += 1
        else:
            break

    return "1" * leading_zeroes + (result or "")


def generate_reference():
    # 32 random bytes encode to a valid Solana-style public-key string.
    return base58_encode(secrets.token_bytes(32))


def utcnow():
    return datetime.utcnow()


def money(value):
    return f"{float(value):.2f}"


def calculate_price(plan, duration_days):
    if plan not in PLANS:
        raise ValueError("Plan invalide.")
    if duration_days not in DURATIONS:
        raise ValueError("Durée invalide.")
    if plan == "enterprise":
        raise ValueError("Enterprise nécessite un devis.")
    monthly = PLANS[plan]["monthly_price"]
    if duration_days == 365:
        return PLANS[plan]["annual_price"]
    return round(monthly * (duration_days / 30), 2)


def create_api_key(user, expires_at=None):
    key = ApiKey(
        key_string=f"gra_live_{secrets.token_hex(24)}",
        user_id=user.id,
        expires_at=expires_at,
        revoked=False,
    )
    db.session.add(key)
    return key


def active_api_key(user):
    now = utcnow()

    for key in user.api_keys:
        if key.revoked:
            continue

        if key.expires_at and key.expires_at < now:
            continue

        return key

    return None


def add_subscription(user, plan, duration_days):
    now = utcnow()
    if (
        user.subscription_expires_at
        and user.subscription_expires_at > now
        and user.plan == plan
    ):
        start = user.subscription_started_at or now
        expiry = user.subscription_expires_at + timedelta(days=duration_days)
    else:
        start = now
        expiry = now + timedelta(days=duration_days)

    user.plan = plan
    user.subscription_started_at = start
    user.subscription_expires_at = expiry
    user.active = True
    user.route_limit = PLANS[plan]["route_limit"]
    user.routes_used = 0

    # Credits are kept for API compatibility; route quotas are tracked
    # separately so a company can see its actual number of route plans.
    user.credits = user.route_limit
    user.unlimited = False

    key = active_api_key(user)
    if key:
        key.expires_at = expiry
        key.revoked = False
    else:
        create_api_key(user, expiry)

    return expiry


def rpc_call(method, params):
    payload = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params,
    }).encode("utf-8")

    req = urllib.request.Request(
        SOLANA_RPC_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=15) as response:
        data = json.loads(response.read().decode("utf-8"))

    if "error" in data:
        raise RuntimeError(str(data["error"]))

    return data.get("result")


def find_signature_by_reference(reference):
    result = rpc_call(
        "getSignaturesForAddress",
        [reference, {"limit": 20}]
    )

    if not result:
        return None

    for item in result:
        if not item.get("err"):
            return item.get("signature")

    return None


def verify_usdc_payment(order):
    """
    Verify the payment directly on Solana.

    The transaction must:
      - contain this order's unique reference;
      - be successful;
      - contain the expected USDC mint;
      - credit the merchant wallet;
      - contain at least the exact expected amount.
    """

    signature = find_signature_by_reference(order.reference)

    if not signature:
        return False, None, "Paiement non trouvé pour le moment."

    tx = rpc_call(
        "getTransaction",
        [
            signature,
            {
                "encoding": "jsonParsed",
                "commitment": "confirmed",
                "maxSupportedTransactionVersion": 0,
            },
        ],
    )

    if not tx:
        return False, None, "Transaction pas encore disponible."

    if tx.get("meta") and tx["meta"].get("err") is not None:
        return False, None, "La transaction Solana a échoué."

    meta = tx.get("meta") or {}
    post_balances = meta.get("postTokenBalances") or []

    expected_raw = int(round(order.amount_usdc * 1_000_000))

    received_raw = 0

    for balance in post_balances:
        mint = balance.get("mint")
        owner = balance.get("owner")
        amount_info = balance.get("uiTokenAmount") or {}
        amount_raw = int(amount_info.get("amount", "0"))

        if mint == USDC_MINT and owner == SOLANA_RECEIVING_WALLET:
            received_raw += amount_raw

    pre_balances = meta.get("preTokenBalances") or []

    pre_raw = 0

    for balance in pre_balances:
        mint = balance.get("mint")
        owner = balance.get("owner")
        amount_info = balance.get("uiTokenAmount") or {}
        amount_raw = int(amount_info.get("amount", "0"))

        if mint == USDC_MINT and owner == SOLANA_RECEIVING_WALLET:
            pre_raw += amount_raw

    delta = received_raw - pre_raw

    if delta < expected_raw:
        return (
            False,
            signature,
            f"Montant reçu insuffisant. Attendu {order.amount_usdc:.2f} USDC."
        )

    return True, signature, "Paiement USDC confirmé."


def activate_paid_order(order, signature):
    if order.status == "paid":
        return

    user = User.query.get(order.user_id)
    if not user:
        raise RuntimeError("Client introuvable.")

    # Idempotency protection:
    # one order can only be credited once.
    existing = PaymentOrder.query.filter_by(
        transaction_signature=signature
    ).first()

    if existing and existing.id != order.id:
        raise RuntimeError("Cette transaction est déjà utilisée.")

    expiry = add_subscription(
        user,
        order.plan,
        order.duration_days
    )

    order.status = "paid"
    order.transaction_signature = signature
    order.paid_at = utcnow()

    db.session.add(
        AuditLog(
            action="PAYMENT_CONFIRMED",
            details=(
                f"order={order.order_code}; "
                f"user={user.email}; "
                f"plan={order.plan}; "
                f"days={order.duration_days}; "
                f"signature={signature}; "
                f"expires={expiry.isoformat()}"
            ),
        )
    )

    db.session.commit()


def require_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return User.query.get(user_id)


def admin_required():
    return bool(session.get("is_admin"))


def parse_stops_data(raw_data):
    """Read both the new JSON route format and the old pipe format."""
    try:
        data = json.loads(raw_data)
        if isinstance(data, list):
            return data
    except Exception:
        pass

    points = []
    for line in raw_data.split("\n"):
        parts = [x.strip() for x in line.split("|")]
        if len(parts) >= 3:
            try:
                lat = float(parts[1])
                lng = float(parts[2])
            except ValueError:
                continue
            points.append({
                "name": parts[0],
                "address": "",
                "lat": lat,
                "lng": lng,
            })
    return points


def build_route_rows(stops):
    return "".join(
        f"<tr><td>{i}</td><td>{p.get('name','')}</td>"
        f"<td>{p.get('address','')}</td><td>{p.get('lat')}</td>"
        f"<td>{p.get('lng')}</td></tr>"
        for i, p in enumerate(stops, 1)
    )


# ============================================================
# CSS / HTML
# ============================================================

BASE_STYLE = """
:root {
    --navy:#0b1220;
    --blue:#2563eb;
    --blue2:#1d4ed8;
    --green:#059669;
    --red:#dc2626;
    --bg:#f5f7fb;
    --card:#ffffff;
    --text:#172033;
    --muted:#64748b;
    --border:#e2e8f0;
}
* { box-sizing:border-box; }
body {
    margin:0;
    background:var(--bg);
    color:var(--text);
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
}
header {
    background:var(--navy);
    color:white;
    padding:15px 20px;
    display:flex;
    justify-content:space-between;
    align-items:center;
    gap:12px;
}
header h1 { margin:0; font-size:17px; }
nav { display:flex; gap:10px; flex-wrap:wrap; }
nav a {
    color:#cbd5e1;
    text-decoration:none;
    font-size:12px;
}
.container {
    width:100%;
    max-width:1120px;
    margin:0 auto;
    padding:24px 16px;
}
.card {
    background:var(--card);
    border:1px solid var(--border);
    border-radius:14px;
    padding:20px;
    margin-bottom:18px;
    box-shadow:0 5px 20px rgba(15,23,42,.04);
}
.hero { text-align:center; padding:42px 20px; }
h2 { margin-top:0; }
h3 { margin-top:24px; }
p { line-height:1.55; }
.btn {
    display:inline-block;
    border:0;
    border-radius:9px;
    padding:11px 15px;
    font-weight:700;
    text-decoration:none;
    cursor:pointer;
    background:var(--blue);
    color:white;
    margin:4px 0;
}
.btn:hover { background:var(--blue2); }
.btn-secondary { background:#eef2f7; color:var(--navy); }
.btn-green { background:var(--green); }
.btn-red { background:var(--red); }
.btn-block { width:100%; }
label {
    display:block;
    margin:12px 0 6px;
    font-size:13px;
    font-weight:700;
}
input,select,textarea {
    width:100%;
    border:1px solid #cbd5e1;
    border-radius:9px;
    padding:12px;
    font-size:14px;
    background:white;
}
table {
    width:100%;
    border-collapse:collapse;
    font-size:12px;
}
th,td {
    border-bottom:1px solid var(--border);
    padding:10px 8px;
    text-align:left;
    vertical-align:top;
}
th { background:#f8fafc; }
.alert {
    padding:12px;
    border-radius:9px;
    margin-bottom:15px;
    font-size:13px;
}
.alert-success { background:#dcfce7; color:#166534; }
.alert-danger { background:#fee2e2; color:#991b1b; }
.grid {
    display:grid;
    grid-template-columns:repeat(3,1fr);
    gap:15px;
}
.stat {
    background:#f8fafc;
    border:1px solid var(--border);
    border-radius:12px;
    padding:15px;
}
.stat strong { display:block; font-size:22px; margin-top:4px; }
.muted { color:var(--muted); font-size:12px; }
.mono {
    font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
    word-break:break-all;
}
.payment-box {
    background:#eff6ff;
    border:1px solid #bfdbfe;
    border-radius:12px;
    padding:16px;
}
#map {
    width:100%;
    height:380px;
    border-radius:10px;
    margin-top:15px;
}
footer {
    color:#94a3b8;
    text-align:center;
    font-size:11px;
    padding:30px;
}
@media(max-width:760px) {
    header { align-items:flex-start; flex-direction:column; }
    .grid { grid-template-columns:1fr; }
    .container { padding:15px 10px; }
    table { display:block; overflow-x:auto; white-space:nowrap; }
}
@media print {
    header, footer, .screen-only, .screen-only + .card, .btn, nav, .alert { display:none !important; }
    body, .container { background:white; padding:0; margin:0; }
    .card { border:0; box-shadow:none; margin:0; padding:0; }
    .route-sheet { display:block !important; }
    .route-sheet table { font-size:10px; }
    .qr { margin-top:4px; }
}
"""

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ title or APP_NAME }}</title>
{% if map_needed %}
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
{% endif %}
<style>{{ style }}</style>
</head>
<body>
<header>
    <h1>{{ APP_NAME }}</h1>
    <nav>
        <a href="/">Accueil</a>
        {% if session.get("user_id") %}
        <a href="/dashboard">Dashboard</a>
        <a href="/logout">Déconnexion</a>
        {% else %}
        <a href="/login-form">Connexion</a>
        <a href="/register-form">Créer un compte</a>
        {% endif %}
        {% if session.get("is_admin") %}
        <a href="/admin-panel">Admin</a>
        {% else %}
        <a href="/admin-panel">Admin</a>
        {% endif %}
        <a href="/driver-login">Livreur</a>
    </nav>
</header>

<div class="container">
{% with messages = get_flashed_messages(with_categories=true) %}
{% for category, message in messages %}
<div class="alert alert-{{ category }}">{{ message }}</div>
{% endfor %}
{% endwith %}

{{ body|safe }}
</div>

<footer>© 2026 {{ APP_NAME }} — B2B Route Optimization</footer>
</body>
</html>
"""


def page(body, title=APP_NAME, map_needed=False):
    return render_template_string(
        HTML_TEMPLATE,
        body=body,
        title=title,
        style=BASE_STYLE,
        APP_NAME=APP_NAME,
        map_needed=map_needed,
        session=session,
    )


# ============================================================
# PUBLIC
# ============================================================

@app.route("/")
def index():
    body = """
    <div class="card hero">
        <h2>Route optimization for modern businesses.</h2>
        <p>
            GlobalRoute AI fournit un espace B2B pour gérer les abonnements,
            les clés API et les tournées de livraison.
        </p>
        <a class="btn" href="/register-form">Créer un compte entreprise</a>
        <a class="btn btn-secondary" href="/login-form">Connexion</a>
    </div>

    <div class="grid">
        <div class="stat">
            <span class="muted">Paiement</span>
            <strong>USDC</strong>
            <span class="muted">Solana mainnet</span>
        </div>
        <div class="stat">
            <span class="muted">API</span>
            <strong>B2B</strong>
            <span class="muted">Clés individuelles</span>
        </div>
        <div class="stat">
            <span class="muted">Activation</span>
            <strong>Auto</strong>
            <span class="muted">Après validation blockchain</span>
        </div>
    </div>
    """
    return page(body)


@app.route("/register-form")
def register_form():
    body = """
    <div class="card">
        <h2>Créer un compte entreprise</h2>
        <form method="POST" action="/register">
            <label>Nom de l'entreprise</label>
            <input name="company_name" required>

            <label>E-mail professionnel</label>
            <input type="email" name="email" required>

            <label>Mot de passe</label>
            <input type="password" name="password" minlength="8" required>

            <label>Adresse</label>
            <input name="address">

            <label>Ville</label>
            <input name="city">

            <label>Pays</label>
            <input name="country">

            <button class="btn btn-block" type="submit">
                Créer mon espace
            </button>
        </form>
    </div>
    """
    return page(body)


@app.route("/register", methods=["POST"])
def register():
    company_name = request.form.get("company_name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    if not company_name or not email or len(password) < 8:
        flash(
            "Veuillez remplir les informations obligatoires. "
            "Le mot de passe doit avoir au moins 8 caractères.",
            "danger",
        )
        return redirect(url_for("register_form"))

    if User.query.filter_by(email=email).first():
        flash("Cet e-mail existe déjà.", "danger")
        return redirect(url_for("register_form"))

    user = User(
        company_name=company_name,
        email=email,
        password_hash=generate_password_hash(password),
        address=request.form.get("address", "").strip(),
        city=request.form.get("city", "").strip(),
        country=request.form.get("country", "").strip(),
        plan="standard",
        credits=0,
    )

    db.session.add(user)
    db.session.commit()

    session["user_id"] = user.id

    flash(
        "Compte créé. Choisissez maintenant votre abonnement.",
        "success"
    )
    return redirect(url_for("plans"))


@app.route("/login-form")
def login_form():
    body = """
    <div class="card">
        <h2>Connexion entreprise</h2>
        <form method="POST" action="/login">
            <label>E-mail</label>
            <input type="email" name="email" required>

            <label>Mot de passe</label>
            <input type="password" name="password" required>

            <button class="btn btn-block" type="submit">
                Se connecter
            </button>
        </form>
    </div>
    """
    return page(body)


@app.route("/login", methods=["POST"])
def login():
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    user = User.query.filter_by(email=email).first()

    if user and check_password_hash(user.password_hash, password):
        session["user_id"] = user.id
        return redirect(url_for("dashboard"))

    flash("Identifiants incorrects.", "danger")
    return redirect(url_for("login_form"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/dashboard")
def dashboard():
    user = require_user()
    if not user:
        return redirect(url_for("login_form"))

    key = active_api_key(user)
    expiry = user.subscription_expires_at.strftime("%Y-%m-%d %H:%M") if user.subscription_expires_at else "—"
    routes = DeliveryRoute.query.filter_by(user_id=user.id).order_by(DeliveryRoute.created_at.desc()).all()
    key_text = key.key_string if key else "Aucune clé active"
    limit = user.route_limit or PLANS.get(user.plan, {}).get("route_limit", 0)
    used = user.routes_used or 0

    route_rows = "".join(
        f"<tr><td>{r.route_name}</td><td>{r.driver_name}</td><td>{r.stops_count}</td>"
        f"<td>{r.status}</td><td><a class='btn btn-secondary' href='/driver-space?code={urllib.parse.quote(r.access_code)}'>Ouvrir</a></td></tr>"
        for r in routes
    )

    pct = min(100, round((used / limit) * 100)) if limit else 0
    remaining = max(0, limit - used) if limit else 0
    body = f"""
    <div class="card">
        <h2>{user.company_name}</h2>
        <p class="muted">{user.email}</p>
        <div class="grid">
            <div class="stat"><span class="muted">Abonnement</span><strong>{user.plan.title()}</strong></div>
            <div class="stat"><span class="muted">Tournées utilisées</span><strong>{used:,} / {limit:,}</strong></div>
            <div class="stat"><span class="muted">Tournées restantes</span><strong>{remaining:,}</strong></div>
            <div class="stat"><span class="muted">Expiration</span><strong>{expiry}</strong></div>
        </div>
    </div>

    <div class="card">
        <h3>📊 Utilisation de votre abonnement</h3>
        <div style="display:flex;align-items:center;gap:22px;flex-wrap:wrap">
            <div style="width:130px;height:130px;border-radius:50%;background:conic-gradient(#2563eb {pct}%, #e2e8f0 0);display:grid;place-items:center">
                <div style="width:88px;height:88px;border-radius:50%;background:white;display:grid;place-items:center;font-weight:800;font-size:20px">{pct}%</div>
            </div>
            <div style="flex:1;min-width:220px">
                <div class="muted">Quota de tournées</div>
                <div style="height:14px;background:#e2e8f0;border-radius:999px;overflow:hidden;margin:8px 0 12px">
                    <div style="height:100%;width:{pct}%;background:#2563eb;border-radius:999px"></div>
                </div>
                <div style="display:flex;justify-content:space-between;font-size:13px">
                    <span><b>{used:,}</b> utilisées</span><span><b>{remaining:,}</b> restantes</span>
                </div>
            </div>
        </div>
    </div>

    <div class="card">
        <h3>🔑 Votre clé API</h3>
        <div class="payment-box mono">{key_text}</div>
        <a class="btn btn-secondary" href="/plans">Gérer l'abonnement</a>
    </div>

    <div class="card">
        <h2>Créer une tournée</h2>
        <form method="POST" action="/create-driver-route" enctype="multipart/form-data">
            <label>Nom de la tournée</label>
            <input name="route_name" placeholder="Ex. Tournée Nord" required>
            <label>Nom du livreur</label>
            <input name="driver_name" placeholder="Ex. Jean Dupont" required>
            <label>Code d'accès du livreur</label>
            <input name="access_code" placeholder="Ex. NORD01" required>
            <label>Importer un CSV</label>
            <input type="file" name="csv_file" accept=".csv">
            <p class="muted">CSV : nom, latitude, longitude — ou nom, adresse, latitude, longitude.</p>
            <label>Ou saisir les étapes manuellement</label>
            <textarea name="manual_stops" rows="6" placeholder="Client A | Adresse A | 19.75 | -72.20&#10;Client B | Adresse B | 19.76 | -72.21"></textarea>
            <button class="btn btn-green btn-block" type="submit">Créer et envoyer au livreur</button>
        </form>
    </div>

    <div class="card">
        <h3>🚚 Mes tournées</h3>
        <table><thead><tr><th>Tournée</th><th>Livreur</th><th>Étapes</th><th>Statut</th><th>Accès</th></tr></thead>
        <tbody>{route_rows or '<tr><td colspan="5">Aucune tournée créée.</td></tr>'}</tbody></table>
    </div>
    """
    return page(body, title="Dashboard")


@app.route("/plans")
def plans():
    user = require_user()
    if not user:
        return redirect(url_for("login_form"))

    cards = []
    for key in ("standard", "pro", "business", "enterprise"):
        p = PLANS[key]
        if key == "enterprise":
            action = "<a class='btn btn-secondary btn-block' href='/contact-enterprise'>Contacter GlobalRoute</a>"
            price = "Sur devis"
            annual = "Sur devis"
        else:
            action = (
                f"<form method='POST' action='/create-payment'>"
                f"<input type='hidden' name='plan' value='{key}'>"
                f"<label>Durée</label>"
                f"<select name='duration_days'>"
                f"<option value='30'>30 jours</option>"
                f"<option value='90'>90 jours</option>"
                f"<option value='180'>180 jours</option>"
                f"<option value='365'>365 jours</option>"
                f"</select>"
                f"<p>Prix : <strong>{p['monthly_price']:.2f} USDC / 30 jours</strong></p>"
                f"<button class='btn btn-green btn-block' type='submit'>Choisir {p['name']}</button>"
                f"</form>"
            )
            price = f"{p['monthly_price']:.0f} USDC / 30 jours"
            annual = f"{p['annual_price']:.0f} USDC / an"

        cards.append(
            f"<div class='card plan-card'>"
            f"<div class='muted'>{p['name']}</div>"
            f"<h2>{price}</h2>"
            f"<p><strong>{p['route_limit']:,}</strong> tournées incluses</p>"
            f"<p class='muted'>Volume prévu pour l'offre {p['name']}.</p>"
            f"<p><strong>{annual}</strong></p>"
            f"{action}</div>"
        )

    body = f"""
    <div class="card hero">
        <h2>Choisissez votre abonnement</h2>
        <p>Paiement en USDC sur Solana. Après confirmation, l'abonnement,
        la clé API et sa date d'expiration sont activés automatiquement.</p>
    </div>
    <div class="grid plans-grid">{''.join(cards)}</div>
    """
    return page(body, title="Abonnements")


@app.route("/contact-enterprise")
def contact_enterprise():
    return page("""
    <div class="card hero">
        <h2>Enterprise — jusqu'à 50 000 tournées</h2>
        <p>Contactez GlobalRoute pour une offre adaptée à votre volume.</p>
        <a class="btn" href="mailto:sales@globalroute.ai">Contacter les ventes</a>
    </div>
    """, title="Enterprise")


# ============================================================
# SOLANA PAYMENT
# ============================================================

@app.route("/create-payment", methods=["POST"])
def create_payment():
    user = require_user()

    if not user:
        return redirect(url_for("login_form"))

    plan = request.form.get("plan")
    try:
        duration_days = int(request.form.get("duration_days", "30"))
    except ValueError:
        duration_days = 30

    if plan not in PLANS or duration_days not in DURATIONS:
        flash("Abonnement invalide.", "danger")
        return redirect(url_for("plans"))

    amount = calculate_price(plan, duration_days)
    reference = generate_reference()

    order = PaymentOrder(
        order_code=f"GR-{secrets.token_hex(7).upper()}",
        reference=reference,
        user_id=user.id,
        plan=plan,
        duration_days=duration_days,
        amount_usdc=amount,
        asset="USDC",
        network="Solana",
        status="pending",
    )

    db.session.add(order)
    db.session.commit()

    # Solana Pay transfer request.
    # USDC uses 6 decimals, but Solana Pay accepts the human amount.
    params = {
        "amount": str(amount),
        "spl-token": USDC_MINT,
        "reference": reference,
        "label": APP_NAME,
        "message": f"GlobalRoute {order.order_code}",
    }

    solana_uri = (
        "solana:"
        + SOLANA_RECEIVING_WALLET
        + "?"
        + urllib.parse.urlencode(params)
    )

    body = f"""
    <div class="card">
        <h2>Paiement {order.order_code}</h2>

        <div class="payment-box">
            <p><strong>Montant :</strong> {amount:.2f} USDC</p>
            <p><strong>Réseau :</strong> Solana</p>
            <p><strong>Plan :</strong> {plan.title()}</p>
            <p><strong>Durée :</strong> {duration_days} jours</p>
        </div>

        <h3>Payer avec ton portefeuille Solana</h3>

        <p>
            Ouvre le lien ci-dessous dans un portefeuille compatible
            Solana Pay.
        </p>

        <a class="btn btn-green btn-block"
           href="{solana_uri}">
           Payer {amount:.2f} USDC
        </a>

        <p class="muted">
            Si ton portefeuille ne reconnaît pas le lien, utilise
            l'adresse publique ci-dessous et envoie exactement le montant.
        </p>

        <div class="payment-box mono">
            {SOLANA_RECEIVING_WALLET}
        </div>

        <h3>Référence de commande</h3>
        <div class="payment-box mono">{reference}</div>

        <button class="btn btn-block"
                onclick="checkPayment()">
            Vérifier le paiement
        </button>

        <div id="status" class="alert" style="margin-top:12px;">
            En attente du paiement...
        </div>
    </div>

    <script>
    let timer = null;

    async function checkPayment() {{
        const response = await fetch(
            "/api/payment-status/{order.id}"
        );

        const data = await response.json();

        const box = document.getElementById("status");
        box.textContent = data.message;

        if (data.paid) {{
            box.className = "alert alert-success";
            clearInterval(timer);

            setTimeout(() => {{
                window.location.href = "/dashboard";
            }}, 1200);
        }} else {{
            box.className = "alert";
        }}
    }}

    checkPayment();
    timer = setInterval(checkPayment, 7000);
    </script>
    """

    return page(body, title="Paiement USDC")


@app.route("/api/payment-status/<int:order_id>")
def payment_status(order_id):
    user = require_user()

    if not user:
        return jsonify({"paid": False, "message": "Connexion requise."}), 401

    order = PaymentOrder.query.get_or_404(order_id)

    if order.user_id != user.id:
        return jsonify({"paid": False, "message": "Accès refusé."}), 403

    if order.status == "paid":
        return jsonify({
            "paid": True,
            "message": "Paiement déjà confirmé."
        })

    try:
        valid, signature, message = verify_usdc_payment(order)

        if valid:
            activate_paid_order(order, signature)

            return jsonify({
                "paid": True,
                "message": (
                    "Paiement confirmé. "
                    "Votre abonnement et vos crédits sont actifs."
                ),
            })

        return jsonify({
            "paid": False,
            "message": message,
        })

    except Exception as exc:
        # Do not expose internal secrets or stack traces to the customer.
        return jsonify({
            "paid": False,
            "message": (
                "Vérification temporairement indisponible. "
                "Réessayez dans quelques secondes."
            ),
        })


# ============================================================
# ADMIN
# ============================================================

@app.route("/admin-panel", methods=["GET", "POST"])
def admin_panel():
    if not admin_required():
        if request.method == "POST":
            password = request.form.get("admin_password", "")

            if password == ADMIN_SECRET_PASSWORD:
                session["is_admin"] = True
                return redirect(url_for("admin_panel"))

            flash("Mot de passe administrateur incorrect.", "danger")

        body = """
        <div class="card">
            <h2>Connexion administrateur</h2>
            <form method="POST">
                <label>Mot de passe admin</label>
                <input type="password" name="admin_password" required>
                <button class="btn btn-block" type="submit">
                    Entrer
                </button>
            </form>
        </div>
        """
        return page(body, title="Admin")

    users = User.query.order_by(User.created_at.desc()).all()
    orders = PaymentOrder.query.order_by(
        PaymentOrder.created_at.desc()
    ).limit(50).all()

    user_rows = ""

    for user in users:
        key = active_api_key(user)

        expiry = (
            user.subscription_expires_at.strftime("%Y-%m-%d")
            if user.subscription_expires_at else "—"
        )

        credits = f"{user.routes_used or 0} / {user.route_limit or 0} tournées"

        key_text = key.key_string if key else "—"

        user_rows += f"""
        <tr>
            <td>
                <strong>{user.company_name}</strong><br>
                <span class="muted">{user.email}</span>
            </td>
            <td>{user.plan.title()}</td>
            <td>{credits}</td>
            <td>{expiry}</td>
            <td class="mono">{key_text}</td>
        </tr>
        """

    order_rows = ""

    for order in orders:
        order_rows += f"""
        <tr>
            <td>{order.order_code}</td>
            <td>{order.customer.email}</td>
            <td>{order.plan.title()}</td>
            <td>{order.duration_days} j</td>
            <td>{order.amount_usdc:.2f} USDC</td>
            <td>{order.status}</td>
            <td>{order.created_at.strftime("%Y-%m-%d %H:%M")}</td>
        </tr>
        """

    body = f"""
    <div class="card">
        <h2>Centre administrateur</h2>

        <a class="btn btn-secondary"
           href="/admin-logout">
           Verrouiller l'admin
        </a>
    </div>

    <div class="card">
        <h3>Créer un testeur / client</h3>

        <form method="POST" action="/admin/create-tester">
            <label>Nom de l'entreprise</label>
            <input name="company_name" required>

            <label>E-mail</label>
            <input type="email" name="email" required>

            <label>Adresse</label>
            <input name="address">

            <label>Ville</label>
            <input name="city">

            <label>Pays</label>
            <input name="country">

            <label>Plan initial</label>
            <select name="plan">
                <option value="standard">Standard</option>
                <option value="pro">Pro</option>
                <option value="business">Business</option>
                <option value="enterprise">Enterprise</option>
            </select>

            <label>Durée</label>
            <select name="duration_days">
                <option value="30">30 jours</option>
                <option value="90">90 jours</option>
                <option value="180">180 jours</option>
                <option value="365">365 jours</option>
            </select>

            <button class="btn btn-green btn-block" type="submit">
                Créer le testeur et générer son lien
            </button>
        </form>
    </div>

    <div class="card">
        <h3>Clients</h3>
        <table>
            <thead>
                <tr>
                    <th>Entreprise</th>
                    <th>Plan</th>
                    <th>Tournées</th>
                    <th>Expiration</th>
                    <th>Clé API</th>
                </tr>
            </thead>
            <tbody>{user_rows}</tbody>
        </table>
    </div>

    <div class="card">
        <h3>Paiements récents</h3>
        <table>
            <thead>
                <tr>
                    <th>Commande</th>
                    <th>Client</th>
                    <th>Plan</th>
                    <th>Durée</th>
                    <th>Montant</th>
                    <th>Statut</th>
                    <th>Date</th>
                </tr>
            </thead>
            <tbody>{order_rows}</tbody>
        </table>
    </div>

    <div class="card">
        <h3>Réception Solana</h3>
        <p class="muted">USDC mainnet</p>
        <div class="payment-box mono">
            {SOLANA_RECEIVING_WALLET}
        </div>
    </div>
    """

    return page(body, title="Admin")


@app.route("/admin/create-tester", methods=["POST"])
def admin_create_tester():
    if not admin_required():
        return redirect(url_for("admin_panel"))

    company_name = request.form.get("company_name", "").strip()
    email = request.form.get("email", "").strip().lower()
    plan = request.form.get("plan", "standard")

    try:
        duration_days = int(
            request.form.get("duration_days", "30")
        )
    except ValueError:
        duration_days = 30

    if not company_name or not email:
        flash("Nom et e-mail obligatoires.", "danger")
        return redirect(url_for("admin_panel"))

    if plan not in PLANS or duration_days not in DURATIONS:
        flash("Plan ou durée invalide.", "danger")
        return redirect(url_for("admin_panel"))

    if User.query.filter_by(email=email).first():
        flash("Cet e-mail existe déjà.", "danger")
        return redirect(url_for("admin_panel"))

    # Admin-created tester gets a temporary random password.
    temporary_password = secrets.token_urlsafe(12)

    user = User(
        company_name=company_name,
        email=email,
        password_hash=generate_password_hash(temporary_password),
        address=request.form.get("address", "").strip(),
        city=request.form.get("city", "").strip(),
        country=request.form.get("country", "").strip(),
        plan=plan,
        credits=0,
    )

    db.session.add(user)
    db.session.commit()

    expiry = add_subscription(user, plan, duration_days)

    invitation_token = secrets.token_urlsafe(32)

    # We use a short-lived invitation record encoded in a signed
    # server-side session-like table would be preferable in a larger app.
    # For this one-file version, store a one-time token in AuditLog.
    db.session.add(
        AuditLog(
            action="TESTER_CREATED",
            details=(
                f"user_id={user.id}; "
                f"email={email}; "
                f"token={invitation_token}; "
                f"temporary_password={temporary_password}; "
                f"expires={expiry.isoformat()}"
            ),
        )
    )

    db.session.commit()

    invite_url = url_for(
        "tester_invite",
        token=invitation_token,
        _external=True,
    )

    flash(
        f"Testeur créé. Lien : {invite_url} | "
        f"Mot de passe temporaire : {temporary_password}",
        "success",
    )

    return redirect(url_for("admin_panel"))


@app.route("/tester-invite/<token>")
def tester_invite(token):
    log = AuditLog.query.filter(
        AuditLog.action == "TESTER_CREATED",
        AuditLog.details.contains(f"token={token}")
    ).order_by(AuditLog.id.desc()).first()

    if not log:
        return page(
            '<div class="card"><h2>Lien invalide ou expiré.</h2></div>',
            title="Invitation"
        )

    body = f"""
    <div class="card">
        <h2>Invitation GlobalRoute AI</h2>
        <p>
            Votre espace entreprise a été préparé par l'administrateur.
        </p>
        <p class="muted">
            Utilisez les identifiants transmis avec ce lien pour vous
            connecter.
        </p>
        <a class="btn btn-block" href="/login-form">
            Ouvrir la connexion
        </a>
    </div>
    """

    return page(body, title="Invitation")


@app.route("/admin-logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("index"))


# ============================================================
# DRIVER
# ============================================================

@app.route("/driver-login")
def driver_login():
    body = """
    <div class="card">
        <h2>🚚 Espace livreur</h2>
        <form method="POST" action="/driver-space">
            <label>Code d'accès</label>
            <input name="access_code" required>
            <button class="btn btn-green btn-block" type="submit">
                Afficher la tournée
            </button>
        </form>
    </div>
    """
    return page(body, title="Livreur")


@app.route("/driver-space", methods=["POST", "GET"])
def driver_space():
    code = request.form.get("access_code") if request.method == "POST" else request.args.get("code")
    if not code:
        return redirect(url_for("driver_login"))

    route = DeliveryRoute.query.filter_by(access_code=code.strip().upper()).first()
    if not route:
        flash("Code d'accès incorrect.", "danger")
        return redirect(url_for("driver_login"))

    stops = parse_stops_data(route.stops_data)
    map_points = json.dumps(stops, ensure_ascii=False)
    route_rows = build_route_rows(stops)

    body = f"""
    <div class="card driver-header">
        <h2>🚚 {route.route_name}</h2>
        <p><strong>Livreur :</strong> {route.driver_name}</p>
        <p class="muted">{len(stops)} étapes · GlobalRoute AI</p>
        <button class="btn" onclick="window.print()">🖨️ Imprimer la fiche de route</button>
    </div>

    <div class="card screen-only">
        <h3>Carte interactive 2D</h3>
        <div id="map"></div>
    </div>

    <div class="card route-sheet">
        <h2>Fiche de route — {route.route_name}</h2>
        <p>Livreur : <strong>{route.driver_name}</strong></p>
        <table>
            <thead><tr><th>#</th><th>Étape</th><th>Adresse</th><th>Latitude</th><th>Longitude</th><th>Navigation</th></tr></thead>
            <tbody>{''.join(f"<tr><td>{i}</td><td>{p.get('name','')}</td><td>{p.get('address','')}</td><td>{p.get('lat')}</td><td>{p.get('lng')}</td><td><a href='https://www.google.com/maps/search/?api=1&query={p.get('lat')},{p.get('lng')}' target='_blank'>GPS</a><div class='qr' data-url='https://www.google.com/maps/search/?api=1&query={p.get('lat')},{p.get('lng')}'></div></td></tr>" for i,p in enumerate(stops,1))}</tbody>
        </table>
    </div>

    <script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"></script>
    <script>
    const points = {map_points};
    const map = L.map("map").setView(
        points.length ? [points[0].lat, points[0].lng] : [19.7558,-72.2042], 13
    );
    L.tileLayer("https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png",
        {{maxZoom:19, attribution:"© OpenStreetMap"}}).addTo(map);
    const bounds = [];
    points.forEach((p,i) => {{
        bounds.push([p.lat,p.lng]);
        L.marker([p.lat,p.lng]).addTo(map).bindPopup(
            "<b>"+(i+1)+". "+p.name+"</b><br>"+(p.address||"")+"<br>GPS: "+p.lat+", "+p.lng
        );
    }});
    if (bounds.length) {{
        L.polyline(bounds, {{weight:4}}).addTo(map);
        map.fitBounds(bounds, {{padding:[35,35]}});
    }}
    document.querySelectorAll(".qr").forEach(el => new QRCode(el, {{text:el.dataset.url,width:72,height:72}}));
    </script>
    """
    return page(body, title="Fiche de route", map_needed=True)


@app.route("/create-driver-route", methods=["POST"])
def create_driver_route():
    user = require_user()
    if not user:
        return redirect(url_for("login_form"))

    limit = user.route_limit or PLANS.get(user.plan, {}).get("route_limit", 0)
    if limit and (user.routes_used or 0) >= limit:
        flash("Votre quota de tournées est atteint. Choisissez un abonnement supérieur.", "danger")
        return redirect(url_for("dashboard"))

    route_name = request.form.get("route_name", "Tournée").strip()
    driver_name = request.form.get("driver_name", "").strip()
    access_code = request.form.get("access_code", "").strip().upper()
    if not driver_name or not access_code:
        flash("Nom du livreur et code d'accès obligatoires.", "danger")
        return redirect(url_for("dashboard"))

    if DeliveryRoute.query.filter_by(access_code=access_code).first():
        flash("Ce code d'accès existe déjà.", "danger")
        return redirect(url_for("dashboard"))

    stops = []
    file = request.files.get("csv_file")
    if file and file.filename.lower().endswith(".csv"):
        try:
            stream = io.TextIOWrapper(file.stream, encoding="utf-8-sig", errors="replace")
            for row in csv.reader(stream):
                if len(row) >= 4:
                    name, address = row[0].strip(), row[1].strip()
                    lat_s, lng_s = row[2].strip(), row[3].strip()
                elif len(row) >= 3:
                    name, address = row[0].strip(), ""
                    lat_s, lng_s = row[1].strip(), row[2].strip()
                else:
                    continue
                try:
                    lat, lng = float(lat_s), float(lng_s)
                except ValueError:
                    continue
                if -90 <= lat <= 90 and -180 <= lng <= 180:
                    stops.append({"name": name, "address": address, "lat": lat, "lng": lng})
        except Exception:
            flash("Impossible de lire le CSV.", "danger")
            return redirect(url_for("dashboard"))

    manual = request.form.get("manual_stops", "").strip()
    if manual:
        for line in manual.splitlines():
            parts = [x.strip() for x in line.split("|")]
            if len(parts) >= 4:
                name, address, lat_s, lng_s = parts[0], parts[1], parts[2], parts[3]
            elif len(parts) >= 3:
                name, address, lat_s, lng_s = parts[0], "", parts[1], parts[2]
            else:
                continue
            try:
                lat, lng = float(lat_s), float(lng_s)
            except ValueError:
                continue
            if -90 <= lat <= 90 and -180 <= lng <= 180:
                stops.append({"name": name, "address": address, "lat": lat, "lng": lng})

    if not stops:
        flash("Ajoutez un CSV ou saisissez au moins une étape valide.", "danger")
        return redirect(url_for("dashboard"))

    route = DeliveryRoute(
        user_id=user.id,
        driver_name=driver_name,
        route_name=route_name,
        access_code=access_code,
        stops_data=json.dumps(stops, ensure_ascii=False),
        stops_count=len(stops),
        status="En cours",
    )
    db.session.add(route)
    user.routes_used = (user.routes_used or 0) + 1
    db.session.commit()

    flash(f"Tournée « {route_name} » créée avec {len(stops)} étapes et envoyée à l'espace livreur.", "success")
    return redirect(url_for("dashboard"))


# ============================================================
# API
# ============================================================

@app.route("/api/v1/route", methods=["POST"])
def route_api():
    api_key_value = request.headers.get("X-API-KEY", "").strip()

    if not api_key_value:
        return jsonify({
            "error": "missing_api_key"
        }), 401

    key = ApiKey.query.filter_by(
        key_string=api_key_value,
        revoked=False
    ).first()

    if not key:
        return jsonify({
            "error": "invalid_api_key"
        }), 401

    if key.expires_at and key.expires_at < utcnow():
        return jsonify({
            "error": "api_key_expired"
        }), 403

    user = User.query.get(key.user_id)

    if not user or not user.active:
        return jsonify({
            "error": "account_inactive"
        }), 403

    if (
        user.subscription_expires_at
        and user.subscription_expires_at < utcnow()
    ):
        return jsonify({
            "error": "subscription_expired"
        }), 403

    payload = request.get_json(silent=True) or {}
    points = payload.get("points", [])

    if not isinstance(points, list) or len(points) < 2:
        return jsonify({
            "error": "at_least_two_points_required"
        }), 400

    # Commercial quota: one accepted routing request consumes one
    # route from the company's subscription quota. The limit is tied
    # to the account/API key, not to the number of GPS points.
    route_limit = user.route_limit or PLANS.get(user.plan, {}).get("route_limit", 0)
    routes_used = user.routes_used or 0

    if route_limit and routes_used >= route_limit:
        return jsonify({
            "error": "route_quota_exceeded",
            "plan": user.plan,
            "route_limit": route_limit,
            "routes_used": routes_used,
            "routes_remaining": 0,
        }), 402

    user.routes_used = routes_used + 1
    db.session.commit()

    # This endpoint validates the commercial API request.
    # The production routing engine can be connected here.
    return jsonify({
        "success": True,
        "engine": APP_NAME,
        "points_received": len(points),
        "plan": user.plan,
        "route_limit": route_limit,
        "routes_used": user.routes_used,
        "routes_remaining": max(0, route_limit - user.routes_used) if route_limit else None,
        "message": "Request accepted by the B2B routing API.",
    })


# ============================================================
# HEALTH
# ============================================================

@app.route("/health")
def health():
    try:
        from sqlalchemy import text
        db.session.execute(text("SELECT 1"))
        database = "ok"
    except Exception as exc:
        database = "error"
    return jsonify({
        "status": "ok" if database == "ok" else "degraded",
        "database": database,
        "service": APP_NAME,
        "payments": "USDC / Solana",
        "wallet": SOLANA_RECEIVING_WALLET,
        "network": "mainnet",
    })


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
