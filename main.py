import os
import math
import sqlite3
from datetime import datetime, timedelta
from typing import List

from fastapi import FastAPI, HTTPException, Security, Depends
from fastapi.security.api_key import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp

app = FastAPI(
    title="GlobalRoute AI - SaaS Logistique Mobile",
    description="Plateforme logistique avec écran d'accueil sécurisé, GPS temps réel et import intégré."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_FILE = "database.db"

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
        raise HTTPException(status_code=401, detail="Clé API manquante.")
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

class Point(BaseModel):
    id: int
    lat: float
    lng: float
    name: str = ""
    demand: int = 1

class RouteRequest(BaseModel):
    depot: Point
    points: List[Point]
    vehicule_capacite: int = 30

class DistanceRequest(BaseModel):
    lat1: float
    lng1: float
    lat2: float
    lng2: float

class AdminCreationRequest(BaseModel):
    nom_entreprise: str
    email: str
    duree_jours: int = 30

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

@app.get("/", response_class=HTMLResponse)
async def index():
    return """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GlobalRoute AI - Application Mobile Logistique</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <style>
        body { font-family: 'Inter', sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 0; }
        header { background: #1e293b; color: white; padding: 15px 20px; display: flex; justify-content: space-between; align-items: center; position: sticky; top: 0; z-index: 1000; border-bottom: 1px solid #334155; }
        header h1 { margin: 0; font-size: 16px; color: #38bdf8; }
        
        /* Écran d'accueil / Authentification bloquant */
        #auth-screen { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: #0f172a; z-index: 2000; display: flex; justify-content: center; align-items: center; padding: 20px; box-sizing: border-box; }
        .auth-card { background: #1e293b; padding: 25px; border-radius: 16px; width: 100%; max-width: 400px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); border: 1px solid #334155; text-align: center; }
        .auth-card h2 { color: #38bdf8; margin-top: 0; font-size: 20px; }
        .auth-card p { font-size: 13px; color: #94a3b8; line-height: 1.4; margin-bottom: 20px; }

        /* Application principale (masquée par défaut) */
        #app-main { display: none; }

        /* Barre de menu mobile */
        .menu-bar { background: #1e293b; display: flex; overflow-x: auto; padding: 10px; gap: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.2); }
        .menu-btn { background: #334155; color: white; border: none; padding: 8px 14px; border-radius: 20px; font-size: 13px; font-weight: 600; cursor: pointer; white-space: nowrap; flex-shrink: 0; transition: background 0.2s; }
        .menu-btn.active { background: #2563eb; }

        .container { max-width: 600px; margin: 15px auto; padding: 0 15px; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }

        .card { background: #1e293b; color: #f8fafc; padding: 15px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); margin-bottom: 15px; border: 1px solid #334155; }
        h3 { font-size: 14px; margin-top: 0; color: #38bdf8; border-bottom: 2px solid #334155; padding-bottom: 6px; }
        
        .form-group { margin-bottom: 12px; display: flex; flex-direction: column; gap: 4px; }
        .form-group label { font-size: 12px; font-weight: 600; color: #cbd5e1; }
        .form-group input, .form-group textarea { padding: 10px; border-radius: 6px; border: 1px solid #475569; background: #0f172a; color: white; font-size: 14px; }
        
        .btn { background: #2563eb; color: white; border: none; padding: 12px; border-radius: 8px; font-weight: 600; cursor: pointer; width: 100%; font-size: 14px; margin-top: 5px; text-align: center; }
        .btn:hover { background: #1d4ed8; }
        .btn-gps { background: #10b981; }
        .btn-gps:hover { background: #059669; }
        .btn-import { background: #8b5cf6; margin-top: 10px; }
        .btn-import:hover { background: #7c3aed; }

        #map { height: 380px; width: 100%; border-radius: 8px; z-index: 1; margin-top: 10px; }
        #output, #distOutput { font-family: monospace; font-size: 12px; background: #0f172a; color: #34d399; padding: 12px; border-radius: 6px; margin-top: 10px; word-break: break-all; border: 1px solid #334155; }
        .admin-link { color: #94a3b8; text-decoration: none; font-size: 12px; }
        .error-msg { color: #ef4444; font-size: 12px; }
    </style>
</head>
<body>

    <!-- ÉCRAN D'ACCUEIL & ABONNEMENT OBLIGATOIRE -->
    <div id="auth-screen">
        <div class="auth-card">
            <h2>Bienvenue sur GlobalRoute AI 🚀</h2>
            <p>Plateforme logistique intelligente. Veuillez entrer votre clé d'abonnement active pour accéder à votre tableau de bord et à vos outils de routage.</p>
            <div class="form-group" style="text-align: left;">
                <label>Clé API Client :</label>
                <input type="password" id="authKeyInput" placeholder="Ex: GR-XXXXXXXX...">
                <span id="authError" class="error-msg"></span>
            </div>
            <button class="btn" onclick="verifierEtActiverApp()">Entrer dans l'Application</button>
            <div style="margin-top: 15px; font-size: 12px;">
                <span style="color: #94a3b8;">Pas encore de clé ?</span> 
                <a href="/admin" style="color: #38bdf8; text-decoration: none; font-weight: 600;">Obtenir un abonnement</a>
            </div>
        </div>
    </div>

    <!-- APPLICATION PRINCIPALE -->
    <div id="app-main">
        <header>
            <h1>GlobalRoute AI 📱</h1>
            <a href="/admin" class="admin-link">🔒 Admin</a>
        </header>

        <!-- Barre de menu mobile interactive -->
        <div class="menu-bar">
            <button class="menu-btn active" onclick="switchTab('tab-dashboard', this)">🔑 Dashboard</button>
            <button class="menu-btn" onclick="switchTab('tab-carte', this)">🗺️ Carte & GPS</button>
            <button class="menu-btn" onclick="switchTab('tab-optimisation', this)">🚀 Optimisation</button>
            <button class="menu-btn" onclick="switchTab('tab-calculateur', this)">📏 Calculateur</button>
        </div>

        <div class="container">
            
            <!-- ONGLET 1 : DASHBOARD -->
            <div id="tab-dashboard" class="tab-content active">
                <div class="card">
                    <h3>🔑 Mon Compte & Clé API</h3>
                    <div class="form-group">
                        <label>Clé API Actuelle :</label>
                        <input type="password" id="currentApiKey" readonly style="background: #0f172a; color: #34d399;">
                    </div>
                    <button class="btn" style="background: #ef4444;" onclick="deconnecterCle()">Se déconnecter / Changer de clé</button>
                </div>
                <div class="card">
                    <h3>ℹ️ Guide d'utilisation rapide</h3>
                    <p style="font-size: 13px; color: #94a3b8; line-height: 1.5;">
                        • Utilisez <b>Carte & GPS</b> pour capturer votre position de départ.<br>
                        • Allez sur <b>Optimisation</b> pour paramétrer votre bus et importer vos points clients en bas de page.<br>
                        • Utilisez le <b>Calculateur</b> pour mesurer rapidement des distances entre deux points.
                    </p>
                </div>
            </div>

            <!-- ONGLET 2 : CARTE & GPS -->
            <div id="tab-carte" class="tab-content">
                <div class="card">
                    <h3>📍 Localisation GPS en Temps Réel</h3>
                    <button class="btn btn-gps" onclick="obtenirPositionGPS()">📍 Utiliser mon GPS actuel</button>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 10px;">
                        <div class="form-group"><label>Lat Dépôt :</label><input type="text" id="depotLat" value="19.738"></div>
                        <div class="form-group"><label>Lng Dépôt :</label><input type="text" id="depotLng" value="-72.217"></div>
                    </div>
                    <h3>🗺️️ Carte Interactive</h3>
                    <div id="map"></div>
                </div>
            </div>

            <!-- ONGLET 3 : OPTIMISATION & IMPORT EN BAS -->
            <div id="tab-optimisation" class="tab-content">
                <div class="card">
                    <h3>🚀 Optimisateur de Tournée CVRP</h3>
                    <div class="form-group">
                        <label>Capacité maximale du Véhicule / Bus :</label>
                        <input type="number" id="vehiculeCapacite" value="30">
                    </div>
                    <button class="btn" onclick="lancerOptimisation()">Lancer l'Optimisation</button>
                    <div id="output">En attente de calcul...</div>

                    <hr style="border: 0; border-top: 1px solid #334155; margin: 20px 0;">

                    <!-- Section Import placée directement en bas de l'optimisation -->
                    <h3>📂 Importer des Points (Optionnel)</h3>
                    <div class="form-group">
                        <label>Coller les coordonnées (Format CSV : Nom, Lat, Lng, Demande) :</label>
                        <textarea id="csvInput" rows="3" placeholder="Client A, 19.74, -72.21, 5&#10;Client B, 19.75, -72.22, 8"></textarea>
                    </div>
                    <button class="btn btn-import" onclick="importerPointsCSV()">Charger les points importés</button>
                    <div id="importOutput" style="font-size: 12px; color: #34d399; margin-top: 6px;"></div>
                </div>
            </div>

            <!-- ONGLET 4 : CALCULATEUR -->
            <div id="tab-calculateur" class="tab-content">
                <div class="card">
                    <h3>📏 Calculateur de Distance & Temps</h3>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
                        <div class="form-group"><label>Lat A :</label><input type="text" id="latA" value="19.738"></div>
                        <div class="form-group"><label>Lng A :</label><input type="text" id="lngA" value="-72.217"></div>
                    </div>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
                        <div class="form-group"><label>Lat B :</label><input type="text" id="latB" value="19.750"></div>
                        <div class="form-group"><label>Lng B :</label><input type="text" id="lngB" value="-72.200"></div>
                    </div>
                    <button class="btn" style="background: #0284c7;" onclick="calculerDistanceDirecte()">Calculer</button>
                    <div id="distOutput">Résultat du calcul...</div>
                </div>
            </div>

        </div>
    </div>

    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
        // Vérification de la clé enregistrée au chargement
        window.onload = function() {
            const savedKey = localStorage.getItem('globalroute_apikey');
            if(savedKey) {
                document.getElementById('authKeyInput').value = savedKey;
                verifierEtActiverApp(true);
            }
        };

        async function verifierEtActiverApp(auto = false) {
            const key = document.getElementById('authKeyInput').value.trim();
            if(!key) {
                document.getElementById('authError').innerText = "Veuillez entrer une clé valide.";
                return;
            }
            
            try {
                const rep = await fetch('/api/optimiser', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-API-KEY': key },
                    body: JSON.stringify({
                        depot: { id: 0, lat: 19.738, lng: -72.217, name: "Test", demand: 0 },
                        vehicule_capacite: 30,
                        points: []
                    })
                });

                if(rep.status === 401 || rep.status === 403) {
                    const errData = await rep.json();
                    if(!auto) alert("Accès refusé : " + errData.detail);
                    document.getElementById('authError').innerText = errData.detail;
                    localStorage.removeItem('globalroute_apikey');
                    return;
                }

                // Succès : déverrouillage de l'application
                localStorage.setItem('globalroute_apikey', key);
                document.getElementById('currentApiKey').value = key;
                document.getElementById('auth-screen').style.display = 'none';
                document.getElementById('app-main').style.display = 'block';
                
                // Rafraîchir la taille de la carte si elle s'affiche
                setTimeout(() => { if(window.mapInstance) window.mapInstance.invalidateSize(); }, 200);

            } catch(e) {
                if(!auto) alert("Erreur de connexion au serveur.");
            }
        }

        function deconnecterCle() {
            localStorage.removeItem('globalroute_apikey');
            location.reload();
        }

        // Navigation fluide dans le menu
        function switchTab(tabId, btnElement) {
            document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
            document.querySelectorAll('.menu-btn').forEach(el => el.classList.remove('active'));
            document.getElementById(tabId).classList.add('active');
            btnElement.classList.add('active');
            if(tabId === 'tab-carte' && window.mapInstance) {
                window.mapInstance.invalidateSize();
            }
        }

        // Initialisation Carte Leaflet
        var map = L.map('map').setView([19.738, -72.217], 13);
        window.mapInstance = map;

        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19,
            attribution: '&copy; OpenStreetMap'
        }).addTo(map);

        var layerGroup = L.layerGroup().addTo(map);
        var gpsMarker = null;
        var pointsImportesDynamiques = [];

        function obtenirPositionGPS() {
            if (navigator.geolocation) {
                navigator.geolocation.getCurrentPosition(
                    (position) => {
                        const lat = position.coords.latitude;
                        const lng = position.coords.longitude;
                        document.getElementById('depotLat').value = lat;
                        document.getElementById('depotLng').value = lng;
                        map.setView([lat, lng], 15);
                        
                        if (gpsMarker) { layerGroup.removeLayer(gpsMarker); }
                        gpsMarker = L.marker([lat, lng], {
                            icon: L.icon({
                                iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-red.png',
                                shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
                                iconSize: [25, 41], iconAnchor: [12, 41]
                            })
                        }).addTo(layerGroup).bindPopup("<b>📍 Votre Position GPS Actuelle</b>").openPopup();

                        alert("GPS détecté et positionné avec succès !");
                    },
                    (error) => { alert("Erreur GPS : " + error.message); },
                    { enableHighAccuracy: true }
                );
            } else {
                alert("La géolocalisation n'est pas supportée par votre appareil.");
            }
        }

        async function calculerDistanceDirecte() {
            const lat1 = parseFloat(document.getElementById('latA').value);
            const lng1 = parseFloat(document.getElementById('lngA').value);
            const lat2 = parseFloat(document.getElementById('latB').value);
            const lng2 = parseFloat(document.getElementById('lngB').value);
            const key = localStorage.getItem('globalroute_apikey');

            try {
                const rep = await fetch('/api/calculer-distance', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-API-KEY': key },
                    body: JSON.stringify({ lat1, lng1, lat2, lng2 })
                });
                const data = await rep.json();
                if(rep.ok) {
                    document.getElementById('distOutput').innerText = `✅ Distance : ${data.distance_km} km\n⏱️ Temps estimé : ${data.temps_estime_min} min`;
                } else {
                    document.getElementById('distOutput').innerText = "Erreur : " + data.detail;
                }
            } catch(e) {
                document.getElementById('distOutput').innerText = "Erreur de connexion.";
            }
        }

        function importerPointsCSV() {
            const texte = document.getElementById('csvInput').value;
            const lignes = texte.split('\\n');
            pointsImportesDynamiques = [];
            let idCounter = 1;
            
            lignes.forEach(ligne => {
                if(ligne.trim() !== '') {
                    const parts = ligne.split(',');
                    if(parts.length >= 3) {
                        pointsImportesDynamiques.push({
                            id: idCounter++,
                            name: parts[0].trim(),
                            lat: parseFloat(parts[1]),
                            lng: parseFloat(parts[2]),
                            demand: parts[3] ? parseInt(parts[3]) : 5
                        });
                    }
                }
            });
            document.getElementById('importOutput').innerText = `✅ ${pointsImportesDynamiques.length} points importés avec succès pour la prochaine optimisation !`;
        }

        async function lancerOptimisation() {
            const key = localStorage.getItem('globalroute_apikey');
            const capacite = parseInt(document.getElementById('vehiculeCapacite').value) || 30;
            const depotLat = parseFloat(document.getElementById('depotLat').value);
            const depotLng = parseFloat(document.getElementById('depotLng').value);
            
            let pointsFinal = pointsImportesDynamiques;
            if(pointsFinal.length === 0) {
                pointsFinal = [
                    { id: 1, lat: depotLat + 0.01, lng: depotLng + 0.01, name: "Client Test 1", demand: 5 },
                    { id: 2, lat: depotLat - 0.01, lng: depotLng + 0.02, name: "Client Test 2", demand: 10 }
                ];
            }

            const payload = {
                depot: { id: 0, lat: depotLat, lng: depotLng, name: "Dépôt (GPS)", demand: 0 },
                vehicule_capacite: capacite,
                points: pointsFinal
            };

            try {
                document.getElementById('output').innerText = "Calcul de la tournée en cours...";
                const rep = await fetch('/api/optimiser', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-API-KEY': key },
                    body: JSON.stringify(payload)
                });
                const data = await rep.json();
                
                if(rep.ok) {
                    document.getElementById('output').innerText = `✅ Dist. Totale : ${data.distance_totale_km} km\n📦 Charge : ${data.charge_totale}/${data.capacite_max}\n📍 Étapes : ${data.nombre_etapes}`;
                    
                    layerGroup.clearLayers();
                    let latLngs = [];
                    data.tournee.forEach((pt, index) => {
                        let coord = [pt.lat, pt.lng];
                        latLngs.push(coord);
                        L.marker(coord).addTo(layerGroup)
                          .bindPopup(`<b>${index === 0 ? 'DÉPÔT' : 'Étape ' + index}</b><br>${pt.name}`);
                    });

                    if(latLngs.length > 0) {
                        let polyline = L.polyline(latLngs, {color: '#38bdf8', weight: 4}).addTo(layerGroup);
                        map.fitBounds(polyline.getBounds(), {padding: [30, 30]});
                    }
                    alert("Optimisation terminée ! Consultez l'onglet Carte pour voir le tracé.");
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

@app.post("/api/calculer-distance")
async def calculer_distance(data: DistanceRequest, auth = Depends(verifier_cle_api)):
    dist = haversine_distance(data.lat1, data.lng1, data.lat2, data.lng2)
    temps_min = round((dist / 40.0) * 60, 1)
    return {
        "statut": "succes",
        "distance_km": round(dist, 2),
        "temps_estime_min": temps_min
    }

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
        body {{ font-family: 'Inter', sans-serif; background: #0f172a; color: #f8fafc; padding: 15px; margin: 0; }}
        .container {{ max-width: 600px; margin: 20px auto; background: #1e293b; padding: 20px; border-radius: 12px; border: 1px solid #334155; }}
        h1 {{ color: #38bdf8; font-size: 18px; margin-top: 0; }}
        .form-group {{ margin-bottom: 12px; display: flex; flex-direction: column; gap: 4px; }}
        .form-group label {{ font-size: 12px; color: #cbd5e1; }}
        .form-group input {{ padding: 10px; border-radius: 6px; border: 1px solid #475569; background: #0f172a; color: white; font-size: 14px; }}
        .btn {{ background: #10b981; color: white; border: none; padding: 10px; border-radius: 6px; font-weight: 600; cursor: pointer; width: 100%; font-size: 14px; }}
        .back-link {{ display: inline-block; margin-bottom: 12px; color: #38bdf8; text-decoration: none; font-size: 13px; }}
        #adminOutput {{ font-family: monospace; font-size: 11px; background: #0f172a; padding: 12px; border-radius: 6px; margin-top: 15px; color: #34d399; word-break: break-all; max-height: 200px; overflow-y: auto; border: 1px solid #334155; }}
    </style>
</head>
<body>
    <div class="container">
        <a href="/" class="back-link">← Retourner à l'application</a>
        <h1>🔐 Console Admin ({ADMIN_USERNAME})</h1>
        <div class="form-group" style="margin-top: 10px;">
            <label>Clé API Admin :</label>
            <input type="password" id="adminKeyInput" placeholder="Entrez la clé admin...">
        </div>
        <hr style="border: 0; border-top: 1px solid #334155; margin: 15px 0;">
        <h3>Générer une clé client</h3>
        <div class="form-group"><label>Entreprise :</label><input type="text" id="nomEntite" placeholder="Nom client"></div>
        <div class="form-group"><label>Email :</label><input type="email" id="emailClient" placeholder="client@mail.com"></div>
        <button class="btn" onclick="genererCle()">Générer la Clé API</button>
        <button class="btn" onclick="listerCles()" style="background: #2563eb; margin-top: 10px;">Lister les abonnés</button>
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
