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

# --- NAVBAR COMMUNE ---
NAVBAR_HTML = """
<nav style="background: rgba(15, 23, 42, 0.9); backdrop-filter: blur(12px); border-bottom: 1px solid rgba(56, 189, 248, 0.15); padding: 18px 40px; display: flex; justify-content: space-between; align-items: center; position: sticky; top: 0; z-index: 1000; box-shadow: 0 4px 20px rgba(0,0,0,0.3);">
    <div style="font-size: 22px; font-weight: 800; color: #38bdf8; display: flex; align-items: center; gap: 12px; letter-spacing: -0.5px;">
        <span style="background: linear-gradient(135deg, #38bdf8, #818cf8); padding: 8px; border-radius: 10px; color: #0f172a; font-size: 16px;">🚀</span> GlobalRoute AI
    </div>
    <div style="display: flex; gap: 30px; align-items: center;">
        <a href="/" style="color: #cbd5e1; text-decoration: none; font-weight: 600; font-size: 15px; transition: 0.25s;" onmouseover="this.style.color='#38bdf8'" onmouseout="this.style.color='#cbd5e1'">Accueil</a>
        <a href="/dashboard" style="color: #cbd5e1; text-decoration: none; font-weight: 600; font-size: 15px; transition: 0.25s;" onmouseover="this.style.color='#38bdf8'" onmouseout="this.style.color='#cbd5e1'">📊 Espace Statistiques</a>
        <a href="/admin" style="color: #94a3b8; text-decoration: none; font-weight: 600; font-size: 15px; border: 1px solid rgba(148, 163, 184, 0.2); padding: 8px 16px; border-radius: 8px; transition: 0.25s;" onmouseover="this.style.color='#38bdf8'; this.style.borderColor='#38bdf8'" onmouseout="this.style.color='#94a3b8'; this.style.borderColor='rgba(148, 163, 184, 0.2)'">🔒 Administration</a>
    </div>
</nav>
"""

