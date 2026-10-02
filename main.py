import os
import secrets
import csv
import io
from datetime import datetime, timedelta
from flask import Flask, render_template_string, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

ADMIN_SECRET_PASSWORD = "admin123"

# Configuration robuste de la base de données (SQLite par défaut en local)
database_url = os.getenv("DATABASE_URL")
if database_url:
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+psycopg2://", 1)
else:
    database_url = "sqlite:///database.db"

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    payment_method = db.Column(db.String(50), default="Crypto USDC")
    subscription_status = db.Column(db.String(50), default="Actif")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    api_keys = db.relationship("ApiKey", backref="owner", lazy=True, cascade="all, delete-orphan")
    logs = db.relationship("UsageLog", backref="user", lazy=True, cascade="all, delete-orphan")
    deliveries = db.relationship("DeliveryRoute", backref="company", lazy=True, cascade="all, delete-orphan")

class ApiKey(db.Model):
    __tablename__ = "api_keys"
    id = db.Column(db.Integer, primary_key=True)
    key_string = db.Column(db.String(255), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default="Active")

class UsageLog(db.Model):
    __tablename__ = "usage_logs"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    action = db.Column(db.String(150), nullable=False)
    ip_address = db.Column(db.String(50), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class DeliveryRoute(db.Model):
    __tablename__ = "delivery_routes"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    driver_name = db.Column(db.String(100), nullable=False)
    access_code = db.Column(db.String(50), unique=True, nullable=False)
    stops_data = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default="En cours")

