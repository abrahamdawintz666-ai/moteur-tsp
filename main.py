import os
import secrets
from datetime import datetime
from flask import Flask, render_template_string, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

# Mot de passe administrateur secret (modifiable via les variables d'environnement sur Render)
ADMIN_SECRET_PASSWORD = os.getenv("ADMIN_PASSWORD", "MonSuperMotDePasseAdmin2026!")

# 1. Configuration de la base de données PostgreSQL sur Render
database_url = os.getenv("DATABASE_URL")
if database_url:
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+psycopg2://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# 2. Modèles de Données (Entreprises, Clés API, Logs, Livreurs/Tournées)
class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    payment_method = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), default="actif")
    api_quota = db.Column(db.Integer, default=100)
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

# 3. Design Mobile-First Complet avec Vraie Carte Interactive Leaflet.js
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>GlobalRoute AI - Enterprise Logistics & Map</title>
    <!-- Intégration de Leaflet.js pour la vraie carte interactive -->
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        :root { --primary: #0f172a; --accent: #2563eb; --bg: #f8fafc; --card: #ffffff; --text: #334155; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: var(--bg); color: var(--text); margin: 0; padding: 0; }
        header { background: var(--primary); color: white; padding: 16px 20px; display: flex; justify-content: space-between; align-items: center; }
        header h1 { margin: 0; font-size: 17px; font-weight: 700; }
        .container { padding: 20px; box-sizing: border-box; max-width: 800px; margin: 0 auto; }
        .hero { background: white; padding: 25px 20px; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.03); text-align: center; margin-bottom: 20px; }
        .hero h2 { color: var(--primary); font-size: 20px; margin-top: 0; }
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
        #map { width: 100%; height: 280px; border-radius: 8px; margin-top: 15px; margin-bottom: 15px; z-index: 1; }
    </style>
