import os
import secrets
import sqlite3
from flask import Flask, render_template_string, request, redirect, url_for, session, flash
import requests

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

DB_NAME = "database.db"
ADMIN_PASSWORD = "admin"  # Mot de passe administrateur par défaut
MERCHANT_SOL_WALLET = "22BzBEYLewJkKe2FXD6EHJYqX4NNshMw9roNw9qFxV9d"  # Ton adresse Solana

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

# --- NAVBAR COMMUNE ---
NAVBAR_HTML = """
<nav style="background: #1e293b; border-bottom: 1px solid #334155; padding: 15px 30px; display: flex; justify-content: space-between; align-items: center; position: sticky; top: 0; z-index: 1000;">
    <div style="font-size: 20px; font-weight: bold; color: #38bdf8; display: flex; align-items: center; gap: 10px;">
        <span>🚀</span> GlobalRoute AI
    </div>
    <div style="display: flex; gap: 25px; align-items: center;">
        <a href="/" style="color: #f8fafc; text-decoration: none; font-weight: 500; transition: 0.2s;" onmouseover="this.style.color='#38bdf8'" onmouseout="this.style.color='#f8fafc'">Accueil</a>
        <a href="/dashboard" style="color: #f8fafc; text-decoration: none; font-weight: 500; transition: 0.2s;" onmouseover="this.style.color='#38bdf8'" onmouseout="this.style.color='#f8fafc'">📊 Espace Graphique</a>
        <a href="/admin" style="color: #94a3b8; text-decoration: none; font-weight: 500; transition: 0.2s;" onmouseover="this.style.color='#38bdf8'" onmouseout="this.style.color='#94a3b8'">🔒 Administration</a>
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
        <title>GlobalRoute AI - Accueil</title>
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 0; }}
            .main-container {{ max-width: 1000px; margin: 40px auto; padding: 20px; }}
            .hero {{ text-align: center; padding: 40px 20px; background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); border-radius: 16px; border: 1px solid #334155; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }}
            h1 {{ color: #38bdf8; font-size: 38px; margin-bottom: 10px; }}
            .subtitle {{ color: #94a3b8; font-size: 16px; margin-bottom: 30px; max-width: 600px; margin-left: auto; margin-right: auto; line-height: 1.5; }}
            .plans {{ display: flex; gap: 30px; justify-content: center; margin-top: 40px; flex-wrap: wrap; }}
            .plan-card {{ background: #1e293b; padding: 35px; border-radius: 16px; width: 40%; min-width: 280px; text-align: center; border: 2px solid #334155; transition: 0.3s; position: relative; }}
            .plan-card:hover {{ border-color: #38bdf8; transform: translateY(-5px); box-shadow: 0 15px 30px rgba(56, 189, 248, 0.1); }}
            .price {{ font-size: 32px; font-weight: bold; color: #38bdf8; margin: 20px 0; }}
            .subtext {{ font-size: 14px; color: #94a3b8; margin-bottom: 20px; line-height: 1.4; }}
            .btn {{ background: #38bdf8; color: #0f172a; padding: 14px 28px; border: none; border-radius: 8px; font-weight: bold; cursor: pointer; text-decoration: none; display: inline-block; transition: 0.2s; font-size: 16px; }}
            .btn:hover {{ background: #0ea5e9; box-shadow: 0 0 15px rgba(56, 189, 248, 0.4); }}
            .verified-badge {{ background: #065f46; color: #34d399; padding: 6px 16px; border-radius: 20px; font-size: 12px; font-weight: bold; display: inline-block; margin-bottom: 20px; border: 1px solid #059669; }}
        </style>
    </head>
    <body>
        {NAVBAR_HTML}
        <div class="main-container">
            <div class="hero">
                <div><span class="verified-badge">🛡️ Verified Solana Secure Gateway</span></div>
                <h1>Intelligence Artificielle & Réseaux Avancés</h1>
                <p class="subtitle">Profitez d'une passerelle de paiement décentralisée instantanée, transparente et certifiée sur la blockchain Solana.</p>
            </div>
            
            <div class="plans">
                <div class="plan-card">
                    <h3>Pass 30 Jours</h3>
                    <p class="subtext">Accès complet à toutes les fonctionnalités et optimisations illimitées pendant 1 mois.</p>
                    <div class="price">1 500 $<br><span style="font-size:16px; color:#22c55e;">(~{{ price_30 }} SOL)</span></div>
                    <a href="/checkout?plan=Pass_30_Jours&price={{ price_30 }}" class="btn">Sélectionner 30 Jours</a>
                </div>
                <div class="plan-card" style="border-color: #059669;">
                    <div style="position: absolute; top: -12px; right: 20px; background: #059669; color: white; padding: 4px 10px; font-size: 11px; border-radius: 6px; font-weight: bold;">POPULAIRE</div>
                    <h3>Pass 365 Jours</h3>
                    <p class="subtext">Accès illimité toute l'année, idéal pour les structures et professionnels exigeants.</p>
                    <div class="price">17 500 $<br><span style="font-size:16px; color:#22c55e;">(~{{ price_365 }} SOL)</span></div>
                    <a href="/checkout?plan=Pass_365_Jours&price={{ price_365 }}" class="btn" style="background: #22c55e; color: white;">Sélectionner 365 Jours</a>
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
        <title>Tableau de bord & Graphiques</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 0; }}
            .main-container {{ max-width: 1000px; margin: 40px auto; padding: 20px; }}
            .card {{ background: #1e293b; padding: 30px; border-radius: 16px; border: 1px solid #334155; box-shadow: 0 10px 25px rgba(0,0,0,0.5); margin-bottom: 30px; }}
            h1 {{ color: #38bdf8; margin-top: 0; }}
            .stats-grid {{ display: flex; gap: 20px; margin-bottom: 30px; }}
            .stat-box {{ background: #334155; flex: 1; padding: 20px; border-radius: 12px; text-align: center; border-left: 4px solid #38bdf8; }}
            .stat-value {{ font-size: 26px; font-weight: bold; color: #38bdf8; margin-top: 5px; }}
            .chart-container {{ position: relative; height: 350px; width: 100%; }}
        </style>
    </head>
    <body>
        {NAVBAR_HTML}
        <div class="main-container">
            <div class="card">
                <h1>📊 Tableau de Bord et Statistiques</h1>
                <p style="color: #94a3b8;">Visualisez en temps réel l'activité de la plateforme et la répartition des abonnements validés par la blockchain.</p>
                
                <div class="stats-grid">
                    <div class="stat-box">
                        <div style="color: #94a3b8; font-size: 14px;">Total Clés Délivrées</div>
                        <div class="stat-value">{total_keys}</div>
                    </div>
                    <div class="stat-box" style="border-left-color: #22c55e;">
                        <div style="color: #94a3b8; font-size: 14px;">Pass 30 Jours Actifs</div>
                        <div class="stat-value" style="color: #22c55e;">{count_30}</div>
                    </div>
                    <div class="stat-box" style="border-left-color: #f59e0b;">
                        <div style="color: #94a3b8; font-size: 14px;">Pass 365 Jours Actifs</div>
                        <div class="stat-value" style="color: #f59e0b;">{count_365}</div>
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
                        label: 'Nombre d\'abonnements validés',
                        data: [{count_30}, {count_365}],
                        backgroundColor: ['#38bdf8', '#22c55e'],
                        borderWidth: 0,
                        borderRadius: 8
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{
                        legend: {{ labels: {{ color: '#f8fafc' }} }}
                    }},
                    scales: {{
                        y: {{ ticks: {{ color: '#94a3b8' }}, grid: {{ color: '#334155' }} }},
                        x: {{ ticks: {{ color: '#94a3b8' }}, grid: {{ display: false }} }}
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
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 0; }}
            .main-container {{ max-width: 650px; margin: 40px auto; padding: 20px; }}
            .card {{ background: #1e293b; padding: 35px; border-radius: 16px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); text-align: center; border: 1px solid #334155; }}
            h1 {{ color: #38bdf8; margin-top: 0; }}
            .wallet-box {{ background: #0f172a; padding: 18px; border-radius: 8px; font-family: monospace; font-size: 15px; margin: 20px 0; word-break: break-all; color: #38bdf8; border: 1px dashed #475569; display: flex; justify-content: space-between; align-items: center; }}
            input[type="text"] {{ width: 90%; padding: 14px; border-radius: 8px; border: 1px solid #475569; background: #0f172a; color: #fff; margin-bottom: 20px; font-size: 14px; outline: none; }}
            input[type="text"]:focus {{ border-color: #38bdf8; }}
            .btn {{ background: #22c55e; color: #fff; padding: 14px 28px; border: none; border-radius: 8px; font-weight: bold; cursor: pointer; font-size: 16px; transition: 0.2s; }}
            .btn:hover {{ background: #16a34a; box-shadow: 0 0 15px rgba(34, 197, 94, 0.4); }}
            .copy-btn {{ background: #334155; color: #38bdf8; border: none; padding: 8px 12px; border-radius: 6px; cursor: pointer; font-weight: bold; font-size: 12px; transition: 0.2s; }}
            .copy-btn:hover {{ background: #475569; }}
            .info-text {{ font-size: 14px; color: #94a3b8; line-height: 1.5; margin-bottom: 20px; }}
        </style>
    </head>
    <body>
        {NAVBAR_HTML}
        <div class="main-container">
            <div class="card">
                <h1>🛡️ Validation Verified Solana</h1>
                <p class="info-text">Formule : <strong>{{ plan.replace('_', ' ') }}</strong><br>
                Montant exact requis : <strong style="color: #22c55e; font-size: 20px;">{{ price }} SOL</strong></p>
                
                <p class="info-text">Transférez les fonds vers l'adresse marchand sécurisée :</p>
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
                <a href="/" style="color: #94a3b8; text-decoration: none; font-size: 14px;">← Annuler et retourner à l'accueil</a>
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
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 0; }}
                .main-container {{ max-width: 650px; margin: 40px auto; padding: 20px; }}
                .card {{ background: #1e293b; padding: 40px; border-radius: 16px; text-align: center; box-shadow: 0 10px 25px rgba(0,0,0,0.5); border: 1px solid #334155; }}
                .key-box {{ background: #0f172a; padding: 22px; border-radius: 8px; font-size: 20px; font-family: monospace; font-weight: bold; color: #22c55e; margin: 25px 0; border: 1px solid #059669; display: flex; justify-content: space-between; align-items: center; }}
                .copy-btn {{ background: #22c55e; color: white; border: none; padding: 10px 16px; border-radius: 6px; cursor: pointer; font-weight: bold; }}
            </style>
        </head>
        <body>
            {NAVBAR_HTML}
            <div class="main-container">
                <div class="card">
                    <h1 style="color: #22c55e; margin-top:0;">🛡️ Paiement Confirmé !</h1>
                    <p style="color: #94a3b8; line-height: 1.6;">Votre transaction a été validée avec succès sur la blockchain Solana. Voici votre clé d'accès unique :</p>
                    
                    <div class="key-box">
                        <span id="keyText">{{ key }}</span>
                        <button class="copy-btn" onclick="copyKey()">Copier</button>
                    </div>
                    
                    <p style="color: #94a3b8; font-size: 13px;">Conservez cette clé précieusement.</p>
                    <br>
                    <a href="/" style="color: #38bdf8; text-decoration: none; font-weight: bold;">Retour à l'accueil</a>
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
        <body style="background:#0f172a; color:white; font-family:sans-serif; text-align:center; padding:0; margin:0;">
            {NAVBAR_HTML}
            <div style="max-width:550px; margin:80px auto; background:#1e293b; padding:40px; border-radius:16px; border:1px solid #475569;">
                <h2 style="color:#ef4444; margin-top:0;">🛡️ Échec de la vérification Solana</h2>
                <p style="color:#94a3b8; line-height:1.6; margin-bottom:25px;">{message}</p>
                <a href="/" style="color:#38bdf8; text-decoration:none; font-weight:bold;">← Réessayer</a>
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
        
        rows_html = "".join([f"<tr><td style='padding:12px; border-bottom:1px solid #334155;'>{k[0]}</td><td style='padding:12px; border-bottom:1px solid #334155; font-family:monospace; color:#38bdf8;'>{k[1]}</td><td style='padding:12px; border-bottom:1px solid #334155;'>{k[2]}</td><td style='padding:12px; border-bottom:1px solid #334155;'>{k[3]}</td><td style='padding:12px; border-bottom:1px solid #334155;'><small style='color:#94a3b8;'>{k[5][:20] if k[5] else 'Manuel'}...</small></td></tr>" for k in keys])
        
        return f"""
        <body style="background:#0f172a; color:white; font-family:sans-serif; margin:0; padding:0;">
            {NAVBAR_HTML}
            <div style="max-width:1000px; margin:40px auto; background:#1e293b; padding:35px; border-radius:16px; border:1px solid #334155; box-shadow: 0 10px 25px rgba(0,0,0,0.5);">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:20px;">
                    <h1 style="color:#38bdf8; margin:0;">Panneau d'Administration</h1>
                    <a href="/logout" style="color:#ef4444; text-decoration:none; font-weight:bold; background:#7f1d1d; padding:8px 16px; border-radius:6px;">Se déconnecter</a>
                </div>
                <p style="color:#94a3b8; margin-bottom:20px;">Historique global des clés certifiées sur la blockchain :</p>
                <table style="width:100%; border-collapse:collapse; margin-top:10px;">
                    <tr style="background:#334155; color:#38bdf8; text-align:left;">
                        <th style="padding:12px;">ID</th>
                        <th style="padding:12px;">Clé d'Accès</th>
                        <th style="padding:12px;">Formule</th>
                        <th style="padding:12px;">Statut</th>
                        <th style="padding:12px;">Signature Solana</th>
                    </tr>
                    {rows_html if rows_html else '<tr><td colspan="5" style="padding:20px; text-align:center; color:#94a3b8;">Aucune clé enregistrée pour le moment.</td></tr>'}
                </table>
            </div>
        </body>
        """
        
    return f"""
    <body style="background:#0f172a; color:white; font-family:sans-serif; margin:0; padding:0;">
        {NAVBAR_HTML}
        <div style="display:flex; justify-content:center; align-items:center; height:80vh;">
            <div style="background:#1e293b; padding:35px; border-radius:16px; width:350px; text-align:center; border:1px solid #334155; box-shadow: 0 10px 25px rgba(0,0,0,0.5);">
                <h2 style="color:#38bdf8; margin-top:0;">Connexion Admin</h2>
                <form method="POST">
                    <input type="password" name="password" placeholder="Mot de passe administrateur" required style="width:90%; padding:12px; margin-bottom:20px; border-radius:8px; border:1px solid #475569; background:#0f172a; color:#fff; font-size:14px; outline:none;"><br>
                    <button type="submit" style="background:#38bdf8; color:#0f172a; padding:12px 20px; border:none; border-radius:8px; font-weight:bold; cursor:pointer; width:100%; font-size:15px;">Se connecter</button>
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
    # TRÈS IMPORTANT POUR RENDER : Utilisation du port dynamique fourni par l'hébergeur
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
