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
        response = requests.post(rpc_url, json=payload, timeout=10)
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
                return False, "Le portefeuille destinataire ne correspond pas à votre adresse marchand."
            
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
            
            return True, "Transaction vérifiée et certifiée sur Solana avec succès !"
        else:
            return False, "Transaction introuvable ou encore en attente sur le réseau."
    except Exception as e:
        return False, f"Erreur de connexion RPC Solana : {str(e)}"

# --- NAVBAR ULTRA-DESIGN ---
NAVBAR_HTML = """
<nav style="background: rgba(15, 23, 42, 0.85); backdrop-filter: blur(12px); border-bottom: 1px solid rgba(56, 189, 248, 0.15); padding: 18px 40px; display: flex; justify-content: space-between; align-items: center; position: sticky; top: 0; z-index: 1000; box-shadow: 0 4px 20px rgba(0,0,0,0.3);">
    <div style="font-size: 22px; font-weight: 800; color: #38bdf8; display: flex; align-items: center; gap: 12px; letter-spacing: -0.5px;">
        <span style="background: linear-gradient(135deg, #38bdf8, #818cf8); padding: 8px; border-radius: 10px; color: #0f172a; font-size: 16px;">🚀</span> GlobalRoute AI
    </div>
    <div style="display: flex; gap: 30px; align-items: center;">
        <a href="/" style="color: #cbd5e1; text-decoration: none; font-weight: 600; font-size: 15px; transition: 0.25s;" onmouseover="this.style.color='#38bdf8'" onmouseout="this.style.color='#cbd5e1'">Accueil</a>
        <a href="/dashboard" style="color: #cbd5e1; text-decoration: none; font-weight: 600; font-size: 15px; transition: 0.25s;" onmouseover="this.style.color='#38bdf8'" onmouseout="this.style.color='#cbd5e1'">📊 Espace Graphique</a>
        <a href="/admin" style="color: #94a3b8; text-decoration: none; font-weight: 600; font-size: 15px; transition: 0.25s; border: 1px solid rgba(148, 163, 184, 0.2); padding: 8px 16px; border-radius: 8px;" onmouseover="this.style.color='#38bdf8'; this.style.borderColor='#38bdf8'" onmouseout="this.style.color='#94a3b8'; this.style.borderColor='rgba(148, 163, 184, 0.2)'">🔒 Admin</a>
    </div>
</nav>
"""