</head>
<body>
    <header>
        <h1>GlobalRoute AI</h1>
        <div style="display: flex; gap: 15px;">
            <a href="/" style="color: #cbd5e1; font-size: 12px; text-decoration: none;">Accueil</a>
            <a href="/driver-login" style="color: #6ee7b7; font-size: 12px; text-decoration: none;">🚚 Espace Livreur</a>
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
            <!-- ACCUEIL -->
            <div class="hero">
                <h2>L'Intelligence Logistique Mondiale</h2>
                <p>Optimisez vos flottes de livraison en temps réel, suivez vos tournées sur une vraie carte interactive et pilotez vos opérations.</p>
                
                <div class="btn-group">
                    <a href="/register-form" class="btn btn-primary">S'inscrire (Nouveau Compte)</a>
                    <a href="/login-form" class="btn btn-secondary">Se Connecter (Entreprise)</a>
                    <a href="/driver-login" class="btn btn-secondary" style="background:#ecfdf5; color:#065f46; border-color:#a7f3d0;">Accès Livreur Terrain</a>
                </div>
            </div>

            <div class="card" style="text-align: left;">
                <h3 style="font-size: 15px; margin-top:0; color:var(--primary);">🚀 Simple pour tous</h3>
                <p style="font-size: 12px; color: #64748b; margin-bottom: 5px;">✔ <strong>Développeurs :</strong> API ultra-rapide et clés d'essai instantanées.</p>
                <p style="font-size: 12px; color: #64748b; margin-bottom: 0;">✔ <strong>Livreurs :</strong> Feuille de route avec vraie carte interactive et guidage.</p>
            </div>

        {% elif page == 'register' %}
            <!-- INSCRIPTION -->
            <div class="card">
                <h2 style="font-size: 16px; margin-top:0; color:var(--primary); margin-bottom: 15px;">Créer un Compte Entreprise</h2>
                <form method="POST" action="/register">
                    <label>Nom de l'entreprise :</label>
                    <input type="text" name="company_name" placeholder="Ex: Global Transport SA" required>

                    <label>E-mail professionnel :</label>
                    <input type="email" name="email" placeholder="admin@entreprise.com" required>

                    <label>Mot de passe :</label>
                    <input type="password" name="password" placeholder="••••••••" required>

                    <label>Mode de Règlement :</label>
                    <select name="payment_method" required>
                        <option value="crypto_usdc">Crypto Stablecoin (USDC / USDT)</option>
                        <option value="bank_transfer">Virement Bancaire International</option>
                    </select>

                    <button type="submit" class="btn btn-primary">Valider l'Inscription</button>
                </form>
                <p style="text-align:center; font-size:12px; margin-top:15px;"><a href="/login-form" style="color:var(--accent);">Vous avez déjà un compte ? Se connecter</a></p>
            </div>

        {% elif page == 'login' %}
            <!-- CONNEXION -->
            <div class="card">
                <h2 style="font-size: 16px; margin-top:0; color:var(--primary); margin-bottom: 15px;">Connexion Espace Entreprise</h2>
                <form method="POST" action="/login">
                    <label>E-mail professionnel :</label>
                    <input type="email" name="email" placeholder="admin@entreprise.com" required>

                    <label>Mot de passe :</label>
                    <input type="password" name="password" placeholder="••••••••" required>

                    <button type="submit" class="btn btn-primary">Se Connecter</button>
                </form>
                <p style="text-align:center; font-size:12px; margin-top:15px;"><a href="/register-form" style="color:var(--accent);">Pas encore de compte ? S'inscrire</a></p>
            </div>

        {% elif page == 'dashboard' and user %}
            <!-- TABLEAU DE BORD CLIENT -->
            <div class="card" style="text-align: left;">
                <h2 style="font-size: 16px; margin-top:0; color:var(--primary);">Tableau de Bord : {{ user.company_name }}</h2>
                <p style="font-size: 12px; color: #64748b;">Statut du compte : <strong style="color: #166534;">Actif</strong></p>
                
                <hr style="border:0; border-top:1px solid #e2e8f0; margin: 15px 0;">

                <label>Votre Clé API Secrète :</label>
                <div class="api-box">
                    {% if user.api_keys %}
                        {{ user.api_keys[0].key_string }}
                    {% else %}
                        Aucune clé générée
                    {% endif %}
                </div>

                <p style="font-size: 12px; margin-top: 15px;"><strong>Consommation du Quota :</strong> {{ user.logs|length }} / {{ user.api_quota }} requêtes</p>

                <!-- GESTION DES TOURNÉES LIVREURS -->
                <h3 style="font-size: 14px; margin-top: 25px; color:var(--primary);">🚚 Assigner une tournée à un livreur</h3>
                <form method="POST" action="/create-driver-route">
                    <label>Nom du Livreur :</label>
                    <input type="text" name="driver_name" placeholder="Ex: Jean Marc" required>

                    <label>Code d'accès secret pour le livreur :</label>
                    <input type="text" name="access_code" placeholder="Ex: LIVREUR01" required>

                    <label>Feuille de route / Instructions :</label>
                    <textarea name="stops_summary" rows="3" placeholder="Étape 1: Entrepôt (Départ)&#10;Étape 2: Supermarché Nord (3 colis)&#10;Étape 3: Pharmacie Centrale (1 colis)" required></textarea>

                    <button type="submit" class="btn btn-primary" style="background:#059669;">Créer l'accès Livreur & Carte</button>
                </form>

                {% if user.deliveries %}
                    <h4 style="font-size: 13px; margin-top: 20px;">Livreurs actifs de l'entreprise :</h4>
                    <ul>
                        {% for d in user.deliveries %}
                            <li style="font-size: 12px; margin-bottom: 5px;"><strong>{{ d.driver_name }}</strong> (Code : <code>{{ d.access_code }}</code>)</li>
                        {% endfor %}
                    </ul>
                {% endif %}

                <div style="margin-top: 25px;">
                    <a href="/logout" class="btn btn-secondary" style="background:#fee2e2; color:#991b1b; border:none;">Se Déconnecter</a>
                </div>
            </div>

        {% elif page == 'driver_login' %}
            <!-- LOGIN LIVREUR -->
            <div class="card" style="text-align: left; border: 2px solid #059669;">
                <h2 style="font-size: 16px; margin-top:0; color:#059669;">🚚 Espace Chauffeur & Livreur</h2>
                <p style="font-size: 12px; color: #64748b; margin-bottom: 15px;">Entrez le code d'accès fourni par votre entreprise pour afficher votre trajet sur la carte.</p>
                
                <form method="POST" action="/driver-space">
                    <label>Code d'accès Livreur :</label>
                    <input type="text" name="access_code" placeholder="Ex: LIVREUR01" required style="text-transform: uppercase;">
                    <button type="submit" class="btn btn-primary" style="background:#059669;">Voir ma Feuille de Route & Carte</button>
                </form>
                <div style="margin-top: 15px;">
                    <a href="/" class="btn btn-secondary">Retour à l'accueil</a>
                </div>
            </div>

        {% elif page == 'driver_space' and route %}
            <!-- ESPACE LIVREUR / TERRAIN AVEC VRAIE CARTE INTERACTIVE -->
            <div class="card" style="text-align: left;">
                <h2 style="font-size: 16px; margin-top:0; color:var(--primary);">🚚 Votre Trajet et Carte du Jour</h2>
                <p style="font-size: 12px; color: #64748b;">Chauffeur : <strong>{{ route.driver_name }}</strong></p>
                
                <hr style="border:0; border-top:1px solid #e2e8f0; margin: 15px 0;">

                <!-- CONTENEUR DE LA CARTE INTERACTIVE -->
                <label>🗺️ Visualisation du Trajet en Direct (Départ & Arrivée) :</label>
                <div id="map"></div>

                <div style="background: #ecfdf5; padding: 15px; border-radius: 8px; margin-top: 15px; border-left: 4px solid #059669;">
                    <span class="badge" style="background: #059669; color: white;">Feuille de Route Validée</span>
                    <h4 style="margin: 10px 0 5px 0; font-size: 14px; color:#065f46;">Instructions :</h4>
                    <p style="font-size: 13px; color: #1e293b; white-space: pre-line; line-height: 1.6; margin: 0;">{{ route.stops_summary }}</p>
                    
                    <a href="https://maps.google.com/?q=destination" target="_blank" class="btn btn-primary" style="margin-top: 15px; font-size: 13px; padding: 12px; background:#2563eb;">🧭 Lancer la Navigation GPS (Google Maps)</a>
                </div>

                <div style="margin-top: 20px;">
                    <a href="/driver-login" class="btn btn-secondary">Quitter l'espace livreur</a>
                </div>
            </div>

            <!-- SCRIPT D'INITIALISATION DE LA CARTE AVEC FLECHES / TRACÉ -->
            <script>
                // Initialisation de la carte centrée par défaut (ex: Cap-Haïtien / Caraïbes ou coordonnées globales)
                var map = L.map('map').setView([19.7558, -72.2042], 13);

                // Fond de carte OpenStreetMap propre et rapide
                L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                    maxZoom: 19,
                    attribution: '© OpenStreetMap'
                }).addTo(map);

                // Points d'exemple pour visualiser le tracé (Départ -> Étape 1 -> Étape 2)
                var startPoint = [19.7558, -72.2042]; // Hub / Départ
                var stop1 = [19.7620, -72.2150];       // Première livraison
                var stop2 = [19.7480, -72.1920];       // Deuxième livraison

                // Marqueurs avec icônes claires
                L.marker(startPoint).addTo(map).bindPopup("<b>Départ / Hub Principal</b>").openPopup();
                L.marker(stop1).addTo(map).bindPopup("<b>Étape 1 : Livraison</b>");
                L.marker(stop2).addTo(map).bindPopup("<b>Étape 2 : Livraison Finale</b>");

                // Tracé de la ligne reliant les points (les flèches de parcours)
                var routeCoordinates = [startPoint, stop1, stop2];
                var polyline = L.polyline(routeCoordinates, {color: '#2563eb', weight: 4, dashArray: '5, 10'}).addTo(map);

                // Ajuster la vue de la carte pour inclure tout le trajet
                map.fitBounds(polyline.getBounds(), {padding: [50, 50]});
            </script>

        {% elif page == 'admin_login' %}
            <!-- CONNEXION ADMIN SÉCURISÉE -->
            <div class="card" style="text-align: left; border: 2px solid var(--primary);">
                <h2 style="font-size: 16px; margin-top:0; color:var(--primary);">🔐 Accès Restreint Administrateur</h2>
                <p style="font-size: 12px; color: #64748b; margin-bottom: 15px;">Veuillez entrer le mot de passe administrateur.</p>
                
                <form method="POST" action="/admin-panel">
                    <label>Mot de passe Admin :</label>
                    <input type="password" name="admin_password" placeholder="••••••••••••" required>
                    <button type="submit" class="btn btn-primary">Se Connecter à l'Admin</button>
                </form>
                <div style="margin-top: 15px;">
                    <a href="/" class="btn btn-secondary">Retour à l'accueil</a>
                </div>
            </div>

        {% elif page == 'admin' %}
            <!-- PANNEAU ADMIN GLOBAL -->
            <div class="card" style="text-align: left;">
                <h2 style="font-size: 16px; margin-top:0; color:var(--primary);">🛡️ Panneau Administrateur</h2>
                <div style="display: flex; gap: 10px; margin-bottom: 15px; flex-wrap: wrap;">
                    <a href="/admin-secret-generator" class="btn btn-primary" style="font-size: 12px; padding: 10px;">🔑 Générateur de Clés d'Essai</a>
                    <a href="/admin-logout" class="btn btn-secondary" style="font-size: 12px; padding: 10px; background:#fee2e2; color:#991b1b; border:none;">Verrouiller Admin</a>
                </div>
                
                <div style="overflow-x: auto;">
                    <table>
                        <thead>
                            <tr>
                                <th>Entreprise</th>
                                <th>Clé API</th>
                                <th>Requêtes / Quota</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for u in users %}
                            <tr>
                                <td><strong>{{ u.company_name }}</strong><br><span style="font-size:10px; color:#64748b;">{{ u.email }}</span></td>
                                <td><code style="background:#f1f5f9; padding:2px; font-size:10px;">{{ u.api_keys[0].key_string if u.api_keys else 'N/A' }}</code></td>
                                <td>{{ u.logs|length }}/{{ u.api_quota }}</td>
                            </tr>
                            {% else %}
                            <tr>
                                <td colspan="3" style="text-align: center; color: #94a3b8;">Aucune entreprise enregistrée.</td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
                <div style="margin-top: 20px;">
                    <a href="/" class="btn btn-secondary">Retour à l'accueil</a>
                </div>
            </div>

        {% elif page == 'secret_generator' %}
            <!-- GÉNÉRATEUR DE CLÉS D'ESSAI -->
            <div class="card" style="text-align: left; border: 2px dashed var(--accent);">
                <h2 style="font-size: 16px; margin-top:0; color:var(--accent);">⚡ Générateur Exclusif de Clés d'Essai (Prospects)</h2>
                <p style="font-size: 12px; color: #64748b; margin-bottom: 15px;">Entrez le nom du prospect pour lui créer une clé d'essai immédiate.</p>
                
                <form method="POST" action="/admin-secret-generator">
                    <label>Nom du Prospect / Entreprise :</label>
                    <input type="text" name="prospect_name" placeholder="Ex: Transit Express Haïti" required>

                    <label>Quota d'essais alloué :</label>
                    <select name="trial_quota">
                        <option value="20">20 requêtes (Test rapide)</option>
                        <option value="50" selected>50 requêtes (Standard Demo)</option>
                        <option value="100">100 requêtes (Grand Compte)</option>
                    </select>

                    <button type="submit" class="btn btn-primary">Générer la Clé d'Essai</button>
                </form>

                <div style="margin-top: 20px;">
                    <a href="/admin-panel" class="btn btn-secondary">Retour au Panneau Admin</a>
                </div>
            </div>
        {% endif %}
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
        flash("Veuillez entrer votre code d'accès livreur.", "danger")
        return redirect(url_for("driver_login"))
    
    route = DeliveryRoute.query.filter_by(access_code=code.strip().upper()).first()
    if not route:
        flash("Code d'accès livreur incorrect ou introuvable.", "danger")
        return redirect(url_for("driver_login"))
        
    return render_template_string(HTML_TEMPLATE, page="driver_space", route=route)

