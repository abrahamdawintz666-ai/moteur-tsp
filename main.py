import os
import secrets
import sqlite3
from flask import Flask, render_template_string, request, redirect, url_for, session
import requests

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

# Configuration de la base de données
DB_NAME = "database.db"

# Mot de passe Admin récupéré depuis Render (Variable d'environnement ADMIN_PASSWORD)
# Si non défini sur Render, utilise 'admin' par défaut
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin")  
MERCHANT_SOL_WALLET = "22BzBEYLewJkKe2FXD6EHJYqX4NNshMw9roNw9qFxV9d"  

PRICE_30_DAYS_SOL = 10.0   
PRICE_365_DAYS_SOL = 116.66

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key_code TEXT UNIQUE NOT NULL,
            plan TEXT NOT NULL,
            status TEXT DEFAULT 'UNUSED',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            tx_signature TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def verify_solana_transaction(tx_signature, expected_sol_amount):
    try:
        rpc_url = "https://api.mainnet-beta.solana.com"
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTransaction",
            "params": [
                tx_signature,
                {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}
            ]
        }
        response = requests.post(rpc_url, json=payload, timeout=12)
        data = response.json()
        
        if "result" in data and data["result"] is not None:
            tx_data = data["result"]
            meta = tx_data.get("meta", {})
            if meta.get("err") is not None:
                return False, "La transaction contient une erreur sur la blockchain."
            
            transaction = tx_data.get("transaction", {})
            message = transaction.get("message", {})
            account_keys = message.get("accountKeys", [])
            account_addresses = [acc.get("pubkey") if isinstance(acc, dict) else str(acc) for acc in account_keys]
            
            if MERCHANT_SOL_WALLET not in account_addresses:
                return False, "L'adresse du portefeuille destinataire ne correspond pas au marchand."
            
            pre_balances = meta.get("preBalances", [])
            post_balances = meta.get("postBalances", [])
            merchant_index = account_addresses.index(MERCHANT_SOL_WALLET) if MERCHANT_SOL_WALLET in account_addresses else -1
            
            if merchant_index != -1 and len(pre_balances) > merchant_index and len(post_balances) > merchant_index:
                diff_lamports = post_balances[merchant_index] - pre_balances[merchant_index]
                received_sol = diff_lamports / 1e9  
                if received_sol < (expected_sol_amount * 0.98):
                    return False, f"Montant insuffisant reçu ({received_sol:.4f} SOL au lieu de {expected_sol_amount} SOL attendus)."
            
            return True, "Transaction vérifiée et certifiée sur Solana avec succès."
        else:
            return False, "Transaction introuvable ou en cours de validation sur le réseau."
    except Exception as e:
        return False, f"Erreur de communication avec le nœud Solana : {str(e)}"

NAVBAR_HTML = """
<nav style="background: rgba(15, 23, 42, 0.95); backdrop-filter: blur(12px); border-bottom: 1px solid rgba(56, 189, 248, 0.15); padding: 14px 20px; display: flex; justify-content: space-between; align-items: center; position: sticky; top: 0; z-index: 1000; flex-wrap: wrap; gap: 10px;">
    <div style="font-size: 18px; font-weight: 800; color: #38bdf8; display: flex; align-items: center; gap: 8px;">
        <span style="background: linear-gradient(135deg, #38bdf8, #818cf8); padding: 6px; border-radius: 8px; color: #0f172a; font-size: 14px;">🚀</span> GlobalRoute AI
    </div>
    <div style="display: flex; gap: 15px; align-items: center; flex-wrap: wrap;">
        <a href="/" style="color: #cbd5e1; text-decoration: none; font-weight: 600; font-size: 14px;">Accueil</a>
        <a href="/dashboard" style="color: #cbd5e1; text-decoration: none; font-weight: 600; font-size: 14px;">📊 Stats</a>
        <a href="/admin" style="color: #94a3b8; text-decoration: none; font-weight: 600; font-size: 14px; border: 1px solid rgba(148, 163, 184, 0.2); padding: 6px 12px; border-radius: 6px;">🔒 Admin</a>
    </div>
</nav>
"""

