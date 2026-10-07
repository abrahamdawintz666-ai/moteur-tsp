import os
import io
import json
import secrets
import hashlib
import hmac
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from flask import Flask, render_template_string, request, redirect, url_for, session, jsonify, make_response, flash
from flask_sqlalchemy import SQLAlchemy
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

APP_NAME = "AntStrike Logistics — GlobalRoute AI"
ADMIN_SECRET_PASSWORD = os.getenv("ADMIN_PASSWORD", "antstrike2026admin")
SOLANA_RECEIVING_WALLET = os.getenv("SOLANA_WALLET", "22BzBEYLewJkKe2FXD6EHJYqX4NNshMw9roNw9qFxV9d")
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", secrets.token_hex(32))
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///antstrike_logistics.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
limiter = Limiter(get_remote_address, app=app, default_limits=["200 per day", "50 per minute"])

# --- MODÈL BAZ DONE ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    address = db.Column(db.String(200))
    city = db.Column(db.String(100))
    country = db.Column(db.String(100))
    tax_id = db.Column(db.String(50))
    role = db.Column(db.String(20), default="dispatcher")
    plan = db.Column(db.String(20), default="free")
    tour_limit = db.Column(db.Integer, default=5)
    tours_used = db.Column(db.Integer, default=0)
    subscription_expires_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    routes = db.relationship("DeliveryRoute", backref="company", lazy=True)
    payments = db.relationship("PaymentOrder", backref="company", lazy=True)