@app.route("/create-driver-route", methods=["POST"])
def create_driver_route():
    user_id = session.get("user_id")
    if not user_id:
        flash("Veuillez vous connecter.", "danger")
        return redirect(url_for("login_form"))
        
    driver_name = request.form.get("driver_name")
    access_code = request.form.get("access_code").strip().upper()
    stops_summary = request.form.get("stops_summary")
    
    if not driver_name or not access_code or not stops_summary:
        flash("Tous les champs pour la tournée livreur sont obligatoires.", "danger")
        return redirect(url_for("dashboard"))
        
    if DeliveryRoute.query.filter_by(access_code=access_code).first():
        flash("Ce code d'accès livreur existe déjà. Choisissez-en un autre.", "danger")
        return redirect(url_for("dashboard"))
        
    new_route = DeliveryRoute(
        user_id=user_id,
        driver_name=driver_name,
        access_code=access_code,
        stops_summary=stops_summary
    )
    db.session.add(new_route)
    db.session.commit()
    
    flash(f"Tournée et carte créées avec succès pour {driver_name} ! Code : {access_code}", "success")
    return redirect(url_for("dashboard"))

@app.route("/admin-panel", methods=["GET", "POST"])
def admin_panel():
    if not session.get("is_admin"):
        if request.method == "POST":
            entered_password = request.form.get("admin_password")
            if entered_password == ADMIN_SECRET_PASSWORD:
                session["is_admin"] = True
                flash("Accès administrateur autorisé.", "success")
            else:
                flash("Mot de passe administrateur incorrect.", "danger")
                return render_template_string(HTML_TEMPLATE, page="admin_login")
        else:
            return render_template_string(HTML_TEMPLATE, page="admin_login")
            
    try:
        all_users = User.query.all()
    except Exception:
        all_users = []
    return render_template_string(HTML_TEMPLATE, page="admin", users=all_users)

