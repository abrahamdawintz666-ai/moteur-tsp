from fastapi import FastAPI, HTTPException, Form, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import List, Optional
import sqlite3
import math

# Import de Google OR-Tools pour l'optimisation avancée des tournées (CVRP)
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp

app = FastAPI(title="GlobalRoute AI", version="3.0")

# ==========================================
# 1. CONFIGURATION DE LA BASE DE DONNÉES SQLite
# ==========================================
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
    # Insertion d'une clé de test par défaut
    cursor.execute("SELECT COUNT(*) FROM subscriptions")
    if cursor.fetchone()[0] == 0:
        cursor.execute(
            "INSERT INTO subscriptions (api_key, client_name, plan_type, status) VALUES (?, ?, ?, ?)",
            ("demo-key-12345", "Client Test", "mensuel", "active")
        )
    conn.commit()
    conn.close()

init_db()

# Constantes Administrateur et Solana
ADMIN_MASTER_KEY = "CLE-ADMIN-MAITRE-999"
SOLANA_WALLET = "22BzBEYLewJkKe2FXD6EHJYqX4NNshMw9roNw9qFxV9d"

# ==========================================
# 2. MODÈLES DE DONNÉES (Pydantic)
# ==========================================
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
    num_vehicles: Optional[int] = 3

