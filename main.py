import os
import secrets
import sqlite3
from flask import Flask, render_template_string, request, redirect, url_for, session, flash
import requests

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

DB_NAME = "database.db"
ADMIN_PASSWORD = "admin"  
MERCHANT_SOL_WALLET = "22BzBEYLewJkKe2FXD6EHJYqX4NNshMw9roNw9qFxV9d"  

# Tarifs officiels
PRICE_30_DAYS_USD = 1500
PRICE_365_DAYS_USD = 17500
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
            
            account_addresses = []
            for acc in account_keys:
                if isinstance(acc, dict):
                    account_addresses.append(acc.get("pubkey"))
                else:
                    account_addresses.append(str(acc))
            
            if MERCHANT_SOL_WALLET not in account_addresses:
                return False, "L'adresse du portefeuille destinataire ne correspond pas au marchand."
            
            pre_balances = meta.get("preBalances", [])
            post_balances = meta.get("postBalances", [])
            
            merchant_index = -1
            for idx, addr in enumerate(account_addresses):
                if addr == MERCHANT_SOL_WALLET:
                    merchant_index = idx
                    break
            
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

# --- NAVBAR COMMUNE RESPONSIVE ---
NAVBAR_HTML = """
<nav style="background: rgba(15, 23, 42, 0.95); backdrop-filter: blur(12px); border-bottom: 1px solid rgba(56, 189, 248, 0.15); padding: 14px 20px; display: flex; justify-content: space-between; align-items: center; position: sticky; top: 0; z-index: 1000; box-shadow: 0 4px 20px rgba(0,0,0,0.3); flex-wrap: wrap; gap: 10px;">
    <div style="font-size: 18px; font-weight: 800; color: #38bdf8; display: flex; align-items: center; gap: 8px; letter-spacing: -0.5px;">
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
    <title>GlobalRoute AI - Passerelle de Paiement Solana</title>
    <style>
        * { box-sizing: border-box; }
        body { font-family: 'Inter', system-ui, -apple-system, sans-serif; background: #090d16; color: #f8fafc; margin: 0; padding: 0; }
        .main-container { max-width: 1100px; margin: 20px auto; padding: 15px; }
        .hero { text-align: center; padding: 30px 15px; background: radial-gradient(circle at center, #1e293b 0%, #0f172a 100%); border-radius: 20px; border: 1px solid rgba(56, 189, 248, 0.2); box-shadow: 0 20px 50px rgba(0,0,0,0.6); }
        h1 { color: #f8fafc; font-size: 26px; margin-bottom: 15px; font-weight: 800; letter-spacing: -1px; }
        @media(min-width: 768px) { h1 { font-size: 38px; } }
        h1 span { background: linear-gradient(135deg, #38bdf8, #818cf8); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .subtitle { color: #94a3b8; font-size: 15px; margin-bottom: 25px; max-width: 650px; margin-left: auto; margin-right: auto; line-height: 1.5; }
        
        /* Espace de connexion pour les clients possédant déjà une clé */
        .client-login-box { background: linear-gradient(145deg, #162032 0%, #0f172a 100%); border: 1px solid rgba(56, 189, 248, 0.3); padding: 25px; border-radius: 16px; margin: 30px 0; text-align: center; box-shadow: 0 10px 30px rgba(0,0,0,0.4); }
        .client-login-box h3 { margin-top: 0; color: #38bdf8; font-size: 18px; font-weight: 700; }
        .client-login-form { display: flex; gap: 10px; max-width: 500px; margin: 15px auto 0 auto; flex-direction: column; }
        @media(min-width: 480px) { .client-login-form { flex-direction: row; } }
        .client-login-input { flex: 1; padding: 12px 15px; border-radius: 10px; border: 1px solid rgba(148, 163, 184, 0.3); background: #090d16; color: #fff; font-size: 14px; outline: none; }
        .client-login-btn { background: linear-gradient(135deg, #38bdf8, #0ea5e9); color: #0f172a; padding: 12px 20px; border: none; border-radius: 10px; font-weight: 700; cursor: pointer; font-size: 14px; }

        .plans { display: flex; gap: 20px; justify-content: center; margin-top: 30px; flex-wrap: wrap; }
        .plan-card { background: linear-gradient(145deg, #162032 0%, #0f172a 100%); padding: 30px 20px; border-radius: 20px; width: 100%; max-width: 450px; text-align: center; border: 1px solid rgba(56, 189, 248, 0.15); position: relative; box-shadow: 0 10px 30px rgba(0,0,0,0.4); }
        .plan-card.popular { border-color: #10b981; background: linear-gradient(145deg, #132822 0%, #0f172a 100%); }
        .price { font-size: 32px; font-weight: 800; color: #f8fafc; margin: 20px 0; }
        .subtext { font-size: 14px; color: #94a3b8; margin-bottom: 20px; line-height: 1.5; }
        .btn { background: linear-gradient(135deg, #38bdf8, #0ea5e9); color: #0f172a; padding: 14px 24px; border: none; border-radius: 12px; font-weight: 700; cursor: pointer; text-decoration: none; display: inline-block; width: 100%; font-size: 15px; box-shadow: 0 4px 15px rgba(56, 189, 248, 0.3); }
        .btn-green { background: linear-gradient(135deg, #10b981, #059669); color: white; box-shadow: 0 4px 15px rgba(16, 185, 129, 0.3); }
        .verified-badge { background: rgba(16, 185, 129, 0.12); color: #34d399; padding: 6px 14px; border-radius: 30px; font-size: 12px; font-weight: 700; display: inline-flex; align-items: center; gap: 6px; margin-bottom: 20px; border: 1px solid rgba(16, 185, 129, 0.3); }
    </style>
</head>
<body>
    <div class="main-container">
        <div class="hero">
            <div><span class="verified-badge">🛡️ Passerelle Solana Certifiée & Sécurisée</span></div>
            <h1>Intelligence Artificielle & <span>Réseaux Avancés</span></h1>
            <p class="subtitle">Bénéficiez d'un accès instantané, sécurisé et entièrement validé par la blockchain Solana pour propulser vos projets.</p>
        </div>

        <!-- Espace de connexion pour les personnes possédant déjà une clé -->
        <div class="client-login-box">
            <h3>🔑 Vous possédez déjà une clé d'accès ?</h3>
            <p style="color: #94a3b8; font-size: 13px; margin: 5px 0 15px 0;">Entrez votre clé ci-dessous pour vous connecter directement à votre espace.</p>
            <form action="/client-login" method="POST" class="client-login-form">
                <input type="text" name="existing_key" class="client-login-input" placeholder="Collez votre clé ici (ex: KEY-...)" required>
                <button type="submit" class="client-login-btn">Accéder</button>
            </form>
        </div>
        
        <div class="plans">
            <div class="plan-card">
                <h3>Pass 30 Jours</h3>
                <p class="subtext">Accès complet à l'ensemble des modules et optimisations illimitées pendant un mois.</p>
                <div class="price">1 500 $<br><span style="font-size:15px; color:#34d399; font-weight:600;">(~{{ price_30 }} SOL)</span></div>
                <a href="/checkout?plan=Pass_30_Jours&price={{ price_30 }}" class="btn">Sélectionner ce Pass</a>
            </div>
            
            <div class="plan-card popular">
                <div style="position: absolute; top: -12px; right: 20px; background: #10b981; color: white; padding: 4px 12px; font-size: 11px; border-radius: 20px; font-weight: 800;">MEILLEUR CHOIX</div>
                <h3>Pass 365 Jours</h3>
                <p class="subtext">Accès illimité sur toute l'année, conçu spécifiquement pour les professionnels exigeants.</p>
                <div class="price">17 500 $<br><span style="font-size:15px; color:#34d399; font-weight:600;">(~{{ price_365 }} SOL)</span></div>
                <a href="/checkout?plan=Pass_365_Jours&price={{ price_365 }}" class="btn btn-green">Sélectionner ce Pass</a>
            </div>
        </div>
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(INDEX_TEMPLATE, price_30=PRICE_30_DAYS_SOL, price_365=PRICE_365_DAYS_SOL)

@app.route('/client-login', methods=['POST'])
def client_login():
    key = request.form.get('existing_key', '').strip()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM keys WHERE key_code = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return render_template_string(SUCCESS_TEMPLATE, key=key)
    else:
        return render_template_string(ERROR_TEMPLATE, message="Clé introuvable ou invalide dans notre base de données.")

DASHBOARD_TEMPLATE = NAVBAR_HTML + """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Espace Statistiques - GlobalRoute AI</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * { box-sizing: border-box; }
        body { font-family: 'Inter', system-ui, -apple-system, sans-serif; background: #090d16; color: #f8fafc; margin: 0; padding: 0; }
        .main-container { max-width: 1100px; margin: 20px auto; padding: 15px; }
        .card { background: linear-gradient(145deg, #162032 0%, #0f172a 100%); padding: 25px; border-radius: 20px; border: 1px solid rgba(56, 189, 248, 0.15); box-shadow: 0 20px 40px rgba(0,0,0,0.5); }
        h1 { color: #f8fafc; margin-top: 0; font-size: 22px; font-weight: 800; }
        .stats-grid { display: flex; gap: 15px; margin: 20px 0; flex-wrap: wrap; }
        .stat-box { background: rgba(15, 23, 42, 0.7); flex: 1; min-width: 140px; padding: 20px; border-radius: 14px; text-align: center; border: 1px solid rgba(56, 189, 248, 0.1); border-left: 4px solid #38bdf8; }
        .stat-value { font-size: 26px; font-weight: 800; color: #38bdf8; margin-top: 5px; }
        .chart-container { position: relative; height: 300px; width: 100%; margin-top: 15px; background: rgba(15, 23, 42, 0.5); padding: 15px; border-radius: 14px; border: 1px solid rgba(56, 189, 248, 0.1); }
    </style>
</head>
<body>
    <div class="main-container">
        <div class="card">
            <h1>📊 Tableau de Bord et Statistiques</h1>
            <p style="color: #94a3b8; font-size: 14px;">Analyse en temps réel de l'activité de la plateforme.</p>
            
            <div class="stats-grid">
                <div class="stat-box">
                    <div style="color: #94a3b8; font-size: 11px; font-weight: 600; text-transform: uppercase;">Total Clés</div>
                    <div class="stat-value">{{ total_keys }}</div>
                </div>
                <div class="stat-box" style="border-left-color: #38bdf8;">
                    <div style="color: #94a3b8; font-size: 11px; font-weight: 600; text-transform: uppercase;">Pass 30J</div>
                    <div class="stat-value" style="color: #38bdf8;">{{ count_30 }}</div>
                </div>
                <div class="stat-box" style="border-left-color: #10b981;">
                    <div style="color: #94a3b8; font-size: 11px; font-weight: 600; text-transform: uppercase;">Pass 365J</div>
                    <div class="stat-value" style="color: #10b981;">{{ count_365 }}</div>
                </div>
            </div>

            <div class="chart-container">
                <canvas id="salesChart"></canvas>
            </div>
        </div>
    </div>

    <script>
        const ctx = document.getElementById('salesChart').getContext('2d');
        const salesChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: ['Pass 30 Jours', 'Pass 365 Jours'],
                datasets: [{
                    label: 'Abonnements',
                    data: [{{ count_30 }}, {{ count_365 }}],
                    backgroundColor: ['rgba(56, 189, 248, 0.85)', 'rgba(16, 185, 129, 0.85)'],
                    borderColor: ['#38bdf8', '#10b981'],
                    borderWidth: 2,
                    borderRadius: 8,
                    barThickness: 40
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { labels: { color: '#f8fafc', font: { family: 'Inter', weight: '600' } } } },
                scales: {
                    y: { ticks: { color: '#94a3b8' }, grid: { color: 'rgba(51, 65, 85, 0.4)' } },
                    x: { ticks: { color: '#94a3b8', font: { weight: '600' } }, grid: { display: false } }
                }
            }
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
    <title>Paiement Sécurisé Solana</title>
    <style>
        * { box-sizing: border-box; }
        body { font-family: 'Inter', system-ui, -apple-system, sans-serif; background: #090d16; color: #f8fafc; margin: 0; padding: 0; }
        .main-container { max-width: 680px; margin: 20px auto; padding: 15px; }
        .card { background: linear-gradient(145deg, #162032 0%, #0f172a 100%); padding: 30px 20px; border-radius: 20px; box-shadow: 0 20px 40px rgba(0,0,0,0.6); text-align: center; border: 1px solid rgba(56, 189, 248, 0.15); }
        h1 { color: #f8fafc; margin-top: 0; font-size: 22px; font-weight: 800; }
        .wallet-box { background: #090d16; padding: 15px; border-radius: 12px; font-family: monospace; font-size: 13px; margin: 15px 0; word-break: break-all; color: #38bdf8; border: 1px dashed rgba(56, 189, 248, 0.4); display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-direction: column; }
        @media(min-width: 480px) { .wallet-box { flex-direction: row; } }
        input[type="text"] { width: 100%; padding: 14px; border-radius: 10px; border: 1px solid rgba(148, 163, 184, 0.3); background: #090d16; color: #fff; margin-bottom: 15px; font-size: 14px; outline: none; }
        .btn { background: linear-gradient(135deg, #10b981, #059669); color: #fff; padding: 14px 20px; border: none; border-radius: 10px; font-weight: 700; cursor: pointer; font-size: 15px; width: 100%; box-shadow: 0 4px 15px rgba(16, 185, 129, 0.3); }
        .copy-btn { background: rgba(56, 189, 248, 0.15); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.3); padding: 8px 14px; border-radius: 8px; cursor: pointer; font-weight: 700; font-size: 12px; white-space: nowrap; }
        .info-text { font-size: 14px; color: #94a3b8; line-height: 1.5; margin-bottom: 15px; }
    </style>
</head>
<body>
    <div class="main-container">
        <div class="card">
            <h1>🛡️ Validation Blockchain Solana</h1>
            <p class="info-text">Formule choisie : <strong style="color: #f8fafc;">{{ plan_formatted }}</strong><br>
            Montant exact requis : <strong style="color: #10b981; font-size: 20px;">{{ price }} SOL</strong></p>
            
            <p class="info-text">Effectuez votre virement vers l'adresse marchand officielle :</p>
            <div class="wallet-box">
                <span id="walletText">{{ merchant_wallet }}</span>
                <button class="copy-btn" onclick="copyWallet()">📋 Copier</button>
            </div>
            
            <p class="info-text">Collez ci-dessous la signature de la transaction (Tx Signature) :</p>
            
            <form action="/verify-payment" method="POST">
                <input type="hidden" name="plan" value="{{ plan }}">
                <input type="hidden" name="price" value="{{ price }}">
                <input type="text" name="tx_signature" placeholder="Collez la signature..." required><br>
                <button type="submit" class="btn">Vérifier et obtenir ma clé</button>
            </form>
            <br>
            <a href="/" style="color: #94a3b8; text-decoration: none; font-size: 13px; font-weight: 600;">← Retour à l'accueil</a>
        </div>
    </div>

    <script>
        function copyWallet() {
            const wallet = document.getElementById('walletText').innerText;
            navigator.clipboard.writeText(wallet);
            alert('Adresse Solana copiée.');
        }
    </script>
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
    <title>Paiement Validé - GlobalRoute AI</title>
    <style>
        * { box-sizing: border-box; }
        body { font-family: 'Inter', system-ui, -apple-system, sans-serif; background: #090d16; color: #f8fafc; margin: 0; padding: 0; }
        .main-container { max-width: 680px; margin: 20px auto; padding: 15px; }
        .card { background: linear-gradient(145deg, #162032 0%, #0f172a 100%); padding: 30px 20px; border-radius: 20px; text-align: center; box-shadow: 0 20px 40px rgba(0,0,0,0.6); border: 1px solid rgba(16, 185, 129, 0.3); }
        .key-box { background: #090d16; padding: 15px; border-radius: 12px; font-size: 16px; font-family: monospace; font-weight: 800; color: #10b981; margin: 20px 0; border: 1px solid rgba(16, 185, 129, 0.4); display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-direction: column; }
        @media(min-width: 480px) { .key-box { flex-direction: row; } }
        .copy-btn { background: linear-gradient(135deg, #10b981, #059669); color: white; border: none; padding: 10px 16px; border-radius: 8px; cursor: pointer; font-weight: 700; font-size: 13px; white-space: nowrap; }
    </style>
</head>
<body>
    <div class="main-container">
        <div class="card">
            <h1 style="color: #10b981; margin-top:0; font-size: 24px; font-weight: 800;">🛡️ Paiement Confirmé</h1>
            <p style="color: #94a3b8; font-size: 14px;">Votre transaction a été certifiée. Voici votre clé d'accès unique :</p>
            
            <div class="key-box">
                <span id="keyText">{{ key }}</span>
                <button class="copy-btn" onclick="copyKey()">Copier</button>
            </div>
            
            <a href="/" style="color: #38bdf8; text-decoration: none; font-weight: 700; font-size: 14px;">← Retour à l'accueil</a>
        </div>
    </div>
    <script>
        function copyKey() {
            navigator.clipboard.writeText(document.getElementById('keyText').innerText);
            alert('Clé copiée.');
        }
    </script>
</body>
</html>
"""

ERROR_TEMPLATE = NAVBAR_HTML + """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Échec de Vérification</title>
    <style>body { font-family: 'Inter', system-ui, sans-serif; background: #090d16; color: #f8fafc; margin: 0; padding: 0; text-align: center; }</style>
</head>
<body>
    <div style="max-width:500px; margin:40px auto; background:linear-gradient(145deg, #162032 0%, #0f172a 100%); padding:30px 20px; border-radius:20px; border:1px solid rgba(239, 68, 68, 0.3);">
        <h2 style="color:#ef4444; margin-top:0; font-size: 22px; font-weight: 800;">🛡️ Échec de la vérification</h2>
        <p style="color:#94a3b8; line-height:1.5; margin-bottom:25px; font-size: 14px;">{{ message }}</p>
        <a href="/" style="color:#38bdf8; text-decoration:none; font-weight:700; font-size: 14px;">← Réessayer</a>
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
        new_key = f"KEY-VERIFIED-{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}"
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO keys (key_code, plan, status, tx_signature) VALUES (?, ?, 'UNUSED', ?)", (new_key, plan, tx_signature))
        conn.commit()
        conn.close()
        return render_template_string(SUCCESS_TEMPLATE, key=new_key)
    else:
        return render_template_string(ERROR_TEMPLATE, message=message)

ADMIN_TEMPLATE = NAVBAR_HTML + """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Administration</title>
    <style>
        * { box-sizing: border-box; }
        body { font-family: 'Inter', system-ui, sans-serif; background: #090d16; color: #f8fafc; margin: 0; padding: 0; }
        .main-container { max-width: 1100px; margin: 20px auto; background: linear-gradient(145deg, #162032 0%, #0f172a 100%); padding: 25px; border-radius: 20px; border: 1px solid rgba(56, 189, 248, 0.15); }
    </style>
</head>
<body>
    <div class="main-container">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:20px; flex-wrap:wrap; gap:10px;">
            <h1 style="color:#f8fafc; margin:0; font-size: 22px; font-weight: 800;">Administration</h1>
            <a href="/logout" style="color:#ef4444; text-decoration:none; font-weight:700; background:rgba(239, 68, 68, 0.15); padding:8px 15px; border-radius:8px; font-size: 13px;">Se déconnecter</a>
        </div>
        <div style="overflow-x: auto;">
            <table style="width:100%; border-collapse:collapse; margin-top:10px; text-align:left; font-size: 13px;">
                <tr style="background:rgba(15, 23, 42, 0.8); color:#38bdf8; text-transform: uppercase;">
                    <th style="padding:12px;">ID</th>
                    <th style="padding:12px;">Clé d'Accès</th>
                    <th style="padding:12px;">Formule</th>
                    <th style="padding:12px;">Statut</th>
                </tr>
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
    <style>body { font-family: 'Inter', system-ui, sans-serif; background: #090d16; color: #f8fafc; margin: 0; padding: 0; }</style>
</head>
<body>
    <div style="display:flex; justify-content:center; align-items:center; height:75vh; padding: 15px;">
        <div style="background:linear-gradient(145deg, #162032 0%, #0f172a 100%); padding:30px 20px; border-radius:20px; width:100%; max-width:380px; text-align:center; border:1px solid rgba(56, 189, 248, 0.15);">
            <h2 style="color:#f8fafc; margin-top:0; font-size: 22px; font-weight: 800;">Connexion Admin</h2>
            <form method="POST">
                <input type="password" name="password" placeholder="Mot de passe" required style="width:100%; padding:14px; margin-bottom:15px; border-radius:10px; border:1px solid rgba(148, 163, 184, 0.3); background:#090d16; color:#fff; font-size:14px; outline:none;"><br>
                <button type="submit" style="background:linear-gradient(135deg, #38bdf8, #0ea5e9); color:#0f172a; padding:14px; border:none; border-radius:10px; font-weight:800; cursor:pointer; width:100%; font-size:15px;">Se connecter</button>
            </form>
        </div>
    </div>
</body>
</html>
"""

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['logged_in'] = True
        else:
            flash("Mot de passe incorrect")
            
    if session.get('logged_in'):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT id, key_code, plan, status, created_at, tx_signature FROM keys ORDER BY id DESC")
        keys = cursor.fetchall()
        conn.close()
        
        rows_html = "".join([f"<tr><td style='padding:12px; border-bottom:1px solid rgba(51, 65, 85, 0.4);'>{k[0]}</td><td style='padding:12px; border-bottom:1px solid rgba(51, 65, 85, 0.4); font-family:monospace; color:#38bdf8;'>{k[1]}</td><td style='padding:12px; border-bottom:1px solid rgba(51, 65, 85, 0.4);'>{k[2]}</td><td style='padding:12px; border-bottom:1px solid rgba(51, 65, 85, 0.4);'>{k[3]}</td></tr>" for k in keys]) if keys else "<tr><td colspan='4' style='padding:20px; text-align:center; color:#94a3b8;'>Aucune clé enregistrée.</td></tr>"
            
        return render_template_string(ADMIN_TEMPLATE, rows_html=rows_html)
    return render_template_string(LOGIN_TEMPLATE)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('index'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