@app.route("/admin-logout")
def admin_logout():
    session.pop("is_admin", None)
    flash("Panneau administrateur verrouillé.", "success")
    return redirect(url_for("index"))

@app.route("/admin-secret-generator", methods=["GET", "POST"])
def secret_generator():
    if not session.get("is_admin"):
        flash("Veuillez vous authentifier en tant qu'administrateur.", "danger")
        return redirect(url_for("admin_panel"))
        
    if request.method == "POST":
        prospect_name = request.form.get("prospect_name")
        quota = int(request.form.get("trial_quota", 50))
        
        if not prospect_name:
            flash("Veuillez entrer un nom d'entreprise.", "danger")
            return redirect(url_for("secret_generator"))
        
        fake_email = f"trial_{secrets.token_hex(4)}@globalroute-trial.com"
        new_user = User(
            company_name=f"[ESSAI] {prospect_name}",
            email=fake_email,
            password_hash=generate_password_hash("trial_secure_pass"),
            payment_method="trial_prospect",
            status="essai",
            api_quota=quota
        )
        db.session.add(new_user)
        db.session.commit()
        
        trial_key = f"gra_trial_{secrets.token_hex(16)}"
        new_api_key = ApiKey(key_string=trial_key, user_id=new_user.id)
        db.session.add(new_api_key)
        db.session.commit()
        
        flash(f"Clé d'essai générée avec succès pour {prospect_name} ! Clé : {trial_key}", "success")
        return redirect(url_for("admin_panel"))
        
    return render_template_string(HTML_TEMPLATE, page="secret_generator")

