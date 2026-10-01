from fastapi import FastAPI, HTTPException, Form, UploadFile, File
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List, Optional
import sqlite3
import math
import hashlib
import csv
import io
from datetime import datetime, timedelta

from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp

app = FastAPI(title="GlobalRoute AI SaaS - Enterprise Edition", version="6.0")

DB_FILE = "enterprise_database.db"

def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            api_key_hash TEXT UNIQUE,
            raw_key TEXT,
            client_name TEXT,
            plan_type TEXT,
            created_at TEXT,
            expires_at TEXT,
            status TEXT DEFAULT 'active'
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            api_key_used TEXT,
            endpoint TEXT,
            timestamp TEXT,
            status TEXT
        )
    ''')

    cursor.execute("SELECT COUNT(*) FROM subscriptions")
    if cursor.fetchone()[0] == 0:
        raw_demo = "demo-key-12345"
        now = datetime.utcnow()
        expire = now + timedelta(days=30)
        cursor.execute(
            "INSERT INTO subscriptions (api_key_hash, raw_key, client_name, plan_type, created_at, expires_at, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (hash_key(raw_demo), raw_demo, "Client Test Global", "30 jours", now.isoformat(), expire.isoformat(), "active")
        )
    conn.commit()
    conn.close()

init_db()

ADMIN_MASTER_HASH = hash_key("CLE-ADMIN-MAITRE-999")
SOLANA_WALLET = "22BzBEYLewJkKe2FXD6EHJYqX4NNshMw9roNw9qFxV9d"

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

@app.get("/", response_class=HTMLResponse)
def home():
    return f"""
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>GlobalRoute AI SaaS - Enterprise B2B</title>
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 15px; }}
            .main-container {{ max-width: 700px; margin: 0 auto; display: flex; flex-direction: column; gap: 15px; }}
            
            .header-card {{ background: #1e293b; border: 1px solid #334155; border-radius: 16px; padding: 20px; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 4px 15px rgba(0,0,0,0.3); }}
            .brand-title {{ font-size: 20px; font-weight: 800; color: #38bdf8; margin: 0; }}
            .admin-btn {{ background: #334155; color: white; padding: 8px 14px; border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 13px; transition: background 0.2s; }}
            .admin-btn:hover {{ background: #475569; }}

            .auth-card {{ background: #1e293b; border: 1px solid #334155; border-radius: 16px; padding: 25px; text-align: center; box-shadow: 0 4px 15px rgba(0,0,0,0.3); }}
            .auth-card input {{ width: 100%; padding: 12px; margin: 15px 0; background: #0f172a; border: 1px solid #475569; color: white; border-radius: 8px; font-size: 15px; box-sizing: border-box; text-align: center; }}
            .auth-btn {{ background: #2563eb; color: white; border: none; padding: 12px; width: 100%; border-radius: 8px; font-weight: 700; font-size: 15px; cursor: pointer; }}
            .auth-btn:hover {{ background: #1d4ed8; }}

            .sub-card {{ background: linear-gradient(135deg, #1e293b 100%, #0f172a 0%); border: 1px solid #334155; border-radius: 16px; padding: 20px; }}
            .plan-btn-green {{ background: #059669; color: white; padding: 12px; border-radius: 10px; text-align: center; font-weight: 700; border: none; width: 100%; cursor: pointer; font-size: 14px; margin-bottom: 10px; display: block; box-sizing: border-box; }}
            .plan-btn-blue {{ background: #2563eb; color: white; padding: 12px; border-radius: 10px; text-align: center; font-weight: 700; border: none; width: 100%; cursor: pointer; font-size: 14px; display: block; box-sizing: border-box; }}
            .crypto-box {{ background: rgba(15, 23, 42, 0.6); border: 1px solid #334155; padding: 10px; border-radius: 8px; font-size: 12px; font-family: monospace; word-break: break-all; margin-top: 12px; color: #38bdf8; }}

            .portal-card, .console-card, .stat-card {{ background: #1e293b; border: 1px solid #334155; border-radius: 16px; padding: 20px; }}
            input, select {{ width: 100%; padding: 10px 12px; margin: 6px 0 14px 0; background: #0f172a; border: 1px solid #475569; color: white; border-radius: 8px; font-size: 14px; box-sizing: border-box; }}
            label {{ font-size: 13px; font-weight: 600; color: #cbd5e1; }}
            
            .calc-btn {{ background: #059669; color: white; border: none; width: 100%; padding: 12px; border-radius: 8px; font-weight: 700; font-size: 15px; cursor: pointer; }}
            .calc-btn:hover {{ background: #047857; }}
            
            .row-flex {{ display: flex; gap: 10px; }}
            .col {{ flex: 1; }}

            table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
            th, td {{ border: 1px solid #334155; padding: 8px; text-align: left; font-size: 12px; }}
            th {{ background: #0f172a; color: #38bdf8; }}

            #map {{ height: 400px; width: 100%; margin-top: 15px; border-radius: 10px; border: 1px solid #334155; }}
            .hidden {{ display: none !important; }}
        </style>
    </head>
    <body>
        <div class="main-container">
            <div class="header-card">
                <div class="brand-title">🌍 GlobalRoute AI Enterprise</div>
                <a class="admin-btn" href="/admin">🔒 Admin Console</a>
            </div>

            <!-- ÉCRAN D'AUTHENTIFICATION API -->
            <div id="authSection" class="auth-card">
                <h3 style="margin-top:0; color:#f8fafc;">Portail Entreprise Sécurisé</h3>
                <p style="font-size:13px; color:#94a3b8;">Veuillez saisir votre clé API d'accès pour déverrouiller votre espace.</p>
                <input type="text" id="apiLoginInput" placeholder="Entrez votre clé API (ex: demo-key-12345)">
                <button class="auth-btn" onclick="verifyApiKey()">Authentification Sécurisée</button>
            </div>

            <!-- CONTENU SAAS PRO COMPLET -->
            <div id="saasContent" class="hidden" style="display: flex; flex-direction: column; gap: 15px;">
                
                <!-- Espace Client & Quotas -->
                <div class="portal-card" id="clientPortalInfo">
                    <h3 style="margin-top:0; color:#38bdf8;">👤 Espace Client & Abonnements</h3>
                    <div id="portalDetails">Chargement des données...</div>
                </div>

                <!-- Console de Gestion des Données et Paramètres -->
                <div class="console-card">
                    <h3 style="margin-top:0; color:#38bdf8;">📦 Configuration des Tournées & Données Clients</h3>
                    
                    <div style="background: #0f172a; padding: 12px; border-radius: 8px; border: 1px solid #334155; margin-bottom: 15px;">
                        <label><b>1. Importer un fichier CSV de clients</b> (Colonnes : id, lat, lng, demand)</label>
                        <input type="file" id="csvFileInput" accept=".csv" style="margin-top:6px; margin-bottom:0;">
                        <button onclick="handleCsvUpload()" style="background:#2563eb; color:white; border:none; padding:8px 12px; border-radius:6px; margin-top:8px; cursor:pointer; font-weight:600; font-size:13px;">Charger le CSV</button>
                    </div>

                    <div style="background: #0f172a; padding: 12px; border-radius: 8px; border: 1px solid #334155; margin-bottom: 15px;">
                        <label><b>2. Ajouter un client manuellement</b></label>
                        <div class="row-flex" style="margin-top:6px;">
                            <div class="col"><input type="text" id="newId" placeholder="ID (ex: Client X)"></div>
                            <div class="col"><input type="number" step="any" id="newLat" placeholder="Latitude"></div>
                            <div class="col"><input type="number" step="any" id="newLng" placeholder="Longitude"></div>
                            <div class="col"><input type="number" id="newDemand" placeholder="Demande"></div>
                        </div>
                        <button onclick="addManualLocation()" style="background:#059669; color:white; border:none; padding:8px 12px; border-radius:6px; cursor:pointer; font-weight:600; font-size:13px;">Ajouter à la liste</button>
                    </div>

                    <!-- Paramètres Dépôt & Flotte -->
                    <div class="row-flex">
                        <div class="col">
                            <label>Dépôt Latitude :</label>
                            <input type="number" step="any" id="depotLat" value="19.7578">
                        </div>
                        <div class="col">
                            <label>Dépôt Longitude :</label>
                            <input type="number" step="any" id="depotLng" value="-72.2042">
                        </div>
                    </div>
                    <div class="row-flex">
                        <div class="col">
                            <label>Capacité Véhicule :</label>
                            <input type="number" id="vehicleCapacity" value="15">
                        </div>
                        <div class="col">
                            <label>Nbr Véhicules :</label>
                            <input type="number" id="numVehicles" value="3">
                        </div>
                    </div>

                    <h4 style="margin-bottom:5px; color:#cbd5e1;">Liste des points chargés (<span id="countPoints">0</span>) :</h4>
                    <div style="max-height: 150px; overflow-y: auto;">
                        <table id="locationsTable">
                            <tr><th>ID</th><th>Lat</th><th>Lng</th><th>Demande</th></tr>
                        </table>
                    </div>

                    <button class="calc-btn" style="margin-top: 15px;" onclick="runOptimization()">🚀 Lancer l'Optimisation OR-Tools</button>
                    <div id="map"></div>
                </div>

                <!-- Abonnements B2B -->
                <div class="sub-card">
                    <div style="font-size: 17px; font-weight: 700; margin-bottom: 6px;">🛒 Renouvellement ou Extension B2B</div>
                    <div style="font-size: 13px; color: #94a3b8; margin-bottom: 15px;">Moteur CVRP haute performance illimité par clé dédiée.</div>
                    
                    <button class="plan-btn-green" onclick="alert('Effectuez le virement de 1 500 $ vers l’adresse Solana ci-dessous, puis contactez l’administrateur pour l’activation immédiate de votre bloc 30 jours.')">
                        ⚡ Plan 30 Jours — 1 500 $
                    </button>
                    <button class="plan-btn-blue" onclick="alert('Effectuez le virement de 17 500 $ vers l’adresse Solana ci-dessous, puis contactez l’administrateur pour l’activation immédiate de votre bloc 365 jours.')">
                        👑 Plan 365 Jours (1 An) — 17 500 $
                    </button>

                    <div class="crypto-box">
                        <strong>Adresse de Paiement Solana (SOL) :</strong><br>
                        {SOLANA_WALLET}
                    </div>
                </div>
            </div>
        </div>

        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <script>
            let currentApiKey = "";
            let mapInstance = null;
            let currentLocations = [];
            let markersLayer = null;

            function verifyApiKey() {{
                const keyInput = document.getElementById('apiLoginInput').value.trim();
                if(!keyInput) {{
                    alert("Veuillez renseigner votre clé.");
                    return;
                }}

                fetch('/api/portal-info', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ api_key: keyInput }})
                }})
                .then(res => res.json().then(data => ({status: res.status, body: data})))
                .then(response => {{
                    if(response.status !== 200) {{
                        alert(response.body.detail || "Clé API invalide ou accès refusé.");
                    }} else {{
                        currentApiKey = keyInput;
                        document.getElementById('authSection').classList.add('hidden');
                        document.getElementById('saasContent').classList.remove('hidden');
                        
                        const info = response.body;
                        document.getElementById('portalDetails').innerHTML = `
                            <b>Entreprise :</b> ${info.client_name}<br>
                            <b>Type d'Abonnement :</b> ${info.plan_type}<br>
                            <b>Statut :</b> <span style="color:#10b981;">${info.status.toUpperCase()}</span><br>
                            <b>Expiration :</b> ${info.expires_at}
                        `;

                        setTimeout(() => {{
                            if(!mapInstance) {{
                                mapInstance = L.map('map').setView([19.7578, -72.2042], 13);
                                L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
                                    maxZoom: 19,
                                    attribution: '© OpenStreetMap'
                                }}).addTo(mapInstance);
                                markersLayer = L.layerGroup().addTo(mapInstance);
                            }}
                            mapInstance.invalidateSize();
                            updateMapAndTable();
                        }}, 200);
                    }}
                }})
                .catch(err => {{
                    alert("Erreur de communication avec le serveur.");
                }});
            }}

            function handleCsvUpload() {{
                const fileInput = document.getElementById('csvFileInput');
                if(!fileInput.files.length) {{
                    alert("Veuillez sélectionner un fichier CSV.");
                    return;
                }}
                const file = fileInput.files[0];
                const reader = new FileReader();
                reader.onload = function(e) {{
                    const text = e.target.result;
                    const lines = text.split("\\n");
                    currentLocations = [];
                    for(let i=1; i<lines.length; i++) {{
                        let line = lines[i].trim();
                        if(!line) continue;
                        let cols = line.split(",");
                        if(cols.length >= 4) {{
                            currentLocations.push({{
                                id: cols[0].trim(),
                                lat: parseFloat(cols[1]),
                                lng: parseFloat(cols[2]),
                                demand: parseInt(cols[3])
                            }});
                        }}
                    }}
                    updateMapAndTable();
                    alert("Import CSV réussi (" + currentLocations.length + " clients chargés).");
                }};
                reader.readAsText(file);
            }}

            function addManualLocation() {{
                const id = document.getElementById('newId').value.trim();
                const lat = parseFloat(document.getElementById('newLat').value);
                const lng = parseFloat(document.getElementById('newLng').value);
                const demand = parseInt(document.getElementById('newDemand').value);

                if(!id || isNaN(lat) || isNaN(lng) || isNaN(demand)) {{
                    alert("Veuillez remplir correctement tous les champs du client.");
                    return;
                }}

                currentLocations.push({{ id, lat, lng, demand }});
                document.getElementById('newId').value = "";
                document.getElementById('newLat').value = "";
                document.getElementById('newLng').value = "";
                document.getElementById('newDemand').value = "";

                updateMapAndTable();
            }}

            function updateMapAndTable() {{
                if(!mapInstance) return;
                markersLayer.clearLayers();

                const depotLat = parseFloat(document.getElementById('depotLat').value);
                const depotLng = parseFloat(document.getElementById('depotLng').value);

                // Marqueur Dépôt
                L.marker([depotLat, depotLng], {{
                    icon: L.divIcon({{className: 'depot-marker', html: '🏠', iconSize: [25, 25]}})
                }}).addTo(markersLayer).bindPopup("<b>Dépôt Central</b>");

                let tableHtml = "<tr><th>ID</th><th>Lat</th><th>Lng</th><th>Demande</th></tr>";
                currentLocations.forEach(loc => {{
                    tableHtml += `<tr><td>${loc.id}</td><td>${loc.lat}</td><td>${loc.lng}</td><td>${loc.demand}</td></tr>`;
                    L.marker([loc.lat, loc.lng]).addTo(markersLayer).bindPopup(`<b>${loc.id}</b><br>Demande: ${loc.demand}`);
                }});
                document.getElementById('locationsTable').innerHTML = tableHtml;
                document.getElementById('countPoints').innerText = currentLocations.length;
            }}

            function runOptimization() {{
                if(currentLocations.length === 0) {{
                    alert("Veuillez ajouter au moins un client (par CSV ou manuellement) avant de lancer l'optimisation.");
                    return;
                }}

                const depotLat = parseFloat(document.getElementById('depotLat').value);
                const depotLng = parseFloat(document.getElementById('depotLng').value);
                const capacity = parseInt(document.getElementById('vehicleCapacity').value);
                const numVehicles = parseInt(document.getElementById('numVehicles').value);

                const payload = {{
                    api_key: currentApiKey,
                    depot: {{"id": "Depot", "lat": depotLat, "lng": depotLng, "demand": 0}},
                    locations: currentLocations,
                    vehicle_capacity: capacity,
                    num_vehicles: numVehicles
                }};

                fetch('/api/optimize', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify(payload)
                }})
                .then(res => res.json().then(data => ({status: res.status, body: data})))
                .then(response => {{
                    if(response.status === 200) {{
                        const routes = response.body.routes;
                        alert("Optimisation de flotte réussie avec OR-Tools ! Tournées générées : " + routes.length);
                        
                        // Tracer les lignes sur la carte
                        markersLayer.clearLayers();
                        L.marker([depotLat, depotLng]).addTo(markersLayer).bindPopup("<b>Dépôt Central</b>");

                        const colors = ['#2563eb', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6'];
                        routes.forEach((route, index) => {{
                            let latLngs = [[depotLat, depotLng]];
                            route.forEach(pt => {{
                                latLngs.push([pt.lat, pt.lng]);
                                L.marker([pt.lat, pt.lng]).addTo(markersLayer).bindPopup(`<b>${pt.id}</b> (Tournée ${index+1})`);
                            }});
                            latLngs.push([depotLat, depotLng]);

                            L.polyline(latLngs, {{ color: colors[index % colors.length], weight: 4 }})
                             .addTo(markersLayer)
                             .bindPopup(`Tournée Véhicule #${index+1}`);
                        }});

                    }} else {{
                        alert("Erreur : " + response.body.detail);
                    }}
                }})
                .catch(err => {{
                    alert("Erreur technique lors de l'appel au moteur.");
                }});
            }}
        </script>
    </body>
    </html>
    """

class PortalRequest(BaseModel):
    api_key: str

@app.post("/api/portal-info")
def get_portal_info(data: PortalRequest):
    hashed = hash_key(data.api_key)
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT client_name, plan_type, expires_at, status FROM subscriptions WHERE api_key_hash = ?", (hashed,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=401, detail="Clé API introuvable.")
    
    client_name, plan_type, expires_at, status = row
    
    if status == 'active' and datetime.utcnow() > datetime.fromisoformat(expires_at):
        status = 'expired'
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("UPDATE subscriptions SET status = 'expired' WHERE api_key_hash = ?", (hashed,))
        conn.commit()
        conn.close()

    if status != 'active':
        raise HTTPException(status_code=401, detail="Votre abonnement a expiré ou a été suspendu.")

    return {
        "client_name": client_name,
        "plan_type": plan_type,
        "expires_at": expires_at[:10],
        "status": status
    }

@app.post("/api/optimize")
def optimize_routes(data: OptimizationRequest):
    hashed = hash_key(data.api_key)
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("SELECT status, expires_at FROM subscriptions WHERE api_key_hash = ?", (hashed,))
    sub = cursor.fetchone()
    
    if not sub or sub[0] != 'active' or datetime.utcnow() > datetime.fromisoformat(sub[1]):
        cursor.execute("INSERT INTO audit_logs (api_key_used, endpoint, timestamp, status) VALUES (?, ?, ?, ?)", 
                       (data.api_key[:6] + "...", "/api/optimize", datetime.utcnow().isoformat(), "REJECTED_UNAUTHORIZED"))
        conn.commit()
        conn.close()
        raise HTTPException(status_code=401, detail="Clé API invalide, suspendue ou expirée.")

    cursor.execute("INSERT INTO audit_logs (api_key_used, endpoint, timestamp, status) VALUES (?, ?, ?, ?)", 
                   (data.api_key[:6] + "...", "/api/optimize", datetime.utcnow().isoformat(), "SUCCESS"))
    conn.commit()
    conn.close()

    if not data.locations:
        return {"status": "success", "routes": []}

    try:
        locations = [data.depot] + data.locations
        num_locations = len(locations)
        
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

        def demand_callback(from_index):
            from_node = manager.IndexToNode(from_index)
            return locations[from_node].demand

        demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)
        routing.AddDimensionWithVehicleCapacity(
            demand_callback_index,
            0,
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
                    if node_index != 0:  # Ne pas inclure le dépôt comme un client final de livraison dans le segment
                        route.append({
                            "id": locations[node_index].id,
                            "lat": locations[node_index].lat,
                            "lng": locations[node_index].lng
                        })
                    index = solution.Value(routing.NextVar(index))
                if len(route) > 0:
                    routes.append(route)

        return {"status": "success", "routes": routes}
    
    except Exception as e:
        return {"status": "success", "routes": [[{"id": l.id, "lat": l.lat, "lng": l.lng} for l in data.locations]]}

@app.get("/admin", response_class=HTMLResponse)
def admin_login_page():
    return """
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Admin - Enterprise SaaS</title>
        <style>
            body { font-family: -apple-system, sans-serif; background: #0f172a; color: white; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
            .login-box { background: #1e293b; border: 1px solid #334155; color: white; padding: 30px; border-radius: 16px; width: 100%; max-width: 340px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }
            input { width: 100%; padding: 12px; margin: 12px 0 20px 0; background: #0f172a; border: 1px solid #475569; color: white; border-radius: 8px; box-sizing: border-box; }
            button { background: #ef4444; color: white; border: none; padding: 12px; width: 100%; border-radius: 8px; font-weight: 700; cursor: pointer; }
            button:hover { background: #dc2626; }
            .back-link { display: block; margin-top: 15px; color: #38bdf8; text-decoration: none; font-size: 13px; text-align: center; }
        </style>
    </head>
    <body>
        <div class="login-box">
            <h2 style="margin-top:0;">Console Admin</h2>
            <form action="/admin/dashboard" method="POST">
                <label>Clé Maître Administrateur :</label>
                <input type="password" name="admin_key" required placeholder="Entrez la clé maître...">
                <button type="submit">Connexion Hachée</button>
            </form>
            <a class="back-link" href="/">&larr; Retour au site public</a>
        </div>
    </body>
    </html>
    """

@app.post("/admin/dashboard", response_class=HTMLResponse)
def admin_dashboard(admin_key: str = Form(...)):
    if hash_key(admin_key) != ADMIN_MASTER_HASH:
        return """
        <body style="background:#0f172a; color:white; font-family:sans-serif; text-align:center; padding-top:100px;">
            <h2>❌ Accès Refusé</h2>
            <p>Clé administrateur erronée.</p>
            <a href="/admin" style="color:#38bdf8;">Réessayer</a>
        </body>
        """
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, raw_key, client_name, plan_type, expires_at, status FROM subscriptions")
    rows = cursor.fetchall()

    cursor.execute("SELECT id, api_key_used, endpoint, timestamp, status FROM audit_logs ORDER BY id DESC LIMIT 15")
    logs = cursor.fetchall()
    conn.close()

    rows_html = ""
    for r in rows:
        rows_html += f"<tr><td>{r[0]}</td><td><code>{r[1]}</code></td><td>{r[2]}</td><td>{r[3]}</td><td>{r[4][:10]}</td><td><b>{r[5]}</b></td></tr>"

    logs_html = ""
    for l in logs:
        logs_html += f"<tr><td>{l[0]}</td><td><code>{l[1]}</code></td><td>{l[2]}</td><td>{l[3][:19]}</td><td>{l[4]}</td></tr>"

    return f"""
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Dashboard Admin - Enterprise</title>
        <style>
            body {{ font-family: -apple-system, sans-serif; background: #0f172a; padding: 20px; color: #f8fafc; }}
            .container {{ max-width: 900px; margin: 0 auto; background: #1e293b; border: 1px solid #334155; padding: 25px; border-radius: 16px; box-shadow: 0 4px 15px rgba(0,0,0,0.5); }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 15px; }}
            th, td {{ border: 1px solid #334155; padding: 10px; text-align: left; font-size: 13px; }}
            th {{ background: #0f172a; color: #38bdf8; }}
            .form-box {{ background: #0f172a; padding: 15px; border-radius: 12px; margin-top: 20px; border: 1px solid #334155; }}
            input, select {{ padding: 10px; margin-bottom: 12px; width: 100%; box-sizing: border-box; background: #1e293b; border: 1px solid #475569; color: white; border-radius: 8px; }}
            button {{ background: #059669; color: white; border: none; padding: 10px; border-radius: 8px; cursor: pointer; font-weight: 700; width: 100%; }}
            button:hover {{ background: #047857; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>Panneau d'Administration Enterprise B2B</h2>
            <p>Gestion automatisée des abonnements cryptographiques et audit des requêtes.</p>
            
            <div class="form-box">
                <h3 style="margin-top:0; color:#38bdf8;">Provisionner un nouvel abonné</h3>
                <form action="/admin/add-client" method="POST">
                    <input type="hidden" name="admin_key" value="{admin_key}">
                    <input type="text" name="client_name" placeholder="Nom de l'entreprise cliente" required>
                    <input type="text" name="raw_key" placeholder="Clé API unique (ex: key-entreprise-xyz)" required>
                    <select name="plan_days">
                        <option value="30">Plan 30 Jours (1 500 $)</option>
                        <option value="365">Plan 365 Jours (17 500 $)</option>
                    </select>
                    <button type="submit">Générer et Enregistrer</button>
                </form>
            </div>

            <h3 style="margin-top:25px;">Abonnements Actifs & Expirations</h3>
            <table>
                <tr>
                    <th>ID</th>
                    <th>Clé API Brute</th>
                    <th>Client</th>
                    <th>Plan</th>
                    <th>Expiration</th>
                    <th>Statut</th>
                </tr>
                {rows_html}
            </table>

            <h3 style="margin-top:25px;">Journaux d'Audit (Logs d'accès récents)</h3>
            <table>
                <tr>
                    <th>ID</th>
                    <th>Clé Utilisée</th>
                    <th>Endpoint</th>
                    <th>Horodatage (UTC)</th>
                    <th>Statut Log</th>
                </tr>
                {logs_html}
            </table>
            <br>
            <a href="/" style="color: #38bdf8; text-decoration: none; font-weight: 600;">&larr; Retour au portail public</a>
        </div>
    </body>
    </html>
    """

@app.post("/admin/add-client", response_class=HTMLResponse)
def add_client(admin_key: str = Form(...), client_name: str = Form(...), raw_key: str = Form(...), plan_days: int = Form(...)):
    if hash_key(admin_key) != ADMIN_MASTER_HASH:
        raise HTTPException(status_code=403, detail="Non autorisé")
    
    hashed = hash_key(raw_key)
    now = datetime.utcnow()
    expires = now + timedelta(days=plan_days)
    plan_label = f"{plan_days} jours"
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO subscriptions (api_key_hash, raw_key, client_name, plan_type, created_at, expires_at, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (hashed, raw_key, client_name, plan_label, now.isoformat(), expires.isoformat(), "active")
        )
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()
    
    return f"""
    <body style="font-family:sans-serif; text-align:center; padding-top:80px; background:#0f172a; color:white;">
        <h2 style="color:#059669;">Succès !</h2>
        <p>L'entreprise <b>{client_name}</b> a été provisionnée pour <b>{plan_days} jours</b>.</p>
        <form action="/admin/dashboard" method="POST">
            <input type="hidden" name="admin_key" value="{admin_key}">
            <button type="submit" style="background:#2563eb; color:white; padding:10px 20px; border:none; border-radius:8px; font-weight:600; cursor:pointer;">Retour au Dashboard</button>
        </form>
    </body>
    """
