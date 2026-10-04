import os
import io
import csv
import json
import secrets
import base64
import math
import urllib.parse
import urllib.request
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timedelta, timezone

from flask import (
    Flask, render_template_string, request, redirect, url_for,
    flash, session, jsonify, make_response
)
from flask_sqlalchemy import SQLAlchemy
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.exc import IntegrityError
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

# Optionnel : Import Google OR-Tools
try:
    from ortools.constraint_solver import pywrapcp, routing_enums_pb2
    HAS_ORTOOLS = True
except ImportError:
    HAS_ORTOOLS = False

# ============================================================
# GLOBALROUTE AI — ENTERPRISE B2B GLOBAL SAAS
# ============================================================

app = Flask(__name__)

# Augmentation de la limite de taille du payload HTTP (16 Mo) pour accepter les gros fichiers CSV / TXT de 500+ villes
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

app.secret_key = os.getenv("SECRET_KEY", secrets.token_hex(32))
ADMIN_SECRET_PASSWORD = os.getenv("ADMIN_SECRET_PASSWORD", "CHANGE-ME")

APP_NAME = "GlobalRoute AI — Global Enterprise Logistics"
SOLANA_RECEIVING_WALLET = "22BzBEYLewJkKe2FXD6EHJYqX4NNshMw9roNw9qFxV9d"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
SOLANA_RPC_URL = "https://api.mainnet.solana.com"

limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=["200 per minute", "20 per second"],
    storage_uri="memory://"
)

TRANSLATIONS = {
    "fr": {
        "home_title": "Optimisation mondiale de tournées pour entreprises B2B.",
        "dashboard": "Tableau de bord",
        "import": "Importer",
        "plans": "Abonnements",
        "logout": "Déconnexion",
        "login": "Connexion",
        "register": "Créer un compte",
        "admin": "Admin",
        "driver_space": "Espace livreur"
    },
    "en": {
        "home_title": "Global route optimization for modern B2B enterprises.",
        "dashboard": "Dashboard",
        "import": "Import",
        "plans": "Plans",
        "logout": "Logout",
        "login": "Login",
        "register": "Register",
        "admin": "Admin",
        "driver_space": "Driver Space"
    },
    "es": {
        "home_title": "Optimización global de rutas para empresas B2B.",
        "dashboard": "Panel",
        "import": "Importar",
        "plans": "Planes",
        "logout": "Cerrar sesión",
        "login": "Iniciar sesión",
        "register": "Registrarse",
        "admin": "Admin",
        "driver_space": "Espacio repartidor"
    }
}

PLANS = {
    "standard": {
        "name": "Standard",
        "monthly_price": 99.00,
        "tour_limit": 500,
    },
    "pro": {
        "name": "Pro",
        "monthly_price": 300.00,
        "tour_limit": 2500,
    },
}

DURATIONS = {
    30: 1.0,
    90: 2.7,
    180: 5.0,
    365: 9.0,
}

# ------------------------------------------------------------
# DATABASE CONFIGURATION
# ------------------------------------------------------------

database_url = os.getenv("DATABASE_URL")
if database_url:
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+psycopg2://", 1)
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
    role = db.Column(db.String(30), default="dispatcher")
    language = db.Column(db.String(10), default="fr")

    address = db.Column(db.String(250), default="")
    city = db.Column(db.String(100), default="")
    country = db.Column(db.String(100), default="")
    tax_id = db.Column(db.String(50), default="")

    plan = db.Column(db.String(30), default="standard")
    subscription_started_at = db.Column(db.DateTime, nullable=True)
    subscription_expires_at = db.Column(db.DateTime, nullable=True)

    credits = db.Column(db.Integer, default=0)
    unlimited = db.Column(db.Boolean, default=False)
    tour_limit = db.Column(db.Integer, default=500)
    tours_used = db.Column(db.Integer, default=0)
    active = db.Column(db.Boolean, default=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    api_keys = db.relationship("ApiKey", backref="owner", lazy=True, cascade="all, delete-orphan")
    deliveries = db.relationship("DeliveryRoute", backref="company", lazy=True, cascade="all, delete-orphan")
    payments = db.relationship("PaymentOrder", backref="customer", lazy=True, cascade="all, delete-orphan")


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
    currency = db.Column(db.String(10), default="USDC")
    status = db.Column(db.String(20), default="pending")
    transaction_signature = db.Column(db.String(160), unique=True, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    paid_at = db.Column(db.DateTime, nullable=True)


class DeliveryRoute(db.Model):
    __tablename__ = "delivery_routes"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    route_name = db.Column(db.Text, default="Tournée")
    driver_name = db.Column(db.String(100), nullable=False)
    access_code = db.Column(db.String(80), nullable=False)
    stops_data = db.Column(db.Text, nullable=False)
    stops_summary = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default="En cours")
    optimized = db.Column(db.Boolean, default=False)


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(120), nullable=False)
    details = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


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
            try:
                type_sql = column.type.compile(dialect=db.engine.dialect)
            except Exception:
                type_sql = str(column.type)
            sql = f'ALTER TABLE "{table_name}" ADD COLUMN "{column.name}" {type_sql}'
            db.session.execute(text(sql))
        db.session.commit()

    try:
        db.session.execute(text('ALTER TABLE delivery_routes ALTER COLUMN stops_summary DROP NOT NULL;'))
        db.session.commit()
    except Exception:
        db.session.rollback()


with app.app_context():
    db.create_all()
    migrate_existing_database()


# ============================================================
# MOTEUR DE ROUTAGE HYBRIDE & SYNCHRONISATION PAR LOTS (500 VILLES)
# ============================================================

ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

def base58_encode(raw: bytes) -> str:
    number = int.from_bytes(raw, "big")
    result = ""
    while number:
        number, remainder = divmod(number, 58)
        result = ALPHABET[remainder] + result
    leading_zeroes = sum(1 for byte in raw if byte == 0)
    return "1" * leading_zeroes + (result or "")

def generate_reference():
    return base58_encode(secrets.token_bytes(32))

def utcnow():
    return datetime.utcnow()

def get_current_lang():
    lang = session.get("lang", "fr")
    return lang if lang in TRANSLATIONS else "fr"

def t(key):
    lang = get_current_lang()
    return TRANSLATIONS.get(lang, TRANSLATIONS["fr"]).get(key, key)