@app.route("/register", methods=["POST"])
def register():
    company_name = request.form.get("company_name")
    email = request.form.get("email")
    password = request.form.get("password")
    payment_method = request.form.get("payment_method")
    
    if not company_name or not email or not password or not payment_method:
        flash("Veuillez remplir tous les champs.", "danger")
        return redirect(url_for("register_form"))
    
    if User.query.filter_by(email=email).first():
        flash("Cet e-mail est déjà enregistré.", "danger")
        return redirect(url_for("register_form"))
    
    hashed_pwd = generate_password_hash(password)
    new_user = User(
        company_name=company_name,
        email=email,
        password_hash=hashed_pwd,
        payment_method=payment_method,
        status="actif",
        api_quota=100
    )
    db.session.add(new_user)
    db.session.commit()
    
    generated_key = f"gra_live_{secrets.token_hex(16)}"
    new_api_key = ApiKey(key_string=generated_key, user_id=new_user.id)
    db.session.add(new_api_key)
    db.session.commit()
    
    session["user_id"] = new_user.id
    flash("Compte créé avec succès ! Bienvenue sur votre tableau de bord.", "success")
    return redirect(url_for("dashboard"))

@app.route("/login", methods=["POST"])
def login():
    email = request.form.get("email")
    password = request.form.get("password")
    
    user = User.query.filter_by(email=email).first()
    if user and check_password_hash(user.password_hash, password):
        session["user_id"] = user.id
        flash("Connexion réussie.", "success")
        return redirect(url_for("dashboard"))
    
    flash("E-mail ou mot de passe incorrect.", "danger")
    return redirect(url_for("login_form"))

