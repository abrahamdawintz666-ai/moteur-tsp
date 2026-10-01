from fastapi import FastAPI, HTTPException, Form
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List, Optional
import sqlite3
import math
import hashlib
import uuid
from datetime import datetime, timedelta

from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp

app = FastAPI(title="GlobalRoute AI SaaS - Enterprise Edition", version="6.7")

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    return HTMLResponse(
        content=f"<h2 style='color:red;'>Erreur Interne du Serveur :</h2><pre>{str(exc)}</pre>",
        status_code=500
    )

DB_FILE = "enterprise_database.db"
SOLANA_WALLET = "22BzBEYLewJkKe2FXD6EHJYqX4NNshMw9roNw9qFxV9d"

def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()

def init_db():
    try:
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
                sub_status TEXT DEFAULT 'active'
            )
        ''')
        cursor.execute("SELECT COUNT(*) FROM subscriptions")
        if cursor.fetchone()[0] == 0:
            raw_demo = "demo-key-12345"
            now = datetime.now()
            expire = now + timedelta(days=30)
            cursor.execute(
                "INSERT INTO subscriptions (api_key_hash, raw_key, client_name, plan_type, created_at, expires_at, sub_status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (hash_key(raw_demo), raw_demo, "Client Test Global", "30 jours", now.isoformat(), expire.isoformat(), "active")
            )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Erreur init_db: {e}")

init_db()

ADMIN_MASTER_HASH = hash_key("CLE-ADMIN-MAITRE-999")

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
    html_content = """
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>GlobalRoute AI SaaS - Enterprise B2B</title>
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 15px; }
            .main-container { max-width: 700px; margin: 0 auto; display: flex; flex-direction: column; gap: 15px; }
            .header-card { background: #1e293b; border: 1px solid #334155; border-radius: 16px; padding: 20px; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 4px 15px rgba(0,0,0,0.3); }
            .brand-title { font-size: 20px; font-weight: 800; color: #38bdf8; margin: 0; }
            .admin-btn { background: #334155; color: white; padding: 8px 14px; border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 13px; }
            .auth-card { background: #1e293b; border: 1px solid #334155; border-radius: 16px; padding: 25px; text-align: center; box-shadow: 0 4px 15px rgba(0,0,0,0.3); }
            .auth-card input { width: 100%; padding: 12px; margin: 15px 0; background: #0f172a; border: 1px solid #475569; color: white; border-radius: 8px; font-size: 15px; box-sizing: border-box; text-align: center; }
            .auth-btn { background: #2563eb; color: white; border: none; padding: 12px; width: 100%; border-radius: 8px; font-weight: 700; font-size: 15px; cursor: pointer; }
            .sub-card { background: #1e293b; border: 1px solid #334155; border-radius: 16px; padding: 20px; }
            .plan-btn-green { background: #059669; color: white; padding: 12px; border-radius: 10px; text-align: center; font-weight: 700; border: none; width: 100%; cursor: pointer; font-size: 14px; margin-bottom: 10px; display: block; }
            .plan-btn-blue { background: #2563eb; color: white; padding: 12px; border-radius: 10px; text-align: center; font-weight: 700; border: none; width: 100%; cursor: pointer; font-size: 14px; display: block; }
            .crypto-box { background: rgba(15, 23, 42, 0.6); border: 1px solid #334155; padding: 10px; border-radius: 8px; font-size: 12px; font-family: monospace; word-break: break-all; margin-top: 12px; color: #38bdf8; }
            .portal-card, .console-card { background: #1e293b; border: 1px solid #334155; border-radius: 16px; padding: 20px; }
            
            .menu-bar { display: flex; gap: 8px; margin-bottom: 15px; border-bottom: 1px solid #334155; padding-bottom: 10px; }
            .menu-tab { background: #0f172a; color: #94a3b8; border: 1px solid #334155; padding: 8px 12px; border-radius: 8px; font-weight: 600; font-size: 13px; cursor: pointer; flex: 1; text-align: center; transition: 0.2s; }
            .menu-tab.active { background: #2563eb; color: white; border-color: #2563eb; }
            .menu-section { display: none; }
            .menu-section.active { display: block; }

            input, select { width: 100%; padding: 10px 12px; margin: 6px 0 14px 0; background: #0f172a; border: 1px solid #475569; color: white; border-radius: 8px; font-size: 14px; box-sizing: border-box; }
            label { font-size: 13px; font-weight: 600; color: #cbd5e1; }
            .calc-btn { background: #059669; color: white; border: none; width: 100%; padding: 12px; border-radius: 8px; font-weight: 700; font-size: 15px; cursor: pointer; }
            .row-flex { display: flex; gap: 10px; }
            .col { flex: 1; }
            table { width: 100%; border-collapse: collapse; margin-top: 10px; }
            th, td { border: 1px solid #334155; padding: 8px; text-align: left; font-size: 12px; }
            th { background: #0f172a; color: #38bdf8; }
            #map { height: 350px; width: 100%; margin-top: 15px; border-radius: 10px; border: 1px solid #334155; }
            .hidden { display: none !important; }
        </style>
    </head>
    <body>
        <div class="main-container">
            <div class="header-card">
                <div class="brand-title">🌍 GlobalRoute AI Enterprise</div>
                <a class="admin-btn" href="/admin">🔒 Admin</a>
            </div>

            <div id="authSection" class="auth-card">
                <h3 style="margin-top:0;">Portail Entreprise Sécurisé</h3>
                <p style="font-size:13px; color:#94a3b8;">Saisissez votre clé API pour déverrouiller l'outil.</p>
                <input type="text" id="apiLoginInput" placeholder="ex: demo-key-12345">
                <button class="auth-btn" onclick="verifyApiKey()">Connexion</button>
            </div>

            <div id="saasContent" class="hidden" style="display: flex; flex-direction: column; gap: 15px;">
                <div class="portal-card" id="clientPortalInfo">
                    <h3 style="margin-top:0; color:#38bdf8;">👤 Espace Client</h3>
                    <div id="portalDetails">Chargement...</div>
                </div>

                <div class="console-card">
                    <h3 style="margin-top:0; color:#38bdf8; margin-bottom: 12px;">🎛️ Console de Tournée Intelligente</h3>
                    
                    <div class="menu-bar">
                        <div class="menu-tab active" onclick="switchMenu('points', this)">📍 Clients & Points</div>
                        <div class="menu-tab" onclick="switchMenu('config', this)">⚙️ Configuration</div>
                        <div class="menu-tab" onclick="switchMenu('simulation', this)">🚀 Simulation & Carte</div>
                    </div>

                    <div id="menu-points" class="menu-section active">
                        <div style="background: #0f172a; padding: 12px; border-radius: 8px; border: 1px solid #334155; margin-bottom: 12px;">
                            <label><b>Importer un fichier CSV</b> (id, lat, lng, demand)</label>
                            <input type="file" id="csvFileInput" accept=".csv" style="margin-top:5px; margin-bottom:0;">
                            <button onclick="handleCsvUpload()" style="background:#2563eb; color:white; border:none; padding:6px 10px; border-radius:6px; margin-top:8px; cursor:pointer; font-weight:600; font-size:12px;">Charger le CSV</button>
                        </div>

                        <div style="background: #0f172a; padding: 12px; border-radius: 8px; border: 1px solid #334155; margin-bottom: 12px;">
                            <label><b>Ajouter un client manuellement</b></label>
                            <div class="row-flex" style="margin-top:4px;">
                                <div class="col"><input type="text" id="newId" placeholder="ID"></div>
                                <div class="col"><input type="number" step="any" id="newLat" placeholder="Lat"></div>
                                <div class="col"><input type="number" step="any" id="newLng" placeholder="Lng"></div>
                                <div class="col"><input type="number" id="newDemand" placeholder="Demande"></div>
                            </div>
                            <button onclick="addManualLocation()" style="background:#059669; color:white; border:none; padding:6px 10px; border-radius:6px; cursor:pointer; font-weight:600; font-size:12px;">Ajouter le client</button>
                        </div>

                        <h4 style="margin-bottom:5px; color:#cbd5e1;">Clients enregistrés (<span id="countPoints">0</span>) :</h4>
                        <div style="max-height: 140px; overflow-y: auto;">
                            <table id="locationsTable">
                                <tr><th>ID</th><th>Lat</th><th>Lng</th><th>Demande</th></tr>
                            </table>
                        </div>
                    </div>

                    <div id="menu-config" class="menu-section">
                        <h4 style="margin-top:0; color:#38bdf8;">Paramètres du Dépôt (Point de départ)</h4>
                        <div class="row-flex">
                            <div class="col"><label>Dépôt Lat :</label><input type="number" step="any" id="depotLat" value="19.7578"></div>
                            <div class="col"><label>Dépôt Lng :</label><input type="number" step="any" id="depotLng" value="-72.2042"></div>
                        </div>

                        <h4 style="color:#38bdf8; margin-top:10px;">Paramètres de la Flotte</h4>
                        <div class="row-flex">
                            <div class="col"><label>Capacité Véhicule :</label><input type="number" id="vehicleCapacity" value="15"></div>
                            <div class="col"><label>Nbr Véhicules :</label><input type="number" id="numVehicles" value="3"></div>
                        </div>
                    </div>

                    <div id="menu-simulation" class="menu-section">
                        <h4 style="margin-top:0; color:#38bdf8;">Lancement & Visualisation Cartographique</h4>
                        <button class="calc-btn" onclick="runOptimization()">🚀 Lancer l'Optimisation OR-Tools</button>
                        <div id="map"></div>
                    </div>
                </div>

                <div class="sub-card">
                    <div style="font-size: 16px; font-weight: 700; margin-bottom: 6px;">🛒 Renouvellement B2B</div>
                    <button class="plan-btn-green" onclick="alert('Transférez 1 500 $ vers l’adresse Solana ci-dessous, puis contactez l’admin pour activer 30 jours.')">⚡ Plan 30 Jours — 1 500 $</button>
                    <button class="plan-btn-blue" onclick="alert('Transférez 17 500 $ vers l’adresse Solana ci-dessous, puis contactez l’admin pour activer 365 jours.')">👑 Plan 365 Jours — 17 500 $</button>
                    <div class="crypto-box"><strong>Adresse Solana :</strong><br>""" + SOLANA_WALLET + """</div>
                </div>
            </div>
        </div>

        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <script>
            let currentApiKey = "";
            let mapInstance = null;
            let currentLocations = [];
            let markersLayer = null;

            function switchMenu(menuId, tabElement) {
                document.querySelectorAll('.menu-section').forEach(sec => sec.classList.remove('active'));
                document.querySelectorAll('.menu-tab').forEach(tab => tab.classList.remove('active'));
                
                document.getElementById('menu-' + menuId).classList.add('active');
                tabElement.classList.add('active');

                if(menuId === 'simulation') {
                    setTimeout(() => {
                        if(!mapInstance) {
                            mapInstance = L.map('map').setView([19.7578, -72.2042], 13);
                            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19 }).addTo(mapInstance);
                            markersLayer = L.layerGroup().addTo(mapInstance);
                        }
                        mapInstance.invalidateSize();
                        updateMapAndTable();
                    }, 200);
                }
            }

            function verifyApiKey() {
                const keyInput = document.getElementById('apiLoginInput').value.trim();
                if(!keyInput) { alert("Entrez une clé."); return; }

                fetch('/api/portal-info', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ api_key: keyInput })
                })
                .then(res => res.json().then(data => ({status: res.status, body: data})))
                .then(response => {
                    if(response.status !== 200) {
                        alert(response.body.detail || "Clé invalide.");
                    } else {
                        currentApiKey = keyInput;
                        document.getElementById('authSection').classList.add('hidden');
                        document.getElementById('saasContent').classList.remove('hidden');
                        const info = response.body;
                        document.getElementById('portalDetails').innerHTML = `
                            <b>Entreprise :</b> ${info.client_name}<br>
                            <b>Plan :</b> ${info.plan_type}<br>
                            <b>Statut :</b> <span style="color:#10b981;">${info.sub_status.toUpperCase()}</span><br>
                            <b>Expire le :</b> ${info.expires_at}
                        `;
                    }
                });
            }

            function handleCsvUpload() {
                const fileInput = document.getElementById('csvFileInput');
                if(!fileInput.files.length) { alert("Sélectionnez un fichier."); return; }
                const reader = new FileReader();
                reader.onload = function(e) {
                    const lines = e.target.result.split("\\n");
                    currentLocations = [];
                    for(let i=1; i<lines.length; i++) {
                        let line = lines[i].trim();
                        if(!line) continue;
                        let cols = line.split(",");
                        if(cols.length >= 4) {
                            currentLocations.push({ id: cols[0].trim(), lat: parseFloat(cols[1]), lng: parseFloat(cols[2]), demand: parseInt(cols[3]) });
                        }
                    }
                    updateMapAndTable();
                    alert("Import CSV réussi (" + currentLocations.length + " points).");
                };
                reader.readAsText(fileInput.files[0]);
            }

            function addManualLocation() {
                const id = document.getElementById('newId').value.trim();
                const lat = parseFloat(document.getElementById('newLat').value);
                const lng = parseFloat(document.getElementById('newLng').value);
                const demand = parseInt(document.getElementById('newDemand').value);
                if(!id || isNaN(lat) || isNaN(lng) || isNaN(demand)) { alert("Remplissez tous les champs."); return; }
                currentLocations.push({ id, lat, lng, demand });
                document.getElementById('newId').value = "";
                document.getElementById('newLat').value = "";
                document.getElementById('newLng').value = "";
                document.getElementById('newDemand').value = "";
                updateMapAndTable();
            }

            function updateMapAndTable() {
                let html = "<tr><th>ID</th><th>Lat</th><th>Lng</th><th>Demande</th></tr>";
                currentLocations.forEach(loc => {
                    html += `<tr><td>${loc.id}</td><td>${loc.lat}</td><td>${loc.lng}</td><td>${loc.demand}</td></tr>`;
                });
                document.getElementById('locationsTable').innerHTML = html;
                document.getElementById('countPoints').innerText = currentLocations.length;

                if(!mapInstance) return;
                markersLayer.clearLayers();
                const depotLat = parseFloat(document.getElementById('depotLat').value);
                const depotLng = parseFloat(document.getElementById('depotLng').value);
                L.marker([depotLat, depotLng], {icon: L.divIcon({className: 'depot', html: '🏠', iconSize: [20,20]})}).addTo(markersLayer).bindPopup("Dépôt");
                currentLocations.forEach(loc => {
                    L.marker([loc.lat, loc.lng]).addTo(markersLayer).bindPopup(loc.id);
                });
            }

            function runOptimization() {
                if(currentLocations.length === 0) { alert("Ajoutez au moins un client."); return; }
                const payload = {
                    api_key: currentApiKey,
                    depot: {"id": "Depot", "lat": parseFloat(document.getElementById('depotLat').value), "lng": parseFloat(document.getElementById('depotLng').value), "demand": 0},
                    locations: currentLocations,
                    vehicle_capacity: parseInt(document.getElementById('vehicleCapacity').value),
                    num_vehicles: parseInt(document.getElementById('numVehicles').value)
                };
                fetch('/api/optimize', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                })
                .then(res => res.json())
                .then(data => {
                    if(data.routes) {
                        alert("Optimisation réussie ! Tournées : " + data.routes.length);
                        markersLayer.clearLayers();
                        const depotLat = parseFloat(document.getElementById('depotLat').value);
                        const depotLng = parseFloat(document.getElementById('depotLng').value);
                        L.marker([depotLat, depotLng]).addTo(markersLayer);
                        const colors = ['#2563eb', '#10b981', '#f59e0b', '#ef4444'];
                        data.routes.forEach((route, idx) => {
                            let pts = [[depotLat, depotLng]];
                            route.forEach(pt => {
                                pts.push([pt.lat, pt.lng]);
                                L.marker([pt.lat, pt.lng]).addTo(markersLayer);
                            });
                            pts.push([depotLat, depotLng]);
                            L.polyline(pts, {color: colors[idx % colors.length], weight: 4}).addTo(markersLayer);
                        });
                    } else {
                        alert("Erreur d'optimisation.");
                    }
                });
            }
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

class PortalRequest(BaseModel):
    api_key: str

@app.post("/api/portal-info")
def get_portal_info(data: PortalRequest):
    hashed = hash_key(data.api_key)
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT client_name, plan_type, expires_at, sub_status FROM subscriptions WHERE api_key_hash = ?", (hashed,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=401, detail="Clé API introuvable.")
    client_name, plan_type, expires_at, sub_status = row
    return {"client_name": client_name, "plan_type": plan_type, "expires_at": expires_at[:10], "sub_status": sub_status}

@app.post("/api/optimize")
def optimize_routes(data: OptimizationRequest):
    hashed = hash_key(data.api_key)
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT sub_status FROM subscriptions WHERE api_key_hash = ?", (hashed,))
    sub_record = cursor.fetchone()
    conn.close()
    
    if not sub_record:
        raise HTTPException(status_code=401, detail="Non autorisé.")

    if not data.locations:
        return {"status": "success", "routes": []}

    try:
        locations = [data.depot] + data.locations
        num_locations = len(locations)
        distance_matrix = [[int(math.hypot(locations[i].lat - locations[j].lat, locations[i].lng - locations[j].lng) * 100000) for j in range(num_locations)] for i in range(num_locations)]

        manager = pywrapcp.RoutingIndexManager(num_locations, data.num_vehicles, 0)
        routing = pywrapcp.RoutingModel(manager)

        def distance_callback(from_index, to_index):
            return distance_matrix[manager.IndexToNode(from_index)][manager.IndexToNode(to_index)]

        routing.SetArcCostEvaluatorOfAllVehicles(routing.RegisterTransitCallback(distance_callback))

        def demand_callback(from_index):
            return locations[manager.IndexToNode(from_index)].demand

        routing.AddDimensionWithVehicleCapacity(
            routing.RegisterUnaryTransitCallback(demand_callback),
            0, [data.vehicle_capacity] * data.num_vehicles, True, "Capacity"
        )

        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        search_parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC

        solution = routing.SolveWithParameters(search_parameters)
        routes = []
        if solution:
            for vehicle_id in range(data.num_vehicles):
                index = routing.Start(vehicle_id)
                route = []
                while not routing.IsEnd(index):
                    node_index = manager.IndexToNode(index)
                    if node_index != 0:
                        route.append({"id": locations[node_index].id, "lat": locations[node_index].lat, "lng": locations[node_index].lng})
                    index = solution.Value(routing.NextVar(index))
                if route:
                    routes.append(route)
        return {"status": "success", "routes": routes}
    except Exception as e:
        fallback_routes = [[{"id": l.id, "lat": l.lat, "lng": l.lng} for l in data.locations]]
        return {"status": "success", "routes": fallback_routes}

@app.get("/admin", response_class=HTMLResponse)
def admin_login():
    return """
    <body style="background:#0f172a; color:white; font-family:sans-serif; display:flex; justify-content:center; align-items:center; height:100vh; margin:0;">
        <form action="/admin/dashboard" method="POST" style="background:#1e293b; padding:25px; border-radius:12px; border:1px solid #334155; width:300px;">
            <h3 style="margin-top:0;">Admin</h3>
            <input type="password" name="admin_key" placeholder="Clé maître..." required style="width:100%; padding:10px; margin:10px 0; background:#0f172a; border:1px solid #475569; color:white; border-radius:6px; box-sizing:border-box;">
            <button type="submit" style="background:#ef4444; color:white; border:none; padding:10px; width:100%; border-radius:6px; font-weight:700; cursor:pointer;">Entrer</button>
        </form>
    </body>
    """

@app.post("/admin/dashboard", response_class=HTMLResponse)
def admin_dash(admin_key: str = Form(...)):
    if hash_key(admin_key) != ADMIN_MASTER_HASH:
        return "<body style='background:#0f172a; color:white; text-align:center; padding-top:100px;'><h2>Accès Refusé</h2><a href='/admin' style='color:#38bdf8;'>Retour</a></body>"
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, raw_key, client_name, plan_type, expires_at, sub_status FROM subscriptions")
    rows = cursor.fetchall()
    conn.close()
    
    rows_html = "".join([f"<tr><td>{r[0]}</td><td><code>{r[1]}</code></td><td>{r[2]}</td><td>{r[3]}</td><td>{r[4][:10]}</td><td><b>{r[5]}</b></td></tr>" for r in rows])
    
    return f"""
    <body style="background:#0f172a; color:white; font-family:sans-serif; padding:20px;">
        <div style="max-width:900px; margin:0 auto; background:#1e293b; padding:25px; border-radius:12px; border:1px solid #334155;">
            <h2>Dashboard Admin - Gestion des Clés Clients</h2>
            
            <div style="background:#0f172a; padding:15px; border-radius:8px; border:1px solid #334155; margin-bottom:20px;">
                <h3 style="margin-top:0; color:#38bdf8;">Générer une nouvelle clé client</h3>
                <form action="/admin/create-key" method="POST" style="display:flex; gap:10px; align-items:flex-end;">
                    <input type="hidden" name="admin_key" value="{admin_key}">
                    <div style="flex:1;">
                        <label style="font-size:12px;">Nom de l'entreprise :</label>
                        <input type="text" name="client_name" placeholder="ex: Transport Express" required style="margin:4px 0 0 0; padding:8px; background:#1e293b; border:1px solid #475569; color:white; border-radius:6px; width:100%;">
                    </div>
                    <div style="flex:1;">
                        <label style="font-size:12px;">Plan :</label>
                        <select name="plan_type" style="margin:4px 0 0 0; padding:8px; background:#1e293b; border:1px solid #475569; color:white; border-radius:6px; width:100%;">
                            <option value="30 jours">30 jours (1 500 $)</option>
                            <option value="365 jours">365 jours (17 500 $)</option>
                        </select>
                    </div>
                    <div>
                        <button type="submit" style="background:#059669; color:white; border:none; padding:9px 15px; border-radius:6px; font-weight:700; cursor:pointer; height:37px;">Créer la clé</button>
                    </div>
                </form>
            </div>

            <h3 style="color:#cbd5e1; margin-bottom:5px;">Liste des abonnés actifs :</h3>
            <table style="width:100%; border-collapse:collapse; margin-top:5px;">
                <tr><th>ID</th><th>Clé API</th><th>Client</th><th>Plan</th><th>Expire</th><th>Statut</th></tr>
                {rows_html}
            </table>
            <br><a href="/" style="color:#38bdf8; text-decoration:none;">&larr; Retour au site principal</a>
        </div>
    </body>
    """

@app.post("/admin/create-key", response_class=HTMLResponse)
def admin_create_key(admin_key: str = Form(...), client_name: str = Form(...), plan_type: str = Form(...)):
    if hash_key(admin_key) != ADMIN_MASTER_HASH:
        return "<body style='background:#0f172a; color:white; text-align:center; padding-top:100px;'><h2>Accès Refusé</h2><a href='/admin' style='color:#38bdf8;'>Retour</a></body>"
    
    raw_new_key = f"key-{uuid.uuid4().hex[:10]}"
    now = datetime.now()
    days = 365 if "365" in plan_type else 30
    expire = now + timedelta(days=days)
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO subscriptions (api_key_hash, raw_key, client_name, plan_type, created_at, expires_at, sub_status) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (hash_key(raw_new_key), raw_new_key, client_name, plan_type, now.isoformat(), expire.isoformat(), "active")
        )
        conn.commit()
    except Exception as e:
        print(f"Erreur insertion: {e}")
    conn.close()
    
    # Redirige proprement vers le dashboard en repassant la clé admin via un formulaire invisible ou en réaffichant la page
    return f"""
    <body style="background:#0f172a; color:white; font-family:sans-serif; display:flex; justify-content:center; align-items:center; height:100vh; margin:0;">
        <div style="background:#1e293b; padding:30px; border-radius:12px; border:1px solid #334155; text-align:center; max-width:450px;">
            <h3 style="color:#10b981; margin-top:0;">Clé créée avec succès !</h3>
            <p style="font-size:13px; color:#94a3b8;">Voici la clé API pour <b>{client_name}</b> :</p>
            <div style="background:#0f172a; padding:12px; border-radius:8px; border:1px solid #38bdf8; color:#38bdf8; font-family:monospace; font-size:15px; margin:15px 0; word-break:break-all;">
                {raw_new_key}
            </div>
            <p style="font-size:12px; color:#f59e0b;">Copiez cette clé dès maintenant. Elle ne sera plus affichée en clair de cette façon.</p>
            <form action="/admin/dashboard" method="POST">
                <input type="hidden" name="admin_key" value="{admin_key}">
                <button type="submit" style="background:#2563eb; color:white; border:none; padding:10px 20px; border-radius:6px; font-weight:700; cursor:pointer; width:100%;">Retour au Dashboard</button>
            </form>
        </div>
    </body>
    """