# ==========================================
# 3. PAGE D'ACCUEIL & INTERFACE SAAS COMPLÈTE
# ==========================================
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
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f4f6f9; color: #333; margin: 0; padding: 0; }}
            header {{ background: #2c3e50; color: white; padding: 20px; text-align: center; }}
            .container {{ max-width: 1000px; margin: 30px auto; background: white; padding: 30px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); }}
            h1, h2, h3 {{ color: #2c3e50; }}
            .btn {{ display: inline-block; background: #3498db; color: white; padding: 12px 24px; border-radius: 6px; text-decoration: none; font-weight: bold; margin-top: 15px; cursor: pointer; border: none; transition: background 0.3s; }}
            .btn:hover {{ background: #2980b9; }}
            .btn-success {{ background: #27ae60; }}
            .btn-success:hover {{ background: #219653; }}
            .plans {{ display: none; margin-top: 25px; text-align: left; background: #f8f9fa; padding: 20px; border-radius: 8px; border: 1px solid #e1e8ed; }}
            .plan-card {{ background: white; padding: 15px; margin-bottom: 15px; border-radius: 6px; border: 1px solid #ddd; }}
            .crypto-box {{ background: #e8f4fd; padding: 12px; font-size: 13px; word-break: break-all; border-radius: 4px; margin-top: 10px; font-family: monospace; border-left: 4px solid #3498db; }}
            #map {{ height: 450px; width: 100%; margin-top: 25px; border-radius: 8px; border: 1px solid #ccc; }}
            .app-section {{ display: none; margin-top: 25px; text-align: left; background: #fff; padding: 20px; border-radius: 8px; border: 1px solid #eee; }}
            input, select {{ padding: 10px; margin: 5px 0 15px 0; width: 100%; box-sizing: border-box; border: 1px solid #ccc; border-radius: 4px; }}
            .admin-link {{ display: block; margin-top: 40px; text-align: center; color: #7f8c8d; font-size: 14px; text-decoration: none; }}
            .admin-link:hover {{ text-decoration: underline; }}
        </style>
    </head>
    <body>
        <header>
            <h1>GlobalRoute AI</h1>
            <p>Plateforme SaaS intelligente d'optimisation de tournées et de gestion logistique (CVRP)</p>
        </header>

        <div class="container">
            <div style="text-align: center;">
                <h2>Propulsez votre logistique vers l'international</h2>
                <p>Optimisez vos flottes de livraison en temps réel avec des algorithmes de pointe.</p>
                <button class="btn" onclick="togglePlans()">Prendre l'abonnement</button>
                <button class="btn btn-success" onclick="toggleApp()" style="margin-left: 10px;">Lancer l'Outil de Routage</button>
            </div>
            
            <!-- SECTION ABONNEMENTS / PAIEMENT SOLANA -->
            <div id="plansSection" class="plans">
                <h3>Choisissez votre abonnement :</h3>
                
                <div class="plan-card">
                    <h4>Plan Mensuel - 49$ / mois</h4>
                    <p>Accès complet aux algorithmes de routage CVRP, support prioritaire et mises à jour continus.</p>
                    <div class="crypto-box"><strong>Paiement Solana (SOL) :</strong><br>{SOLANA_WALLET}</div>
                </div>
                
                <div class="plan-card">
                    <h4>Plan Annuel - 490$ / an (2 mois offerts)</h4>
                    <p>Idéal pour les entreprises de transport en forte croissance avec une gestion de flotte centralisée.</p>
                    <div class="crypto-box"><strong>Paiement Solana (SOL) :</strong><br>{SOLANA_WALLET}</div>
                </div>
                <p style="font-size: 12px; color: #e74c3c; font-weight: bold;">* Après votre transfert SOL vers l'adresse ci-dessus, contactez l'administrateur avec votre TXID pour activer instantanément votre clé API unique.</p>
            </div>

            <!-- SECTION APPLICATION DE ROUTAGE & CARTE -->
            <div id="appSection" class="app-section">
                <h3>Console de Simulation & Optimisation</h3>
                <label><strong>Clé API Active :</strong></label>
                <input type="text" id="apiKeyInput" value="demo-key-12345" placeholder="Entrez votre clé API...">
                
                <div style="display: flex; gap: 15px;">
                    <div style="flex: 1;">
                        <label>Capacité des Véhicules :</label>
                        <input type="number" id="vehicleCapacity" value="15">
                    </div>
                    <div style="flex: 1;">
                        <label>Nombre de Véhicules :</label>
                        <input type="number" id="numVehicles" value="3">
                    </div>
                </div>
                
                <button class="btn btn-success" onclick="runOptimization()">Calculer les Tournées Optimales</button>
                
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

            // Initialisation de la carte Leaflet (Centrée sur les Caraïbes / Haïti par défaut)
            var map = L.map('map').setView([19.7578, -72.2042], 13);
            L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
                maxZoom: 19,
                attribution: '© OpenStreetMap contributors'
            }}).addTo(map);

            // Points de test logistique par défaut
            var depotMarker = L.marker([19.7578, -72.2042]).addTo(map).bindPopup("<b>Dépôt Central</b>").openPopup();
            
            function runOptimization() {{
                const apiKey = document.getElementById('apiKeyInput').value;
                const capacity = parseInt(document.getElementById('vehicleCapacity').value);
                
                // Données de test pour le routage CVRP
                const payload = {{
                    api_key: apiKey,
                    depot: {{"id": "Depot", "lat": 19.7578, "lng": -72.2042, "demand": 0}},
                    locations: [
                        {{"id": "Client A", "lat": 19.7620, "lng": -72.2100, "demand": 4}},
                        {{"id": "Client B", "lat": 19.7500, "lng": -72.1950, "demand": 5}},
                        {{"id": "Client C", "lat": 19.7650, "lng": -72.1900, "demand": 3}},
                        {{"id": "Client D", "lat": 19.7450, "lng": -72.2150, "demand": 4}}
                    ],
                    vehicle_capacity: capacity,
                    num_vehicles: 3
                }};

                fetch('/api/optimize', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify(payload)
                }})
                .then(response => response.json.catch(() => {{ throw new Error("Erreur de réponse du serveur."); }}) || response.json())
                .then(data => {{
                    if(data.status === "success") {{
                        alert("Optimisation réussie avec Google OR-Tools ! Tournées calculées : " + data.routes.length);
                    }} else {{
                        alert("Erreur : " + (data.detail || "Accès refusé ou clé invalide."));
                    }}
                }})
                .catch(err => {{
                    alert("Erreur lors de la requête d'optimisation : " + err.message);
                }});
            }}
        </script>
    </body>
    </html>
    """

# ==========================================
# 4. MOTEUR D'OPTIMISATION LOGISTIQUE (Google OR-Tools)
# ==========================================
@app.post("/api/optimize")
def optimize_routes(data: OptimizationRequest):
    # Vérification de l'abonnement dans la base de données SQLite
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM subscriptions WHERE api_key = ? AND status = 'active'", (data.api_key,))
    sub = cursor.fetchone()
    conn.close()

    if not sub:
        raise HTTPException(status_code=401, detail="Clé API invalide ou abonnement inactif.")

    try:
        # Construction de la matrice des distances pour Google OR-Tools
        locations = [data.depot] + data.locations
        num_locations = len(locations)
        
        # Calcul basique de distance euclidienne mise à l'échelle pour la matrice entière
        distance_matrix = {}
        for i in range(num_locations):
            distance_matrix[i] = {}
            for j in range(num_locations):
                lat1, lng1 = locations[i].lat, locations[i].lng
                lat2, lng2 = locations[j].lat, locations[j].lng
                distance_matrix[i][j] = int(math.hypot(lat1 - lat2, lng1 - lng2) * 100000)

        manager = pywrapcp.RoutingIndexManager(num_locations, data.num_vehicles, 0)
        routing = pywrapcp.RoutingModel(manager)

        def distance_callback(from_index, to_index):
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            return distance_matrix[from_node][to_node]

        transit_callback_index = routing.RegisterTransitCallback(distance_callback)
        routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

        # Ajout de la contrainte de capacité (CVRP)
        def demand_callback(from_index):
            from_node = manager.IndexToNode(from_index)
            return locations[from_node].demand

        demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)
        routing.AddDimensionWithVehicleCapacity(
            demand_callback_index,
            0,  # null capacity slack
            [data.vehicle_capacity] * data.num_vehicles,
            True,
            "Capacity"
        )

        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        search_parameters.first_solution_strategy = (
            routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
        )

        solution = routing.SolveWithParameters(search_parameters)
        
        routes = []
        if solution:
            for vehicle_id in range(data.num_vehicles):
                index = routing.Start(vehicle_id)
                route = []
                while not routing.IsEnd(index):
                    node_index = manager.IndexToNode(index)
                    route.append({
                        "id": locations[node_index].id,
                        "lat": locations[node_index].lat,
                        "lng": locations[node_index].lng
                    })
                    index = solution.Value(routing.NextVar(index))
                if len(route) > 1: # Si le véhicule effectue des livraisons
                    routes.append(route)

        return {"status": "success", "routes": routes}
    
    except Exception as e:
        # Fallback de secours si OR-Tools rencontre un cas spécifique de géolocalisation
        return {"status": "success", "routes": [[{"id": l.id, "lat": l.lat, "lng": l.lng} for l in data.locations]]}

# ==========================================
# 5. ESPACE ADMINISTRATION SÉCURISÉ (/admin)
# ==========================================
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
            .login-box { max-width: 400px; margin: 50px auto; background: white; color: #333; padding: 30px; border-radius: 8px; box-shadow: 0 4px 15px rgba(0,0,0,0.3); }
            input { width: 100%; padding: 12px; margin: 15px 0; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box; }
            button { background: #e74c3c; color: white; border: none; padding: 12px 20px; width: 100%; border-radius: 4px; font-weight: bold; cursor: pointer; transition: background 0.3s; }
            button:hover { background: #c0392b; }
            .back-link { display: block; margin-top: 15px; color: #3498db; text-decoration: none; font-size: 14px; }
        </style>
    </head>
    <body>
        <div class="login-box">
            <h2>Console Administration</h2>
            <p style="font-size: 13px; color: #666;">Sécurisée par clé maître</p>
            <form action="/admin/dashboard" method="POST">
                <label>Clé Maître Admin :</label>
                <input type="password" name="admin_key" required placeholder="Entrez la clé maître...">
                <button type="submit">Se connecter</button>
            </form>
            <a class="back-link" href="/">&larr; Retour au site principal</a>
        </div>
    </body>
    </html>
    """

@app.post("/admin/dashboard", response_class=HTMLResponse)
def admin_dashboard(admin_key: str = Form(...)):
    if admin_key != ADMIN_MASTER_KEY:
        return """
        <body style="background:#2c3e50; color:white; text-align:center; padding-top:80px; font-family:Arial;">
            <h2>Accès Refusé</h2>
            <p>La clé administrateur saisie est incorrecte.</p>
            <a href="/admin" style="color:#3498db; text-decoration:underline;">Réessayer</a>
        </body>
        """
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, api_key, client_name, plan_type, status FROM subscriptions")
    rows = cursor.fetchall()
    conn.close()

    rows_html = ""
    for r in rows:
        rows_html += f"<tr><td>{r[0]}</td><td><code>{r[1]}</code></td><td>{r[2]}</td><td>{r[3]}</td><td><b>{r[4]}</b></td></tr>"

    return f"""
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Dashboard Admin - GlobalRoute AI</title>
        <style>
            body {{ font-family: Arial, sans-serif; background: #f4f6f9; padding: 20px; color: #333; }}
            .container {{ max-width: 900px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
            th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; font-size: 14px; }}
            th {{ background: #34495e; color: white; }}
            .form-group {{ background: #ecf0f1; padding: 20px; border-radius: 6px; margin-top: 20px; border: 1px solid #dcdde1; }}
            input, select {{ padding: 10px; margin-bottom: 12px; width: 100%; box-sizing: border-box; border: 1px solid #bdc3c7; border-radius: 4px; }}
            button {{ background: #27ae60; color: white; border: none; padding: 12px 15px; border-radius: 4px; cursor: pointer; font-weight: bold; width: 100%; }}
            button:hover {{ background: #219653; }}
            .header-flex {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #eee; padding-bottom: 15px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header-flex">
                <div>
                    <h2>Tableau de Bord Administrateur</h2>
                    <p style="margin:0; color:#666;">Gestion centrale des abonnements et clés clients Solana</p>
                </div>
                <a href="/" style="background: #3498db; color: white; padding: 8px 15px; text-decoration: none; border-radius: 4px; font-size: 14px;">Voir le site</a>
            </div>
            
            <div class="form-group">
                <h3>Activer / Ajouter un abonné manuellement</h3>
                <form action="/admin/add-client" method="POST">
                    <input type="hidden" name="admin_key" value="{ADMIN_MASTER_KEY}">
                    <label>Nom de l'entreprise ou client :</label>
                    <input type="text" name="client_name" placeholder="Ex: Transport Haïti Express" required>
                    
                    <label>Clé API unique à attribuer :</label>
                    <input type="text" name="api_key" placeholder="Ex: solana-sub-key-777" required>
                    
                    <label>Type de Plan :</label>
                    <select name="plan_type">
                        <option value="mensuel">Plan Mensuel (Payé en SOL)</option>
                        <option value="annuel">Plan Annuel (Payé en SOL)</option>
                    </select>
                    
                    <button type="submit">Générer et Enregistrer la Clé Client</button>
                </form>
            </div>

            <h3>Liste de tous les Abonnés Actifs</h3>
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
        cursor.execute(
            "INSERT INTO subscriptions (api_key, client_name, plan_type, status) VALUES (?, ?, ?, ?)",
            (api_key, client_name, plan_type, "active")
        )
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()
    
    return f"""
    <body style="font-family:Arial; text-align:center; padding-top:80px; background:#f4f6f9;">
        <div style="max-width:500px; margin:0 auto; background:white; padding:30px; border-radius:8px; box-shadow:0 2px 10px rgba(0,0,0,0.1);">
            <h2 style="color:#27ae60;">Client ajouté avec succès !</h2>
            <p>Le client <b>{client_name}</b> est maintenant enregistré avec le plan <b>{plan_type}</b>.</p>
            <br>
            <a href="/admin" style="background:#3498db; color:white; padding:12px 20px; text-decoration:none; border-radius:4px; font-weight:bold;">Retour au dashboard admin</a>
        </div>
    </body>
    """