def calculate_price(plan, duration_days):
    if plan not in PLANS or duration_days not in DURATIONS:
        raise ValueError("Paramètres invalides.")
    return round(PLANS[plan]["monthly_price"] * DURATIONS[duration_days], 2)

def parse_coordinate(val):
    try:
        val_str = str(val).strip().replace(',', '.')
        return float(val_str)
    except (ValueError, TypeError):
        return None

def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))

def route_distance(route):
    dist = 0.0
    for i in range(len(route) - 1):
        dist += haversine(float(route[i]['lat']), float(route[i]['lng']), float(route[i+1]['lat']), float(route[i+1]['lng']))
    return dist

def local_two_opt_pass(route):
    improved = True
    iterations = 0
    max_iterations = 60
    optimized = list(route)
    while improved and iterations < max_iterations:
        improved = False
        iterations += 1
        for i in range(1, len(optimized) - 2):
            for j in range(i + 1, len(optimized)):
                if j - i == 1:
                    continue
                new_route = optimized[:i] + optimized[i:j][::-1] + optimized[j:]
                if route_distance(new_route) < route_distance(optimized):
                    optimized = new_route
                    improved = True
    return optimized

def nearest_neighbor_guided(route):
    if len(route) <= 2:
        return route
    anchor = route[0]
    unvisited = list(route[1:])
    optimized = [anchor]
    while unvisited:
        current = optimized[-1]
        next_stop = min(
            unvisited,
            key=lambda s: haversine(float(current['lat']), float(current['lng']), float(s['lat']), float(s['lng']))
        )
        unvisited.remove(next_stop)
        optimized.append(next_stop)
    return optimized

def certify_route_with_ortools(route):
    if not HAS_ORTOOLS or len(route) <= 3:
        return route
    try:
        n = len(route)
        distance_matrix = [[0] * n for _ in range(n)]
        for i in range(n):
            for j in range(n):
                if i != j:
                    distance_matrix[i][j] = int(haversine(
                        float(route[i]['lat']), float(route[i]['lng']),
                        float(route[j]['lat']), float(route[j]['lng'])
                    ) * 1000)

        manager = pywrapcp.RoutingIndexManager(n, 1, 0)
        routing = pywrapcp.RoutingModel(manager)

        def distance_callback(from_index, to_index):
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            return distance_matrix[from_node][to_node]

        transit_callback_index = routing.RegisterTransitCallback(distance_callback)
        routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        search_parameters.first_solution_strategy = (
            routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
        )
        search_parameters.time_limit.seconds = 2

        solution = routing.SolveWithParameters(search_parameters)
        if solution:
            index = routing.Start(0)
            certified_indices = []
            while not routing.IsEnd(index):
                certified_indices.append(manager.IndexToNode(index))
                index = solution.Value(routing.NextVar(index))
            
            certified_route = [route[i] for i in certified_indices if i < len(route)]
            if len(certified_route) == len(route):
                return certified_route
    except Exception:
        pass
    return route

def process_single_shard(shard):
    try:
        if len(shard) <= 2:
            return shard
        route = nearest_neighbor_guided(shard)
        route = local_two_opt_pass(route)
        certified_route = certify_route_with_ortools(route)
        return certified_route
    except Exception:
        return sorted(shard, key=lambda p: (p['lat'], p['lng']))

def optimize_stops_order(stops):
    if len(stops) <= 15:
        return process_single_shard(stops)
    
    chunk_size = 100
    shards = [stops[i:i + chunk_size] for i in range(0, len(stops), chunk_size)]
    processed_shards = []
    
    current_origin = stops[0] if stops else None
    for shard in shards:
        if current_origin and current_origin not in shard:
            shard = [current_origin] + [s for s in shard if s != current_origin]
        
        res = process_single_shard(shard)
        if processed_shards and res:
            res = [processed_shards[-1]] + [s for s in res if s != processed_shards[-1]]
            res = local_two_opt_pass(res)
        
        processed_shards.extend(res if not processed_shards else res[1:])
        if processed_shards:
            current_origin = processed_shards[-1]

    return local_two_opt_pass(processed_shards)


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
        if not key.revoked and (not key.expires_at or key.expires_at >= now):
            return key
    return None


def add_subscription(user, plan, duration_days):
    now = utcnow()
    same_plan = bool(user.subscription_expires_at and user.subscription_expires_at > now and user.plan == plan)
    
    if same_plan:
        expiry = user.subscription_expires_at + timedelta(days=duration_days)
        user.tour_limit = int(user.tour_limit or 0) + int(PLANS[plan]["tour_limit"])
    else:
        expiry = now + timedelta(days=duration_days)
        user.plan = plan
        user.subscription_started_at = now
        user.subscription_expires_at = expiry
        user.tour_limit = int(PLANS[plan]["tour_limit"])
        user.tours_used = 0

    user.credits = user.tour_limit
    key = active_api_key(user)
    if key:
        key.expires_at = expiry
    else:
        create_api_key(user, expiry)

    return expiry


def rpc_call(method, params):
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode("utf-8")
    req = urllib.request.Request(SOLANA_RPC_URL, data=payload, headers={"Content-Type": "application/json"}, method="POST")
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
        return False, None, "Paiement non trouvé sur la blockchain."

    existing_order = PaymentOrder.query.filter_by(transaction_signature=signature).first()
    if existing_order and existing_order.id != order.id:
        return False, signature, "Cette transaction a déjà été validée pour une autre commande."

    tx = rpc_call("getTransaction", [signature, {"encoding": "jsonParsed", "commitment": "confirmed", "maxSupportedTransactionVersion": 0}])
    if not tx or (tx.get("meta") and tx["meta"].get("err") is not None):
        return False, None, "Transaction Solana invalide ou échouée."

    meta = tx.get("meta") or {}
    expected_raw = int(round(order.amount_usdc * 1_000_000))
    received_raw = sum(
        int(b.get("uiTokenAmount", {}).get("amount", "0"))
        for b in (meta.get("postTokenBalances") or [])
        if b.get("mint") == USDC_MINT and b.get("owner") == SOLANA_RECEIVING_WALLET
    )
    pre_raw = sum(
        int(b.get("uiTokenAmount", {}).get("amount", "0"))
        for b in (meta.get("preTokenBalances") or [])
        if b.get("mint") == USDC_MINT and b.get("owner") == SOLANA_RECEIVING_WALLET
    )

    if (received_raw - pre_raw) < expected_raw:
        return False, signature, f"Montant USDC insuffisant. Attendu : {order.amount_usdc} USDC."
    return True, signature, "Paiement vérifié."


