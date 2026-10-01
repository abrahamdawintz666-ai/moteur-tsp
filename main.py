from fastapi import FastAPI, HTTPException, Form, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import List, Optional
import sqlite3
import math

app = FastAPI(title="GlobalRoute AI", version="2.5")

# Configuration de la base de données SQLite
DB_FILE = "database.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            api_key TEXT UNIQUE,
            client_name TEXT,
            plan_type TEXT,
            status TEXT DEFAULT 'active'
        )
    ''')
    # Insérer une clé de test par défaut si elle n'existe pas
    cursor.execute("SELECT COUNT(*) FROM subscriptions")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO subscriptions (api_key, client_name, plan_type, status) VALUES (?, ?, ?, ?)",
                       ("demo-key-12345", "Client Test", "mensuel", "active"))
    conn.commit()
    conn.close()

init_db()

# Clé maître administrateur et Adresse Solana
ADMIN_MASTER_KEY = "CLE-ADMIN-MAITRE-999"
SOLANA_WALLET = "22BzBEYLewJkKe2FXD6EHJYqX4NNshMw9roNw9qFxV9d"

# Modèle pour l'API d'optimisation CVRP
class Location(BaseModel):
    id: str
    lat: float
    lng: float
    demand: int

class OptimizationRequest(BaseModel):
    api_key: str
    depot: Location
    locations: List[Location]
    vehicle_capacity: int

@app.get("/", response_class=HTMLResponse)
def home():
    return f"""
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>GlobalRoute AI - SaaS Logistique & CVRP</title>
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
        <style>
            body {{ font-family: Arial, sans-serif; background: #f4f6f9; color: #333; margin: 0; padding: 20px; text-align: center; }}
            .container {{ max-width: 800px; margin: 20px auto; background: white; padding: 30px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); }}
            h1 {{ color: #2c3e50; }}
            p {{ color: #666; }}
            .btn {{ display: inline-block; background: #3498db; color: white; padding: 12px 24px; border-radius: 6px; text-decoration: none; font-weight: bold; margin-top: 15px; cursor: pointer; border: none; }}
            .btn:hover {{ background: #2980b9; }}
            .plans {{ display: none; margin-top: 25px; text-align: left; background: #f8f9fa; padding: 20px; border-radius: 8px; }}
            .plan-card {{ background: white; padding: 15px; margin-bottom: 15px; border-radius: 6px; border: 1px solid #ddd; }}
            .crypto-box {{ background: #e8f4fd; padding: 10px; font-size: 13px; word-break: break-all; border-radius: 4px; margin-top: 10px; font-family: monospace; }}
            #map {{ height: 400px; width: 100%; margin-top: 25px; border-radius: 8px; display: none; }}
            .admin-link {{ display: block; margin-top: 30px; color: #7f8c8d; font-size: 14px; text-decoration: none; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>GlobalRoute AI</h1>
            <p>Plateforme SaaS intelligente d'optimisation de tournées et de gestion logistique pour professionnels.</p>
            
            <button class="btn" onclick="togglePlans()">Prendre l'abonnement</button>
            
            <div id="plansSection" class="plans">
                <h3>Choisissez votre abonnement :</h3>
                
                <div class="plan-card">
                    <h4>Plan Mensuel - 49$ / mois</h4>
                    <p>Accès complet aux algorithmes de routage CVRP et support prioritaire.</p>
                    <div class="crypto-box"><strong>Paiement Solana (SOL) :</strong><br>{SOLANA_WALLET}</div>
                </div>
                
                <div class="plan-card">
                    <h4>Plan Annuel - 490$ / an (2 mois offerts)</h4>
                    <p>Idéal pour les flottes en forte croissance avec mises à jour en temps réel.</p>
                    <div class="crypto-box"><strong>Paiement Solana (SOL) :</strong><br>{SOLANA_WALLET}</div>
                </div>
                <p style="font-size: 12px; color: #e74c3c;">* Après votre transfert SOL, contactez l'admin pour activer votre clé API unique.</p>
            </div>

            <div style="margin-top: 30px;">
                <button class="btn" style="background: #27ae60;" onclick="toggleApp()">Tester l'outil de routage</button>
            </div>

            <div id="appSection" style="display:none; text-align:left; margin-top:20px;">
                <h3>Espace de Simulation Logistique</h3>
                <p>Entrez votre clé API pour lancer le calcul d'optimisation :</p>
                <input type="text" id="apiKeyInput" placeholder="Votre clé API..." style="padding:8px; width:60%; margin-bottom:10px;"><br>
                <div id="map"></div>
            </div>
            
            <a class="admin-link" href="/admin">Accéder à la Console Administrateur</a>
        </div>

        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <script>
            function togglePlans() {{
                var section = document.getElementById('plansSection');
                section.style.display = (section.style.display === 'block') ? 'none' : 'block';
            }}

            function toggleApp() {{
                var section = document.getElementById('appSection');
                if (section.style.display === 'block') {{
                    section.style.display = 'none';
                }} else {{
                    section.style.display = 'block';
                    setTimeout(function() {{ map.invalidateSize(); }}, 300);
                }}
            }}

            // Initialisation de la carte Leaflet
            var map = L.map('map').setView([19.7578, -72.2042], 13); // Centré par défaut (ex: Cap-Haïtien / Caraïbes)
            L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
                maxZoom: 19,
                attribution: '© OpenStreetMap'
            }}).addTo(map);
        </script>
    </body>
    </html>
    """

@app.post("/api/optimize")
def optimize_routes(data: OptimizationRequest):
    # Vérification de la validité de la clé API dans la base de données
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM subscriptions WHERE api_key = ? AND status = 'active'", (data.api_key,))
    sub = cursor.fetchone()
    conn.close()

    if not sub:
        raise HTTPException(status_code=401, detail="Clé API invalide ou abonnement inactif.")

    # Algorithme simple de routage (CVRP heuristique de base)
    unvisited = data.locations.copy()
    routes = []
    
    while unvisited:
        current_route = []
        current_load = 0
        current_pos = data.depot
        
        while unvisited:
            # Trouver le point le plus proche respectant la capacité du véhicule
            next_loc = min(
                [loc for loc in unvisited if current_load + loc.demand <= data.vehicle_capacity],
                key=lambda loc: math.hypot(loc.lat - current_pos.lat, loc.lng - current_pos.lng),
                default=None
            )
            
            if not next_loc:
                break
                
            current_route.append(next_loc)
            current_load += next_loc.demand
            unvisited.remove(next_loc)
            current_pos = next_loc
            
        if not current_route:
            break
        routes.append(current_route)

    return {"status": "success", "routes": routes}

@app.get("/admin", response_class=HTMLResponse)
def admin_login_page():
    return """
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Admin - GlobalRoute AI</title>
        <style>
            body { font-family: Arial, sans-serif; background: #2c3e50; color: white; margin: 0; padding: 50px; text-align: center; }
            .login-box { max-width: 400px; margin: 0 auto; background: white; color: #333; padding: 30px; border-radius: 8px; }
            input { width: 100%; padding: 10px; margin: 10px 0; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box; }
            button { background: #e74c3c; color: white; border: none; padding: 10px 20px; width: 100%; border-radius: 4px; font-weight: bold; cursor: pointer; }
            button:hover { background: #c0392b; }
        </style>
    </head>
    <body>
        <div class="login-box">
            <h2>Administration</h2>
            <form action="/admin/dashboard" method="POST">
                <label>Entrez la Clé Maître :</label>
                <input type="password" name="admin_key" required placeholder="Clé admin...">
                <button type="submit">Se connecter</button>
            </form>
        </div>
    </body>
    </html>
    """

@app.post("/admin/dashboard", response_class=HTMLResponse)
def admin_dashboard(admin_key: str = Form(...)):
    if admin_key != ADMIN_MASTER_KEY:
        return """
        <body style="background:#2c3e50; color:white; text-align:center; padding-top:50px; font-family:Arial;">
            <h2>Accès Refusé</h2>
            <p>Clé administrateur incorrecte.</p>
            <a href="/admin" style="color:#3498db;">Réessayer</a>
        </body>
        """
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, api_key, client_name, plan_type, status FROM subscriptions")
    rows = cursor.fetchall()
    conn.close()

    rows_html = ""
    for r in rows:
        rows_html += f"<tr><td>{r[0]}</td><td><code>{r[1]}</code></td><td>{r[2]}</td><td>{r[3]}</td><td>{r[4]}</td></tr>"

    return f"""
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Dashboard Admin</title>
        <style>
            body {{ font-family: Arial, sans-serif; background: #f4f6f9; padding: 20px; color: #333; }}
            .container {{ max-width: 800px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
            th, td {{ border: 1px solid #ddd; padding: 10px; text-align: left; font-size: 14px; }}
            th {{ background: #34495e; color: white; }}
            .form-group {{ background: #ecf0f1; padding: 15px; border-radius: 6px; margin-top: 20px; }}
            input, select {{ padding: 8px; margin-bottom: 10px; width: 100%; box-sizing: border-box; }}
            button {{ background: #27ae60; color: white; border: none; padding: 10px 15px; border-radius: 4px; cursor: pointer; font-weight: bold; width: 100%; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>Tableau de Bord Administrateur</h2>
            <p>Gestion des clés API et abonnements clients.</p>
            
            <div class="form-group">
                <h3>Ajouter un abonné manuellement</h3>
                <form action="/admin/add-client" method="POST">
                    <input type="hidden" name="admin_key" value="{ADMIN_MASTER_KEY}">
                    <input type="text" name="client_name" placeholder="Nom du client" required>
                    <input type="text" name="api_key" placeholder="Clé API unique (ex: key-xyz)" required>
                    <select name="plan_type">
                        <option value="mensuel">Plan Mensuel (SOL)</option>
                        <option value="annuel">Plan Annuel (SOL)</option>
                    </select>
                    <button type="submit">Créer la clé client</button>
                </form>
            </div>

            <h3>Liste des Abonnés</h3>
            <table>
                <tr>
                    <th>ID</th>
                    <th>Clé API</th>
                    <th>Client</th>
                    <th>Plan</th>
                    <th>Statut</th>
                </tr>
                {rows_html}
            </table>
            <br>
            <a href="/" style="color: #3498db; text-decoration: none;">&larr; Retour à l'accueil</a>
        </div>
    </body>
    </html>
    """

@app.post("/admin/add-client", response_class=HTMLResponse)
def add_client(admin_key: str = Form(...), client_name: str = Form(...), api_key: str = Form(...), plan_type: str = Form(...)):
    if admin_key != ADMIN_MASTER_KEY:
        raise HTTPException(status_code=403, detail="Non autorisé")
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO subscriptions (api_key, client_name, plan_type, status) VALUES (?, ?, ?, ?)",
                       (api_key, client_name, plan_type, "active"))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()
    
    return f"""
    <body style="font-family:Arial; text-align:center; padding-top:50px;">
        <h2 style="color:green;">Client ajouté avec succès !</h2>
        <p>Le client <b>{client_name}</b> a bien été enregistré.</p>
        <a href="/admin" style="background:#3498db; color:white; padding:10px 20px; text-decoration:none; border-radius:4px;">Retour au dashboard</a>
    </body>
    """