@app.route('/')
def index():
    return render_template_string(f'''
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <title>GlobalRoute AI - Accueil Pro</title>
        <style>
            body {{ font-family: 'Inter', system-ui, -apple-system, sans-serif; background: #090d16; color: #f8fafc; margin: 0; padding: 0; overflow-x: hidden; }}
            .main-container {{ max-width: 1100px; margin: 50px auto; padding: 20px; }}
            .hero {{ text-align: center; padding: 60px 30px; background: radial-gradient(circle at center, #1e293b 0%, #0f172a 100%); border-radius: 24px; border: 1px solid rgba(56, 189, 248, 0.2); box-shadow: 0 20px 50px rgba(0,0,0,0.6); position: relative; overflow: hidden; }}
            .hero::before {{ content: ''; position: absolute; top: -50px; left: 50%; transform: translateX(-50%); width: 200px; height: 200px; background: rgba(56, 189, 248, 0.15); filter: blur(60px); border-radius: 50%; z-index: 0; }}
            h1 {{ color: #f8fafc; font-size: 44px; margin-bottom: 15px; font-weight: 800; letter-spacing: -1px; position: relative; z-index: 1; }}
            h1 span {{ background: linear-gradient(135deg, #38bdf8, #818cf8); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
            .subtitle {{ color: #94a3b8; font-size: 18px; margin-bottom: 35px; max-width: 650px; margin-left: auto; margin-right: auto; line-height: 1.6; position: relative; z-index: 1; }}
            .plans {{ display: flex; gap: 30px; justify-content: center; margin-top: 50px; flex-wrap: wrap; }}
            .plan-card {{ background: linear-gradient(145deg, #162032 0%, #0f172a 100%); padding: 40px 30px; border-radius: 20px; width: 42%; min-width: 300px; text-align: center; border: 1px solid rgba(56, 189, 248, 0.15); transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); position: relative; box-shadow: 0 10px 30px rgba(0,0,0,0.4); }}
            .plan-card:hover {{ border-color: #38bdf8; transform: translateY(-8px); box-shadow: 0 20px 40px rgba(56, 189, 248, 0.15); }}
            .plan-card.popular {{ border-color: #10b981; background: linear-gradient(145deg, #132822 0%, #0f172a 100%); }}
            .plan-card.popular:hover {{ border-color: #34d399; box-shadow: 0 20px 40px rgba(16, 185, 129, 0.2); }}
            .price {{ font-size: 38px; font-weight: 800; color: #f8fafc; margin: 25px 0; letter-spacing: -1px; }}
            .subtext {{ font-size: 15px; color: #94a3b8; margin-bottom: 25px; line-height: 1.5; }}
            .btn {{ background: linear-gradient(135deg, #38bdf8, #0ea5e9); color: #0f172a; padding: 16px 32px; border: none; border-radius: 12px; font-weight: 700; cursor: pointer; text-decoration: none; display: inline-block; transition: all 0.2s ease; font-size: 16px; box-shadow: 0 4px 15px rgba(56, 189, 248, 0.3); }}
            .btn:hover {{ transform: scale(1.03); box-shadow: 0 6px 20px rgba(56, 189, 248, 0.5); }}
            .btn-green {{ background: linear-gradient(135deg, #10b981, #059669); color: white; box-shadow: 0 4px 15px rgba(16, 185, 129, 0.3); }}
            .btn-green:hover {{ box-shadow: 0 6px 20px rgba(16, 185, 129, 0.5); }}
            .verified-badge {{ background: rgba(16, 185, 129, 0.12); color: #34d399; padding: 8px 18px; border-radius: 30px; font-size: 13px; font-weight: 700; display: inline-flex; align-items: center; gap: 8px; margin-bottom: 25px; border: 1px solid rgba(16, 185, 129, 0.3); position: relative; z-index: 1; }}
        </style>
    </head>
    <body>
        {NAVBAR_HTML}
        <div class="main-container">
            <div class="hero">
                <div><span class="verified-badge">🛡️ Verified Solana Secure Gateway v2.6</span></div>
                <h1>Intelligence Artificielle & <span>Réseaux Avancés</span></h1>
                <p class="subtitle">Propulsez vos infrastructures avec une passerelle de paiement décentralisée ultra-rapide, sécurisée et certifiée sur la blockchain Solana.</p>
            </div>
            
            <div class="plans">
                <div class="plan-card">
                    <h3>Pass 30 Jours</h3>
                    <p class="subtext">Accès complet à toutes les fonctionnalités et optimisations illimitées pendant 1 mois.</p>
                    <div class="price">1 500 $<br><span style="font-size:16px; color:#34d399; font-weight:600;">(~{{ price_30 }} SOL)</span></div>
                    <a href="/checkout?plan=Pass_30_Jours&price={{ price_30 }}" class="btn">Sélectionner 30 Jours</a>
                </div>
                <div class="plan-card popular">
                    <div style="position: absolute; top: -14px; right: 25px; background: #10b981; color: white; padding: 5px 14px; font-size: 12px; border-radius: 20px; font-weight: 800; letter-spacing: 0.5px; box-shadow: 0 4px 10px rgba(16,185,129,0.4);">POPULAIRE</div>
                    <h3>Pass 365 Jours</h3>
                    <p class="subtext">Accès illimité toute l'année, idéal pour les structures et professionnels exigeants.</p>
                    <div class="price">17 500 $<br><span style="font-size:16px; color:#34d399; font-weight:600;">(~{{ price_365 }} SOL)</span></div>
                    <a href="/checkout?plan=Pass_365_Jours&price={{ price_365 }}" class="btn btn-green">Sélectionner 365 Jours</a>
                </div>
            </div>
        </div>
    </body>
    </html>
    ''', price_30=PRICE_30_DAYS_SOL, price_365=PRICE_365_DAYS_SOL)

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

    return render_template_string(f'''
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <title>Tableau de bord & Graphiques Pro</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            body {{ font-family: 'Inter', system-ui, -apple-system, sans-serif; background: #090d16; color: #f8fafc; margin: 0; padding: 0; }}
            .main-container {{ max-width: 1100px; margin: 40px auto; padding: 20px; }}
            .card {{ background: linear-gradient(145deg, #162032 0%, #0f172a 100%); padding: 35px; border-radius: 24px; border: 1px solid rgba(56, 189, 248, 0.15); box-shadow: 0 20px 40px rgba(0,0,0,0.5); margin-bottom: 30px; }}
            h1 {{ color: #f8fafc; margin-top: 0; font-size: 28px; font-weight: 800; letter-spacing: -0.5px; }}
            .stats-grid {{ display: flex; gap: 20px; margin: 30px 0; flex-wrap: wrap; }}
            .stat-box {{ background: rgba(15, 23, 42, 0.7); flex: 1; min-width: 220px; padding: 25px; border-radius: 16px; text-align: center; border: 1px solid rgba(56, 189, 248, 0.1); border-left: 5px solid #38bdf8; box-shadow: 0 8px 20px rgba(0,0,0,0.2); transition: transform 0.2s; }}
            .stat-box:hover {{ transform: translateY(-3px); }}
            .stat-value {{ font-size: 32px; font-weight: 800; color: #38bdf8; margin-top: 8px; letter-spacing: -1px; }}
            .chart-container {{ position: relative; height: 380px; width: 100%; margin-top: 20px; background: rgba(15, 23, 42, 0.5); padding: 20px; border-radius: 16px; border: 1px solid rgba(56, 189, 248, 0.1); }}
        </style>
    </head>
    <body>
        {NAVBAR_HTML}
        <div class="main-container">
            <div class="card">
                <h1>📊 Tableau de Bord et Statistiques Avancées</h1>
                <p style="color: #94a3b8; font-size: 15px;">Analyse en temps réel de l'activité de la plateforme et de la distribution des abonnements certifiés.</p>
                
                <div class="stats-grid">
                    <div class="stat-box">
                        <div style="color: #94a3b8; font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;">Total Clés Délivrées</div>
                        <div class="stat-value">{total_keys}</div>
                    </div>
                    <div class="stat-box" style="border-left-color: #38bdf8;">
                        <div style="color: #94a3b8; font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;">Pass 30 Jours</div>
                        <div class="stat-value" style="color: #38bdf8;">{count_30}</div>
                    </div>
                    <div class="stat-box" style="border-left-color: #10b981;">
                        <div style="color: #94a3b8; font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;">Pass 365 Jours</div>
                        <div class="stat-value" style="color: #10b981;">{count_365}</div>
                    </div>
                </div>

                <div class="chart-container">
                    <canvas id="salesChart"></canvas>
                </div>
            </div>
        </div>

        <script>
            const ctx = document.getElementById('salesChart').getContext('2d');
            const salesChart = new Chart(ctx, {{
                type: 'bar',
                data: {{
                    labels: ['Pass 30 Jours', 'Pass 365 Jours'],
                    datasets: [{{
                        label: 'Abonnements validés',
                        data: [{count_30}, {count_365}],
                        backgroundColor: ['rgba(56, 189, 248, 0.85)', 'rgba(16, 185, 129, 0.85)'],
                        borderColor: ['#38bdf8', '#10b981'],
                        borderWidth: 2,
                        borderRadius: 12,
                        barThickness: 60
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{
                        legend: {{ labels: {{ color: '#f8fafc', font: {{ family: 'Inter', weight: '600' }} }} }}
                    }},
                    scales: {{
                        y: {{ 
                            ticks: {{ color: '#94a3b8', font: {{ family: 'Inter' }} }}, 
                            grid: {{ color: 'rgba(51, 65, 85, 0.4)' }} 
                        }},
                        x: {{ 
                            ticks: {{ color: '#94a3b8', font: {{ family: 'Inter', weight: '600' }} }}, 
                            grid: {{ display: false }} 
                        }}
                    }}
                }}
            }});
        </script>
    </body>
    </html>
    ''')

