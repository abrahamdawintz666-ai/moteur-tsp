import os
import math
import csv
import io
import uuid
import sqlite3
from datetime import datetime, timedelta
from typing import List, Tuple, Optional

from fastapi import FastAPI, HTTPException, Security, Depends, UploadFile, File
from fastapi.security.api_key import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel

from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp

app = FastAPI(
    title="GlobalRoute AI - Enterprise SaaS Sécurisé",
    description="Plateforme logistique mondiale avec GPS temps réel, calculateur de distance, CVRP et console admin."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_FILE = "database.db"

# Récupération sécurisée depuis les variables d'environnement de Render
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "Boaram")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "CLE-ADMIN-MAITRE-999")

def initialiser_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS abonnes (
            cle_api TEXT PRIMARY KEY,
            nom TEXT NOT NULL,
            email TEXT NOT NULL,
            actif INTEGER NOT NULL,
            admin INTEGER NOT NULL,
            expiration TEXT
        )
    ''')
    cursor.execute("SELECT COUNT(*) FROM abonnes")
    if cursor.fetchone()[0] == 0:
        cursor.execute('''
            INSERT INTO abonnes (cle_api, nom, email, actif, admin, expiration)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (ADMIN_PASSWORD, ADMIN_USERNAME, "admin@globalroute.ai", 1, 1, None))
    else:
        cursor.execute('''
            UPDATE abonnes SET cle_api = ? WHERE admin = 1
        ''', (ADMIN_PASSWORD,))
    conn.commit()
    conn.close()

initialiser_db()

API_KEY_HEADER = APIKeyHeader(name="X-API-KEY", auto_error=False)

def verifier_cle_api(api_key: str = Security(API_KEY_HEADER)):
    if not api_key:
        raise HTTPException(status_code=401, detail="Clé API manquante dans les en-têtes (X-API-KEY). Veuillez entrer votre clé.")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT nom, actif, admin, expiration FROM abonnes WHERE cle_api = ?", (api_key,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=403, detail="Clé API invalide.")
    
    nom, actif, admin, expiration = row
    if not actif:
        raise HTTPException(status_code=403, detail="Abonnement désactivé.")
    
    if expiration:
        date_exp = datetime.fromisoformat(expiration)
        if datetime.utcnow() > date_exp:
            raise HTTPException(status_code=403, detail="Abonnement expiré.")
            
    return {"nom": nom, "admin": bool(admin)}

# --- MODÈLES DE DONNÉES ---
class Point(BaseModel):
    id: int
    lat: float
    lng: float
    name: str = ""
    demand: int = 1

class RouteRequest(BaseModel):
    depot: Point
    points: List[Point]
    vehicule_capacite: int = 50

class DistanceRequest(BaseModel):
    lat1: float
    lng1: float
    lat2: float
    lng2: float

class AdminCreationRequest(BaseModel):
    nom_entreprise: str
    email: str
    duree_jours: int = 30