INDEX_TEMPLATE = NAVBAR_HTML + """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <title>GlobalRoute AI - Passerelle de Paiement Solana</title>
    <style>
        body { font-family: 'Inter', system-ui, -apple-system, sans-serif; background: #090d16; color: #f8fafc; margin: 0; padding: 0; }
        .main-container { max-width: 1100px; margin: 50px auto; padding: 20px; }
        .hero { text-align: center; padding: 60px 30px; background: radial-gradient(circle at center, #1e293b 0%, #0f172a 100%); border-radius: 24px; border: 1px solid rgba(56, 189, 248, 0.2); box-shadow: 0 20px 50px rgba(0,0,0,0.6); }
        h1 { color: #f8fafc; font-size: 42px; margin-bottom: 15px; font-weight: 800; letter-spacing: -1px; }
        h1 span { background: linear-gradient(135deg, #38bdf8, #818cf8); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .subtitle { color: #94a3b8; font-size: 18px; margin-bottom: 35px; max-width: 650px; margin-left: auto; margin-right: auto; line-height: 1.6; }
        .plans { display: flex; gap: 30px; justify-content: center; margin-top: 50px; flex-wrap: wrap; }
        .plan-card { background: linear-gradient(145deg, #162032 0%, #0f172a 100%); padding: 40px 30px; border-radius: 20px; width: 42%; min-width: 300px; text-align: center; border: 1px solid rgba(56, 189, 248, 0.15); transition: all 0.3s ease; position: relative; box-shadow: 0 10px 30px rgba(0,0,0,0.4); }
        .plan-card:hover { border-color: #38bdf8; transform: translateY(-6px); box-shadow: 0 20px 40px rgba(56, 189, 248, 0.15); }
        .plan-card.popular { border-color: #10b981; background: linear-gradient(145deg, #132822 0%, #0f172a 100%); }
        .plan-card.popular:hover { border-color: #34d399; }
        .price { font-size: 38px; font-weight: 800; color: #f8fafc; margin: 25px 0; }
        .subtext { font-size: 15px; color: #94a3b8; margin-bottom: 25px; line-height: 1.5; }
        .btn { background: linear-gradient(135deg, #38bdf8, #0ea5e9); color: #0f172a; padding: 16px 32px; border: none; border-radius: 12px; font-weight: 700; cursor: pointer; text-decoration: none; display: inline-block; transition: all 0.2s; font-size: 16px; box-shadow: 0 4px 15px rgba(56, 189, 248, 0.3); }
        .btn:hover { transform: scale(1.02); }
        .btn-green { background: linear-gradient(135deg, #10b981, #059669); color: white; box-shadow: 0 4px 15px rgba(16, 185, 129, 0.3); }
        .verified-badge { background: rgba(16, 185, 129, 0.12); color: #34d399; padding: 8px 18px; border-radius: 30px; font-size: 13px; font-weight: 700; display: inline-flex; align-items: center; gap: 8px; margin-bottom: 25px; border: 1px solid rgba(16, 185, 129, 0.3); }
    </style>
</head>
<body>
    <div class="main-container">
        <div class="hero">
            <div><span class="verified-badge">🛡️ Passerelle Solana Certifiée & Sécurisée</span></div>
            <h1>Intelligence Artificielle & <span>Réseaux Avancés</span></h1>
            <p class="subtitle">Bénéficiez d'un accès instantané, sécurisé et entièrement validé par la blockchain Solana pour propulser vos projets.</p>
        </div>
        
        <div class="plans">
            <div class="plan-card">
                <h3>Pass 30 Jours</h3>
                <p class="subtext">Accès complet à l'ensemble des modules et optimisations illimitées pendant un mois.</p>
                <div class="price">1 500 $<br><span style="font-size:16px; color:#34d399; font-weight:600;">(~{{ price_30 }} SOL)</span></div>
                <a href="/checkout?plan=Pass_30_Jours&price={{ price_30 }}" class="btn">Sélectionner ce Pass</a>
            </div>
            
            <div class="plan-card popular">
                <div style="position: absolute; top: -14px; right: 25px; background: #10b981; color: white; padding: 5px 14px; font-size: 12px; border-radius: 20px; font-weight: 800;">MEILLEUR CHOIX</div>
                <h3>Pass 365 Jours</h3>
                <p class="subtext">Accès illimité sur toute l'année, conçu spécifiquement pour les professionnels exigeants.</p>
                <div class="price">17 500 $<br><span style="font-size:16px; color:#34d399; font-weight:600;">(~{{ price_365 }} SOL)</span></div>
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

DASHBOARD_TEMPLATE = NAVBAR_HTML + """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <title>Espace Statistiques - GlobalRoute AI</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { font-family: 'Inter', system-ui, -apple-system, sans-serif; background: #090d16; color: #f8fafc; margin: 0; padding: 0; }
        .main-container { max-width: 1100px; margin: 40px auto; padding: 20px; }
        .card { background: linear-gradient(145deg, #162032 0%, #0f172a 100%); padding: 35px; border-radius: 24px; border: 1px solid rgba(56, 189, 248, 0.15); box-shadow: 0 20px 40px rgba(0,0,0,0.5); }
        h1 { color: #f8fafc; margin-top: 0; font-size: 28px; font-weight: 800; }
        .stats-grid { display: flex; gap: 20px; margin: 30px 0; flex-wrap: wrap; }
        .stat-box { background: rgba(15, 23, 42, 0.7); flex: 1; min-width: 220px; padding: 25px; border-radius: 16px; text-align: center; border: 1px solid rgba(56, 189, 248, 0.1); border-left: 5px solid #38bdf8; }
        .stat-value { font-size: 32px; font-weight: 800; color: #38bdf8; margin-top: 8px; }
        .chart-container { position: relative; height: 380px; width: 100%; margin-top: 20px; background: rgba(15, 23, 42, 0.5); padding: 20px; border-radius: 16px; border: 1px solid rgba(56, 189, 248, 0.1); }
    </style>
</head>
<body>
    <div class="main-container">
        <div class="card">
            <h1>📊 Tableau de Bord et Statistiques</h1>
            <p style="color: #94a3b8; font-size: 15px;">Analyse en temps réel de l'activité de la plateforme et de la distribution des abonnements validés.</p>
            
            <div class="stats-grid">
                <div class="stat-box">
                    <div style="color: #94a3b8; font-size: 13px; font-weight: 600; text-transform: uppercase;">Total Clés Délivrées</div>
                    <div class="stat-value">{{ total_keys }}</div>
                </div>
                <div class="stat-box" style="border-left-color: #38bdf8;">
                    <div style="color: #94a3b8; font-size: 13px; font-weight: 600; text-transform: uppercase;">Pass 30 Jours</div>
                    <div class="stat-value" style="color: #38bdf8;">{{ count_30 }}</div>
                </div>
                <div class="stat-box" style="border-left-color: #10b981;">
                    <div style="color: #94a3b8; font-size: 13px; font-weight: 600; text-transform: uppercase;">Pass 365 Jours</div>
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
                    label: 'Abonnements validés',
                    data: [{{ count_30 }}, {{ count_365 }}],
                    backgroundColor: ['rgba(56, 189, 248, 0.85)', 'rgba(16, 185, 129, 0.85)'],
                    borderColor: ['#38bdf8', '#10b981'],
                    borderWidth: 2,
                    borderRadius: 12,
                    barThickness: 60
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { labels: { color: '#f8fafc', font: { family: 'Inter', weight: '600' } } }
                },
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
    
    total_keys = total_keys or 0
    count_30 = count_30 or 0
    count_365 = count_365 or 0

    return render_template_string(DASHBOARD_TEMPLATE, total_keys=total_keys, count_30=count_30, count_365=count_365)

CHECKOUT_TEMPLATE = NAVBAR_HTML + """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <title>Paiement Sécurisé Solana</title>
    <style>
        body { font-family: 'Inter', system-ui, -apple-system, sans-serif; background: #090d16; color: #f8fafc; margin: 0; padding: 0; }
        .main-container { max-width: 680px; margin: 40px auto; padding: 20px; }
        .card { background: linear-gradient(145deg, #162032 0%, #0f172a 100%); padding: 40px; border-radius: 24px; box-shadow: 0 20px 40px rgba(0,0,0,0.6); text-align: center; border: 1px solid rgba(56, 189, 248, 0.15); }
        h1 { color: #f8fafc; margin-top: 0; font-size: 26px; font-weight: 800; }
        .wallet-box { background: #090d16; padding: 20px; border-radius: 14px; font-family: monospace; font-size: 14px; margin: 20px 0; word-break: break-all; color: #38bdf8; border: 1px dashed rgba(56, 189, 248, 0.4); display: flex; justify-content: space-between; align-items: center; }
        input[type="text"] { width: 92%; padding: 15px; border-radius: 12px; border: 1px solid rgba(148, 163, 184, 0.3); background: #090d16; color: #fff; margin-bottom: 20px; font-size: 15px; outline: none; }
        input[type="text"]:focus { border-color: #38bdf8; box-shadow: 0 0 10px rgba(56, 189, 248, 0.2); }
        .btn { background: linear-gradient(135deg, #10b981, #059669); color: #fff; padding: 16px 32px; border: none; border-radius: 12px; font-weight: 700; cursor: pointer; font-size: 16px; width: 100%; box-shadow: 0 4px 15px rgba(16, 185, 129, 0.3); }
        .btn:hover { transform: translateY(-2px); }
        .copy-btn { background: rgba(56, 189, 248, 0.15); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.3); padding: 10px 16px; border-radius: 10px; cursor: pointer; font-weight: 700; font-size: 13px; }
        .info-text { font-size: 15px; color: #94a3b8; line-height: 1.6; margin-bottom: 20px; }
    </style>
</head>
<body>
    <div class="main-container">
        <div class="card">
            <h1>🛡️ Validation Blockchain Solana</h1>
            <p class="info-text">Formule choisie : <strong style="color: #f8fafc;">{{ plan_formatted }}</strong><br>
            Montant exact requis : <strong style="color: #10b981; font-size: 22px;">{{ price }} SOL</strong></p>
            
            <p class="info-text">Effectuez votre virement vers l'adresse marchand officielle :</p>
            <div class="wallet-box">
                <span id="walletText">{{ merchant_wallet }}</span>
                <button class="copy-btn" onclick="copyWallet()">📋 Copier</button>
            </div>
            
            <p class="info-text">Une fois le transfert effectué, veuillez coller ci-dessous la signature de la transaction (Tx Signature) :</p>
            
            <form action="/verify-payment" method="POST">
                <input type="hidden" name="plan" value="{{ plan }}">
                <input type="hidden" name="price" value="{{ price }}">
                <input type="text" name="tx_signature" placeholder="Collez la signature de transaction..." required><br>
                <button type="submit" class="btn">Vérifier et obtenir ma clé</button>
            </form>
            <br>
            <a href="/" style="color: #94a3b8; text-decoration: none; font-size: 14px; font-weight: 600;">← Retour à l'accueil</a>
        </div>
    </div>

    <script>
        function copyWallet() {
            const wallet = document.getElementById('walletText').innerText;
            navigator.clipboard.writeText(wallet);
            alert('Adresse Solana copiée dans le presse-papier.');
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
        
    plan_formatted = plan.replace('_', ' ')
    return render_template_string(CHECKOUT_TEMPLATE, plan=plan, plan_formatted=plan_formatted, price=price, merchant_wallet=MERCHANT_SOL_WALLET)

SUCCESS_TEMPLATE = NAVBAR_HTML + """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <title>Paiement Validé - GlobalRoute AI</title>
    <style>
        body { font-family: 'Inter', system-ui, -apple-system, sans-serif; background: #090d16; color: #f8fafc; margin: 0; padding: 0; }
        .main-container { max-width: 680px; margin: 40px auto; padding: 20px; }
        .card { background: linear-gradient(145deg, #162032 0%, #0f172a 100%); padding: 45px; border-radius: 24px; text-align: center; box-shadow: 0 20px 40px rgba(0,0,0,0.6); border: 1px solid rgba(16, 185, 129, 0.3); }
        .key-box { background: #090d16; padding: 22px; border-radius: 14px; font-size: 20px; font-family: monospace; font-weight: 800; color: #10b981; margin: 25px 0; border: 1px solid rgba(16, 185, 129, 0.4); display: flex; justify-content: space-between; align-items: center; }
        .copy-btn { background: linear-gradient(135deg, #10b981, #059669); color: white; border: none; padding: 12px 20px; border-radius: 10px; cursor: pointer; font-weight: 700; font-size: 14px; }
    </style>
</head>
<body>
    <div class="main-container">
        <div class="card">
            <h1 style="color: #10b981; margin-top:0; font-size: 28px; font-weight: 800;">🛡️ Paiement Confirmé avec Succès</h1>
            <p style="color: #94a3b8; line-height: 1.6; font-size: 15px;">Votre transaction a été validée et authentifiée par la blockchain Solana. Voici votre clé d'accès unique :</p>
            
            <div class="key-box">
                <span id="keyText">{{ key }}</span>
                <button class="copy-btn" onclick="copyKey()">Copier</button>
            </div>
            
            <p style="color: #64748b; font-size: 13px;">Veuillez conserver précieusement cette clé dans un endroit sécurisé.</p>
            <br>
            <a href="/" style="color: #38bdf8; text-decoration: none; font-weight: 700; font-size: 15px;">← Retour à l'accueil</a>
        </div>
    </div>
    <script>
        function copyKey() {
            const key = document.getElementById('keyText').innerText;
            navigator.clipboard.writeText(key);
            alert('Clé d\'accès copiée avec succès.');
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
    <title>Échec de Vérification</title>
    <style>
        body { font-family: 'Inter', system-ui, -apple-system, sans-serif; background: #090d16; color: #f8fafc; margin: 0; padding: 0; text-align: center; }
    </style>
</head>
<body>
    <div style="max-width:580px; margin:80px auto; background:linear-gradient(145deg, #162032 0%, #0f172a 100%); padding:45px; border-radius:24px; border:1px solid rgba(239, 68, 68, 0.3); box-shadow: 0 20px 40px rgba(0,0,0,0.6);">
        <h2 style="color:#ef4444; margin-top:0; font-size: 24px; font-weight: 800;">🛡️ Échec de la vérification Solana</h2>
        <p style="color:#94a3b8; line-height:1.6; margin-bottom:30px; font-size: 15px;">{{ message }}</p>
        <a href="/" style="color:#38bdf8; text-decoration:none; font-weight:700; font-size: 15px;">← Réessayer avec une autre transaction</a>
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
        cursor.execute("INSERT INTO keys (key_code, plan, status, tx_signature) VALUES (?, ?, 'UNUSED', ?)", 
                       (new_key, plan, tx_signature))
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
    <title>Administration - GlobalRoute AI</title>
    <style>
        body { font-family: 'Inter', system-ui, -apple-system, sans-serif; background: #090d16; color: #f8fafc; margin: 0; padding: 0; }
        .main-container { max-width: 1100px; margin: 40px auto; background: linear-gradient(145deg, #162032 0%, #0f172a 100%); padding: 40px; border-radius: 24px; border: 1px solid rgba(56, 189, 248, 0.15); box-shadow: 0 20px 40px rgba(0,0,0,0.6); }
    </style>
</head>
<body>
    <div class="main-container">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:25px;">
            <h1 style="color:#f8fafc; margin:0; font-size: 26px; font-weight: 800;">Panneau d'Administration</h1>
            <a href="/logout" style="color:#ef4444; text-decoration:none; font-weight:700; background:rgba(239, 68, 68, 0.15); padding:10px 20px; border-radius:10px; border: 1px solid rgba(239, 68, 68, 0.3);">Se déconnecter</a>
        </div>
        <p style="color:#94a3b8; margin-bottom:25px; font-size: 15px;">Historique global et sécurisé de toutes les licences certifiées sur la blockchain :</p>
        <div style="overflow-x: auto;">
            <table style="width:100%; border-collapse:collapse; margin-top:10px; text-align:left;">
                <tr style="background:rgba(15, 23, 42, 0.8); color:#38bdf8; font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px;">
                    <th style="padding:15px; border-top-left-radius: 10px;">ID</th>
                    <th style="padding:15px;">Clé d'Accès</th>
                    <th style="padding:15px;">Formule</th>
                    <th style="padding:15px;">Statut</th>
                    <th style="padding:15px; border-top-right-radius: 10px;">Signature Solana</th>
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
    <title>Connexion Administration</title>
    <style>
        body { font-family: 'Inter', system-ui, -apple-system, sans-serif; background: #090d16; color: #f8fafc; margin: 0; padding: 0; }
    </style>
</head>
<body>
    <div style="display:flex; justify-content:center; align-items:center; height:80vh;">
        <div style="background:linear-gradient(145deg, #162032 0%, #0f172a 100%); padding:45px; border-radius:24px; width:380px; text-align:center; border:1px solid rgba(56, 189, 248, 0.15); box-shadow: 0 20px 40px rgba(0,0,0,0.6);">
            <h2 style="color:#f8fafc; margin-top:0; font-size: 24px; font-weight: 800;">Connexion Admin</h2>
            <p style="color:#94a3b8; font-size: 14px; margin-bottom: 25px;">Accès restreint à la gestion de la plateforme.</p>
            <form method="POST">
                <input type="password" name="password" placeholder="Mot de passe administrateur" required style="width:90%; padding:15px; margin-bottom:20px; border-radius:12px; border:1px solid rgba(148, 163, 184, 0.3); background:#090d16; color:#fff; font-size:15px; outline:none;"><br>
                <button type="submit" style="background:linear-gradient(135deg, #38bdf8, #0ea5e9); color:#0f172a; padding:15px 20px; border:none; border-radius:12px; font-weight:800; cursor:pointer; width:100%; font-size:16px;">Se connecter</button>
            </form>
        </div>
    </div>
</body>
</html>
"""

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if request.method == 'POST':
        password = request.form.get('password')
        if password == ADMIN_PASSWORD:
            session['logged_in'] = True
        else:
            flash("Mot de passe incorrect")
            
    if session.get('logged_in'):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT id, key_code, plan, status, created_at, tx_signature FROM keys ORDER BY id DESC")
        keys = cursor.fetchall()
        conn.close()
        
        if keys:
            rows_html = "".join([f"<tr><td style='padding:15px; border-bottom:1px solid rgba(51, 65, 85, 0.4); color: #cbd5e1;'>{k[0]}</td><td style='padding:15px; border-bottom:1px solid rgba(51, 65, 85, 0.4); font-family:monospace; color:#38bdf8; font-weight:600;'>{k[1]}</td><td style='padding:15px; border-bottom:1px solid rgba(51, 65, 85, 0.4); color: #cbd5e1;'>{k[2]}</td><td style='padding:15px; border-bottom:1px solid rgba(51, 65, 85, 0.4);'><span style='background:rgba(16,185,129,0.15); color:#34d399; padding:4px 10px; border-radius:6px; font-size:12px; font-weight:700;'>{k[3]}</span></td><td style='padding:15px; border-bottom:1px solid rgba(51, 65, 85, 0.4);'><small style='color:#94a3b8;'>{k[5][:18] if k[5] else 'Manuel'}...</small></td></tr>" for k in keys])
        else:
            rows_html = "<tr><td colspan='5' style='padding:30px; text-align:center; color:#94a3b8;'>Aucune clé enregistrée pour le moment.</td></tr>"
            
        return render_template_string(ADMIN_TEMPLATE, rows_html=rows_html)
        
    return render_template_string(LOGIN_TEMPLATE)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('index'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