@app.route('/checkout')
def checkout():
    plan = request.args.get('plan')
    price = request.args.get('price')
    
    if not plan or not price:
        return redirect(url_for('index'))
        
    return render_template_string(f'''
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <title>Paiement Sécurisé Solana</title>
        <style>
            body {{ font-family: 'Inter', system-ui, -apple-system, sans-serif; background: #090d16; color: #f8fafc; margin: 0; padding: 0; }}
            .main-container {{ max-width: 680px; margin: 40px auto; padding: 20px; }}
            .card {{ background: linear-gradient(145deg, #162032 0%, #0f172a 100%); padding: 40px; border-radius: 24px; box-shadow: 0 20px 40px rgba(0,0,0,0.6); text-align: center; border: 1px solid rgba(56, 189, 248, 0.15); }}
            h1 {{ color: #f8fafc; margin-top: 0; font-size: 26px; font-weight: 800; }}
            .wallet-box {{ background: #090d16; padding: 20px; border-radius: 14px; font-family: monospace; font-size: 14px; margin: 20px 0; word-break: break-all; color: #38bdf8; border: 1px dashed rgba(56, 189, 248, 0.4); display: flex; justify-content: space-between; align-items: center; box-shadow: inset 0 2px 5px rgba(0,0,0,0.5); }}
            input[type="text"] {{ width: 92%; padding: 15px; border-radius: 12px; border: 1px solid rgba(148, 163, 184, 0.3); background: #090d16; color: #fff; margin-bottom: 20px; font-size: 15px; outline: none; transition: border-color 0.2s; }}
            input[type="text"]:focus {{ border-color: #38bdf8; box-shadow: 0 0 10px rgba(56, 189, 248, 0.2); }}
            .btn {{ background: linear-gradient(135deg, #10b981, #059669); color: #fff; padding: 16px 32px; border: none; border-radius: 12px; font-weight: 700; cursor: pointer; font-size: 16px; transition: all 0.2s; box-shadow: 0 4px 15px rgba(16, 185, 129, 0.3); width: 100%; }}
            .btn:hover {{ transform: translateY(-2px); box-shadow: 0 6px 20px rgba(16, 185, 129, 0.5); }}
            .copy-btn {{ background: rgba(56, 189, 248, 0.15); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.3); padding: 10px 16px; border-radius: 10px; cursor: pointer; font-weight: 700; font-size: 13px; transition: 0.2s; }}
            .copy-btn:hover {{ background: rgba(56, 189, 248, 0.3); }}
            .info-text {{ font-size: 15px; color: #94a3b8; line-height: 1.6; margin-bottom: 20px; }}
        </style>
    </head>
    <body>
        {NAVBAR_HTML}
        <div class="main-container">
            <div class="card">
                <h1>🛡️ Validation Verified Solana</h1>
                <p class="info-text">Formule : <strong style="color: #f8fafc;">{{ plan.replace('_', ' ') }}</strong><br>
                Montant exact requis : <strong style="color: #10b981; font-size: 22px;">{{ price }} SOL</strong></p>
                
                <p class="info-text">Transférez les fonds vers l'adresse marchand sécurisée ci-dessous :</p>
                <div class="wallet-box">
                    <span id="walletText">{MERCHANT_SOL_WALLET}</span>
                    <button class="copy-btn" onclick="copyWallet()">📋 Copier</button>
                </div>
                
                <p class="info-text">Après votre transfert, collez la signature de transaction (Tx Signature) fournie par votre portefeuille :</p>
                
                <form action="/verify-payment" method="POST">
                    <input type="hidden" name="plan" value="{{ plan }}">
                    <input type="hidden" name="price" value="{{ price }}">
                    <input type="text" name="tx_signature" placeholder="Collez la signature ici (ex: 5K1a...)" required><br>
                    <button type="submit" class="btn">Vérifier et obtenir ma clé</button>
                </form>
                <br>
                <a href="/" style="color: #94a3b8; text-decoration: none; font-size: 14px; font-weight: 600; transition: color 0.2s;" onmouseover="this.style.color='#38bdf8'" onmouseout="this.style.color='#94a3b8'">← Annuler et retourner à l'accueil</a>
            </div>
        </div>

        <script>
            function copyWallet() {{
                const wallet = document.getElementById('walletText').innerText;
                navigator.clipboard.writeText(wallet);
                alert('Adresse Solana copiée dans le presse-papier !');
            }}
        </script>
    </body>
    </html>
    ''', plan=plan, price=price, merchant_wallet=MERCHANT_SOL_WALLET)