# --- MOTEUR OR-TOOLS & MATHS ---
def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def resoudre_cvrp_ortools(depot: Point, points: List[Point], vehicule_capacite: int):
    tous_les_points = [depot] + points
    n = len(tous_les_points)
    
    matrix = [[0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i != j:
                matrix[i][j] = int(haversine_distance(
                    tous_les_points[i].lat, tous_les_points[i].lng,
                    tous_les_points[j].lat, tous_les_points[j].lng
                ) * 1000)

    manager = pywrapcp.RoutingIndexManager(n, 1, 0)
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return matrix[from_node][to_node]

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    def demand_callback(from_index):
        from_node = manager.IndexToNode(from_index)
        return tous_les_points[from_node].demand

    demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)
    routing.AddDimensionWithVehicleCapacity(
        demand_callback_index,
        0,
        [vehicule_capacite],
        True,
        "Capacity"
    )

    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    search_parameters.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    search_parameters.time_limit.seconds = 3

    solution = routing.SolveWithParameters(search_parameters)
    
    tournee = []
    distance_totale_m = 0
    charge_totale = 0
    
    if solution:
        index = routing.Start(0)
        while not routing.IsEnd(index):
            node_index = manager.IndexToNode(index)
            pt_dict = tous_les_points[node_index].dict()
            tournee.append(pt_dict)
            charge_totale += tous_les_points[node_index].demand
            
            previous_index = index
            index = solution.Value(routing.NextVar(index))
            distance_totale_m += routing.GetArcCostForVehicle(previous_index, index, 0)
            
        tournee.append(tous_les_points[0].dict())
        
    return tournee, distance_totale_m / 1000.0, charge_totale

# --- INTERFACE UTILISATEUR AVEC GPS & CALCULATEUR ---
@app.get("/", response_class=HTMLResponse)
async def index():
    return """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GlobalRoute AI - SaaS Logistique Mondial & GPS</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap" rel="stylesheet">
    <!-- Leaflet CSS -->
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <style>
        body { font-family: 'Inter', sans-serif; background: #f8fafc; color: #1e293b; margin: 0; padding: 0; }
        header { background: #0f172a; color: white; padding: 20px 40px; display: flex; justify-content: space-between; align-items: center; }
        header h1 { margin: 0; font-size: 20px; color: #38bdf8; }
        .main-container { max-width: 1350px; margin: 25px auto; padding: 0 20px; display: grid; grid-template-columns: 420px 1fr; gap: 25px; }
        .card { background: white; padding: 20px; border-radius: 12px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); margin-bottom: 20px; }
        h2 { font-size: 15px; margin-top: 0; color: #0f172a; border-bottom: 2px solid #f1f5f9; padding-bottom: 6px; }
        .form-group { margin-bottom: 12px; display: flex; flex-direction: column; gap: 4px; }
        .form-group label { font-size: 12px; font-weight: 600; color: #475569; }
        .form-group input { padding: 8px; border-radius: 6px; border: 1px solid #cbd5e1; font-size: 13px; }
        .btn { background: #2563eb; color: white; border: none; padding: 10px 15px; border-radius: 6px; font-weight: 600; cursor: pointer; width: 100%; font-size: 13px; margin-top: 5px; }
        .btn:hover { background: #1d4ed8; }
        .btn-gps { background: #10b981; }
        .btn-gps:hover { background: #059669; }
        #map { height: 550px; width: 100%; border-radius: 8px; z-index: 1; }
        #output, #distOutput { font-family: monospace; font-size: 11px; background: #0f172a; color: #34d399; padding: 10px; border-radius: 6px; margin-top: 10px; max-height: 120px; overflow-y: auto; }
        .admin-link { color: #94a3b8; text-decoration: none; font-size: 13px; }
        .admin-link:hover { color: white; }
        .error-msg { color: #ef4444; font-size: 11px; }
    </style>
</head>
<body>
    <header>
        <h1>GlobalRoute AI 🚀 (GPS & Mondial)</h1>
        <a href="/admin" class="admin-link">🔒 Accès Console Admin</a>
    </header>

    <div class="main-container">
        <!-- Colonne Gauche : Commandes -->
        <div>
            <!-- Clé & Paramètres -->
            <div class="card">
                <h2>🔑 Authentification Client</h2>
                <div class="form-group">
                    <label>Clé API Client :</label>
                    <input type="password" id="apiKey" placeholder="Entrez votre clé API...">
                    <span id="keyError" class="error-msg"></span>
                </div>
                
                <h2 style="margin-top: 15px;">🚌 GPS & Dépôt Actuel</h2>
                <button class="btn btn-gps" onclick="obtenirPositionGPS()">📍 Utiliser mon GPS en temps réel</button>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 8px;">
                    <div class="form-group"><label>Lat Dépôt :</label><input type="text" id="depotLat" value="48.8566"></div>
                    <div class="form-group"><label>Lng Dépôt :</label><input type="text" id="depotLng" value="2.3522"></div>
                </div>
                <div class="form-group">
                    <label>Capacité maximale du Bus :</label>
                    <input type="number" id="vehiculeCapacite" value="30">
                </div>

                <button class="btn" onclick="lancerOptimisation()">Calculer la Tournée</button>
                <div id="output">En attente...</div>
            </div>

            <!-- Calculateur de Distance entre 2 points -->
            <div class="card">
                <h2>📏 Calculateur Distance & Temps</h2>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
                    <div class="form-group"><label>Lat Point A :</label><input type="text" id="latA" value="48.8566"></div>
                    <div class="form-group"><label>Lng Point A :</label><input type="text" id="lngA" value="2.3522"></div>
                </div>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
                    <div class="form-group"><label>Lat Point B :</label><input type="text" id="latB" value="48.8600"></div>
                    <div class="form-group"><label>Lng Point B :</label><input type="text" id="lngB" value="2.3400"></div>
                </div>
                <button class="btn" style="background: #0284c7;" onclick="calculerDistanceDirecte()">Calculer Distance & Temps</button>
                <div id="distOutput">Résultat du calcul entre 2 points...</div>
            </div>
        </div>

        <!-- Colonne Droite : Carte Globale Leaflet -->
        <div class="card" style="display: flex; flex-direction: column;">
            <h2>🌍 Carte Interactive Mondiale en Temps Réel</h2>
            <div id="map"></div>
        </div>
    </div>

    <!-- Leaflet JS -->
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
        var map = L.map('map').setView([20, 0], 2);

        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19,
            attribution: '&copy; OpenStreetMap contributors'
        }).addTo(map);

        var layerGroup = L.layerGroup().addTo(map);
        var gpsMarker = null;

        // Fonction GPS du téléphone
        function obtenirPositionGPS() {
            if (navigator.geolocation) {
                navigator.geolocation.getCurrentPosition(
                    (position) => {
                        const lat = position.coords.latitude;
                        const lng = position.coords.longitude;
                        
                        document.getElementById('depotLat').value = lat;
                        document.getElementById('depotLng').value = lng;
                        
                        // Mettre à jour la carte avec la position GPS en temps réel
                        map.setView([lat, lng], 14);
                        
                        if (gpsMarker) {
                            layerGroup.removeLayer(gpsMarker);
                        }
                        gpsMarker = L.marker([lat, lng], {
                            icon: L.icon({
                                iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-red.png',
                                shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
                                iconSize: [25, 41], iconAnchor: [12, 41]
                            })
                        }).addTo(layerGroup).bindPopup("<b>📍 Votre position GPS actuelle</b>").openPopup();

                        alert("Position GPS détectée avec succès !");
                    },
                    (error) => {
                        alert("Erreur de géolocalisation : " + error.message);
                    },
                    { enableHighAccuracy: true }
                );
            } else {
                alert("La géolocalisation n'est pas supportée par votre navigateur.");
            }
        }

        // Calculateur de distance et temps entre 2 points
        async function calculerDistanceDirecte() {
            const lat1 = parseFloat(document.getElementById('latA').value);
            const lng1 = parseFloat(document.getElementById('lngA').value);
            const lat2 = parseFloat(document.getElementById('latB').value);
            const lng2 = parseFloat(document.getElementById('lngB').value);
            const key = document.getElementById('apiKey').value;

            if(!key) { alert("Veuillez entrer votre clé API !"); return; }

            try {
                const rep = await fetch('/api/calculer-distance', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-API-KEY': key },
                    body: JSON.stringify({ lat1, lng1, lat2, lng2 })
                });
                const data = await rep.json();
                if(rep.ok) {
                    document.getElementById('distOutput').innerText = `✅ Distance : ${data.distance_km} km\n⏱️ Temps estimé (véhicule) : ${data.temps_estime_min} min`;
                } else {
                    document.getElementById('distOutput').innerText = "Erreur : " + data.detail;
                }
            } catch(e) {
                document.getElementById('distOutput').innerText = "Erreur de connexion.";
            }
        }

        // Lancer l'optimisation de tournée
        async function lancerOptimisation() {
            const key = document.getElementById('apiKey').value;
            const capacite = parseInt(document.getElementById('vehiculeCapacite').value) || 30;
            const depotLat = parseFloat(document.getElementById('depotLat').value);
            const depotLng = parseFloat(document.getElementById('depotLng').value);
            const errSpan = document.getElementById('keyError');
            
            if(!key) { errSpan.innerText = "⚠️ Clé API requise !"; return; }
            errSpan.innerText = "";

            const payload = {
                depot: { id: 0, lat: depotLat, lng: depotLng, name: "Dépôt (GPS/Actuel)", demand: 0 },
                vehicule_capacite: capacite,
                points: [
                    { id: 1, lat: depotLat + 0.02, lng: depotLng + 0.02, name: "Arrêt Client 1", demand: 8 },
                    { id: 2, lat: depotLat - 0.02, lng: depotLng + 0.03, name: "Arrêt Client 2", demand: 12 },
                    { id: 3, lat: depotLat + 0.03, lng: depotLng - 0.02, name: "Arrêt Client 3", demand: 7 }
                ]
            };

            try {
                document.getElementById('output').innerText = "Calcul en cours...";
                const rep = await fetch('/api/optimiser', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-API-KEY': key },
                    body: JSON.stringify(payload)
                });
                const data = await rep.json();
                
                if(rep.ok) {
                    document.getElementById('output').innerText = `✅ Distance : ${data.distance_totale_km} km\nCharge : ${data.charge_totale}/${data.capacite_max}`;
                    
                    layerGroup.clearLayers();
                    let latLngs = [];
                    data.tournee.forEach((pt, index) => {
                        let coord = [pt.lat, pt.lng];
                        latLngs.push(coord);
                        L.marker(coord).addTo(layerGroup)
                          .bindPopup(`<b>${index === 0 ? 'DÉPÔT' : 'Étape ' + index}</b><br>${pt.name}`);
                    });

                    if(latLngs.length > 0) {
                        let polyline = L.polyline(latLngs, {color: '#2563eb', weight: 4}).addTo(layerGroup);
                        map.fitBounds(polyline.getBounds(), {padding: [50, 50]});
                    }
                } else {
                    document.getElementById('output').innerText = "Erreur : " + data.detail;
                }
            } catch(e) {
                document.getElementById('output').innerText = "Erreur de connexion au serveur.";
            }
        }
    </script>
</body>
</html>
    """

# --- API DISTANCE & TEMPS ENTRE DEUX POINTS ---
@app.post("/api/calculer-distance")
async def calculer_distance(data: DistanceRequest, auth = Depends(verifier_cle_api)):
    dist = haversine_distance(data.lat1, data.lng1, data.lat2, data.lng2)
    # Estimation de vitesse moyenne en ville/route : ~40 km/h -> temps en minutes = (distance / 40) * 60
    temps_min = round((dist / 40.0) * 60, 1)
    return {
        "statut": "succes",
        "distance_km": round(dist, 2),
        "temps_estime_min": temps_min
    }

# --- API OPTIMISATION ---
@app.post("/api/optimiser")
async def optimiser_tournee(data: RouteRequest, auth = Depends(verifier_cle_api)):
    try:
        tournee, distance, charge = resoudre_cvrp_ortools(data.depot, data.points, data.vehicule_capacite)
        return {
            "statut": "succes",
            "utilisateur": auth["nom"],
            "capacite_max": data.vehicule_capacite,
            "charge_totale": charge,
            "distance_totale_km": round(distance, 2),
            "nombre_etapes": len(tournee),
            "tournee": tournee
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- CONSOLE ADMIN (/admin) ---
@app.get("/admin", response_class=HTMLResponse)
async def afficher_admin_page():
    return f"""
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GlobalRoute AI - Console Admin</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap" rel="stylesheet">
    <style>
        body {{ font-family: 'Inter', sans-serif; background: #0f172a; color: #f8fafc; padding: 20px; margin: 0; }}
        .container {{ max-width: 800px; margin: 40px auto; background: #1e293b; padding: 30px; border-radius: 12px; }}
        h1 {{ color: #38bdf8; font-size: 20px; margin-top: 0; }}
        .form-group {{ margin-bottom: 15px; display: flex; flex-direction: column; gap: 5px; }}
        .form-group label {{ font-size: 13px; color: #cbd5e1; }}
        .form-group input, .form-group select {{ padding: 10px; border-radius: 6px; border: 1px solid #475569; background: #0f172a; color: white; }}
        .btn {{ background: #10b981; color: white; border: none; padding: 10px 20px; border-radius: 6px; font-weight: 600; cursor: pointer; }}
        .back-link {{ display: inline-block; margin-bottom: 15px; color: #38bdf8; text-decoration: none; font-size: 13px; }}
        #adminOutput {{ font-family: monospace; font-size: 11px; background: #0f172a; padding: 15px; border-radius: 6px; margin-top: 15px; color: #34d399; max-height: 250px; overflow-y: auto; }}
    </style>
</head>
<body>
    <div class="container">
        <a href="/" class="back-link">← Retourner à l'application</a>
        <h1>🔐 Console Admin ({ADMIN_USERNAME})</h1>
        <div class="form-group" style="margin-top: 15px;">
            <label>Clé API Admin :</label>
            <input type="password" id="adminKeyInput" placeholder="Entrez la clé admin...">
        </div>
        <hr style="border: 0; border-top: 1px solid #475569; margin: 15px 0;">
        <h3>Générer une clé client</h3>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
            <div class="form-group"><label>Entreprise :</label><input type="text" id="nomEntite" placeholder="Nom client"></div>
            <div class="form-group"><label>Email :</label><input type="email" id="emailClient" placeholder="client@mail.com"></div>
        </div>
        <button class="btn" onclick="genererCle()">Générer la Clé</button>
        <button class="btn" onclick="listerCles()" style="background: #2563eb; margin-left: 10px;">Lister les abonnés</button>
        <div id="adminOutput">Logs admin...</div>
    </div>
    <script>
        async function genererCle() {{
            const cle = document.getElementById('adminKeyInput').value;
            const nomEntite = document.getElementById('nomEntite').value;
            const email = document.getElementById('emailClient').value;
            if(!cle || !nomEntite || !email) {{ alert("Remplissez tous les champs !"); return; }}
            const rep = await fetch('/admin/generer-cle', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json', 'X-API-KEY': cle }},
                body: JSON.stringify({ nom_entreprise: nomEntite, email: email, duree_jours: 30 })
            }});
            const data = await rep.json();
            document.getElementById('adminOutput').innerText = rep.ok ? `✅ Clé générée : ${data.cle_api}` : "Erreur : " + data.detail;
        }}
        async function listerCles() {{
            const cle = document.getElementById('adminKeyInput').value;
            const rep = await fetch('/admin/cles', {{ headers: {{ 'X-API-KEY': cle }} }});
            const data = await rep.json();
            document.getElementById('adminOutput').innerText = rep.ok ? JSON.stringify(data.cles_enregistrees, null, 2) : "Erreur : " + data.detail;
        }}
    </script>
</body>
</html>
    """

@app.post("/admin/generer-cle")
async def admin_generer_cle(req: AdminCreationRequest, auth = Depends(verifier_cle_api)):
    if not auth["admin"]: raise HTTPException(status_code=403, detail="Admin requis.")
    nouvelle_cle = f"GR-{uuid.uuid4().hex.upper()}"
    date_exp = (datetime.utcnow() + timedelta(days=req.duree_jours)).isoformat()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO abonnes (cle_api, nom, email, actif, admin, expiration) VALUES (?, ?, ?, 1, 0, ?)', 
                   (nouvelle_cle, req.nom_entreprise, req.email, date_exp))
    conn.commit()
    conn.close()
    return {"statut": "succes", "entreprise": req.nom_entreprise, "cle_api": nouvelle_cle, "expiration": date_exp}

@app.get("/admin/cles")
async def admin_lister_cles(auth = Depends(verifier_cle_api)):
    if not auth["admin"]: raise HTTPException(status_code=403, detail="Admin requis.")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT cle_api, nom, email, actif, admin, expiration FROM abonnes")
    rows = cursor.fetchall()
    conn.close()
    return {"cles_enregistrees": [{"cle_api": r[0], "nom": r[1], "email": r[2], "actif": bool(r[3]), "admin": bool(r[4]), "expiration": r[5]} for r in rows]}
