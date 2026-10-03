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

app.secret_key = os.getenv("SECRET_KEY", secrets.token_hex(32))
ADMIN_SECRET_PASSWORD = os.getenv("ADMIN_SECRET_PASSWORD", "CHANGE-ME")

APP_NAME = "GlobalRoute AI"
SOLANA_RECEIVING_WALLET = "22BzBEYLewJkKe2FXD6EHJYqX4NNshMw9roNw9qFxV9d"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
SOLANA_RPC_URL = "https://api.mainnet.solana.com"

# Catalogue des abonnements
PLANS = {
    "standard": {
        "name": "Standard",
        "monthly_price": 99.00,
        "tour_limit": 500,
        "credit_limit": 500,
        "unlimited": False,
    },
    "pro": {
        "name": "Pro",
        "monthly_price": 300.00,
        "tour_limit": 2500,
        "credit_limit": 2500,
        "unlimited": False,
    },
}

DURATIONS = {
    30: 1.0,
    90: 2.7,
    180: 5.0,
    365: 9.0,
}

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
    tour_limit = db.Column(db.Integer, default=500)
    tours_used = db.Column(db.Integer, default=0)
    active = db.Column(db.Boolean, default=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    api_keys = db.relationship(
        "ApiKey", backref="owner", lazy=True, cascade="all, delete-orphan"
    )
    deliveries = db.relationship(
        "DeliveryRoute", backref="company", lazy=True, cascade="all, delete-orphan"
    )
    payments = db.relationship(
        "PaymentOrder", backref="customer", lazy=True, cascade="all, delete-orphan"
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
    order_code = db.Column(db.String(80), unique=True, nullable=False, index=True)
    reference = db.Column(db.String(64), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    plan = db.Column(db.String(30), nullable=False)
    duration_days = db.Column(db.Integer, nullable=False)
    amount_usdc = db.Column(db.Float, nullable=False)
    asset = db.Column(db.String(20), default="USDC")
    network = db.Column(db.String(30), default="Solana")
    status = db.Column(db.String(20), default="pending")
    transaction_signature = db.Column(db.String(160), unique=True, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    paid_at = db.Column(db.DateTime, nullable=True)


class DeliveryRoute(db.Model):
    __tablename__ = "delivery_routes"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    route_name = db.Column(db.String(150), default="Tournée")
    driver_name = db.Column(db.String(100), nullable=False)
    access_code = db.Column(db.String(80), unique=True, nullable=False)
    stops_data = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default="En cours")


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(120), nullable=False)
    details = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


def _column_type_sql(column):
    try:
        return column.type.compile(dialect=db.engine.dialect)
    except Exception:
        return str(column.type)


def migrate_existing_database():
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
        existing_columns = {col["name"] for col in inspector.get_columns(table_name)}
        for column in model.__table__.columns:
            if column.name in existing_columns or column.primary_key:
                continue
            type_sql = _column_type_sql(column)
            sql = f'ALTER TABLE "{table_name}" ADD COLUMN "{column.name}" {type_sql}'
            db.session.execute(text(sql))
        db.session.commit()


with app.app_context():
    db.create_all()
    migrate_existing_database()


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
    return base58_encode(secrets.token_bytes(32))


def utcnow():
    return datetime.utcnow()


def calculate_price(plan, duration_days):
    if plan not in PLANS:
        raise ValueError("Plan invalide.")
    if duration_days not in DURATIONS:
        raise ValueError("Durée invalide.")
    monthly = PLANS[plan]["monthly_price"]
    multiplier = DURATIONS[duration_days]
    return round(monthly * multiplier, 2)


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
    same_active_plan = bool(
        user.subscription_expires_at
        and user.subscription_expires_at > now
        and user.plan == plan
    )
    if same_active_plan:
        start = user.subscription_started_at or now
        expiry = user.subscription_expires_at + timedelta(days=duration_days)
    else:
        start = now
        expiry = now + timedelta(days=duration_days)

    user.plan = plan
    user.subscription_started_at = start
    user.subscription_expires_at = expiry

    if same_active_plan:
        user.tour_limit = int(user.tour_limit or 0) + int(PLANS[plan]["tour_limit"])
    else:
        user.tour_limit = int(PLANS[plan]["tour_limit"])
        user.tours_used = 0

    user.unlimited = False
    user.credits = user.tour_limit

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
    result = rpc_call("getSignaturesForAddress", [reference, {"limit": 20}])
    if not result:
        return None
    for item in result:
        if not item.get("err"):
            return item.get("signature")
    return None


def verify_usdc_payment(order):
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
            f"Montant reçu insuffisant. Attendu {order.amount_usdc:.2f} USDC.",
        )
    return True, signature, "Paiement USDC confirmé."


def activate_paid_order(order, signature):
    if order.status == "paid":
        return
    user = User.query.get(order.user_id)
    if not user:
        raise RuntimeError("Client introuvable.")

    existing = PaymentOrder.query.filter_by(transaction_signature=signature).first()
    if existing and existing.id != order.id:
        raise RuntimeError("Cette transaction est déjà utilisée.")

    expiry = add_subscription(user, order.plan, order.duration_days)
    order.status = "paid"
    order.transaction_signature = signature
    order.paid_at = utcnow()

    db.session.add(
        AuditLog(
            action="PAYMENT_CONFIRMED",
            details=(
                f"order={order.order_code}; user={user.email}; "
                f"plan={order.plan}; days={order.duration_days}; "
                f"signature={signature}; expires={expiry.isoformat()}"
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


# ============================================================
# CSS / HTML TEMPLATES
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
    padding:10px 16px;
    display:flex;
    align-items:center;
    gap:12px;
    position:relative;
}
header h1 { margin:0; font-size:17px; flex:1; }
.menu-toggle {
    width:42px;
    height:42px;
    border:1px solid rgba(255,255,255,.18);
    border-radius:10px;
    background:rgba(255,255,255,.08);
    color:white;
    display:inline-flex;
    align-items:center;
    justify-content:center;
    font-size:23px;
    cursor:pointer;
}
nav {
    display:none;
    position:absolute;
    top:58px;
    left:12px;
    z-index:1000;
    min-width:210px;
    padding:8px;
    flex-direction:column;
    gap:4px;
    background:var(--navy);
    border:1px solid rgba(255,255,255,.12);
    border-radius:12px;
    box-shadow:0 14px 35px rgba(0,0,0,.25);
}
nav.open { display:flex; }
nav a {
    color:#e2e8f0;
    text-decoration:none;
    font-size:13px;
    padding:10px 12px;
    border-radius:8px;
}
nav a:hover { background:rgba(255,255,255,.09); }
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
.plan-grid { display:grid; grid-template-columns:repeat(2,1fr); gap:18px; }
.plan-card { background:white; border:1px solid var(--border); border-radius:16px; padding:24px; box-shadow:0 8px 28px rgba(15,23,42,.06); }
.plan-card.featured { border:2px solid var(--blue); }
.plan-badge { font-size:11px; font-weight:800; letter-spacing:.08em; color:var(--blue); }
.plan-price { font-size:30px; font-weight:800; margin:12px 0; }
.plan-price small { font-size:12px; font-weight:500; color:var(--muted); }
.plan-card li { margin:8px 0; color:#475569; }
.btn-small { padding:6px 9px; font-size:11px; margin:0; }
.driver-head { display:flex; justify-content:space-between; align-items:center; gap:15px; }
.driver-actions { display:flex; gap:8px; flex-wrap:wrap; }
.stop-list { padding-left:22px; }
.stop-list li { margin:12px 0; padding-bottom:12px; border-bottom:1px solid var(--border); display:flex; justify-content:space-between; gap:10px; align-items:center; }
.address { font-size:13px; }
.print-only { display:none; }
@media print { body { background:white; } header, footer, .driver-actions, .map-card, .no-print { display:none !important; } .container { max-width:none; padding:0; } .card { box-shadow:none; border:0; } .print-only { display:block; } }
@media(max-width:760px) { .plan-grid { grid-template-columns:1fr; } .driver-head { flex-direction:column; align-items:flex-start; } }
footer {
    color:#94a3b8;
    text-align:center;
    font-size:11px;
    padding:30px;
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
    <button class="menu-toggle" type="button" aria-label="Ouvrir le menu" aria-expanded="false"
            onclick="toggleGlobalMenu()">☰</button>
    <h1>{{ APP_NAME }}</h1>
    <nav id="global-menu">
        <a href="/">⌂ &nbsp;Accueil</a>
        {% if session.get("user_id") %}
        <a href="/dashboard">▣ &nbsp;Dashboard</a>
        <a href="/import-space">⇧ &nbsp;Importer</a>
        <a href="/plans">◈ &nbsp;Abonnement</a>
        {% else %}
        <a href="/login-form">↪ &nbsp;Connexion</a>
        <a href="/register-form">＋ &nbsp;Créer un compte</a>
        {% endif %}
        <a href="/admin-panel">⚙ &nbsp;Admin</a>
        <a href="/driver-login">🚚 &nbsp;Espace livreur</a>
    </nav>
    <script>
    function toggleGlobalMenu() {
        const menu = document.getElementById("global-menu");
        const button = document.querySelector(".menu-toggle");
        const open = menu.classList.toggle("open");
        button.setAttribute("aria-expanded", open ? "true" : "false");
    }
    document.addEventListener("click", function(event) {
        const menu = document.getElementById("global-menu");
        const button = document.querySelector(".menu-toggle");
        if (menu && menu.classList.contains("open") &&
            !menu.contains(event.target) && !button.contains(event.target)) {
            menu.classList.remove("open");
            button.setAttribute("aria-expanded", "false");
        }
    });
    </script>
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
# PUBLIC ROUTES
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

    flash("Compte créé. Choisissez maintenant votre abonnement.", "success")
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
# DASHBOARD & IMPORT SPACE
# ============================================================

@app.route("/dashboard")
def dashboard():
    user = require_user()
    if not user:
        return redirect(url_for("login_form"))

    key = active_api_key(user)
    expiry = user.subscription_expires_at.strftime("%Y-%m-%d") if user.subscription_expires_at else "—"
    key_text = key.key_string if key else "Aucune clé active"

    if user.tour_limit is None:
        user.tour_limit = int(PLANS.get(user.plan, PLANS["standard"])["tour_limit"])
        user.tours_used = int(user.tours_used or 0)
        db.session.commit()

    remaining = max(0, int(user.tour_limit or 0) - int(user.tours_used or 0))
    route_rows = ""
    for r in DeliveryRoute.query.filter_by(user_id=user.id).order_by(DeliveryRoute.id.desc()).limit(50).all():
        try:
            stops = json.loads(r.stops_data or "[]")
            count = len(stops) if isinstance(stops, list) else 0
        except Exception:
            count = len([x for x in (r.stops_data or "").splitlines() if x.strip()])
        route_rows += f"""
        <tr>
            <td><strong>{r.route_name or 'Tournée'}</strong></td>
            <td>{r.driver_name}</td>
            <td>{count}</td>
            <td>{r.status}</td>
            <td><a class='btn btn-small' href='/driver-space?code={urllib.parse.quote(r.access_code)}'>Ouvrir</a></td>
        </tr>"""

    if not route_rows:
        route_rows = '<tr><td colspan="5" class="muted">Aucune tournée créée.</td></tr>'

    body = f"""
    <div class="card">
        <h2>{user.company_name}</h2>
        <p class="muted">{user.email}</p>
        <div class="grid">
            <div class="stat"><span class="muted">Abonnement</span><strong>{user.plan.title()}</strong></div>
            <div class="stat"><span class="muted">Tournées utilisées</span><strong>{int(user.tours_used or 0)} / {int(user.tour_limit or 0)}</strong></div>
            <div class="stat"><span class="muted">Tournées restantes</span><strong>{remaining}</strong></div>
        </div>
        <p class="muted">Expiration : {expiry}</p>
    </div>

    <div class="card">
        <h3>🚚 Importer / créer une tournée</h3>
        <p class="muted">Sélectionnez un fichier CSV ou saisissez vos étapes directement.</p>
        <a class="btn btn-green" href="/import-space">Ouvrir l’espace Importer</a>
        <a class="btn btn-secondary" href="/logout">↪ Déconnexion</a>
    </div>

    <div class="card">
        <h3>📋 Mes tournées</h3>
        <table>
            <thead><tr><th>Tournée</th><th>Livreur</th><th>Étapes</th><th>Statut</th><th></th></tr></thead>
            <tbody>{route_rows}</tbody>
        </table>
    </div>

    <div class="card">
        <h3>🔑 Votre clé API</h3>
        <div class="payment-box mono">{key_text}</div>
        <p class="muted">La clé est liée à votre abonnement et à son quota de tournées.</p>
    </div>

    <div class="card">
        <h3>Abonnement</h3>
        <a class="btn" href="/plans">Voir les abonnements</a>
        <a class="btn btn-secondary" href="/driver-login">Espace livreur</a>
    </div>

    <div class="card no-print" style="text-align:right;">
        <a class="btn btn-red" href="/logout">⏻ Déconnexion du Dashboard</a>
    </div>
    """
    return page(body, title="Dashboard")


def render_import_form(route_name="", driver_name="", access_code="", manual_stops=""):
    body = f"""
    <div class="card">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;">
            <div>
                <h2>Importer une tournée</h2>
                <p class="muted">Sélectionnez votre fichier CSV (intégration automatique) ou remplissez le texte manuellement.</p>
            </div>
            <a class="btn btn-red" href="/logout">⏻ Déconnexion</a>
        </div>

        <form method="POST" action="/create-driver-route" enctype="multipart/form-data">
            <label>Nom de la tournée</label>
            <input name="route_name" value="{route_name}" placeholder="Ex. Livraison du matin" required>

            <label>Nom du livreur</label>
            <input name="driver_name" value="{driver_name}" placeholder="Ex. Jean Dupont" required>

            <label>Code d'accès du livreur (Libre : ex. AB-123, livreur1, etc.)</label>
            <input name="access_code" value="{access_code}" placeholder="Ex. LIVREUR01" required>

            <label>Importer un fichier CSV (Recommandé - Intégration directe)</label>
            <input type="file" name="csv_file" accept=".csv,text/csv" style="padding:8px">

            <label>Ou Saisie manuelle / Optionnel (Nom | Adresse | Latitude | Longitude)</label>
            <textarea name="manual_stops" rows="6"
                placeholder="Exemple : Client ABC | 15 Rue Lamartinière | 19.7558 | -72.2042">{manual_stops}</textarea>

            <button class="btn btn-green btn-block" type="submit" style="margin-top:20px;">Créer et envoyer au livreur</button>
        </form>
    </div>

    <div class="card">
        <a class="btn btn-secondary" href="/dashboard">← Retour au Dashboard</a>
    </div>
    """
    return page(body, title="Importer une tournée")


@app.route("/import-space")
def import_space():
    user = require_user()
    if not user:
        return redirect(url_for("login_form"))
    return render_import_form()


@app.route("/plans")
def plans():
    user = require_user()
    if not user:
        return redirect(url_for("login_form"))

    body = """
    <div class="card hero">
        <h2>Abonnements GlobalRoute</h2>
        <p class="muted">Choisissez votre volume de tournées et votre durée. Paiement USDC sur Solana.</p>
    </div>
    <div class="plan-grid">
        <div class="plan-card">
            <span class="plan-badge">STANDARD</span>
            <h2>Standard</h2>
            <div class="plan-price">99 USDC <small>/ 30 jours</small></div>
            <p><strong>500 tournées</strong></p>
            <ul><li>Carte interactive</li><li>Espace livreur</li><li>CSV / saisie manuelle</li><li>Fiche imprimable</li><li>Clé API</li></ul>
            <form method="POST" action="/create-payment">
                <input type="hidden" name="plan" value="standard">
                <label>Durée</label>
                <select name="duration_days">
                    <option value="30">30 jours — 99.00 USDC</option>
                    <option value="90">90 jours — 267.30 USDC</option>
                    <option value="180">180 jours — 495.00 USDC</option>
                    <option value="365">365 jours — 891.00 USDC</option>
                </select>
                <button class="btn btn-block" type="submit">Choisir Standard</button>
            </form>
        </div>
        <div class="plan-card featured">
            <span class="plan-badge">PRO</span>
            <h2>Pro</h2>
            <div class="plan-price">300 USDC <small>/ 30 jours</small></div>
            <p><strong>2 500 tournées</strong></p>
            <ul><li>Tout le Standard</li><li>Quota 2 500 tournées</li><li>API B2B</li><li>Statistiques</li><li>Gestion avancée des livreurs</li></ul>
            <form method="POST" action="/create-payment">
                <input type="hidden" name="plan" value="pro">
                <label>Durée</label>
                <select name="duration_days">
                    <option value="30">30 jours — 300.00 USDC</option>
                    <option value="90">90 jours — 810.00 USDC</option>
                    <option value="180">180 jours — 1500.00 USDC</option>
                    <option value="365">365 jours — 2700.00 USDC</option>
                </select>
                <button class="btn btn-green btn-block" type="submit">Choisir Pro</button>
            </form>
        </div>
    </div>
    """
    return page(body, title="Abonnements")


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
        <a class="btn btn-green btn-block" href="{solana_uri}">Payer {amount:.2f} USDC</a>

        <div class="payment-box mono" style="margin-top:15px;">
            {SOLANA_RECEIVING_WALLET}
        </div>

        <h3>Référence de commande</h3>
        <div class="payment-box mono">{reference}</div>

        <button class="btn btn-block" onclick="checkPayment()">Vérifier le paiement</button>
        <div id="status" class="alert" style="margin-top:12px;">En attente du paiement...</div>
    </div>

    <script>
    let timer = null;
    async function checkPayment() {{
        const response = await fetch("/api/payment-status/{order.id}");
        const data = await response.json();
        const box = document.getElementById("status");
        box.textContent = data.message;
        if (data.paid) {{
            box.className = "alert alert-success";
            clearInterval(timer);
            setTimeout(() => {{ window.location.href = "/dashboard"; }}, 1200);
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
        return jsonify({"paid": True, "message": "Paiement déjà confirmé."})

    try:
        valid, signature, message = verify_usdc_payment(order)
        if valid:
            activate_paid_order(order, signature)
            return jsonify({"paid": True, "message": "Paiement confirmé."})
        return jsonify({"paid": False, "message": message})
    except Exception:
        return jsonify({"paid": False, "message": "Vérification temporairement indisponible."})


# ============================================================
# ADMIN PANEL
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
                <button class="btn btn-block" type="submit">Entrer</button>
            </form>
        </div>
        """
        return page(body, title="Admin")

    users = User.query.order_by(User.created_at.desc()).all()
    orders = PaymentOrder.query.order_by(PaymentOrder.created_at.desc()).limit(50).all()

    user_rows = ""
    for user in users:
        key = active_api_key(user)
        expiry = user.subscription_expires_at.strftime("%Y-%m-%d") if user.subscription_expires_at else "—"
        credits = "Illimité" if user.unlimited else str(user.credits)
        key_text = key.key_string if key else "—"
        user_rows += f"""
        <tr>
            <td><strong>{user.company_name}</strong><br><span class="muted">{user.email}</span></td>
            <td>{user.plan.title()}</td>
            <td>{credits}</td>
            <td>{expiry}</td>
            <td class="mono">{key_text}</td>
        </tr>"""

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
        </tr>"""

    body = f"""
    <div class="card">
        <h2>Centre administrateur</h2>
        <a class="btn btn-secondary" href="/admin-logout">Verrouiller l'admin</a>
    </div>

    <div class="card">
        <h3>Clients</h3>
        <table>
            <thead><tr><th>Entreprise</th><th>Plan</th><th>Crédits</th><th>Expiration</th><th>Clé API</th></tr></thead>
            <tbody>{user_rows}</tbody>
        </table>
    </div>

    <div class="card">
        <h3>Paiements récents</h3>
        <table>
            <thead><tr><th>Commande</th><th>Client</th><th>Plan</th><th>Durée</th><th>Montant</th><th>Statut</th><th>Date</th></tr></thead>
            <tbody>{order_rows}</tbody>
        </table>
    </div>
    """
    return page(body, title="Admin")


@app.route("/admin-logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("index"))


# ============================================================
# DRIVER SPACE & ROUTE CREATION
# ============================================================

@app.route("/driver-logout")
def driver_logout():
    session.pop("driver_route_code", None)
    return redirect(url_for("driver_login"))


@app.route("/driver-login")
def driver_login():
    body = """
    <div class="card">
        <h2>🚚 Espace livreur</h2>
        <p class="muted">Entrez le code fourni par votre entreprise.</p>
        <form method="POST" action="/driver-space">
            <label>Code d'accès</label>
            <input name="access_code" required>
            <button class="btn btn-green btn-block" type="submit">Afficher ma tournée</button>
        </form>
    </div>
    """
    return page(body, title="Livreur")


@app.route("/driver-space", methods=["POST", "GET"])
def driver_space():
    code = request.form.get("access_code") if request.method == "POST" else request.args.get("code")
    if not code:
        return redirect(url_for("driver_login"))

    route = DeliveryRoute.query.filter_by(access_code=code.strip()).first()
    if not route:
        flash("Code d'accès incorrect.", "danger")
        return redirect(url_for("driver_login"))

    raw_data = route.stops_data or "[]"
    try:
        data = json.loads(raw_data)
        if not isinstance(data, list):
            raise ValueError
    except Exception:
        data = []
        for line in raw_data.splitlines():
            p = [x.strip() for x in line.split("|")]
            if len(p) >= 3:
                try:
                    data.append({"name": p[0], "address": p[1] if len(p) >= 4 else "", "lat": float(p[-2]), "lng": float(p[-1])})
                except Exception:
                    pass

    route_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")

    body = f"""
    <div class="card driver-head">
        <div><span class="muted">Entreprise</span><h2>{route.company.company_name}</h2><p><strong>{route.route_name or 'Tournée'}</strong> · Livreur : {route.driver_name}</p></div>
        <div class="driver-actions">
            <button class="btn btn-green" onclick="locateDriver()">📍 Ma position</button>
            <button class="btn" onclick="window.print()">🖨️ Imprimer</button>
            <a class="btn btn-red" href="/driver-logout">⏻ Déconnexion</a>
        </div>
    </div>

    <div class="grid">
        <div class="stat"><span class="muted">Étapes</span><strong id="stop-count">0</strong></div>
        <div class="stat"><span class="muted">Distance</span><strong id="distance-total">0 km</strong></div>
        <div class="stat"><span class="muted">Navigation</span><strong>GPS</strong></div>
    </div>

    <div class="card map-card"><div id="map"></div><div id="location-status" class="muted"></div></div>

    <div class="card">
        <h3>📋 Fiche de route</h3>
        <div id="stops"></div>
    </div>

    <script>
    const points = {route_json};
    const map = L.map("map").setView(points.length ? [points[0].lat, points[0].lng] : [19.7558,-72.2042], 13);
    L.tileLayer("https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png", {{maxZoom:19, attribution:"© OpenStreetMap contributors"}}).addTo(map);
    const bounds=[]; let total=0; let list="<ol class='stop-list'>";
    function esc(v) {{ return String(v ?? '').replace(/[&<>\"']/g, m => ({{'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}}[m])); }}
    function hav(a,b,c,d) {{ const R=6371, r=Math.PI/180; const x=(c-a)*r, y=(d-b)*r; const q=Math.sin(x/2)**2+Math.cos(a*r)*Math.cos(c*r)*Math.sin(y/2)**2; return 2*R*Math.asin(Math.sqrt(q)); }}
    points.forEach((p,i)=>{{
        if(Number.isNaN(Number(p.lat))||Number.isNaN(Number(p.lng))) return;
        p.lat=Number(p.lat); p.lng=Number(p.lng); bounds.push([p.lat,p.lng]);
        if(i>0) total += hav(points[i-1].lat,points[i-1].lng,p.lat,p.lng);
        const url="https://www.google.com/maps/search/?api=1&query="+p.lat+","+p.lng;
        L.marker([p.lat,p.lng]).addTo(map).bindPopup("<b>"+esc(p.name)+"</b><br>"+esc(p.address)+"<br>Lat: "+p.lat+"<br>Lng: "+p.lng);
        list += "<li><div><strong>"+esc(p.name)+"</strong><br><span class='address'>"+esc(p.address||'Adresse non renseignée')+"</span><br><span class='muted'>GPS: "+p.lat+", "+p.lng+"</span></div><a class='btn btn-small' target='_blank' href='"+url+"'>🧭 Naviguer</a></li>";
    }});
    list += "</ol>"; document.getElementById('stops').innerHTML=list;
    document.getElementById('stop-count').textContent=points.length; document.getElementById('distance-total').textContent=total.toFixed(1)+' km';
    if(bounds.length) {{ const line=L.polyline(bounds,{{weight:3,dashArray:'4 8'}}).addTo(map); map.fitBounds(line.getBounds(),{{padding:[35,35]}}); }}
    function locateDriver() {{ if(!navigator.geolocation) {{document.getElementById('location-status').textContent='Géolocalisation non disponible.';return;}} navigator.geolocation.getCurrentPosition(pos=>{{ const ll=[pos.coords.latitude,pos.coords.longitude]; L.marker(ll).addTo(map).bindPopup('📍 Votre position').openPopup(); map.setView(ll,16); document.getElementById('location-status').textContent='Position actuelle : '+ll[0].toFixed(5)+', '+ll[1].toFixed(5); }},()=>document.getElementById('location-status').textContent='Autorisation de localisation refusée ou indisponible.'); }}
    </script>
    """
    return page(body, title="Tournée", map_needed=True)


@app.route("/create-driver-route", methods=["POST"])
def create_driver_route():
    user = require_user()
    if not user:
        return redirect(url_for("login_form"))

    route_name = request.form.get("route_name", "Tournée").strip() or "Tournée"
    driver_name = request.form.get("driver_name", "").strip()
    access_code = request.form.get("access_code", "").strip()  # Accepte tout format de code
    manual = request.form.get("manual_stops", "").strip()
    file = request.files.get("csv_file")

    if user.subscription_expires_at and user.subscription_expires_at < utcnow():
        flash("Votre abonnement a expiré.", "danger")
        return render_import_form(route_name, driver_name, access_code, manual)

    if user.tour_limit is None:
        user.tour_limit = int(PLANS.get(user.plan, PLANS["standard"])["tour_limit"])
    if user.tours_used is None:
        user.tours_used = 0

    if user.tours_used >= user.tour_limit:
        flash("Quota atteint.", "danger")
        return render_import_form(route_name, driver_name, access_code, manual)

    if not driver_name or not access_code:
        flash("Nom du livreur et code d'accès obligatoires.", "danger")
        return render_import_form(route_name, driver_name, access_code, manual)

    if DeliveryRoute.query.filter_by(access_code=access_code).first():
        flash("Ce code livreur existe déjà. Veuillez en choisir un autre.", "danger")
        return render_import_form(route_name, driver_name, access_code, manual)

    stops = []
    try:
        # Priorité au fichier CSV s'il est fourni
        if file and file.filename:
            stream = io.TextIOWrapper(file.stream, encoding='utf-8-sig', errors='replace')
            for row in csv.reader(stream):
                if not row or not any(row):
                    continue
                name = row[0].strip() if len(row) > 0 else f"Étape {len(stops)+1}"
                address = row[1].strip() if len(row) > 1 else ""
                lat, lng = 19.7558, -72.2042  # Valeur par défaut si manquant

                if len(row) >= 4:
                    try:
                        lat = float(row[2].strip())
                        lng = float(row[3].strip())
                    except ValueError:
                        pass

                if name.lower() in ["nom", "name", "client"]:
                    continue

                stops.append({"name": name, "address": address, "lat": lat, "lng": lng})

        # Sinon, lecture du champ texte manuel
        elif manual:
            for line in manual.splitlines():
                if not line.strip():
                    continue
                parts = [x.strip() for x in line.replace(";", "|").split('|')]
                name = parts[0] if len(parts) > 0 and parts[0] else f"Étape {len(stops)+1}"
                address = parts[1] if len(parts) > 1 and parts[1] else "Adresse non spécifiée"
                lat, lng = 19.7558, -72.2042

                if len(parts) >= 4:
                    try:
                        lat = float(parts[-2])
                        lng = float(parts[-1])
                        address = " | ".join(parts[1:-2])
                    except ValueError:
                        pass
                elif len(parts) == 3:
                    try:
                        lat = float(parts[2])
                    except ValueError:
                        pass

                stops.append({"name": name, "address": address, "lat": lat, "lng": lng})

        if not stops:
            flash("Aucune étape valide trouvée (veuillez importer un fichier CSV ou remplir le champ texte).", "danger")
            return render_import_form(route_name, driver_name, access_code, manual)

        route = DeliveryRoute(
            user_id=user.id,
            route_name=route_name,
            driver_name=driver_name,
            access_code=access_code,
            stops_data=json.dumps(stops, ensure_ascii=False),
            status='En cours'
        )
        db.session.add(route)
        user.tours_used = int(user.tours_used or 0) + 1
        db.session.commit()
        flash(f"Tournée créée avec succès : {len(stops)} étape(s).", "success")
        return redirect(url_for("dashboard"))

    except Exception as e:
        db.session.rollback()
        flash(f"Erreur lors de la création : {str(e)}", "danger")
        return render_import_form(route_name, driver_name, access_code, manual)


@app.route("/api/v1/route", methods=["POST"])
def route_api():
    api_key_value = request.headers.get("X-API-KEY", "").strip()
    if not api_key_value:
        return jsonify({"error": "missing_api_key"}), 401

    key = ApiKey.query.filter_by(key_string=api_key_value, revoked=False).first()
    if not key or (key.expires_at and key.expires_at < utcnow()):
        return jsonify({"error": "invalid_or_expired_api_key"}), 401

    user = User.query.get(key.user_id)
    if not user or not user.active:
        return jsonify({"error": "account_inactive"}), 403

    payload = request.get_json(silent=True) or {}
    points = payload.get("points", [])
    if not isinstance(points, list) or len(points) < 2:
        return jsonify({"error": "at_least_two_points_required"}), 400

    if user.tours_used >= user.tour_limit:
        return jsonify({"error": "tour_quota_exceeded"}), 402

    user.tours_used += 1
    db.session.commit()

    return jsonify({
        "success": True,
        "engine": APP_NAME,
        "points_received": len(points),
        "tours_used": user.tours_used,
        "tour_limit": user.tour_limit,
    })


@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "service": APP_NAME,
        "payments": "USDC / Solana",
        "wallet": SOLANA_RECEIVING_WALLET,
        "network": "mainnet",
    })


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