INDEX_TEMPLATE = NAVBAR_HTML + """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GlobalRoute AI - Accueil</title>
    <style>
        * { box-sizing: border-box; }
        body { font-family: 'Inter', system-ui, -apple-system, sans-serif; background: #090d16; color: #f8fafc; margin: 0; padding: 0; }
        .main-container { max-width: 900px; margin: 30px auto; padding: 15px; text-align: center; }
        .hero { padding: 40px 20px; background: radial-gradient(circle at center, #1e293b 0%, #0f172a 100%); border-radius: 20px; border: 1px solid rgba(56, 189, 248, 0.2); box-shadow: 0 20px 50px rgba(0,0,0,0.6); margin-bottom: 25px; }
        h1 { color: #f8fafc; font-size: 26px; margin-bottom: 15px; font-weight: 800; }
        @media(min-width: 768px) { h1 { font-size: 36px; } }
        h1 span { background: linear-gradient(135deg, #38bdf8, #818cf8); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .subtitle { color: #94a3b8; font-size: 15px; margin-bottom: 30px; line-height: 1.6; max-width: 600px; margin-left: auto; margin-right: auto; }
        
        .client-login-box { background: linear-gradient(145deg, #162032 0%, #0f172a 100%); border: 1px solid rgba(56, 189, 248, 0.3); padding: 20px; border-radius: 16px; margin-bottom: 25px; box-shadow: 0 10px 30px rgba(0,0,0,0.4); text-align: left; }
        .client-login-box h3 { margin-top: 0; color: #38bdf8; font-size: 16px; }
        .client-login-form { display: flex; gap: 10px; margin-top: 10px; flex-direction: column; }
        @media(min-width: 480px) { .client-login-form { flex-direction: row; } }
        .client-login-input { flex: 1; padding: 12px; border-radius: 10px; border: 1px solid rgba(148, 163, 184, 0.3); background: #090d16; color: #fff; font-size: 14px; outline: none; }
        .client-login-btn { background: linear-gradient(135deg, #38bdf8, #0ea5e9); color: #0f172a; padding: 12px 20px; border: none; border-radius: 10px; font-weight: 700; cursor: pointer; font-size: 14px; }

        .cta-box { display: flex; gap: 15px; justify-content: center; flex-direction: column; }
        @media(min-width: 480px) { .cta-box { flex-direction: row; } }
        .btn-main { background: linear-gradient(135deg, #38bdf8, #0ea5e9); color: #0f172a; padding: 15px 25px; border-radius: 12px; text-decoration: none; font-weight: 800; font-size: 15px; box-shadow: 0 4px 15px rgba(56, 189, 248, 0.3); display: inline-block; flex: 1; }
        .btn-sec { background: linear-gradient(135deg, #10b981, #059669); color: white; padding: 15px 25px; border-radius: 12px; text-decoration: none; font-weight: 800; font-size: 15px; box-shadow: 0 4px 15px rgba(16, 185, 129, 0.3); display: inline-block; flex: 1; }
        .btn-trial { background: linear-gradient(135deg, #f59e0b, #d97706); color: white; padding: 12px 20px; border-radius: 12px; text-decoration: none; font-weight: 700; font-size: 14px; margin-top: 15px; display: inline-block; }
    </style>
</head>
<body>
    <div class="main-container">
        <div class="hero">
            <h1>Intelligence Artificielle & <span>Réseaux Avancés</span></h1>
            <p class="subtitle">Propulsez vos infrastructures avec une passerelle de paiement décentralisée ultra-rapide, sécurisée et certifiée sur la blockchain Solana.</p>
            
            <div class="cta-box">
                <a href="/checkout?plan=Pass_30_Jours&price={{ price_30 }}" class="btn-main">Prendre Pass 30 Jours (1 500 $)</a>
                <a href="/checkout?plan=Pass_365_Jours&price={{ price_365 }}" class="btn-sec">Prendre Pass 365 Jours (17 500 $)</a>
            </div>
            <div>
                <a href="/request-trial" class="btn-trial">🎁 Activer un essai gratuit de 7 jours</a>
            </div>
        </div>

        <div class="client-login-box">
            <h3>🔑 Déjà une clé d'accès ? Connectez-vous</h3>
            <form action="/client-login" method="POST" class="client-login-form">
                <input type="text" name="existing_key" class="client-login-input" placeholder="Entrez votre clé (ex: KEY-...)" required>
                <button type="submit" class="client-login-btn">Se connecter</button>
            </form>
        </div>
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(INDEX_TEMPLATE, price_30=PRICE_30_DAYS_SOL, price_365=PRICE_365_DAYS_SOL)

@app.route('/request-trial')
def request_trial():
    trial_key = f"TRIAL-7DAYS-{secrets.token_hex(4).upper()}"
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO keys (key_code, plan, status, tx_signature) VALUES (?, 'Essai_7_Jours', 'UNUSED', 'GRATUIT_TRIAL')", (trial_key,))
    conn.commit()
    conn.close()
    return render_template_string(SUCCESS_TEMPLATE, key=trial_key, title="🎁 Essai Gratuit de 7 Jours Activé")

@app.route('/client-login', methods=['POST'])
def client_login():
    key = request.form.get('existing_key', '').strip()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM keys WHERE key_code = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return render_template_string(SUCCESS_TEMPLATE, key=key, title="🛡️ Clé Validée avec Succès")
    else:
        return render_template_string(ERROR_TEMPLATE, message="Clé introuvable ou invalide.")

DASHBOARD_TEMPLATE = NAVBAR_HTML + """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Stats - GlobalRoute AI</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { font-family: 'Inter', system-ui, sans-serif; background: #090d16; color: #f8fafc; margin: 0; padding: 0; }
        .main-container { max-width: 1000px; margin: 20px auto; padding: 15px; }
        .card { background: #162032; padding: 25px; border-radius: 20px; border: 1px solid rgba(56, 189, 248, 0.15); }
        .stats-grid { display: flex; gap: 15px; margin: 20px 0; flex-wrap: wrap; }
        .stat-box { background: #0f172a; flex: 1; min-width: 140px; padding: 20px; border-radius: 14px; text-align: center; border-left: 4px solid #38bdf8; }
        .stat-value { font-size: 26px; font-weight: 800; color: #38bdf8; margin-top: 5px; }
    </style>
</head>
<body>
    <div class="main-container">
        <div class="card">
            <h1>📊 Statistiques de la plateforme</h1>
            <div class="stats-grid">
                <div class="stat-box">
                    <div style="color: #94a3b8; font-size: 11px;">TOTAL CLÉS</div>
                    <div class="stat-value">{{ total_keys }}</div>
                </div>
                <div class="stat-box" style="border-left-color: #38bdf8;">
                    <div style="color: #94a3b8; font-size: 11px;">PASS 30J</div>
                    <div class="stat-value" style="color: #38bdf8;">{{ count_30 }}</div>
                </div>
                <div class="stat-box" style="border-left-color: #10b981;">
                    <div style="color: #94a3b8; font-size: 11px;">PASS 365J</div>
                    <div class="stat-value" style="color: #10b981;">{{ count_365 }}</div>
                </div>
            </div>
            <div style="height: 250px; background: #0f172a; padding: 15px; border-radius: 14px;">
                <canvas id="salesChart"></canvas>
            </div>
        </div>
    </div>
    <script>
        const ctx = document.getElementById('salesChart').getContext('2d');
        new Chart(ctx, {
            type: 'bar',
            data: {
                labels: ['Pass 30 Jours', 'Pass 365 Jours'],
                datasets: [{
                    label: 'Ventes',
                    data: [{{ count_30 }}, {{ count_365 }}],
                    backgroundColor: ['#38bdf8', '#10b981'],
                    borderRadius: 8
                }]
            },
            options: { responsive: true, maintainAspectRatio: false, scales: { y: { ticks: { color: '#94a3b8' } }, x: { ticks: { color: '#94a3b8' } } } }
        });
    </script>
</body>
</html>
"""

@app.route('/dashboard')
def dashboard():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*), SUM(CASE WHEN plan LIKE '%30%' THEN 1 ELSE 0 END), SUM(CASE WHEN plan LIKE '%365%' THEN 1 ELSE 0 END) FROM keys")
    total_keys, count_30, count_365 = cursor.fetchone()
    conn.close()
    return render_template_string(DASHBOARD_TEMPLATE, total_keys=total_keys or 0, count_30=count_30 or 0, count_365=count_365 or 0)

CHECKOUT_TEMPLATE = NAVBAR_HTML + """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Paiement Solana</title>
    <style>
        body { font-family: 'Inter', system-ui, sans-serif; background: #090d16; color: #f8fafc; margin: 0; padding: 0; }
        .main-container { max-width: 600px; margin: 20px auto; padding: 15px; }
        .card { background: #162032; padding: 25px; border-radius: 20px; text-align: center; border: 1px solid rgba(56, 189, 248, 0.15); }
        .wallet-box { background: #090d16; padding: 12px; border-radius: 10px; font-family: monospace; color: #38bdf8; margin: 15px 0; font-size: 12px; word-break: break-all; }
        input[type="text"] { width: 100%; padding: 12px; border-radius: 10px; border: 1px solid rgba(148, 163, 184, 0.3); background: #090d16; color: #fff; margin-bottom: 15px; }
        .btn { background: #10b981; color: #fff; padding: 12px; border: none; border-radius: 10px; font-weight: 700; cursor: pointer; width: 100%; }
    </style>
</head>
<body>
    <div class="main-container">
        <div class="card">
            <h1>🛡️ Paiement Solana</h1>
            <p style="color: #94a3b8;">Formule : <strong>{{ plan_formatted }}</strong> (<strong>{{ price }} SOL</strong>)</p>
            <div class="wallet-box" id="wAddr">{{ merchant_wallet }}</div>
            <form action="/verify-payment" method="POST">
                <input type="hidden" name="plan" value="{{ plan }}">
                <input type="hidden" name="price" value="{{ price }}">
                <input type="text" name="tx_signature" placeholder="Collez la signature de la transaction..." required>
                <button type="submit" class="btn">Vérifier et obtenir la clé</button>
            </form>
            <br><a href="/" style="color: #94a3b8; font-size: 13px; text-decoration: none;">← Retour</a>
        </div>
    </div>
</body>
</html>
"""

@app.route('/checkout')
def checkout():
    plan = request.args.get('plan')
    price = request.args.get('price')
    if not plan or not price:
        return redirect(url_for('index'))
    return render_template_string(CHECKOUT_TEMPLATE, plan=plan, plan_formatted=plan.replace('_', ' '), price=price, merchant_wallet=MERCHANT_SOL_WALLET)

SUCCESS_TEMPLATE = NAVBAR_HTML + """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Succès</title>
    <style>body { font-family: 'Inter', sans-serif; background: #090d16; color: #f8fafc; padding: 20px; text-align: center; }</style>
</head>
<body>
    <div style="max-width: 500px; margin: 30px auto; background: #162032; padding: 25px; border-radius: 20px; border: 1px solid #10b981;">
        <h1 style="color: #10b981; font-size: 22px;">{{ title }}</h1>
        <div style="background: #090d16; padding: 12px; border-radius: 10px; font-family: monospace; color: #10b981; margin: 15px 0; font-weight: bold;">{{ key }}</div>
        <a href="/" style="color: #38bdf8; text-decoration: none; font-weight: bold;">← Accueil</a>
    </div>
</body>
</html>
"""

ERROR_TEMPLATE = NAVBAR_HTML + """
<!DOCTYPE html>
<html lang="fr">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Erreur</title><style>body{background:#090d16;color:#fff;font-family:sans-serif;text-align:center;padding:20px;}</style></head>
<body>
    <div style="max-width:500px; margin:30px auto; background:#162032; padding:25px; border-radius:20px; border:1px solid #ef4444;">
        <h2 style="color:#ef4444;">Échec</h2>
        <p style="color:#94a3b8;">{{ message }}</p>
        <a href="/" style="color:#38bdf8; text-decoration:none;">Réessayer</a>
    </div>
</body>
</html>
"""

@app.route('/verify-payment', methods=['POST'])
def verify_payment():
    plan = request.form.get('plan')
    expected_price = float(request.form.get('price', 10.0))
    tx_signature = request.form.get('tx_signature', '').strip()
    is_valid, message = verify_solana_transaction(tx_signature, expected_price)
    if is_valid:
        new_key = f"KEY-VERIFIED-{secrets.token_hex(4).upper()}"
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO keys (key_code, plan, status, tx_signature) VALUES (?, ?, 'UNUSED', ?)", (new_key, plan, tx_signature))
        conn.commit()
        conn.close()
        return render_template_string(SUCCESS_TEMPLATE, key=new_key, title="🛡️ Clé Validée avec Succès")
    else:
        return render_template_string(ERROR_TEMPLATE, message=message)

ADMIN_TEMPLATE = NAVBAR_HTML + """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin - GlobalRoute AI</title>
    <style>body { font-family: 'Inter', sans-serif; background: #090d16; color: #f8fafc; margin: 0; padding: 0; }</style>
</head>
<body>
    <div style="max-width: 1000px; margin: 20px auto; background: #162032; padding: 25px; border-radius: 20px; border: 1px solid rgba(56,189,248,0.2);">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:15px; flex-wrap: wrap; gap: 10px;">
            <h1 style="font-size: 20px; margin:0; color:#38bdf8;">Panel Admin - Gestion des Clés</h1>
            <a href="/logout" style="color:#ef4444; text-decoration:none; font-weight:bold; font-size:13px; border: 1px solid #ef4444; padding: 6px 12px; border-radius: 6px;">Déconnexion</a>
        </div>

        <!-- Section de génération manuelle de clé par l'Admin -->
        <div style="background:#0f172a; padding:15px; border-radius:12px; margin-bottom:20px; border: 1px solid rgba(56,189,248,0.2);">
            <h3 style="margin-top:0; font-size:15px; color:#38bdf8;">🛠️️ Générer une clé de test pour une entreprise</h3>
            <form action="/admin/generate-key" method="POST" style="display:flex; gap:10px; flex-wrap:wrap;">
                <select name="plan_type" style="padding:10px; border-radius:8px; background:#162032; color:#fff; border:1px solid rgba(148,163,184,0.3); outline:none;">
                    <option value="Test_Entreprise_7J">Test Entreprise (7 Jours)</option>
                    <option value="Pass_30_Jours">Pass 30 Jours</option>
                    <option value="Pass_365_Jours">Pass 365 Jours</option>
                </select>
                <button type="submit" style="background:#38bdf8; color:#0f172a; padding:10px 15px; border:none; border-radius:8px; font-weight:bold; cursor:pointer;">Générer Clé Manuelle</button>
            </form>
        </div>

        <div style="overflow-x: auto;">
            <table style="width:100%; border-collapse:collapse; font-size: 13px; text-align:left;">
                <tr style="background:#0f172a; color:#38bdf8;"><th style="padding:10px;">ID</th><th style="padding:10px;">Clé</th><th style="padding:10px;">Formule</th><th style="padding:10px;">Statut</th><th style="padding:10px;">Date</th></tr>
                {{ rows_html | safe }}
            </table>
        </div>
    </div>
</body>
</html>
"""

LOGIN_TEMPLATE = NAVBAR_HTML + """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Connexion Admin</title>
    <style>body { font-family: 'Inter', sans-serif; background: #090d16; color: #f8fafc; margin: 0; padding: 0; }</style>
</head>
<body>
    <div style="display:flex; justify-content:center; align-items:center; height:70vh; padding:15px;">
        <div style="background:#162032; padding:25px; border-radius:20px; width:100%; max-width:350px; text-align:center; border:1px solid rgba(56,189,248,0.2);">
            <h2 style="font-size: 20px; margin-top:0; color:#38bdf8;">🔒 Espace Admin</h2>
            {% if error %}
            <p style="color:#ef4444; font-size:13px; margin-bottom:15px;">{{ error }}</p>
            {% endif %}
            <form action="/admin" method="POST">
                <!-- type="password" garantit que les caractères sont masqués par des points -->
                <input type="password" name="password" placeholder="Mot de passe" required style="width:100%; padding:12px; margin-bottom:15px; border-radius:10px; border:1px solid rgba(148,163,184,0.3); background:#090d16; color:#fff; outline:none; font-size:14px;"><br>
                <button type="submit" style="background:linear-gradient(135deg, #38bdf8, #0ea5e9); color:#0f172a; padding:12px; border:none; border-radius:10px; font-weight:bold; width:100%; cursor:pointer; font-size:14px;">Entrer</button>
            </form>
        </div>
    </div>
</body>
</html>
"""

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    error_msg = None
    if request.method == 'POST':
        entered_password = request.form.get('password', '').strip()
        if entered_password == ADMIN_PASSWORD:
            session['admin_logged'] = True
            return redirect(url_for('admin'))
        else:
            error_msg = "Mot de passe incorrect."
            
    if session.get('admin_logged'):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT id, key_code, plan, status, created_at FROM keys ORDER BY id DESC")
        keys = cursor.fetchall()
        conn.close()
        
        rows_html = "".join([f"<tr><td style='padding:10px; border-bottom:1px solid #0f172a;'>{k[0]}</td><td style='padding:10px; border-bottom:1px solid #0f172a; font-family:monospace; color:#38bdf8;'>{k[1]}</td><td style='padding:10px; border-bottom:1px solid #0f172a;'>{k[2]}</td><td style='padding:10px; border-bottom:1px solid #0f172a;'>{k[3]}</td><td style='padding:10px; border-bottom:1px solid #0f172a; color:#94a3b8;'>{k[4]}</td></tr>" for k in keys]) if keys else "<tr><td colspan='5' style='padding:15px; text-align:center; color:#94a3b8;'>Aucune clé enregistrée pour le moment.</td></tr>"
        
        return render_template_string(ADMIN_TEMPLATE, rows_html=rows_html)
    
    return render_template_string(LOGIN_TEMPLATE, error=error_msg)

@app.route('/admin/generate-key', methods=['POST'])
def generate_key_admin():
    if not session.get('admin_logged'):
        return redirect(url_for('admin'))
    
    plan_type = request.form.get('plan_type', 'Test_Entreprise_7J')
    manual_key = f"MANUAL-{secrets.token_hex(4).upper()}"
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO keys (key_code, plan, status, tx_signature) VALUES (?, ?, 'UNUSED', 'MANUAL_GENERATION')", (manual_key, plan_type))
    conn.commit()
    conn.close()
    
    return redirect(url_for('admin'))

@app.route('/logout')
def logout():
    session.pop('admin_logged', None)
    return redirect(url_for('index'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