def activate_paid_order(order, signature):
    if order.status == "paid":
        return
    user = User.query.get(order.user_id)
    if not user:
        raise RuntimeError("Utilisateur introuvable.")

    expiry = add_subscription(user, order.plan, order.duration_days)
    order.status = "paid"
    order.transaction_signature = signature
    order.paid_at = utcnow()

    db.session.add(AuditLog(action="PAYMENT_CONFIRMED", details=f"order={order.order_code}; user={user.email}; sig={signature}"))
    db.session.commit()


# ============================================================
# DESIGN & CSS STYLES (FLUIDE & MOBILE OPTIMIZED)
# ============================================================

BASE_STYLE = """
:root {
    --navy:#0f172a; --blue:#2563eb; --blue2:#1d4ed8; --green:#059669; --red:#dc2626;
    --bg:#f8fafc; --card:#ffffff; --text:#0f172a; --muted:#64748b; --border:#e2e8f0;
}
* { box-sizing:border-box; }
html, body { 
    margin:0; 
    padding:0; 
    background:var(--bg); 
    color:var(--text); 
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; 
    overflow-x: hidden; 
}
header { background:var(--navy); color:white; padding:12px 20px; display:flex; align-items:center; gap:15px; position:relative; }
header h1 { margin:0; font-size:18px; flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.lang-selector { background:rgba(255,255,255,.1); color:white; border:1px solid rgba(255,255,255,.2); border-radius:6px; padding:6px; font-size:12px; }
.menu-toggle { width:40px; height:40px; border:1px solid rgba(255,255,255,.2); border-radius:8px; background:rgba(255,255,255,.1); color:white; font-size:20px; cursor:pointer; flex-shrink: 0; }
nav { display:none; position:absolute; top:60px; left:15px; z-index:1000; min-width:220px; padding:10px; background:var(--navy); border:1px solid rgba(255,255,255,.15); border-radius:12px; box-shadow:0 10px 30px rgba(0,0,0,.3); flex-direction:column; gap:6px; }
nav.open { display:flex; }
nav a { color:#e2e8f0; text-decoration:none; font-size:13px; padding:10px; border-radius:8px; }
nav a:hover { background:rgba(255,255,255,.1); }

.container { width:100%; max-width:1150px; margin:0 auto; padding:16px; overflow-x: hidden; }
.card { background:var(--card); border:1px solid var(--border); border-radius:14px; padding:18px; margin-bottom:20px; box-shadow:0 4px 15px rgba(0,0,0,.03); word-break:break-word; }
.hero { text-align:center; padding:30px 15px; }

.btn { display:inline-block; border:0; border-radius:8px; padding:12px 16px; font-weight:600; text-decoration:none; cursor:pointer; background:var(--blue); color:white; text-align:center; font-size:14px; }
.btn:hover { background:var(--blue2); }
.btn-secondary { background:#e2e8f0; color:var(--navy); }
.btn-green { background:var(--green); color:white; }
.btn-red { background:var(--red); color:white; }
.btn-block { width:100%; display:block; }

label { display:block; margin:12px 0 6px; font-size:13px; font-weight:700; }
input, select, textarea { width:100%; max-width:100%; border:1px solid #cbd5e1; border-radius:8px; padding:11px; font-size:14px; background:white; }

.table-responsive { width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch; margin-bottom: 10px; }
table { width:100%; border-collapse:collapse; font-size:13px; white-space: nowrap; }
th, td { border-bottom:1px solid var(--border); padding:12px 10px; text-align:left; }
th { background:#f1f5f9; }

.alert { padding:12px; border-radius:8px; margin-bottom:15px; font-size:13px; }
.alert-success { background:#dcfce7; color:#166534; }
.alert-danger { background:#fee2e2; color:#991b1b; }

.grid { display:grid; grid-template-columns:repeat(3,1fr); gap:15px; }
.stat { background:#f8fafc; border:1px solid var(--border); border-radius:10px; padding:15px; }
.stat strong { display:block; font-size:20px; margin-top:4px; word-break:break-all; }
.muted { color:var(--muted); font-size:12px; }
.mono { font-family:monospace; word-break:break-all; }

#map { width:100%; height:400px; border-radius:10px; margin-top:15px; z-index: 1; }
.plan-grid { display:grid; grid-template-columns:repeat(2,1fr); gap:20px; }
.plan-card { background:white; border:1px solid var(--border); border-radius:14px; padding:20px; }
.plan-card.featured { border:2px solid var(--blue); }

@media(max-width:768px) { 
    .grid { grid-template-columns:1fr; } 
    .plan-grid { grid-template-columns:1fr; }
    body { font-size: 14px; }
    .container { padding: 10px; }
    .card { padding: 14px; }
}
"""

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="{{ session.get('lang', 'fr') }}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{ title or APP_NAME }}</title>
{% if map_needed %}
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
{% endif %}
<style>{{ style }}</style>
</head>
<body>
<header>
    <button class="menu-toggle" type="button" onclick="toggleMenu()">☰</button>
    <h1>{{ APP_NAME }}</h1>
    <select class="lang-selector" onchange="location.href='/set-lang/'+this.value">
        <option value="fr" {% if session.get('lang')=='fr' %}selected{% endif %}>Français</option>
        <option value="en" {% if session.get('lang')=='en' %}selected{% endif %}>English</option>
        <option value="es" {% if session.get('lang')=='es' %}selected{% endif %}>Español</option>
    </select>
    <nav id="global-menu">
        <a href="/">⌂ &nbsp;Accueil</a>
        {% if session.get("user_id") %}
        <a href="/dashboard">▣ &nbsp;{{ t('dashboard') }}</a>
        <a href="/import-space">⇧ &nbsp;{{ t('import') }}</a>
        <a href="/plans">◈ &nbsp;{{ t('plans') }}</a>
        <a href="/logout">⏻ &nbsp;{{ t('logout') }}</a>
        {% else %}
        <a href="/login-form">↪ &nbsp;{{ t('login') }}</a>
        <a href="/register-form">＋ &nbsp;{{ t('register') }}</a>
        {% endif %}
        <a href="/admin-panel">⚙ &nbsp;{{ t('admin') }}</a>
        <a href="/driver-login">🚚 &nbsp;{{ t('driver_space') }}</a>
    </nav>
    <script>
    function toggleMenu() { document.getElementById("global-menu").classList.toggle("open"); }
    </script>