@app.route('/verify-payment', methods=['POST'])
def verify_payment():
    plan = request.form.get('plan')
    expected_price = float(request.form.get('price', 10.0))
    tx_signature = request.form.get('tx_signature').strip()
    
    is_valid, message = verify_solana_transaction(tx_signature, expected_price)
    
    if is_valid:
        new_key = f"KEY-VERIFIED-{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}"
        
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO keys (key_code, plan, status, tx_signature) VALUES (?, ?, 'UNUSED', ?)", 
                       (new_key, plan, tx_signature))
        conn.commit()
        conn.close()
        
        return render_template_string(f'''
        <!DOCTYPE html>
        <html lang="fr">
        <head>
            <meta charset="UTF-8">
            <title>Paiement Validé</title>
            <style>
                body {{ font-family: 'Inter', system-ui, -apple-system, sans-serif; background: #090d16; color: #f8fafc; margin: 0; padding: 0; }}
                .main-container {{ max-width: 680px; margin: 40px auto; padding: 20px; }}
                .card {{ background: linear-gradient(145deg, #162032 0%, #0f172a 100%); padding: 45px; border-radius: 24px; text-align: center; box-shadow: 0 20px 40px rgba(0,0,0,0.6); border: 1px solid rgba(16, 185, 129, 0.3); }}
                .key-box {{ background: #090d16; padding: 22px; border-radius: 14px; font-size: 20px; font-family: monospace; font-weight: 800; color: #10b981; margin: 25px 0; border: 1px solid rgba(16, 185, 129, 0.4); display: flex; justify-content: space-between; align-items: center; box-shadow: inset 0 2px 5px rgba(0,0,0,0.5); }}
                .copy-btn {{ background: linear-gradient(135deg, #10b981, #059669); color: white; border: none; padding: 12px 20px; border-radius: 10px; cursor: pointer; font-weight: 700; font-size: 14px; transition: transform 0.2s; }}
                .copy-btn:hover {{ transform: scale(1.03); }}
            </style>
        </head>
        <body>
            {NAVBAR_HTML}
            <div class="main-container">
                <div class="card">
                    <h1 style="color: #10b981; margin-top:0; font-size: 28px; font-weight: 800;">🛡️ Paiement Confirmé !</h1>
                    <p style="color: #94a3b8; line-height: 1.6; font-size: 15px;">Votre transaction a été validée avec succès sur la blockchain Solana. Voici votre clé d'accès unique :</p>
                    
                    <div class="key-box">
                        <span id="keyText">{{ key }}</span>
                        <button class="copy-btn" onclick="copyKey()">Copier</button>
                    </div>
                    
                    <p style="color: #64748b; font-size: 13px;">Conservez cette clé précieusement dans un endroit sûr.</p>
                    <br>
                    <a href="/" style="color: #38bdf8; text-decoration: none; font-weight: 700; font-size: 15px;">← Retour à l'accueil</a>
                </div>
            </div>
            <script>
                function copyKey() {{
                    const key = document.getElementById('keyText').innerText;
                    navigator.clipboard.writeText(key);
                    alert('Clé copiée avec succès !');
                }}
            </script>
        </body>
        </html>
        ''', key=new_key)
    else:
        return f"""
        <body style="background:#090d16; color:white; font-family:'Inter', sans-serif; text-align:center; padding:0; margin:0;">
            {NAVBAR_HTML}
            <div style="max-width:580px; margin:80px auto; background:linear-gradient(145deg, #162032 0%, #0f172a 100%); padding:45px; border-radius:24px; border:1px solid rgba(239, 68, 68, 0.3); box-shadow: 0 20px 40px rgba(0,0,0,0.6);">
                <h2 style="color:#ef4444; margin-top:0; font-size: 24px; font-weight: 800;">🛡️ Échec de la vérification Solana</h2>
                <p style="color:#94a3b8; line-height:1.6; margin-bottom:30px; font-size: 15px;">{message}</p>
                <a href="/" style="color:#38bdf8; text-decoration:none; font-weight:700; font-size: 15px;">← Réessayer avec une autre transaction</a>
            </div>
        </body>
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
        
        rows_html = "".join([f"<tr><td style='padding:15px; border-bottom:1px solid rgba(51, 65, 85, 0.4); color: #cbd5e1;'>{k[0]}</td><td style='padding:15px; border-bottom:1px solid rgba(51, 65, 85, 0.4); font-family:monospace; color:#38bdf8; font-weight:600;'>{k[1]}</td><td style='padding:15px; border-bottom:1px solid rgba(51, 65, 85, 0.4); color: #cbd5e1;'>{k[2]}</td><td style='padding:15px; border-bottom:1px solid rgba(51, 65, 85, 0.4);'><span style='background:rgba(16,185,129,0.15); color:#34d399; padding:4px 10px; border-radius:6px; font-size:12px; font-weight:700;'>{k[3]}</span></td><td style='padding:15px; border-bottom:1px solid rgba(51, 65, 85, 0.4);'><small style='color:#94a3b8;'>{k[5][:18] if k[5] else 'Manuel'}...</small></td></tr>" for k in keys])
        
        return f"""
        <body style="background:#090d16; color:white; font-family:'Inter', sans-serif; margin:0; padding:0;">
            {NAVBAR_HTML}
            <div style="max-width:1100px; margin:40px auto; background:linear-gradient(145deg, #162032 0%, #0f172a 100%); padding:40px; border-radius:24px; border:1px solid rgba(56, 189, 248, 0.15); box-shadow: 0 20px 40px rgba(0,0,0,0.6);">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:25px;">
                    <h1 style="color:#f8fafc; margin:0; font-size: 26px; font-weight: 800;">Panneau d'Administration</h1>
                    <a href="/logout" style="color:#ef4444; text-decoration:none; font-weight:700; background:rgba(239, 68, 68, 0.15); padding:10px 20px; border-radius:10px; border: 1px solid rgba(239, 68, 68, 0.3); transition: 0.2s;" onmouseover="this.style.background='rgba(239, 68, 68, 0.25)'" onmouseout="this.style.background='rgba(239, 68, 68, 0.15)'">Se déconnecter</a>
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
                        {rows_html if rows_html else '<tr><td colspan="5" style="padding:30px; text-align:center; color:#94a3b8;">Aucune clé enregistrée pour le moment.</td></tr>'}
                    </table>
                </div>
            </div>
        </body>
        """
        
    return f"""
    <body style="background:#090d16; color:white; font-family:'Inter', sans-serif; margin:0; padding:0;">
        {NAVBAR_HTML}
        <div style="display:flex; justify-content:center; align-items:center; height:80vh;">
            <div style="background:linear-gradient(145deg, #162032 0%, #0f172a 100%); padding:45px; border-radius:24px; width:380px; text-align:center; border:1px solid rgba(56, 189, 248, 0.15); box-shadow: 0 20px 40px rgba(0,0,0,0.6);">
                <h2 style="color:#f8fafc; margin-top:0; font-size: 24px; font-weight: 800;">Connexion Admin</h2>
                <p style="color:#94a3b8; font-size: 14px; margin-bottom: 25px;">Accès restreint à la gestion de la plateforme.</p>
                <form method="POST">
                    <input type="password" name="password" placeholder="Mot de passe administrateur" required style="width:90%; padding:15px; margin-bottom:20px; border-radius:12px; border:1px solid rgba(148, 163, 184, 0.3); background:#090d16; color:#fff; font-size:15px; outline:none;"><br>
                    <button type="submit" style="background:linear-gradient(135deg, #38bdf8, #0ea5e9); color:#0f172a; padding:15px 20px; border:none; border-radius:12px; font-weight:800; cursor:pointer; width:100%; font-size:16px; box-shadow: 0 4px 15px rgba(56, 189, 248, 0.3);">Se connecter</button>
                </form>
            </div>
        </div>
    </body>
    """

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('index'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