class ApiKey(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    key_string = db.Column(db.String(64), unique=True, nullable=False)
    expires_at = db.Column(db.DateTime)
    revoked = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class PaymentOrder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_code = db.Column(db.String(30), unique=True, nullable=False)
    reference = db.Column(db.String(64), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    plan = db.Column(db.String(20), nullable=False)
    duration_days = db.Column(db.Integer, default=30)
    amount_usdc = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default="pending")
    transaction_signature = db.Column(db.String(128))
    paid_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class DeliveryRoute(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    route_name = db.Column(db.String(120), nullable=False)
    driver_name = db.Column(db.String(120), nullable=False)
    access_code = db.Column(db.String(50), nullable=False)
    stops_data = db.Column(db.Text, nullable=False)
    optimized = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(200), nullable=False)
    details = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

def utcnow():
    return datetime.utcnow()

TRANSLATIONS = {
    "fr": {
        "home_title": "Optimisation Logistique B2B & Raccourcis Intelligents",
        "dashboard": "Tableau de Bord",
        "import": "Importer / Tournées",
        "plans": "Abonnements",
        "login": "Connexion",
        "register": "Inscription",
        "logout": "Déconnexion",
        "admin": "Admin",
        "driver_space": "Espace Livreur"
    },
    "en": {
        "home_title": "B2B Logistics Optimization & Smart Shortcuts",
        "dashboard": "Dashboard",
        "import": "Import / Routes",
        "plans": "Plans",
        "login": "Login",
        "register": "Register",
        "logout": "Logout",
        "admin": "Admin",
        "driver_space": "Driver Space"
    },
    "es": {
        "home_title": "Optimización Logística B2B y Atajos Inteligentes",
        "dashboard": "Panel",
        "import": "Importar / Rutas",
        "plans": "Planes",
        "login": "Iniciar Sesión",
        "register": "Registrarse",
        "logout": "Cerrar Sesión",
        "admin": "Admin",
        "driver_space": "Espacio Conductor"
    }
}

def t(key):
    lang = session.get("lang", "fr")
    return TRANSLATIONS.get(lang, TRANSLATIONS["fr"]).get(key, key)

def parse_coordinate(val):
    try:
        val_str = str(val).strip().replace(',', '.')
        return float(val_str)
    except Exception:
        return None

def calculate_distance(lat1, lon1, lat2, lon2):
    import math
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.asin(math.sqrt(a))
    return R * c

def nearest_neighbor_guided(points):
    if not points:
        return []
    unvisited = list(points)
    current = unvisited.pop(0)
    ordered = [current]
    while unvisited:
        next_point = min(unvisited, key=lambda p: calculate_distance(current['lat'], current['lng'], p['lat'], p['lng']))
        unvisited.remove(next_point)
        ordered.append(next_point)
        current = next_point
    return ordered

def local_two_opt_pass(route):
    best = list(route)
    improved = True
    while improved:
        improved = False
        for i in range(1, len(best) - 2):
            for j in range(i + 1, len(best)):
                if j - i == 1:
                    continue
                new_route = best[:i] + best[i:j][::-1] + best[j:]
                old_dist = sum(calculate_distance(best[k]['lat'], best[k]['lng'], best[k+1]['lat'], best[k+1]['lng']) for k in range(len(best)-1))
                new_dist = sum(calculate_distance(new_route[k]['lat'], new_route[k]['lng'], new_route[k+1]['lat'], new_route[k+1]['lng']) for k in range(len(new_route)-1))
                if new_dist < old_dist:
                    best = new_route
                    improved = True
        break
    return best

def optimize_stops_order(points):
    if len(points) <= 3:
        return points
    nn = nearest_neighbor_guided(points)
    optimized = local_two_opt_pass(nn)
    return optimized

def calculate_price(plan, duration_days):
    base_monthly = 99.0 if plan == "standard" else 300.0 if plan == "pro" else 0.0
    amount = (base_monthly / 30.0) * duration_days
    if duration_days >= 90:
        amount *= 0.9
    return round(amount, 2)

def generate_reference():
    return secrets.token_hex(16)

def verify_usdc_payment(order):
    try:
        url = "https://public-api.solscan.io/chaininfo"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status != 200:
                return False, None, "Solscan indisponib kounye a."
    except Exception:
        pass
    
    if os.getenv("FLASK_ENV") == "development" or order.amount_usdc == 0:
        return True, "DEV_MOCK_SIGNATURE_" + secrets.token_hex(8), "Siksè (Mock)"
        
    return False, None, "Tèk ap tann konfimasyon sou rezo Solana a..."

def activate_paid_order(order, signature):
    order.status = "paid"
    order.transaction_signature = signature
    order.paid_at = utcnow()
    user = User.query.get(order.user_id)
    user.plan = order.plan
    if order.plan == "standard":
        user.tour_limit = 500
    elif order.plan == "pro":
        user.tour_limit = 2500
    user.tours_used = 0
    base_time = user.subscription_expires_at if user.subscription_expires_at and user.subscription_expires_at > utcnow() else utcnow()
    user.subscription_expires_at = base_time + timedelta(days=order.duration_days)
    db.session.commit()

def active_api_key(user):
    key = ApiKey.query.filter_by(user_id=user.id, revoked=False).first()
    if not key:
        key = ApiKey(user_id=user.id, key_string=secrets.token_hex(32), expires_at=utcnow() + timedelta(days=365))
        db.session.add(key)
        db.session.commit()
    return key

def create_api_key(user, expiry):
    key = ApiKey(user_id=user.id, key_string=secrets.token_hex(32), expires_at=expiry)
    db.session.add(key)
    return key

# --- ESTIL AK UI ---
BASE_STYLE = """
:root {
  --navy:#0f172a; --blue:#2563eb; --blue2:#1d4ed8; --green:#059669; --red:#dc2626;
  --bg:#f8fafc; --card:#ffffff; --text:#0f172a; --muted:#64748b; --border:#e2e8f0;
}
* { box-sizing:border-box; }
html, body { margin:0; padding:0; background:var(--bg); color:var(--text); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; overflow-x: hidden; }
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

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{ title or APP_NAME }}</title>
{% if map_needed %}
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
{% endif %}
<style>{{ style|safe }}</style>
</head>
<body>
<header>
  <button class="menu-toggle" onclick="toggleMenu()">☰</button>
  <h1>{{ APP_NAME }}</h1>
  <select class="lang-selector" onchange="location.href='/set-lang/'+this.value">
    <option value="fr" {% if session.get('lang','fr')=='fr' %}selected{% endif %}>Français</option>
    <option value="en" {% if session.get('lang')=='en' %}selected{% endif %}>English</option>
    <option value="es" {% if session.get('lang')=='es' %}selected{% endif %}>Español</option>
  </select>
</header>
<nav id="global-menu">
  <a href="{{ url_for('index') }}">⌂ &nbsp; Accueil</a>
  {% if session.get("user_id") %}
  <a href="{{ url_for('dashboard') }}">▣ &nbsp; {{ t('dashboard') }}</a>
  <a href="{{ url_for('import_space') }}">⇧ &nbsp; {{ t('import') }}</a>
  <a href="{{ url_for('plans') }}">◈ &nbsp; {{ t('plans') }}</a>
  <a href="{{ url_for('logout') }}">⏻ &nbsp; {{ t('logout') }}</a>
  {% else %}
  <a href="{{ url_for('login_form') }}">↪ &nbsp; {{ t('login') }}</a>
  <a href="{{ url_for('register_form') }}">＋ &nbsp; {{ t('register') }}</a>
  {% endif %}
  <a href="{{ url_for('admin_panel') }}">⚙ &nbsp; {{ t('admin') }}</a>
  <a href="{{ url_for('driver_login') }}">🚚 &nbsp; {{ t('driver_space') }}</a>
</nav>
<script>
function toggleMenu() { document.getElementById("global-menu").classList.toggle("open"); }
</script>
<div class="container">
  {% with messages = get_flashed_messages(with_categories=true) %}
    {% for cat, msg in messages %}
      <div class="alert alert-{{ cat }}">{{ msg }}</div>
    {% endfor %}
  {% endwith %}
  {{ body|safe }}
</div>
<footer style="text-align:center; padding:20px; color:var(--muted); font-size:12px; border-top: 1px solid var(--border); margin-top: 30px;">
  <p>© 2026 AntStrike Logistics — GlobalRoute AI. Tout dwa rezève.</p>
  <p style="margin-top: 5px;">
    📞 WhatsApp: <a href="https://wa.me/50941817761" target="_blank" style="color: var(--blue); text-decoration: none;">+509 41 81 7761</a> | 
    ✉️ Imèl: <a href="mailto:abrahamdawintz410@gmail.com" style="color: var(--blue); text-decoration: none;">abrahamdawintz410@gmail.com</a>
  </p>
</footer>
</body>
</html>
"""

def page(body, title=APP_NAME, map_needed=False):
    return render_template_string(HTML_TEMPLATE, body=body, title=title, style=BASE_STYLE, APP_NAME=APP_NAME, map_needed=map_needed, session=session, t=t)

@app.route("/set-lang/<lang>")
def set_lang(lang):
    if lang in TRANSLATIONS:
        session["lang"] = lang
    return redirect(request.referrer or url_for("index"))

@app.route("/")
def index():
    body = f"""
    <div class="hero card">
      <h2>{t('home_title')}</h2>
      <p class="muted">AntStrike Logistics & GlobalRoute AI fournissent l'itinéraire le plus court, le plus rapide et le plus sûr pour maximiser la performance de vos tournées de livraison.</p>
      <div style="display:flex; gap:10px; justify-content:center; margin-top:20px;">
        <a href="{url_for('register_form')}" class="btn">Créer un compte entreprise</a>
        <a href="{url_for('login_form')}" class="btn btn-secondary">Connexion</a>
      </div>
    </div>
    <div class="grid">
      <div class="card stat"><strong>Réseau</strong> Paiement USDC / Solana<br><span class="muted">Instant & Zéro frais</span></div>
      <div class="card stat"><strong>Moteur Raccourci</strong> Hybride Avancé<br><span class="muted">Optimisation maximale</span></div>
      <div class="card stat">
        <strong>Besoin d'aide ?</strong> AntStrike Support<br>
        <span class="muted">
          <a href="https://wa.me/50941817761" target="_blank" style="color:var(--blue); text-decoration:none;">💬 WhatsApp (+509 41 81 7761)</a>
        </span>
      </div>
    </div>
    """
    return page(body)

@app.route("/register-form")
def register_form():
    body = f"""
    <div class="card" style="max-width:500px; margin:0 auto;">
      <h2>Créer un compte entreprise B2B</h2>
      <form method="POST" action="{url_for('register')}">
        <label>Nom de l'entreprise</label>
        <input type="text" name="company_name" required>
        <label>E-mail professionnel</label>
        <input type="email" name="email" required>
        <label>Mot de passe (8 caractères min.)</label>
        <input type="password" name="password" required minlength="8">
        <label>Adresse</label>
        <input type="text" name="address">
        <label>Ville</label>
        <input type="text" name="city">
        <label>Pays</label>
        <input type="text" name="country">
        <label>Numéro de TVA / Tax ID (Optionnel)</label>
        <input type="text" name="tax_id">
        <button type="submit" class="btn btn-block" style="margin-top:20px;">S'inscrire</button>
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
    body = f"""
    <div class="card" style="max-width:400px; margin:0 auto;">
      <h2>Connexion Entreprise</h2>
      <form method="POST" action="{url_for('login')}">
        <label>E-mail</label>
        <input type="email" name="email" required>
        <label>Mot de passe</label>
        <input type="password" name="password" required>
        <button type="submit" class="btn btn-block" style="margin-top:20px;">Connexion</button>
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
        opt_badge = '<span style="color:var(--green)">⚡ Raccourci optimal</span>' if r.optimized else 'Standard'
        route_rows += f"""
        <tr>
          <td>{r.route_name}</td>
          <td>{r.driver_name}</td>
          <td>{c} étapes</td>
          <td>{opt_badge}</td>
          <td><a href="{url_for('driver_space', code=r.access_code)}" class="btn" style="padding:6px 12px; font-size:12px;">Ouvrir</a></td>
        </tr>
        """
        
    payments = PaymentOrder.query.filter_by(user_id=user.id).order_by(PaymentOrder.created_at.desc()).all()
    payment_rows = ""
    for p in payments:
        pdf_btn = f'<a href="{url_for("download_invoice", order_id=p.id)}" class="btn btn-secondary" style="padding:4px 8px; font-size:11px;">📄 PDF</a>' if p.status == "paid" else ""
        payment_rows += f"""
        <tr>
          <td class="mono">{p.order_code}</td>
          <td>{p.plan.title()}</td>
          <td>{p.amount_usdc} USDC</td>
          <td>{p.status}</td>
          <td>{pdf_btn}</td>
        </tr>
        """

    body = f"""
    <div class="card">
      <h2>{user.company_name}</h2>
      <p class="muted">Email : {user.email} | TVA : {user.tax_id or 'Non renseigné'}</p>
      <div class="grid" style="margin-top:20px;">
        <div class="stat"><strong>Abonnement</strong>{user.plan.title()}</div>
        <div class="stat"><strong>Tournées utilisées</strong>{user.tours_used} / {user.tour_limit}</div>
        <div class="stat"><strong>Restantes</strong>{remaining} (Expiration : {expiry})</div>
      </div>
    </div>

    <div class="card">
      <h3>🚀 Gestion des tournées</h3>
      <p class="muted">Importez votre fichier pour calculer instantanément la route la plus courte, rapide et sûre.</p>
      <a href="{url_for('import_space')}" class="btn">Importer / Créer une tournée</a>
    </div>

    <div class="card">
      <h3>📋 Historique des tournées</h3>
      <div class="table-responsive">
        <table>
          <thead>
            <tr><th>Tournée</th><th>Livreur</th><th>Étapes</th><th>Optimisation</th><th>Action</th></tr>
          </thead>
          <tbody>
            {route_rows or '<tr><td colspan="5" class="muted">Aucune tournée.</td></tr>'}
          </tbody>
        </table>
      </div>
    </div>

    <div class="card">
      <h3>💳 Factures & Paiements</h3>
      <div class="table-responsive">
        <table>
          <thead>
            <tr><th>Commande</th><th>Plan</th><th>Montant</th><th>Statut</th><th>Facture</th></tr>
          </thead>
          <tbody>
            {payment_rows or '<tr><td colspan="5" class="muted">Aucun paiement.</td></tr>'}
          </tbody>
        </table>
      </div>
    </div>

    <div class="card">
      <h3>🔑 Clé API B2B & Accès JSON</h3>
      <p class="muted">Utilisez cet endpoint pour intégrer les calculs directement via JSON : <code>POST /api/v1/route</code> avec le header <code>X-API-KEY: [Votre Clé]</code></p>
      <input type="text" readonly value="{key_text}" class="mono" onclick="this.select()">
    </div>
    """
    return page(body, title="Dashboard B2B")

@app.route("/import-space")
def import_space():
    if not session.get("user_id"):
        return redirect(url_for("login_form"))
    return render_template_string(IMPORT_FORM_HTML, style=BASE_STYLE, APP_NAME=APP_NAME, session=session)

IMPORT_FORM_HTML = """<!DOCTYPE html>
<html lang="fr">
<head><meta charset="UTF-8"><title>Importer</title><style>{{ style|safe }}</style></head>
<body>
<div class="container" style="max-width:700px; margin-top:30px;">
  <div class="card">
    <h2>Trouver le raccourci optimal</h2>
    <p class="muted">Sélectionnez un fichier ou remplissez la saisie manuelle ci-dessous.</p>
    <form method="POST" action="/create-driver-route">
      <label>Nom de la tournée</label>
      <input type="text" name="route_name" required value="Tournée Principale">
      
      <label>Nom du livreur</label>
      <input type="text" name="driver_name" required placeholder="Ex: Jean Paul">
      
      <label>Code d'accès du livreur (Réutilisable)</label>
      <input type="text" name="access_code" required value="driver123">
      
      <label>Sélectionner un fichier (.csv ou .txt)</label>
      <input type="file" id="file-input" accept=".csv, .txt">
      
      <label>Ou Saisie manuelle (Nom | Adresse | Lat | Lng)</label>
      <textarea id="manual-stops" name="manual_stops" rows="8" placeholder="Client A | Rue Principale, Ville | 18.539 | -72.335\nClient B | Rue Secondaire, Ville | 18.542 | -72.338" required></textarea>
      
      <div style="display:flex; gap:10px; margin-top:20px;">
        <button type="submit" class="btn" style="flex:1;">Calculer le raccourci et créer</button>
        <a href="/dashboard" class="btn btn-secondary">Retour</a>
      </div>
    </form>
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
</body>
</html>
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
                    
    if len(stops) < 2:
        flash("Veuillez fournir au moins 2 étapes valides avec des coordonnées correctes.", "danger")
        return redirect(url_for("import_space"))
        
    optimized_stops = optimize_stops_order(stops)
    
    route = DeliveryRoute(
        user_id=user.id,
        route_name=route_name,
        driver_name=driver_name,
        access_code=access_code,
        stops_data=json.dumps(optimized_stops, ensure_ascii=False),
        optimized=True
    )
    user.tours_used += 1
    db.session.add(route)
    db.session.commit()
    flash("Tournée optimisée et créée avec succès !", "success")
    return redirect(url_for("dashboard"))

@app.route("/plans")
def plans():
    body = f"""
    <div class="hero">
      <h2>Abonnements B2B Mondiaux</h2>
      <p class="muted">Réglez instantanément en USDC sur le réseau Solana.</p>
    </div>
    <div class="plan-grid">
      <div class="plan-card">
        <h3>Standard</h3>
        <p style="font-size:24px; font-weight:bold;">99 USDC / mois</p>
        <p class="muted">500 tournées incluses / mois</p>
        <form method="POST" action="{url_for('create_payment')}">
          <input type="hidden" name="plan" value="standard">
          <label>Durée</label>
          <select name="duration_days">
            <option value="30">30 jours (99 USDC)</option>
            <option value="90">90 jours (267.30 USDC)</option>
          </select>
          <button type="submit" class="btn btn-block" style="margin-top:15px;">Sélectionner</button>
        </form>
      </div>
      <div class="plan-card featured">
        <h3>Pro</h3>
        <p style="font-size:24px; font-weight:bold;">300 USDC / mois</p>
        <p class="muted">2 500 tournées incluses + API B2B illimitée</p>
        <form method="POST" action="{url_for('create_payment')}">
          <input type="hidden" name="plan" value="pro">
          <label>Durée</label>
          <select name="duration_days">
            <option value="30">30 jours (300 USDC)</option>
            <option value="90">90 jours (810 USDC)</option>
          </select>
          <button type="submit" class="btn btn-block" style="margin-top:15px;">Sélectionner Pro</button>
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
    
    body = f"""
    <div class="card" style="max-width:500px; margin:0 auto; text-align:center;">
      <h2>Paiement de la commande {order.order_code}</h2>
      <p style="font-size:22px; font-weight:bold; color:var(--blue);">{amount} USDC</p>
      <p class="muted mono">Wallet : {SOLANA_RECEIVING_WALLET}</p>
      <p class="muted mono">Référence : {ref}</p>
      <div id="status" class="alert" style="background:#f1f5f9;">En attente de confirmation sur la blockchain...</div>
      <a href="solana:{SOLANA_RECEIVING_WALLET}?amount={amount}&spl-token={USDC_MINT}&reference={ref}&label=GlobalRouteAI" class="btn btn-green btn-block">Payer avec Phantom / Solana Wallet</a>
      <a href="{url_for('dashboard')}" class="btn btn-secondary btn-block" style="margin-top:10px;">Retour au dashboard</a>
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
    body = f"""
    <div class="card" style="max-width:400px; margin:0 auto;">
      <h2>🚚 Espace Livreur</h2>
      <form method="POST" action="{url_for('driver_space')}">
        <label>Code d'accès de la tournée</label>
        <input type="text" name="access_code" required placeholder="Ex: driver123">
        <button type="submit" class="btn btn-block" style="margin-top:20px;">Accéder au raccourci</button>
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
      <p class="muted">Livreur : {route.driver_name} | Entreprise : {route.company.company_name}</p>
      <div class="grid" style="margin-top:15px;">
        <div class="stat"><strong>Distance Route</strong><span id="total-distance">Calcul en cours...</span></div>
        <div class="stat"><strong>Nombre d'étapes</strong>{len(stops)}</div>
        <div class="stat"><strong>Statut GPS</strong><span id="gps-status" class="muted">Recherche...</span></div>
      </div>
      <div style="display:flex; gap:10px; margin-top:15px;">
        <button onclick="toggleTracking()" class="btn btn-green">📍 Activer mon suivi GPS en direct</button>
        <a href="{url_for('driver_print', code=route.access_code)}" target="_blank" class="btn btn-secondary">🖨️ Imprimer la fiche</a>
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
        L.marker([p.lat, p.lng]).addTo(map).bindPopup("<b>#" + (i+1) + " " + p.name + "</b><br>" + p.address);
        list += "<li style='margin-bottom: 8px;'><strong>#" + (i+1) + " - " + p.name + "</strong><br><span class='muted'>" + p.address + "</span> <a href='https://www.google.com/maps/dir/?api=1&destination=" + p.lat + "," + p.lng + "' target='_blank' style='margin-left: 10px; font-size: 12px;'>🧭 Naviguer (Google Maps)</a></li>";
    }});
    list += "</ol>";
    document.getElementById('stops-list').innerHTML = list;
    
    if (points.length >= 2) {{
        const maxChunk = 150;
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
                    L.polyline(fullRoadCoords, {{ color: '#2563eb', weight: 6, opacity: 0.9 }}).addTo(map);
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
            L.polyline(latLngs, {{ color: '#dc2626', weight: 4, dashArray: '8, 8', opacity: 0.8 }}).addTo(map).bindPopup("Route de secours / Raccourci direct");
        }}
        document.getElementById('total-distance').textContent = "Calcul direct";
    }}
    
    let trackingInterval = null;
    let driverMarker = null;
    let trackingActive = false;
    function toggleTracking() {{
        const statusEl = document.getElementById('gps-status');
        if (!trackingActive) {{
            if (!navigator.geolocation) {{ alert("La géolocalisation n'est pas supportée par votre appareil."); return; }}
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
                    driverMarker = L.marker([lat, lng], {{ icon: L.icon({{ iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png', iconSize: [25, 41], iconAnchor: [12, 41] }}) }}).addTo(map).bindPopup("<b>Vous êtes ici (Position en direct)</b>");
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
          <td><strong>{p.get('name')}</strong><br>{p.get('address')}</td>
          <td style="text-align:center;">[ &nbsp; ]</td>
        </tr>
        """
    html = f"""<!DOCTYPE html>
    <html lang="fr">
    <head><meta charset="UTF-8"><title>Fiche de Route - {route.route_name}</title>
    <style>
    body {{ font-family: Arial, sans-serif; color: #000; margin: 20px; }}
    h2, p {{ margin: 5px 0; }}
    .header {{ border-bottom: 2px solid #000; padding-bottom: 10px; margin-bottom: 20px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 15px; }}
    th, td {{ border: 1px solid #000; padding: 10px; text-align: left; font-size: 14px; }}
    th {{ background-color: #eee; }}
    @media print {{ .no-print {{ display: none; }} }}
    </style>
    </head>
    <body>
    <div class="header">
      <h2>FICHE DE ROUTE (Raccourci Optimal) : {route.route_name}</h2>
      <p>Entreprise : {route.company.company_name} | Livreur : {route.driver_name}</p>
      <p>Date d'impression : {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} (UTC)</p>
    </div>
    <button class="no-print" onclick="window.print()" style="padding:10px 20px; font-size:16px; margin-bottom:15px; cursor:pointer;">Imprimer</button>
    <table>
      <thead>
        <tr><th style="width:50px;">#</th><th>Client & Adresse (Ordre Optimal)</th><th style="width:80px; text-align:center;">Statut</th></tr>
      </thead>
      <tbody>
        {rows or '<tr><td colspan="3">Aucune étape trouvée.</td></tr>'}
      </tbody>
    </table>
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
        body = f"""
        <div class="card" style="max-width:400px; margin:0 auto;">
          <h2>Administration Globale</h2>
          <form method="POST">
            <label>Mot de passe Admin</label>
            <input type="password" name="password" required>
            <button type="submit" class="btn btn-block" style="margin-top:20px;">Entrer</button>
          </form>
        </div>
        """
        return page(body, title="Admin")
        
    users = User.query.all()
    user_options = "".join([f'<option value="{u.id}">{u.company_name} ({u.email})</option>' for u in users])
    user_rows = "".join([f"<tr><td>{u.company_name}</td><td>{u.email}</td><td>{u.plan}</td><td>{u.tours_used}/{u.tour_limit}</td></tr>" for u in users])
    
    body = f"""
    <div class="card">
      <div style="display:flex; justify-content:space-between; align-items:center;">
        <h2>Panel Administrateur</h2>
        <a href="{url_for('admin_logout')}" class="btn btn-red">Quitter l'admin</a>
      </div>
      <hr style="margin:20px 0; border:0; border-top:1px solid var(--border);">
      <h3>🔑 Générer une clé API pour une entreprise</h3>
      <form method="POST" action="{url_for('admin_generate_key')}">
        <label>Sélectionner l'entreprise</label>
        <select name="user_id">{user_options}</select>
        <button type="submit" class="btn" style="margin-top:15px;">Générer et assigner la clé API</button>
      </form>
    </div>

    <div class="card">
      <h3>Liste des Entreprises</h3>
      <div class="table-responsive">
        <table>
          <thead>
            <tr><th>Entreprise</th><th>Email</th><th>Plan</th><th>Tournées</th></tr>
          </thead>
          <tbody>
            {user_rows or '<tr><td colspan="4" class="muted">Aucune entreprise.</td></tr>'}
          </tbody>
        </table>
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
            "service": "AntStrike Logistics & GlobalRoute AI API",
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
        return jsonify({"error": "subscription_expired"}), 402
    if user.tours_used >= user.tour_limit:
        return jsonify({"error": "quota_exceeded"}), 402
        
    payload = request.get_json(silent=True) or {}
    points = payload.get("points", [])
    if not isinstance(points, list) or len(points) < 2:
        return jsonify({"error": "at_least_2_points_required"}), 400
    
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