</header>
<div class="container">
{% with messages = get_flashed_messages(with_categories=true) %}
{% for cat, msg in messages %}
<div class="alert alert-{{ cat }}">{{ msg }}</div>
{% endfor %}
{% endwith %}
{{ body|safe }}
</div>
<footer>© 2026 GlobalRoute AI — Global Enterprise B2B Logistics</footer>
</body>
</html>
"""

def page(body, title=APP_NAME, map_needed=False):
    return render_template_string(HTML_TEMPLATE, body=body, title=title, style=BASE_STYLE, APP_NAME=APP_NAME, map_needed=map_needed, session=session, t=t)


# ============================================================
# ROUTES & APPLICATION LOGIC
# ============================================================

@app.route("/set-lang/<lang>")
def set_lang(lang):
    if lang in TRANSLATIONS:
        session["lang"] = lang
    return redirect(request.referrer or url_for("index"))


@app.route("/")
def index():
    body = f"""
    <div class="card hero">
        <h2>{t('home_title')}</h2>
        <p class="muted">GlobalRoute AI fournit l'itinéraire le plus court, le plus rapide et le plus sûr pour maximiser la performance de vos tournées de livraison internationales.</p>
        <a class="btn" href="/register-form">Créer un compte entreprise</a>
        <a class="btn btn-secondary" href="/login-form">Connexion</a>
    </div>
    <div class="grid">
        <div class="stat"><span class="muted">Réseau Paiement</span><strong>USDC / Solana</strong><span class="muted">Instant & Zéro frais</span></div>
        <div class="stat"><span class="muted">Moteur Raccourci</span><strong>Hybride Avancé</strong><span class="muted">Optimisation maximale</span></div>
        <div class="stat"><span class="muted">Facturation</span><strong>Conforme PDF</strong><span class="muted">Téléchargeable</span></div>
    </div>
    """
    return page(body)


@app.route("/register-form")
def register_form():
    body = """
    <div class="card">
        <h2>Créer un compte entreprise B2B</h2>
        <form method="POST" action="/register">
            <label>Nom de l'entreprise</label><input name="company_name" required>
            <label>E-mail professionnel</label><input type="email" name="email" required>
            <label>Mot de passe (8 caractères min.)</label><input type="password" name="password" minlength="8" required>
            <label>Adresse</label><input name="address">
            <label>Ville</label><input name="city">
            <label>Pays</label><input name="country">
            <label>Numéro de TVA / Tax ID (Optionnel)</label><input name="tax_id">
            <button class="btn btn-block" type="submit" style="margin-top:15px;">S'inscrire</button>
        </form>
    </div>
    """
    return page(body)


@app.route("/register", methods=["POST"])
def register():
    company = request.form.get("company_name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    if not company or not email or len(password) < 8:
        flash("Champs incomplets ou mot de passe trop court.", "danger")
        return redirect(url_for("register_form"))

    if User.query.filter_by(email=email).first():
        flash("Cet e-mail est déjà associé à un compte.", "danger")
        return redirect(url_for("register_form"))

    user = User(
        company_name=company,
        email=email,
        password_hash=generate_password_hash(password),
        address=request.form.get("address", "").strip(),
        city=request.form.get("city", "").strip(),
        country=request.form.get("country", "").strip(),
        tax_id=request.form.get("tax_id", "").strip(),
        role="dispatcher"
    )
    db.session.add(user)
    db.session.commit()
    session["user_id"] = user.id
    flash("Compte créé avec succès. Veuillez choisir un abonnement.", "success")
    return redirect(url_for("plans"))


@app.route("/login-form")
def login_form():
    body = """
    <div class="card">
        <h2>Connexion Entreprise</h2>
        <form method="POST" action="/login">
            <label>E-mail</label><input type="email" name="email" required>
            <label>Mot de passe</label><input type="password" name="password" required>
            <button class="btn btn-block" type="submit" style="margin-top:15px;">Connexion</button>
        </form>
    </div>
    """
    return page(body)


@app.route("/login", methods=["POST"])
def login():
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    
    user = db.session.execute(db.select(User).filter_by(email=email)).scalar_one_or_none()

    if user and check_password_hash(user.password_hash, password):
        session["user_id"] = user.id
        return redirect(url_for("dashboard"))
    flash("Identifiants incorrects.", "danger")
    return redirect(url_for("login_form"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/dashboard")
def dashboard():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login_form"))
    user = User.query.get(user_id)

    key = active_api_key(user)
    key_text = key.key_string if key else "Aucune clé active"
    expiry = user.subscription_expires_at.strftime("%Y-%m-%d") if user.subscription_expires_at else "—"
    remaining = max(0, int(user.tour_limit or 0) - int(user.tours_used or 0))

    routes = DeliveryRoute.query.filter_by(user_id=user.id).order_by(DeliveryRoute.id.desc()).limit(30).all()
    route_rows = ""
    for r in routes:
        try:
            stops = json.loads(r.stops_data or "[]")
            c = len(stops)
        except Exception:
            c = 0
        opt_badge = '<span style="color:var(--green)">⚡ Raccourci optimal</span>' if r.optimized else '<span class="muted">Standard</span>'
        route_rows += f"""
        <tr>
            <td><strong>{r.route_name}</strong></td>
            <td>{r.driver_name}</td>
            <td>{c} étapes</td>
            <td>{opt_badge}</td>
            <td><a class='btn' style='padding:4px 8px;font-size:11px;' href='/driver-space?code={urllib.parse.quote(r.access_code)}'>Ouvrir</a></td>
        </tr>"""

    payments = PaymentOrder.query.filter_by(user_id=user.id).order_by(PaymentOrder.created_at.desc()).all()
    payment_rows = ""
    for p in payments:
        pdf_btn = f"<a class='btn btn-secondary' style='padding:2px 6px;font-size:10px;' href='/invoice/{p.id}'>📄 PDF</a>" if p.status == "paid" else ""
        payment_rows += f"<tr><td>{p.order_code}</td><td>{p.plan.title()}</td><td>{p.amount_usdc} USDC</td><td>{p.status}</td><td>{pdf_btn}</td></tr>"

    body = f"""
    <div class="card">
        <h2>{user.company_name}</h2>
        <p class="muted">Email : {user.email} | TVA : {user.tax_id or 'Non renseigné'}</p>
        <div class="grid">
            <div class="stat"><span class="muted">Abonnement</span><strong>{user.plan.title()}</strong></div>
            <div class="stat"><span class="muted">Tournées utilisées</span><strong>{user.tours_used} / {user.tour_limit}</strong></div>
            <div class="stat"><span class="muted">Restantes</span><strong>{remaining}</strong></div>
        </div>
        <p class="muted" style="margin-top:10px;">Expiration : {expiry}</p>
    </div>

    <div class="card">
        <h3>🚀 Gestion des tournées</h3>
        <p class="muted">Importez votre fichier pour calculer instantanément la route la plus courte, rapide et sûre.</p>
        <a class="btn btn-green" href="/import-space">Importer / Créer une tournée</a>
    </div>

    <div class="card">
        <h3>📋 Historique des tournées</h3>
        <div class="table-responsive">
            <table>
                <thead><tr><th>Tournée</th><th>Livreur</th><th>Étapes</th><th>Optimisation</th><th>Action</th></tr></thead>
                <tbody>{route_rows or '<tr><td colspan="5" class="muted">Aucune tournée.</td></tr>'}</tbody>
            </table>
        </div>
    </div>

    <div class="card">
        <h3>💳 Factures & Paiements</h3>
        <div class="table-responsive">
            <table>
                <thead><tr><th>Commande</th><th>Plan</th><th>Montant</th><th>Statut</th><th>Facture</th></tr></thead>
                <tbody>{payment_rows or '<tr><td colspan="5" class="muted">Aucun paiement.</td></tr>'}</tbody>
            </table>
        </div>
    </div>

    <div class="card">
        <h3>🔑 Clé API B2B & Accès JSON</h3>
        <p class="muted">Utilisez cet endpoint pour intégrer les calculs directement via JSON : <code class="mono">POST /api/v1/route</code> avec le header <code class="mono">X-API-KEY: [Votre Clé]</code></p>
        <div class="payment-box mono" style="background:#f1f5f9;padding:12px;border-radius:8px;">{key_text}</div>
    </div>
    """
    return page(body, title="Dashboard B2B")


@app.route("/import-space")
def import_space():
    if not session.get("user_id"):
        return redirect(url_for("login_form"))
    return render_template_string(IMPORT_FORM_HTML, style=BASE_STYLE, APP_NAME=APP_NAME, session=session)

IMPORT_FORM_HTML = """
<!DOCTYPE html>
<html lang="fr"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Importer</title><style>{{ style }}</style></head>
<body>
<div class="container">
    <div class="card">
        <h2>Trouver le raccourci optimal</h2>
        <p class="muted">Sélectionnez un fichier ou remplissez la saisie manuelle ci-dessous.</p>
        <form method="POST" action="/create-driver-route" enctype="multipart/form-data">
            <label>Nom de la tournée</label><input name="route_name" required placeholder="Ex. Tournée Centre-Ville">
            <label>Nom du livreur</label><input name="driver_name" required placeholder="Ex. Thomas">
            <label>Code d'accès du livreur (Réutilisable)</label><input name="access_code" required placeholder="Ex. LIVREUR-01">
            
            <label>Sélectionner un fichier (Le texte s'injectera automatiquement)</label>
            <input type="file" id="file-input" accept=".csv,.txt">

            <label>Ou Saisie manuelle (Nom | Adresse | Lat | Lng)</label>
            <textarea id="manual-stops" name="manual_stops" rows="6" placeholder="Client A | 12 Rue de Paris | 18.5385 | -72.335"></textarea>
            
            <button class="btn btn-green btn-block" type="submit" style="margin-top:15px;">Calculer le raccourci et créer</button>
        </form>
        <a class="btn btn-secondary" href="/dashboard" style="margin-top:10px;display:inline-block;">Retour</a>
    </div>
</div>
<script>
document.getElementById('file-input').addEventListener('change', function(event) {
    const file = event.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = function(e) {
        document.getElementById('manual-stops').value = e.target.result;
    };
    reader.readAsText(file, 'UTF-8');
});
</script>
</body></html>
"""


@app.route("/create-driver-route", methods=["POST"])
def create_driver_route():
    user = User.query.get(session.get("user_id"))
    if not user:
        return redirect(url_for("login_form"))

    if user.subscription_expires_at and user.subscription_expires_at < utcnow():
        flash("Votre abonnement a expiré. Veuillez le renouveler pour créer de nouvelles tournées.", "danger")
        return redirect(url_for("plans"))

    route_name = request.form.get("route_name", "Tournée").strip()
    driver_name = request.form.get("driver_name", "").strip()
    access_code = request.form.get("access_code", "").strip()
    manual = request.form.get("manual_stops", "").strip()

    if user.tours_used >= user.tour_limit:
        flash("Quota de tournées atteint. Veuillez mettre à niveau votre abonnement.", "danger")
        return redirect(url_for("dashboard"))

    stops = []
    if manual:
        for line in manual.splitlines():
            parts = [x.strip() for x in line.split("|")]
            if len(parts) >= 4:
                lat = parse_coordinate(parts[2])
                lng = parse_coordinate(parts[3])
                if lat is not None and lng is not None and -90 <= lat <= 90 and -180 <= lng <= 180:
                    stops.append({"name": parts[0], "address": parts[1], "lat": lat, "lng": lng})

    if not stops:
        flash("Aucune étape valide détectée (vérifiez le format et les coordonnées GPS).", "danger")
        return redirect(url_for("import_space"))

    try:
        optimized_stops = optimize_stops_order(stops)
    except Exception as e:
        flash(f"Erreur lors du calcul d'optimisation : {str(e)}", "danger")
        return redirect(url_for("import_space"))

    route = DeliveryRoute.query.filter_by(user_id=user.id, access_code=access_code).first()
    if route:
        route.route_name = route_name
        route.driver_name = driver_name
        route.stops_data = json.dumps(optimized_stops, ensure_ascii=False)
        route.status = "En cours"
        route.optimized = True
    else:
        route = DeliveryRoute(
            user_id=user.id,
            route_name=route_name,
            driver_name=driver_name,
            access_code=access_code,
            stops_data=json.dumps(optimized_stops, ensure_ascii=False),
            status="En cours",
            optimized=True
        )
        db.session.add(route)
    
    try:
        user.tours_used += 1
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(f"Une erreur inattendue est survenue lors de l'enregistrement : {str(e)}", "danger")
        return redirect(url_for("import_space"))

    flash(f"Raccourci optimal calculé avec succès ({len(stops)} étapes triées).", "success")
    return redirect(url_for("dashboard"))


@app.route("/plans")
def plans():
    if not session.get("user_id"):
        return redirect(url_for("login_form"))
    body = """
    <div class="card hero">
        <h2>Abonnements B2B Mondiaux</h2>
        <p class="muted">Réglez instantanément en USDC sur le réseau Solana.</p>
    </div>
    <div class="plan-grid">
        <div class="plan-card">
            <h3>Standard</h3>
            <div style="font-size:28px;font-weight:bold;margin:10px 0;">99 USDC <small>/ mois</small></div>
            <p>500 tournées incluses / mois</p>
            <form method="POST" action="/create-payment">
                <input type="hidden" name="plan" value="standard">
                <label>Durée</label>
                <select name="duration_days">
                    <option value="30">30 jours (99 USDC)</option>
                    <option value="90">90 jours (267.30 USDC)</option>
                </select>
                <button class="btn btn-block" type="submit" style="margin-top:15px;">Sélectionner</button>
            </form>
        </div>
        <div class="plan-card featured">
            <h3>Pro</h3>
            <div style="font-size:28px;font-weight:bold;margin:10px 0;">300 USDC <small>/ mois</small></div>
            <p>2 500 tournées incluses + API B2B illimitée</p>
            <form method="POST" action="/create-payment">
                <input type="hidden" name="plan" value="pro">
                <label>Durée</label>
                <select name="duration_days">
                    <option value="30">30 jours (300 USDC)</option>
                    <option value="90">90 jours (810 USDC)</option>
                </select>
                <button class="btn btn-green btn-block" type="submit" style="margin-top:15px;">Sélectionner Pro</button>
            </form>
        </div>
    </div>
    """
    return page(body, title="Abonnements")


@app.route("/create-payment", methods=["POST"])
def create_payment():
    user = User.query.get(session.get("user_id"))
    if not user:
        return redirect(url_for("login_form"))

    plan = request.form.get("plan")
    duration = int(request.form.get("duration_days", 30))
    amount = calculate_price(plan, duration)
    ref = generate_reference()

    order = PaymentOrder(
        order_code=f"GR-{secrets.token_hex(6).upper()}",
        reference=ref,
        user_id=user.id,
        plan=plan,
        duration_days=duration,
        amount_usdc=amount,
        status="pending"
    )
    db.session.add(order)
    db.session.commit()

    solana_uri = f"solana:{SOLANA_RECEIVING_WALLET}?amount={amount}&spl-token={USDC_MINT}&reference={ref}&label=GlobalRouteAI"

    body = f"""
    <div class="card">
        <h2>Paiement de la commande {order.order_code}</h2>
        <div style="background:#f8fafc;padding:15px;border-radius:8px;margin:15px 0;">
            <p><strong>Montant :</strong> {amount} USDC</p>
            <p><strong>Wallet :</strong> <span class="mono">{SOLANA_RECEIVING_WALLET}</span></p>
            <p><strong>Référence :</strong> <span class="mono">{ref}</span></p>
        </div>
        <a class="btn btn-green btn-block" href="{solana_uri}">Payer avec Phantom / Solana Wallet</a>
        <button class="btn btn-block" onclick="checkPay()" style="margin-top:10px;">Vérifier le paiement</button>
        <div id="status" class="alert" style="margin-top:15px;">En attente de confirmation sur la blockchain...</div>
    </div>
    <script>
    async function checkPay() {{
        let res = await fetch("/api/payment-status/{order.id}");
        let data = await res.json();
        document.getElementById("status").textContent = data.message;
        if(data.paid) {{
            document.getElementById("status").className = "alert alert-success";
            setTimeout(() => location.href="/dashboard", 1500);
        }}
    }}
    setInterval(checkPay, 6000);
    </script>
    """
    return page(body, title="Paiement USDC")


@app.route("/api/payment-status/<int:order_id>")
def payment_status(order_id):
    order = PaymentOrder.query.get_or_404(order_id)
    if order.status == "paid":
        return jsonify({"paid": True, "message": "Déjà payé."})
    valid, sig, msg = verify_usdc_payment(order)
    if valid:
        activate_paid_order(order, sig)
        return jsonify({"paid": True, "message": "Paiement validé avec succès ! Redirection..."})
    return jsonify({"paid": False, "message": msg})


@app.route("/invoice/<int:order_id>")
def download_invoice(order_id):
    user = User.query.get(session.get("user_id"))
    order = PaymentOrder.query.get_or_404(order_id)
    if not user or order.user_id != user.id or order.status != "paid":
        return "Accès refusé", 403

    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    p.drawString(50, 750, f"FACTURE / INVOICE - {APP_NAME}")
    p.drawString(50, 725, f"Commande : {order.order_code}")
    p.drawString(50, 700, f"Client : {user.company_name} ({user.email})")
    p.drawString(50, 675, f"Plan : {order.plan.title()} ({order.duration_days} jours)")
    p.drawString(50, 650, f"Montant total : {order.amount_usdc} USDC")
    p.drawString(50, 625, f"Date : {order.paid_at}")
    p.drawString(50, 575, f"Transaction Solana : {order.transaction_signature}")
    p.showPage()
    p.save()
    buffer.seek(0)

    response = make_response(buffer.read())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename=facture_{order.order_code}.pdf'
    return response


@app.route("/driver-login")
def driver_login():
    body = """
    <div class="card">
        <h2>🚚 Espace Livreur</h2>
        <form method="POST" action="/driver-space">
            <label>Code d'accès de la tournée</label><input name="access_code" required>
            <button class="btn btn-green btn-block" type="submit" style="margin-top:15px;">Accéder au raccourci</button>
        </form>
    </div>
    """
    return page(body, title="Livreur")


@app.route("/driver-space", methods=["GET", "POST"])
def driver_space():
    code = request.form.get("access_code") if request.method == "POST" else request.args.get("code")
    route = DeliveryRoute.query.filter_by(access_code=code).first() if code else None
    if not route:
        flash("Code d'accès invalide.", "danger")
        return redirect(url_for("driver_login"))

    stops = json.loads(route.stops_data or "[]")
    stops_json = json.dumps(stops, ensure_ascii=False)
    
    body = f"""
    <div class="card">
        <h2>Tournée : {route.route_name}</h2>
        <p><strong>Livreur :</strong> {route.driver_name} | <strong>Entreprise :</strong> {route.company.company_name}</p>
        <div class="grid" style="margin: 15px 0;">
            <div class="stat"><span class="muted">Distance Route (Réelle)</span><strong id="total-distance">Calcul en cours...</strong></div>
            <div class="stat"><span class="muted">Nombre d'étapes</span><strong>{len(stops)}</strong></div>
            <div class="stat"><span class="muted">Statut GPS</span><strong id="gps-status" style="color:var(--blue);">Recherche...</strong></div>
        </div>
        <div style="display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 10px;">
            <button class="btn btn-green" onclick="toggleTracking()">📍 Activer mon suivi GPS en direct</button>
            <a class="btn btn-secondary" href="/driver-print?code={urllib.parse.quote(route.access_code)}" target="_blank">🖨️ Imprimer la fiche</a>
        </div>
        <div id="map"></div>
    </div>
    <div class="card">
        <h3>Étapes du raccourci optimal</h3>
        <div id="stops-list"></div>
    </div>
    <script>
    const points = {stops_json};
    const map = L.map('map').setView(points.length ? [points[0].lat, points[0].lng] : [18.5385, -72.335], 13);
    L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{maxZoom:19}}).addTo(map);

    let list = "<ol>";
    points.forEach((p, i) => {{
        if (i < 200) {{
            L.marker([p.lat, p.lng]).addTo(map).bindPopup("<b>#" + (i+1) + " " + p.name + "</b><br>" + p.address);
        }}
        list += "<li style='margin-bottom: 8px;'><strong>#" + (i+1) + " - " + p.name + "</strong><br><span class='muted'>" + p.address + "</span> <a href='https://www.google.com/maps/dir/?api=1&destination=" + p.lat + "," + p.lng + "' target='_blank' style='margin-left: 10px; font-size: 12px;'>🧭 Naviguer (Google Maps)</a></li>";
    }});
    list += "</ol>";
    document.getElementById('stops-list').innerHTML = list;

    if (points.length >= 2) {{
        const maxChunk = 100;
        let chunkPromises = [];
        for (let i = 0; i < points.length; i += maxChunk) {{
            let chunkPoints = points.slice(i, i + maxChunk);
            if (i > 0 && points[i-1]) {{
                chunkPoints = [points[i-1]].concat(chunkPoints);
            }}
            const coordsString = chunkPoints.map(p => p.lng + "," + p.lat).join(';');
            const osrmUrl = "https://router.project-osrm.org/route/v1/driving/" + coordsString + "?overview=full&geometries=geojson";
            chunkPromises.push(fetch(osrmUrl).then(res => res.json()).catch(() => null));
        }}

        Promise.all(chunkPromises)
            .then(results => {{
                let fullRoadCoords = [];
                let totalDistanceMeters = 0;
                let successCount = 0;

                results.forEach(data => {{
                    if (data && data.code === 'Ok' && data.routes && data.routes.length > 0) {{
                        totalDistanceMeters += data.routes[0].distance;
                        const roadCoords = data.routes[0].geometry.coordinates.map(c => [c[1], c[0]]);
                        if (fullRoadCoords.length > 0) {{
                            fullRoadCoords = fullRoadCoords.concat(roadCoords.slice(1));
                        }} else {{
                            fullRoadCoords = fullRoadCoords.concat(roadCoords);
                        }}
                        successCount++;
                    }}
                }});

                if (successCount > 0 && fullRoadCoords.length > 0) {{
                    document.getElementById('total-distance').textContent = (totalDistanceMeters / 1000).toFixed(1) + " km";
                    L.polyline(fullRoadCoords, {{
                        color: '#2563eb',
                        weight: 6,
                        opacity: 0.9
                    }}).addTo(map);
                }} else {{
                    fallbackStraightLine();
                }}
            }})
            .catch(err => {{
                console.warn("Erreur OSRM globale, repli sur le tracé de secours", err);
                fallbackStraightLine();
            }});
    }} else {{
        document.getElementById('total-distance').textContent = "0.0 km";
    }}

    function fallbackStraightLine() {{
        const latLngs = points.map(p => [p.lat, p.lng]);
        if (latLngs.length > 0) {{
            L.polyline(latLngs, {{ color: '#dc2626', weight: 4, dashArray: '8, 8', opacity: 0.8 }})
             .addTo(map)
             .bindPopup("Route de secours / Raccourci direct");
        }}
        document.getElementById('total-distance').textContent = "Calcul direct";
    }}

    let trackingInterval = null;
    let driverMarker = null;
    let trackingActive = false;

    function toggleTracking() {{
        const statusEl = document.getElementById('gps-status');
        if (!trackingActive) {{
            if (!navigator.geolocation) {{
                alert("La géolocalisation n'est pas supportée par votre appareil.");
                return;
            }}
            trackingActive = true;
            statusEl.textContent = "Actif (Suivi live)";
            statusEl.style.color = "var(--green)";

            updateDriverPosition();
            trackingInterval = setInterval(updateDriverPosition, 5000);
        }} else {{
            trackingActive = false;
            if (trackingInterval) clearInterval(trackingInterval);
            statusEl.textContent = "Désactivé";
            statusEl.style.color = "var(--muted)";
            if (driverMarker) map.removeLayer(driverMarker);
        }}
    }}

    function updateDriverPosition() {{
        navigator.geolocation.getCurrentPosition(
            (position) => {{
                const lat = position.coords.latitude;
                const lng = position.coords.longitude;
                
                if (!driverMarker) {{
                    driverMarker = L.marker([lat, lng], {{
                        icon: L.icon({{
                            iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
                            iconSize: [25, 41],
                            iconAnchor: [12, 41]
                        }})
                    }}).addTo(map).bindPopup("<b>Vous êtes ici (Position en direct)</b>");
                }} else {{
                    driverMarker.setLatLng([lat, lng]);
                }}
                map.setView([lat, lng], 16);
            }},
            (error) => {{
                document.getElementById('gps-status').textContent = "Erreur GPS";
                console.warn("Erreur de géolocalisation: " + error.message);
            }},
            {{ enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }}
        );
    }}
    </script>
    """
    return page(body, title="Tournée Livreur", map_needed=True)


@app.route("/driver-print")
def driver_print():
    code = request.args.get("code")
    route = DeliveryRoute.query.filter_by(access_code=code).first() if code else None
    if not route:
        return "Code d'accès invalide ou introuvable.", 404

    stops = json.loads(route.stops_data or "[]")
    rows = ""
    for i, p in enumerate(stops, 1):
        rows += f"""
        <tr>
            <td style="text-align:center; font-weight:bold;">{i}</td>
            <td><strong>{p.get('name')}</strong><br><span style="color:#555;">{p.get('address')}</span></td>
            <td style="text-align:center; width:60px;">[ &nbsp; ]</td>
        </tr>
        """

    html = f"""
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <title>Fiche de Route - {route.route_name}</title>
        <style>
            body {{ font-family: Arial, sans-serif; color: #000; margin: 20px; }}
            h2, p {{ margin: 5px 0; }}
            .header {{ border-bottom: 2px solid #000; padding-bottom: 10px; margin-bottom: 20px; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 15px; }}
            th, td {{ border: 1px solid #000; padding: 10px; text-align: left; font-size: 14px; }}
            th {{ background-color: #eee; }}
            @media print {{
                .no-print {{ display: none; }}
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h2>FICHE DE ROUTE (Raccourci Optimal) : {route.route_name}</h2>
            <p><strong>Entreprise :</strong> {route.company.company_name} | <strong>Livreur :</strong> {route.driver_name}</p>
            <p><strong>Date d'impression :</strong> {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} (UTC)</p>
        </div>
        <button class="no-print" onclick="window.print()" style="padding: 10px 20px; font-size: 16px; cursor: pointer; margin-bottom: 15px; background: #2563eb; color: #fff; border: none; border-radius: 5px;">Imprimer</button>
        <table>
            <thead>
                <tr>
                    <th style="width: 40px; text-align:center;">#</th>
                    <th>Client & Adresse (Ordre Optimal)</th>
                    <th style="text-align:center;">Statut</th>
                </tr>
            </thead>
            <tbody>
                {rows or '<tr><td colspan="3">Aucune étape trouvée.</td></tr>'}
            </tbody>
        </table>
        <script>
            window.onload = function() {{ window.print(); }};
        </script>
    </body>
    </html>
    """
    return html


@app.route("/admin-panel", methods=["GET", "POST"])
def admin_panel():
    if request.method == "POST":
        if request.form.get("password") == ADMIN_SECRET_PASSWORD:
            session["is_admin"] = True
        else:
            flash("Mot de passe admin incorrect.", "danger")

    if not session.get("is_admin"):
        body = """
        <div class="card">
            <h2>Administration Globale</h2>
            <form method="POST">
                <label>Mot de passe Admin</label><input type="password" name="password" required>
                <button class="btn btn-block" type="submit" style="margin-top:15px;">Entrer</button>
            </form>
        </div>
        """
        return page(body, title="Admin")

    users = User.query.all()
    user_options = "".join([f'<option value="{u.id}">{u.company_name} ({u.email})</option>' for u in users])
    user_rows = "".join([f"<tr><td>{u.company_name}</td><td>{u.email}</td><td>{u.plan}</td><td>{u.tours_used}/{u.tour_limit}</td></tr>" for u in users])

    body = f"""
    <div class="card">
        <h2>Panel Administrateur</h2>
        <a class="btn btn-red" href="/admin-logout">Quitter l'admin</a>
    </div>

    <div class="card">
        <h3>🔑 Générer une clé API pour une entreprise</h3>
        <form method="POST" action="/admin/generate-key">
            <label>Sélectionner l'entreprise</label>
            <select name="user_id" required>{user_options}</select>
            <button class="btn btn-green" type="submit" style="margin-top:15px;">Générer et assigner la clé API</button>
        </form>
    </div>

    <div class="card">
        <h3>Liste des Entreprises</h3>
        <div class="table-responsive">
            <table><thead><tr><th>Entreprise</th><th>Email</th><th>Plan</th><th>Tournées</th></tr></thead><tbody>{user_rows}</tbody></table>
        </div>
    </div>
    """
    return page(body, title="Admin Panel")


@app.route("/admin/generate-key", methods=["POST"])
def admin_generate_key():
    if not session.get("is_admin"):
        return redirect(url_for("admin_panel"))

    user_id = request.form.get("user_id")
    user = User.query.get(user_id)
    if not user:
        flash("Entreprise introuvable.", "danger")
        return redirect(url_for("admin_panel"))

    expiry = user.subscription_expires_at if user.subscription_expires_at and user.subscription_expires_at > utcnow() else utcnow() + timedelta(days=30)
    create_api_key(user, expiry)
    db.session.commit()

    flash(f"Nouvelle clé API générée avec succès pour {user.company_name}.", "success")
    return redirect(url_for("admin_panel"))


@app.route("/admin-logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("index"))


@app.route("/api/v1/route", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def api_v1_route():
    if request.method == "GET":
        return jsonify({
            "service": "GlobalRoute AI API",
            "usage": "Envoyez une requête POST avec le header X-API-KEY et un payload JSON contenant 'points'."
        }), 200

    key_val = request.headers.get("X-API-KEY")
    
    user = None
    if "user_id" in session:
        user = User.query.get(session["user_id"])
    
    if not user:
        key = ApiKey.query.filter_by(key_string=key_val, revoked=False).first()
        if not key or (key.expires_at and key.expires_at < utcnow()):
            return jsonify({"error": "invalid_api_key"}), 401
        user = User.query.get(key.user_id)

    if user.subscription_expires_at and user.subscription_expires_at < utcnow():
        return jsonify({"error": "subscription_expired"}, 402)

    if user.tours_used >= user.tour_limit:
        return jsonify({"error": "quota_exceeded"}, 402)

    payload = request.get_json(silent=True) or {}
    points = payload.get("points", [])
    if not isinstance(points, list) or len(points) < 2:
        return jsonify({"error": "at_least_2_points_required"}, 400)

    optimized = optimize_stops_order(points)
    user.tours_used += 1
    db.session.commit()

    return jsonify({"success": True, "optimized_points": optimized, "tours_used": user.tours_used})


@app.route("/health")
def health():
    return jsonify({"status": "healthy", "service": APP_NAME, "blockchain": "Solana Mainnet", "engine": "Optimal Shortcut Engine"})


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
