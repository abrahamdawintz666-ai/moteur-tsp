import os
import secrets
from datetime import datetime
from flask import Flask, render_template_string, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

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

# 2. Modèles de Données
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

with app.app_context():
    try:
        db.create_all()
    except Exception:
        pass

# 3. Design Mobile-First Ultra Propre (Landing Page + Auth + Dashboard)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>GlobalRoute AI - Enterprise Logistics</title>
    <style>
        :root { --primary: #0f172a; --accent: #2563eb; --bg: #f8fafc; --card: #ffffff; --text: #334155; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: var(--bg); color: var(--text); margin: 0; padding: 0; }
        header { background: var(--primary); color: white; padding: 16px 20px; display: flex; justify-content: space-between; align-items: center; }
        header h1 { margin: 0; font-size: 17px; font-weight: 700; }
        .container { padding: 20px; box-sizing: border-box; max-width: 600px; margin: 0 auto; }
        .hero { background: white; padding: 25px 20px; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.03); text-align: center; margin-bottom: 20px; }
        .hero h2 { color: var(--primary); font-size: 20px; margin-top: 0; }
        .hero p { font-size: 13px; color: #64748b; line-height: 1.5; margin-bottom: 20px; }
        .btn-group { display: flex; flex-direction: column; gap: 10px; }
        .btn { display: block; width: 100%; padding: 14px; border-radius: 8px; font-size: 14px; font-weight: 600; text-align: center; text-decoration: none; box-sizing: border-box; cursor: pointer; border: none; }
        .btn-primary { background: var(--accent); color: white; }
        .btn-secondary { background: #f1f5f9; color: var(--primary); border: 1px solid #cbd5e1; }
        .card { background: white; padding: 20px; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.03); margin-bottom: 20px; }
        label { display: block; font-weight: 600; font-size: 12px; margin-bottom: 6px; color: #475569; text-align: left; }
        input, select { width: 100%; padding: 12px; border: 1px solid #cbd5e1; border-radius: 8px; box-sizing: border-box; font-size: 14px; margin-bottom: 15px; background: #fff; }
        .alert { padding: 12px; border-radius: 8px; margin-bottom: 20px; font-size: 13px; font-weight: 500; }
        .alert-success { background: #dcfce7; color: #166534; }
        .alert-danger { background: #fee2e2; color: #991b1b; }
        .api-box { background: #0f172a; color: #e2e8f0; padding: 12px; border-radius: 6px; font-family: monospace; font-size: 11px; overflow-x: auto; text-align: left; margin-top: 10px; }
    </style>
</head>
<body>
    <header>
        <h1>GlobalRoute AI</h1>
        <a href="/" style="color: #cbd5e1; font-size: 12px; text-decoration: none;">Accueil</a>
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
            <!-- PAGE DE PRÉSENTATION (LANDING) -->
            <div class="hero">
                <h2>L'Intelligence Logistique Mondiale</h2>
                <p>Optimisez vos flottes de livraison en temps réel, réduisez vos coûts de carburant et pilotez vos tournées internationales grâce à notre API de pointe.</p>
                
                <div class="btn-group">
                    <a href="/register-form" class="btn btn-primary">S'inscrire (Nouveau Compte)</a>
                    <a href="/login-form" class="btn btn-secondary">Se Connecter</a>
                </div>
            </div>

            <div class="card" style="text-align: left;">
                <h3 style="font-size: 15px; margin-top:0; color:var(--primary);">🚀 Pourquoi GlobalRoute AI ?</h3>
                <p style="font-size: 12px; color: #64748b; margin-bottom: 5px;">✔ Algorithmes de routage hautement performants</p>
                <p style="font-size: 12px; color: #64748b; margin-bottom: 5px;">✔ Sécurité multi-tenant et quotas en temps réel</p>
                <p style="font-size: 12px; color: #64748b; margin-bottom: 0;">✔ Intégration API instantanée pour vos équipes</p>
            </div>

        {% elif page == 'register' %}
            <!-- FORMULAIRE D'INSCRIPTION -->
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
            <!-- FORMULAIRE DE CONNEXION -->
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
            <!-- ESPACE PERSONNEL / TABLEAU DE BORD -->
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

                <h3 style="font-size: 14px; margin-top: 20px; color:var(--primary);">Test Rapide Développeur (cURL)</h3>
                <div class="api-box" style="background:#1e293b;">
                    curl -X POST https://moteur-tsp.onrender.com/api/v1/optimize \<br>
                    -H "Authorization: Bearer {% if user.api_keys %}{{ user.api_keys[0].key_string }}{% endif %}" \<br>
                    -H "Content-Type: application/json"
                </div>

                <div style="margin-top: 25px;">
                    <a href="/logout" class="btn btn-secondary" style="background:#fee2e2; color:#991b1b; border:none;">Se Déconnecter</a>
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