@app.route("/dashboard")
def dashboard():
    user_id = session.get("user_id")
    if not user_id:
        flash("Veuillez vous connecter pour accéder à votre espace.", "danger")
        return redirect(url_for("login_form"))
    
    user = User.query.get(user_id)
    return render_template_string(HTML_TEMPLATE, page="dashboard", user=user)

@app.route("/logout")
def logout():
    session.pop("user_id", None)
    flash("Vous avez été déconnecté.", "success")
    return redirect(url_for("index"))

@app.route("/api/v1/optimize", methods=["POST"])
def api_optimize():
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return jsonify({"error": "Clé API manquante ou invalide (Format: Bearer VOTRE_CLE)"}), 401
    
    token = auth_header.split(" ")[1]
    api_key_record = ApiKey.query.filter_by(key_string=token).first()
    
    if not api_key_record:
        return jsonify({"error": "Clé API non reconnue."}), 403
    
    user = User.query.get(api_key_record.user_id)
    log = UsageLog(user_id=user.id, endpoint="/api/v1/optimize")
    db.session.add(log)
    db.session.commit()
    
    return jsonify({
        "status": "success",
        "engine": "GlobalRoute AI Core v3.0",
        "message": f"Optimisation réussie pour {user.company_name}",
        "remaining_quota": user.api_quota - len(user.logs),
        "optimized_route": {
            "origin": "Hub Logistique Principal",
            "stops_count": 4,
            "total_distance_km": 289.4,
            "fuel_efficiency_gain": "24.2%"
        }
    }), 200

if __name__ == "__main__":
    app.run(debug=True)
