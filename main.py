import os
import secrets
from datetime import datetime
from flask import Flask, render_template_string, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

ADMIN_SECRET_PASSWORD = os.getenv("ADMIN_PASSWORD", "MonSuperMotDePasseAdmin2026!")

database_url = os.getenv("DATABASE_URL")
if database_url:
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+psycopg2://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    payment_method = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), default="actif")
    api_quota = db.Column(db.Integer, default=150)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    api_keys = db.relationship("ApiKey", backref="owner", lazy=True, cascade="all, delete-orphan")
    logs = db.relationship("UsageLog", backref="user", lazy=True, cascade="all, delete-orphan")
    deliveries = db.relationship("DeliveryRoute", backref="company", lazy=True, cascade="all, delete-orphan")

class ApiKey(db.Model):
    __tablename__ = "api_keys"
    id = db.Column(db.Integer, primary_key=True)
    key_string = db.Column(db.String(255), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

class UsageLog(db.Model):
    __tablename__ = "usage_logs"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    endpoint = db.Column(db.String(100), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class DeliveryRoute(db.Model):
    __tablename__ = "delivery_routes"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    driver_name = db.Column(db.String(100), nullable=False)
    access_code = db.Column(db.String(50), unique=True, nullable=False)
    stops_summary = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default="En cours")

with app.app_context():
    try:
        db.create_all()
    except Exception:
        pass

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>GlobalRoute AI - Enterprise Logistics SaaS & Map</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        :root { --primary: #0f172a; --accent: #2563eb; --bg: #f8fafc; --card: #ffffff; --text: #334155; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: var(--bg); color: var(--text); margin: 0; padding: 0; }
        header { background: var(--primary); color: white; padding: 16px 20px; display: flex; justify-content: space-between; align-items: center; }
        header h1 { margin: 0; font-size: 17px; font-weight: 700; letter-spacing: -0.5px; }
        .container { padding: 20px; box-sizing: border-box; max-width: 850px; margin: 0 auto; }
        .hero { background: white; padding: 30px 20px; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.03); text-align: center; margin-bottom: 20px; }
        .hero h2 { color: var(--primary); font-size: 22px; margin-top: 0; }
        .hero p { font-size: 13px; color: #64748b; line-height: 1.5; margin-bottom: 20px; }
        .btn-group { display: flex; flex-direction: column; gap: 10px; }
        .btn { display: block; width: 100%; padding: 14px; border-radius: 8px; font-size: 14px; font-weight: 600; text-align: center; text-decoration: none; box-sizing: border-box; cursor: pointer; border: none; }
        .btn-primary { background: var(--accent); color: white; }
        .btn-secondary { background: #f1f5f9; color: var(--primary); border: 1px solid #cbd5e1; }
        .card { background: white; padding: 20px; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.03); margin-bottom: 20px; }
        label { display: block; font-weight: 600; font-size: 12px; margin-bottom: 6px; color: #475569; text-align: left; }
        input, select, textarea { width: 100%; padding: 12px; border: 1px solid #cbd5e1; border-radius: 8px; box-sizing: border-box; font-size: 14px; margin-bottom: 15px; background: #fff; }
        .alert { padding: 12px; border-radius: 8px; margin-bottom: 20px; font-size: 13px; font-weight: 500; }
        .alert-success { background: #dcfce7; color: #166534; }
        .alert-danger { background: #fee2e2; color: #991b1b; }
        .api-box { background: #0f172a; color: #e2e8f0; padding: 12px; border-radius: 6px; font-family: monospace; font-size: 11px; overflow-x: auto; text-align: left; margin-top: 10px; }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 12px; }
        th, td { padding: 10px 8px; text-align: left; border-bottom: 1px solid #e2e8f0; }
        th { background: #f1f5f9; color: #475569; }
        .badge { padding: 3px 6px; border-radius: 4px; font-size: 10px; font-weight: bold; background: #dcfce7; color: #166534; }
        #map { width: 100%; height: 300px; border-radius: 8px; margin-top: 15px; margin-bottom: 15px; z-index: 1; }
        footer { text-align: center; font-size: 11px; color: #94a3b8; margin: 30px 0 20px 0; }
        footer a { color: #64748b; text-decoration: none; margin: 0 10px; }
    </style>
</head>
<body>
    <header>
        <h1>GlobalRoute AI</h1>
        <div style="display: flex; gap: 12px; align-items:center;">
            <a href="/" style="color: #cbd5e1; font-size: 12px; text-decoration: none;">Accueil</a>
            <a href="/driver-login" style="color: #6ee7b7; font-size: 12px; text-decoration: none;">🚚 Livreurs</a>
            <a href="/admin-panel" style="color: #93c5fd; font-size: 12px; text-decoration: none;">Admin</a>
        </div>
    </header>

    <div class="container">
        {% with messages = get_flashed_messages(with_categories=true) %}
          {% if messages %}
            {% for category, message in messages %}
              <div class="alert alert-{{ category }}">{{ message }}</div>
            {% endfor %}
          {% endif %}
        {% endwith %}

        {% if page == 'home' %}
            <div class="hero">
                <h2>Optimisation Logistique & Géolocalisation Précise</h2>
                <p>Gérez vos tournées avec des adresses exactes et des coordonnées GPS pour éliminer toute confusion sur le terrain.</p>
                <div class="btn-group">
                    <a href="/register-form" class="btn btn-primary">Créer un Compte Entreprise</a>
                    <a href="/login-form" class="btn btn-secondary">Connexion Entreprise</a>
                    <a href="/driver-login" class="btn btn-secondary" style="background:#ecfdf5; color:#065f46; border-color:#a7f3d0;">Accès Livreur Terrain</a>
                </div>
            </div>

        {% elif page == 'register' %}
            <div class="card">
                <h2 style="font-size: 16px; margin-top:0; color:var(--primary);">Inscription Entreprise</h2>
                <form method="POST" action="/register">
                    <label>Nom de l'entreprise :</label>
                    <input type="text" name="company_name" placeholder="Ex: Transit Global SA" required>
                    <label>E-mail professionnel :</label>
                    <input type="email" name="email" placeholder="admin@entreprise.com" required>
                    <label>Mot de passe :</label>
                    <input type="password" name="password" placeholder="••••••••" required>
                    <label>Mode de Règlement :</label>
                    <select name="payment_method" required>
                        <option value="crypto_usdc">Crypto USDC / USDT</option>
                        <option value="bank_transfer">Virement Bancaire International</option>
                    </select>
                    <button type="submit" class="btn btn-primary">Valider</button>
                </form>
            </div>

        {% elif page == 'login' %}
            <div class="card">
                <h2 style="font-size: 16px; margin-top:0; color:var(--primary);">Connexion Entreprise</h2>
                <form method="POST" action="/login">
                    <label>E-mail :</label>
                    <input type="email" name="email" required>
                    <label>Mot de passe :</label>
                    <input type="password" name="password" required>
                    <button type="submit" class="btn btn-primary">Se Connecter</button>
                </form>
            </div>

        {% elif page == 'dashboard' and user %}
            <div class="card" style="text-align: left;">
                <h2 style="font-size: 16px; margin-top:0; color:var(--primary);">Tableau de Bord : {{ user.company_name }}</h2>
                <label>Clé API :</label>
                <div class="api-box">{{ user.api_keys[0].key_string if user.api_keys else 'N/A' }}</div>

                <h3 style="font-size: 14px; margin-top: 25px; color:var(--primary);">🚚 Assigner une tournée avec Adresses Précises</h3>
                <form method="POST" action="/create-driver-route">
                    <label>Nom du Livreur :</label>
                    <input type="text" name="driver_name" placeholder="Ex: Jean Dupont" required>

                    <label>Code d'accès secret :</label>
                    <input type="text" name="access_code" placeholder="Ex: LIVREUR01" required>

                    <label>Feuille de route (Inclure Nom précis + Ville/Quartier) :</label>
                    <textarea name="stops_summary" rows="4" placeholder="Étape 0: Entrepôt Central, Boulevard J. Danton&#10;Étape 1: Église Évangélique d'Haïti, Rue 9, Cap-Haïtien&#10;Étape 2: Pharmacie Centrale, Avenue 4" required></textarea>

                    <button type="submit" class="btn btn-primary" style="background:#059669;">Créer la Tournée Sécurisée</button>
                </form>

                <div style="margin-top: 25px;">
                    <a href="/logout" class="btn btn-secondary" style="background:#fee2e2; color:#991b1b; border:none;">Se Déconnecter</a>
                </div>
            </div>

        {% elif page == 'driver_login' %}
            <div class="card" style="text-align: left; border: 2px solid #059669;">
                <h2 style="font-size: 16px; margin-top:0; color:#059669;">🚚 Espace Livreur Terrain</h2>
                <form method="POST" action="/driver-space">
                    <label>Code d'accès Livreur :</label>
                    <input type="text" name="access_code" placeholder="Ex: LIVREUR01" required style="text-transform: uppercase;">
                    <button type="submit" class="btn btn-primary" style="background:#059669;">Afficher ma Feuille de Route & Carte</button>
                </form>
            </div>

        {% elif page == 'driver_space' and route %}
            <div class="card" style="text-align: left;">
                <h2 style="font-size: 16px; margin-top:0; color:var(--primary);">🚚 Feuille de Route & Guidage GPS</h2>
                <p style="font-size: 12px; color: #64748b;">Chauffeur : <strong>{{ route.driver_name }}</strong></p>
                <hr style="border:0; border-top:1px solid #e2e8f0; margin: 15px 0;">

                <label>🗺️ Carte interactive avec repères géolocalisés précis :</label>
                <div id="map"></div>

                <div style="background: #ecfdf5; padding: 15px; border-radius: 8px; margin-top: 15px; border-left: 4px solid #059669;">
                    <span class="badge" style="background: #059669; color: white;">Instructions Détaillées (anti-confusion)</span>
                    <p style="font-size: 13px; color: #1e293b; white-space: pre-line; line-height: 1.6; margin-top: 10px;">{{ route.stops_summary }}</p>
                    
                    <a href="https://maps.google.com/?q=destination" target="_blank" class="btn btn-primary" style="margin-top: 15px; font-size: 13px; padding: 12px; background:#2563eb;">🧭 Lancer la Navigation GPS Directe</a>
                </div>

                <div style="margin-top: 20px;">
                    <a href="/driver-login" class="btn btn-secondary">Quitter l'espace livreur</a>
                </div>
            </div>

            <script>
                // Coordonnées précises par défaut (ex: Cap-Haïtien / repères cibles)
                var map = L.map('map').setView([19.7558, -72.2042], 14);

                L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                    maxZoom: 19,
                    attribution: '© OpenStreetMap'
                }).addTo(map);

                // Points précis avec libellés uniques pour éviter les confusions de noms similaires
                var hub = [19.7558, -72.2042];
                var eglisePrecise = [19.7610, -72.2080]; // Emplacement exact de l'église ciblée avec rue/quartier
                var stopClient = [19.7490, -72.1950];

                L.marker(hub).addTo(map).bindPopup("<b>Hub / Départ</b>").openPopup();
                L.marker(eglisePrecise).addTo(map).bindPopup("<b>Étape : Église Évangélique (Rue 9 / Précis)</b>");
                L.marker(stopClient).addTo(map).bindPopup("<b>Étape Finale : Livraison Client</b>");

                var routeCoords = [hub, eglisePrecise, stopClient];
                var polyline = L.polyline(routeCoords, {color: '#2563eb', weight: 4, dashArray: '5, 8'}).addTo(map);
                map.fitBounds(polyline.getBounds(), {padding: [40, 40]});
            </script>

        {% elif page == 'admin_login' %}
            <div class="card" style="text-align: left; border: 2px solid var(--primary);">
                <h2 style="font-size: 16px; margin-top:0; color:var(--primary);">🔐 Connexion Administrateur</h2>
                <form method="POST" action="/admin-panel">
                    <label>Mot de passe Admin :</label>
                    <input type="password" name="admin_password" required>
                    <button type="submit" class="btn btn-primary">Entrer</button>
                </form>
            </div>

        {% elif page == 'admin' %}
            <div class="card" style="text-align: left;">
                <h2 style="font-size: 16px; margin-top:0; color:var(--primary);">🛡️ Panneau Administrateur</h2>
                <a href="/admin-logout" class="btn btn-secondary" style="background:#fee2e2; color:#991b1b; border:none; margin-bottom:15px;">Verrouiller</a>
                <table>
                    <thead>
                        <tr><th>Entreprise</th><th>Clé API</th><th>Requêtes</th></tr>
                    </thead>
                    <tbody>
                        {% for u in users %}
                        <tr>
                            <td><strong>{{ u.company_name }}</strong></td>
                            <td><code>{{ u.api_keys[0].key_string if u.api_keys else 'N/A' }}</code></td>
                            <td>{{ u.logs|length }}/{{ u.api_quota }}</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        {% endif %}
        <footer>
            <p>&copy; 2026 GlobalRoute AI. Tous droits réservés.</p>
        </footer>
    </div>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE, page="home")

@app.route("/register-form")
def register_form():
    return render_template_string(HTML_TEMPLATE, page="register")

@app.route("/login-form")
def login_form():
    return render_template_string(HTML_TEMPLATE, page="login")

@app.route("/driver-login")
def driver_login():
    return render_template_string(HTML_TEMPLATE, page="driver_login")

@app.route("/driver-space", methods=["POST", "GET"])
def driver_space():
    code = request.form.get("access_code") if request.method == "POST" else request.args.get("code")
    if not code:
        flash("Entrez votre code d'accès livreur.", "danger")
        return redirect(url_for("driver_login"))
    route = DeliveryRoute.query.filter_by(access_code=code.strip().upper()).first()
    if not route:
        flash("Code d'accès incorrect.", "danger")
        return redirect(url_for("driver_login"))
    return render_template_string(HTML_TEMPLATE, page="driver_space", route=route)

@app.route("/create-driver-route", methods=["POST"])
def create_driver_route():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login_form"))
    driver_name = request.form.get("driver_name")
    access_code = request.form.get("access_code").strip().upper()
    stops_summary = request.form.get("stops_summary")
    
    new_route = DeliveryRoute(user_id=user_id, driver_name=driver_name, access_code=access_code, stops_summary=stops_summary)
    db.session.add(new_route)
    db.session.commit()
    flash("Tournée créée avec succès avec les adresses détaillées !", "success")
    return redirect(url_for("dashboard"))

@app.route("/admin-panel", methods=["GET", "POST"])
def admin_panel():
    if not session.get("is_admin"):
        if request.method == "POST":
            if request.form.get("admin_password") == ADMIN_SECRET_PASSWORD:
                session["is_admin"] = True
            else:
                flash("Mot de passe incorrect.", "danger")
                return render_template_string(HTML_TEMPLATE, page="admin_login")
        else:
            return render_template_string(HTML_TEMPLATE, page="admin_login")
    return render_template_string(HTML_TEMPLATE, page="admin", users=User.query.all())

@app.route("/admin-logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("index"))

@app.route("/register", methods=["POST"])
def register():
    company_name = request.form.get("company_name")
    email = request.form.get("email")
    password = request.form.get("password")
    payment_method = request.form.get("payment_method")
    
    if User.query.filter_by(email=email).first():
        flash("Cet e-mail existe déjà.", "danger")
        return redirect(url_for("register_form"))
    
    new_user = User(company_name=company_name, email=email, password_hash=generate_password_hash(password), payment_method=payment_method)
    db.session.add(new_user)
    db.session.commit()
    
    new_api_key = ApiKey(key_string=f"gra_live_{secrets.token_hex(16)}", user_id=new_user.id)
    db.session.add(new_api_key)
    db.session.commit()
    
    session["user_id"] = new_user.id
    return redirect(url_for("dashboard"))

@app.route("/login", methods=["POST"])
def login():
    user = User.query.filter_by(email=request.form.get("email")).first()
    if user and check_password_hash(user.password_hash, request.form.get("password")):
        session["user_id"] = user.id
        return redirect(url_for("dashboard"))
    flash("Identifiants incorrects.", "danger")
    return redirect(url_for("login_form"))

@app.route("/dashboard")
def dashboard():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login_form"))
    return render_template_string(HTML_TEMPLATE, page="dashboard", user=User.query.get(user_id))

@app.route("/logout")
def logout():
    session.pop("user_id", None)
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(debug=True)