with app.app_context():
    try:
        db.create_all()
    except Exception as e:
        print("Erreur initialisation DB (recréation propre) :", e)
        db.drop_all()
        db.create_all()

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>GlobalRoute AI - Master Admin Dashboard</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        :root { --primary: #0f172a; --accent: #2563eb; --bg: #f8fafc; --card: #ffffff; --text: #334155; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: var(--bg); color: var(--text); margin: 0; padding: 0; }
        header { background: var(--primary); color: white; padding: 16px 20px; display: flex; justify-content: space-between; align-items: center; }
        header h1 { margin: 0; font-size: 17px; font-weight: 700; }
        .container { padding: 20px; box-sizing: border-box; max-width: 950px; margin: 0 auto; }
        .hero { background: white; padding: 30px 20px; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.03); text-align: center; margin-bottom: 20px; }
        .btn { display: block; width: 100%; padding: 12px; border-radius: 8px; font-size: 14px; font-weight: 600; text-align: center; text-decoration: none; cursor: pointer; border: none; margin-bottom: 10px; }
        .btn-primary { background: var(--accent); color: white; }
        .btn-secondary { background: #f1f5f9; color: var(--primary); border: 1px solid #cbd5e1; }
        .card { background: white; padding: 20px; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.03); margin-bottom: 20px; }
        label { display: block; font-weight: 600; font-size: 12px; margin-bottom: 6px; color: #475569; text-align: left; }
        input, select, textarea { width: 100%; padding: 12px; border: 1px solid #cbd5e1; border-radius: 8px; box-sizing: border-box; font-size: 14px; margin-bottom: 15px; background: #fff; }
        .alert { padding: 12px; border-radius: 8px; margin-bottom: 20px; font-size: 13px; font-weight: 500; }
        .alert-success { background: #dcfce7; color: #166534; }
        .alert-danger { background: #fee2e2; color: #991b1b; }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 11px; }
        th, td { padding: 10px 6px; text-align: left; border-bottom: 1px solid #e2e8f0; }
        th { background: #f1f5f9; color: #475569; }
        .badge { padding: 3px 6px; border-radius: 4px; font-size: 10px; font-weight: bold; }
        .badge-active { background: #dcfce7; color: #166534; }
        .badge-revoked { background: #fee2e2; color: #991b1b; }
        #map { width: 100%; height: 350px; border-radius: 8px; margin-top: 15px; margin-bottom: 15px; z-index: 1; }
        footer { text-align: center; font-size: 11px; color: #94a3b8; margin: 30px 0; }
    </style>
</head>
<body>
    <header>
        <h1>GlobalRoute AI (Admin Master)</h1>
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
                <h2>Plateforme Logistique SaaS & Gestion Avancée</h2>
                <p>Outil de gestion centralisée pour administrateur.</p>
                <a href="/register-form" class="btn btn-primary">Créer un Compte Entreprise</a>
                <a href="/login-form" class="btn btn-secondary">Connexion Entreprise</a>
                <a href="/driver-login" class="btn btn-secondary" style="background:#ecfdf5; color:#065f46; border-color:#a7f3d0;">Accès Livreur Terrain</a>
            </div>

        {% elif page == 'register' %}
            <div class="card">
                <h2>Inscription Entreprise</h2>
                <form method="POST" action="/register">
                    <label>Nom de l'entreprise :</label>
                    <input type="text" name="company_name" required>
                    <label>E-mail :</label>
                    <input type="email" name="email" required>
                    <label>Mot de passe :</label>
                    <input type="password" name="password" required>
                    <button type="submit" class="btn btn-primary">Valider</button>
                </form>
            </div>

        {% elif page == 'login' %}
            <div class="card">
                <h2>Connexion Entreprise</h2>
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
                <h2>Tableau de Bord : {{ user.company_name }}</h2>
                <label>Vos Clés Actives :</label>
                {% for k in user.api_keys %}
                    {% if k.status == 'Active' %}
                        <div style="background:#0f172a; color:#e2e8f0; padding:10px; border-radius:6px; font-family:monospace; font-size:11px; margin-bottom:5px;">{{ k.key_string }} (Expire le : {{ k.expires_at.strftime('%Y-%m-%d') }})</div>
                    {% endif %}
                {% endfor %}
                
                <h3 style="font-size: 14px; margin-top: 25px; color:var(--primary);">📁 Importer une Tournée via Fichier CSV</h3>
                <form method="POST" action="/create-driver-route" enctype="multipart/form-data">
                    <label>Nom du Livreur :</label>
                    <input type="text" name="driver_name" placeholder="Ex: Jean Dupont" required>
                    <label>Code d'accès secret du livreur :</label>
                    <input type="text" name="access_code" placeholder="Ex: LIVREUR01" required>
                    <label>Fichier CSV des étapes (.csv) :</label>
                    <input type="file" name="csv_file" accept=".csv" required style="padding: 8px; background: #f8fafc;">
                    <button type="submit" class="btn btn-primary" style="background:#059669;">Importer et Valider la Tournée</button>
                </form>

                <div style="margin-top: 20px;">
                    <a href="/logout" class="btn btn-secondary" style="background:#fee2e2; color:#991b1b; border:none;">Se Déconnecter</a>
                </div>
            </div>

        {% elif page == 'driver_login' %}
            <div class="card" style="text-align: left; border: 2px solid #059669;">
                <h2 style="color:#059669;">🚚 Espace Livreur Terrain</h2>
                <form method="POST" action="/driver-space">
                    <label>Code d'accès :</label>
                    <input type="text" name="access_code" placeholder="Ex: LIVREUR01" required style="text-transform: uppercase;">
                    <button type="submit" class="btn btn-primary" style="background:#059669;">Afficher la Carte & Itinéraire</button>
                </form>
            </div>

        {% elif page == 'driver_space' and route %}
            <div class="card" style="text-align: left;">
                <h2>🚚 Feuille de Route de {{ route.driver_name }}</h2>
                <div id="map"></div>
                <div style="background: #ecfdf5; padding: 15px; border-radius: 8px; margin-top: 15px; border-left: 4px solid #059669;">
                    <h4 style="margin:0 0 10px 0; color:#065f46;">Étapes Importées :</h4>
                    <ul id="stops-list" style="margin:0; padding-left: 20px; font-size: 13px; line-height: 1.6;"></ul>
                </div>
                <a href="/driver-login" class="btn btn-secondary" style="margin-top: 20px;">Quitter l'espace livreur</a>
            </div>

            <script>
                var rawData = {{ route.stops_data | tojson }};
                var lines = rawData.split("\\n");
                var points = [];
                lines.forEach(function(line) {
                    if(line.trim() !== "") {
                        var parts = line.split("|");
                        if(parts.length >= 3) {
                            points.push({ name: parts[0].trim(), lat: parseFloat(parts[1].trim()), lng: parseFloat(parts[2].trim()) });
                        }
                    }
                });
                var defaultCenter = points.length > 0 ? [points[0].lat, points[0].lng] : [19.7558, -72.2042];
                var map = L.map('map').setView(defaultCenter, 14);
                L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '© OpenStreetMap' }).addTo(map);

                var latLngs = [];
                var listHtml = "";
                points.forEach(function(pt, index) {
                    latLngs.push([pt.lat, pt.lng]);
                    var gmapsUrl = "https://www.google.com/maps/search/?api=1&query=" + pt.lat + "," + pt.lng;
                    var popupContent = "<b>Étape " + index + ": " + pt.name + "</b><br>Lat: " + pt.lat + ", Lng: " + pt.lng + "<br><a href='" + gmapsUrl + "' target='_blank' style='color:#2563eb; font-weight:bold;'>🧭 GPS</a>";
                    L.marker([pt.lat, pt.lng]).addTo(map).bindPopup(popupContent);
                    listHtml += "<li><b>" + pt.name + "</b> (GPS: " + pt.lat + ", " + pt.lng + ")<br><a href='" + gmapsUrl + "' target='_blank' style='font-size:11px; color:#2563eb;'>Lancer l'itinéraire GPS</a></li><br>";
                });
                document.getElementById("stops-list").innerHTML = listHtml;
                if(latLngs.length > 0) {
                    var polyline = L.polyline(latLngs, {color: '#2563eb', weight: 4, dashArray: '5, 8'}).addTo(map);
                    map.fitBounds(polyline.getBounds(), {padding: [40, 40]});
                }
            </script>

        {% elif page == 'admin_login' %}
            <div class="card" style="text-align: left; border: 2px solid var(--primary);">
                <h2>🔐 Connexion Administrateur</h2>
                <form method="POST" action="/admin-panel">
                    <label>Mot de passe Admin :</label>
                    <input type="password" name="admin_password" required>
                    <button type="submit" class="btn btn-primary">Entrer</button>
                </form>
            </div>

        {% elif page == 'admin' %}
            <div class="card" style="text-align: left;">
                <h2>🛡 Panneau Maître Administrateur</h2>
                <a href="/admin-logout" class="btn btn-secondary" style="background:#fee2e2; color:#991b1b; border:none; margin-bottom:15px; width:auto; display:inline-block; padding:8px 15px;">Verrouiller l'Admin</a>

                <div style="background:#f1f5f9; padding:15px; border-radius:8px; margin-bottom:20px;">
                    <h3 style="margin-top:0; font-size:14px; color:var(--primary);">➕ Générer une Nouvelle Clé API & Compte</h3>
                    <form method="POST" action="/admin/generate-custom-key" style="margin:0;">
                        <label>Nom de l'entreprise :</label>
                        <input type="text" name="company_name" placeholder="Ex: Transports Haïti SA" required>
                        
                        <label>Adresse E-mail :</label>
                        <input type="email" name="email" placeholder="contact@entreprise.com" required>
                        
                        <label>Durée de validité (en Jours) :</label>
                        <input type="number" name="duration_days" value="30" min="1" required>
                        
                        <button type="submit" class="btn btn-primary" style="background:#2563eb;">Générer et Enregistrer la Clé</button>
                    </form>
                </div>

                <h3 style="font-size:14px; color:var(--primary);">📋 Suivi des Utilisateurs, Clés et Abonnements</h3>
                <table>
                    <thead>
                        <tr>
                            <th>Entreprise / Email</th>
                            <th>Détails Clé & Validité</th>
                            <th>Abonnement</th>
                            <th>Dernière Connexion / Logs</th>
                            <th>Actions (Révocation)</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for u in users %}
                        <tr>
                            <td>
                                <strong>{{ u.company_name }}</strong><br>
                                <span style="color:#64748b;">{{ u.email }}</span>
                            </td>
                            <td>
                                {% for k in u.api_keys %}
                                    <div style="margin-bottom:4px;">
                                        <code style="background:#f8fafc; padding:2px 4px; border-radius:3px;">{{ k.key_string[:18] }}...</code><br>
                                        <span style="font-size:9px; color:#475569;">Pris le: {{ k.created_at.strftime('%Y-%m-%d') }} | Expire: {{ k.expires_at.strftime('%Y-%m-%d') }}</span><br>
                                        <span class="badge {% if k.status == 'Active' %}badge-active{% else %}badge-revoked{% endif %}">{{ k.status }}</span>
                                    </div>
                                {% endfor %}
                            </td>
                            <td>
                                <span class="badge badge-active">{{ u.subscription_status }}</span><br>
                                <span style="font-size:9px; color:#64748b;">{{ u.payment_method }}</span>
                            </td>
                            <td>
                                {% if u.logs %}
                                    {% set last_log = u.logs[-1] %}
                                    {{ last_log.action }}<br>
                                    <span style="font-size:9px; color:#64748b;">IP: {{ last_log.ip_address or 'N/A' }}<br>{{ last_log.timestamp.strftime('%Y-%m-%d %H:%M') }}</span>
                                {% else %}
                                    <span style="color:#94a3b8;">Aucune activité</span>
                                {% endif %}
                            </td>
                            <td>
                                {% for k in u.api_keys %}
                                    {% if k.status == 'Active' %}
                                        <form method="POST" action="/admin/revoke-key/{{ k.id }}" style="margin:2px 0;">
                                            <button type="submit" class="btn" style="padding:4px 8px; font-size:10px; background:#fee2e2; color:#991b1b; width:auto;">Révoquer</button>
                                        </form>
                                    {% endif %}
                                {% endfor %}
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        {% endif %}
        <footer><p>&copy; 2026 GlobalRoute AI. Tous droits réservés.</p></footer>
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
    file = request.files.get("csv_file")
    
    if not file or not file.filename.endswith(".csv"):
        flash("Format de fichier invalide. Veuillez importer un fichier .csv valide.", "danger")
        return redirect(url_for("dashboard"))

    try:
        stream = io.TextIOWrapper(file.stream, encoding="utf-8")
        csv_reader = csv.reader(stream)
        stops_list = []
        for row in csv_reader:
            if len(row) >= 3:
                name = row[0].strip()
                try:
                    lat = float(row[1].strip())
                    lng = float(row[2].strip())
                    stops_list.append(f"{name}|{lat}|{lng}")
                except ValueError:
                    continue

        if not stops_list:
            flash("Erreur : Le fichier CSV est vide ou le format est incorrect.", "danger")
            return redirect(url_for("dashboard"))

        new_route = DeliveryRoute(
            user_id=user_id, 
            driver_name=driver_name, 
            access_code=access_code, 
            stops_data="\n".join(stops_list)
        )
        db.session.add(new_route)
        db.session.commit()
        
        ip = request.remote_addr
        log = UsageLog(user_id=user_id, action="Importation de tournée CSV", ip_address=ip)
        db.session.add(log)
        db.session.commit()

        flash(f"Tournée importée avec succès ! {len(stops_list)} étapes chargées.", "success")
    except Exception as e:
        flash(f"Erreur lors du traitement du fichier CSV : {str(e)}", "danger")

    return redirect(url_for("dashboard"))

@app.route("/admin-panel", methods=["GET", "POST"])
def admin_panel():
    if not session.get("is_admin"):
        if request.method == "POST":
            if request.form.get("admin_password") == ADMIN_SECRET_PASSWORD:
                session["is_admin"] = True
            else:
                flash("Mot de passe incorrect (Utilise 'admin123').", "danger")
                return render_template_string(HTML_TEMPLATE, page="admin_login")
        else:
            return render_template_string(HTML_TEMPLATE, page="admin_login")
    return render_template_string(HTML_TEMPLATE, page="admin", users=User.query.all())

@app.route("/admin/generate-custom-key", methods=["POST"])
def admin_generate_custom_key():
    if not session.get("is_admin"):
        return redirect(url_for("admin_panel"))
    
    company_name = request.form.get("company_name")
    email = request.form.get("email")
    try:
        duration_days = int(request.form.get("duration_days", 30))
    except ValueError:
        duration_days = 30

    user = User.query.filter_by(email=email).first()
    if not user:
        user = User(
            company_name=company_name,
            email=email,
            password_hash=generate_password_hash("password123"),
            subscription_status="Actif"
        )
        db.session.add(user)
        db.session.commit()

    expires_at = datetime.utcnow() + timedelta(days=duration_days)
    key_string = f"gra_live_{secrets.token_hex(16)}"
    
    new_key = ApiKey(
        key_string=key_string,
        user_id=user.id,
        expires_at=expires_at,
        status="Active"
    )
    db.session.add(new_key)
    db.session.commit()
    
    flash(f"Clé générée avec succès pour {company_name}. Clé : {key_string} (Expire dans {duration_days} jours)", "success")
    return redirect(url_for("admin_panel"))

@app.route("/admin/revoke-key/<int:key_id>", methods=["POST"])
def admin_revoke_key(key_id):
    if not session.get("is_admin"):
        return redirect(url_for("admin_panel"))
    
    # CORRECTION : Utilisation de db.session.get au lieu de .query.get (compatible SQLAlchemy 2.0+)
    key_obj = db.session.get(ApiKey, key_id)
    if key_obj:
        key_obj.status = "Révoquée"
        db.session.commit()
        flash("La clé API a été révoquée avec succès.", "success")
    
    return redirect(url_for("admin_panel"))

@app.route("/admin-logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("index"))

@app.route("/register", methods=["POST"])
def register():
    company_name = request.form.get("company_name")
    email = request.form.get("email")
    password = request.form.get("password")
    
    if User.query.filter_by(email=email).first():
        flash("Cet e-mail existe déjà.", "danger")
        return redirect(url_for("register_form"))
    
    new_user = User(company_name=company_name, email=email, password_hash=generate_password_hash(password), subscription_status="Actif")
    db.session.add(new_user)
    db.session.commit()
    
    expires_at = datetime.utcnow() + timedelta(days=30)
    new_api_key = ApiKey(key_string=f"gra_live_{secrets.token_hex(16)}", user_id=new_user.id, expires_at=expires_at, status="Active")
    db.session.add(new_api_key)
    db.session.commit()
    
    session["user_id"] = new_user.id
    return redirect(url_for("dashboard"))

@app.route("/login", methods=["POST"])
def login():
    user = User.query.filter_by(email=request.form.get("email")).first()
    if user and check_password_hash(user.password_hash, request.form.get("password")):
        session["user_id"] = user.id
        
        ip = request.remote_addr
        log = UsageLog(user_id=user.id, action="Connexion Entreprise", ip_address=ip)
        db.session.add(log)
        db.session.commit()

        return redirect(url_for("dashboard"))
    flash("Identifiants incorrects.", "danger")
    return redirect(url_for("login_form"))

@app.route("/dashboard")
def dashboard():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login_form"))
    
    # CORRECTION : Utilisation de db.session.get au lieu de User.query.get
    current_user = db.session.get(User, user_id)
    return render_template_string(HTML_TEMPLATE, page="dashboard", user=current_user)

@app.route("/logout")
def logout():
    session.pop("user_id", None)
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
