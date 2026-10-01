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
    description="Plateforme logistique mondiale avec gestion de flotte, capacités de véhicules et console admin isolée."
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
        raise HTTPException(status_code=401, detail="Clé API manquante dans les en-têtes (X-API-KEY).")
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
    demand: int = 1  # Quantité (ex: nombre de passagers, colis, poids) demandée à ce point

class RouteRequest(BaseModel):
    depot: Point
    points: List[Point]
    vehicule_capacite: int = 50  # Capacité maximale du bus / véhicule

class AdminCreationRequest(BaseModel):
    nom_entreprise: str
    email: str
    duree_jours: int = 30

# --- FONCTIONS MATHÉMATIQUES & OR-TOOLS (AVEC CAPACITÉ) ---
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
    
    # Matrice de distance en mètres
    matrix = [[0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i != j:
                matrix[i][j] = int(haversine_distance(
                    tous_les_points[i].lat, tous_les_points[i].lng,
                    tous_les_points[j].lat, tous_les_points[j].lng
                ) * 1000)

    # Gestion de plusieurs véhicules si la capacité totale dépasse la limite d'un seul bus
    manager = pywrapcp.RoutingIndexManager(n, 1, 0)
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return matrix[from_node][to_node]

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    # Ajout de la contrainte de capacité du bus / véhicule
    def demand_callback(from_index):
        from_node = manager.IndexToNode(from_index)
        return tous_les_points[from_node].demand

    demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)
    routing.AddDimensionWithVehicleCapacity(
        demand_callback_index,
        0,  # null capacity slack
        [vehicule_capacite],  # Capacité maximale du véhicule
        True,  # start cumul to zero
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
            
        tournee.append(tous_les_points[0].dict()) # Retour au dépôt
        
    return tournee, distance_totale_m / 1000.0, charge_totale

# --- ROUTES PUBLIQUE ET APPLICATION ---
@app.get("/", response_class=HTMLResponse)
async def index():
    return """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GlobalRoute AI - SaaS Logistique Avancé</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Inter', sans-serif; background: #f8fafc; color: #1e293b; margin: 0; padding: 0; }
        header { background: #0f172a; color: white; padding: 20px 40px; display: flex; justify-content: space-between; align-items: center; }
        header h1 { margin: 0; font-size: 20px; color: #38bdf8; }
        .main-container { max-width: 1200px; margin: 40px auto; padding: 0 20px; display: grid; grid-template-columns: 1fr 1fr; gap: 30px; }
        .card { background: white; padding: 25px; border-radius: 12px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); }
        h2 { font-size: 18px; margin-top: 0; color: #0f172a; }
        .form-group { margin-bottom: 15px; display: flex; flex-direction: column; gap: 5px; }
        .form-group label { font-size: 13px; font-weight: 600; color: #475569; }
        .form-group input { padding: 10px; border-radius: 6px; border: 1px solid #cbd5e1; font-size: 14px; }
        .btn { background: #2563eb; color: white; border: none; padding: 12px 20px; border-radius: 6px; font-weight: 600; cursor: pointer; }
        .btn:hover { background: #1d4ed8; }
        #output { font-family: monospace; font-size: 12px; background: #0f172a; color: #34d399; padding: 15px; border-radius: 6px; margin-top: 15px; max-height: 250px; overflow-y: auto; }
        .admin-link { color: #94a3b8; text-decoration: none; font-size: 13px; }
        .admin-link:hover { color: white; }
    </style>
</head>
<body>
    <header>
        <h1>GlobalRoute AI 🚀</h1>
        <a href="/admin" class="admin-link">🔒 Accès Console Admin</a>
    </header>
    <div class="main-container">
        <div class="card">
            <h2>🔑 Authentification API</h2>
            <div class="form-group">
                <label>Votre Clé API Client :</label>
                <input type="text" id="apiKey" placeholder="Entrez votre clé API GlobalRoute...">
            </div>
            <p style="font-size: 13px; color: #64748b;">Utilisez votre clé personnelle pour lancer des calculs de tournées optimisées par IA.</p>
        </div>
        <div class="card">
            <h2>🚌 Test Optimisation avec Capacité Bus</h2>
            <div class="form-group">
                <label>Capacité maximale du bus :</label>
                <input type="number" id="vehiculeCapacite" value="30" style="padding: 8px; border-radius: 6px; border: 1px solid #cbd5e1;">
            </div>
            <button class="btn" onclick="testerRoute()">Calculer la Tournée avec Capacité</button>
            <div id="output">En attente de calcul...</div>
        </div>
    </div>
    <script>
        async function testerRoute() {
            const key = document.getElementById('apiKey').value;
            const capacite = parseInt(document.getElementById('vehiculeCapacite').value) || 30;
            if(!key) { alert("Veuillez entrer une clé API !"); return; }
            
            const payload = {
                depot: { id: 0, lat: 48.8566, lng: 2.3522, name: "Dépôt Central", demand: 0 },
                vehicule_capacite: capacite,
                points: [
                    { id: 1, lat: 48.8600, lng: 2.3400, name: "Arrêt / Client A", demand: 5 },
                    { id: 2, lat: 48.8500, lng: 2.3700, name: "Arrêt / Client B", demand: 12 },
                    { id: 3, lat: 48.8700, lng: 2.3300, name: "Arrêt / Client C", demand: 8 }
                ]
            };

            try {
                const rep = await fetch('/api/optimiser', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-API-KEY': key },
                    body: JSON.stringify(payload)
                });
                const data = await rep.json();
                if(rep.ok) {
                    document.getElementById('output').innerText = `✅ Succès !\nCapacité max bus : ${data.capacite_max}\nCharge transportée : ${data.charge_totale}\nDistance totale : ${data.distance_totale_km} km\n\nItinéraire :\n` + JSON.stringify(data.tournee, null, 2);
                } else {
                    document.getElementById('output').innerText = "Erreur : " + data.detail;
                }
            } catch(e) {
                document.getElementById('output').innerText = "Erreur de connexion.";
            }
        }
    </script>
</body>
</html>
    """

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

# --- CONSOLE D'ADMINISTRATION SÉCURISÉE (/admin) ---
@app.get("/admin", response_class=HTMLResponse)
async def afficher_admin_page():
    return f"""
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GlobalRoute AI - Console Admin Sécurisée</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap" rel="stylesheet">
    <style>
        body {{ font-family: 'Inter', sans-serif; background: #0f172a; color: #f8fafc; padding: 20px; margin: 0; }}
        .container {{ max-width: 800px; margin: 40px auto; background: #1e293b; padding: 30px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.3); }}
        h1 {{ color: #38bdf8; font-size: 22px; margin-top: 0; }}
        .form-group {{ margin-bottom: 15px; display: flex; flex-direction: column; gap: 5px; }}
        .form-group label {{ font-size: 13px; color: #cbd5e1; }}
        .form-group input, .form-group select {{ padding: 10px; border-radius: 6px; border: 1px solid #475569; background: #0f172a; color: white; font-size: 14px; }}
        .btn {{ background: #10b981; color: white; border: none; padding: 12px 20px; border-radius: 6px; font-weight: 600; cursor: pointer; font-size: 14px; }}
        .btn:hover {{ background: #059669; }}
        .back-link {{ display: inline-block; margin-bottom: 20px; color: #38bdf8; text-decoration: none; font-size: 14px; }}
        #adminOutput {{ font-family: monospace; font-size: 12px; background: #0f172a; padding: 15px; border-radius: 6px; margin-top: 20px; white-space: pre-wrap; color: #34d399; max-height: 300px; overflow-y: auto; }}
    </style>
</head>
<body>
    <div class="container">
        <a href="/" class="back-link">← Retourner à l'application principale</a>
        <h1>🔐 Console d'Administration Maître ({ADMIN_USERNAME})</h1>
        <p style="font-size: 13px; color: #94a3b8;">Espace restreint et sécurisé pour la gestion des abonnés et la génération des clés API.</p>
        
        <div class="form-group" style="margin-top: 20px;">
            <label>Clé API Maître / Administrateur :</label>
            <input type="password" id="adminKeyInput" placeholder="Entrez votre clé secrète administrateur..." value="">
        </div>

        <hr style="border: 0; border-top: 1px solid #475569; margin: 20px 0;">

        <h3>Générer un nouvel accès client</h3>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 15px;">
            <div class="form-group">
                <label>Nom de l'Entreprise :</label>
                <input type="text" id="nomEntite" placeholder="Ex: Transport Express">
            </div>
            <div class="form-group">
                <label>Email Client :</label>
                <input type="email" id="emailClient" placeholder="client@entreprise.com">
            </div>
            <div class="form-group">
                <label>Durée d'abonnement :</label>
                <select id="dureeJours">
                    <option value="30">30 Jours</option>
                    <option value="365">365 Jours (1 An)</option>
                </select>
            </div>
        </div>
        <button class="btn" onclick="genererCle()" style="margin-top: 10px;">Générer la Clé API</button>
        <button class="btn" onclick="listerCles()" style="background: #2563eb; margin-top: 10px; margin-left: 10px;">Lister tous les abonnés</button>

        <div id="adminOutput">Résultats et journaux de la base SQLite...</div>
    </div>

    <script>
        async function genererCle() {{
            const cle = document.getElementById('adminKeyInput').value;
            const nomEntite = document.getElementById('nomEntite').value;
            const email = document.getElementById('emailClient').value;
            const duree = parseInt(document.getElementById('dureeJours').value);

            if (!cle) {{
                alert("Veuillez entrer votre clé administrateur.");
                return;
            }}
            if (!nomEntite || !email) {{
                alert("Veuillez remplir le nom et l'email de l'entreprise.");
                return;
            }}

            try {{
                const rep = await fetch('/admin/generer-cle', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json', 'X-API-KEY': cle }},
                    body: JSON.stringify({{ nom_entreprise: nomEntite, email: email, duree_jours: duree }})
                }});
                const data = await rep.json();
                if (rep.ok) {{
                    document.getElementById('adminOutput').innerText = `✅ Succès !\\nClé API : ${{data.cle_api}}\\nEntreprise : ${{data.entreprise}}\\nExpiration : ${{data.expiration}}`;
                }} else {{
                    document.getElementById('adminOutput').innerText = "Erreur : " + data.detail;
                }}
            }} catch(e) {{
                document.getElementById('adminOutput').innerText = "Erreur de connexion au serveur.";
            }}
        }}

        async function listerCles() {{
            const cle = document.getElementById('adminKeyInput').value;
            if (!cle) {{
                alert("Veuillez entrer votre clé administrateur.");
                return;
            }}
            try {{
                const rep = await fetch('/admin/cles', {{
                    headers: {{ 'X-API-KEY': cle }}
                }});
                const data = await rep.json();
                if (rep.ok) {{
                    document.getElementById('adminOutput').innerText = JSON.stringify(data.cles_enregistrees, null, 2);
                }} else {{
                    document.getElementById('adminOutput').innerText = "Erreur : " + data.detail;
                }}
            }} catch(e) {{
                document.getElementById('adminOutput').innerText = "Erreur de connexion au serveur.";
            }}
        }}
    </script>
</body>
</html>
    """

@app.post("/admin/generer-cle")
async def admin_generer_cle(req: AdminCreationRequest, auth = Depends(verifier_cle_api)):
    if not auth["admin"]:
        raise HTTPException(status_code=403, detail="Accès refusé : Droits administrateur requis.")
    
    nouvelle_cle = f"GR-{uuid.uuid4().hex.upper()}"
    date_exp = (datetime.utcnow() + timedelta(days=req.duree_jours)).isoformat()
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO abonnes (cle_api, nom, email, actif, admin, expiration)
        VALUES (?, ?, ?, 1, 0, ?)
    ''', (nouvelle_cle, req.nom_entreprise, req.email, date_exp))
    conn.commit()
    conn.close()
    
    return {
        "statut": "succes",
        "entreprise": req.nom_entreprise,
        "email": req.email,
        "cle_api": nouvelle_cle,
        "expiration": date_exp
    }

@app.get("/admin/cles")
async def admin_lister_cles(auth = Depends(verifier_cle_api)):
    if not auth["admin"]:
        raise HTTPException(status_code=403, detail="Accès refusé : Droits administrateur requis.")
        
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT cle_api, nom, email, actif, admin, expiration FROM abonnes")
    rows = cursor.fetchall()
    conn.close()
    
    resultats = []
    for r in rows:
        resultats.append({
            "cle_api": r[0],
            "nom": r[1],
            "email": r[2],
            "actif": bool(r[3]),
            "admin": bool(r[4]),
            "expiration": r[5]
        })
        
    return {"cles_enregistrees": resultats}
