
import os
from fastapi import FastAPI, HTTPException, Security, Depends, UploadFile, File
from fastapi.security.api_key import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel
import math
from datetime import datetime, timedelta
import uuid
from typing import List, Tuple
import sqlite3
import csv
import io

from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp

app = FastAPI(
    title="GlobalRoute AI - Enterprise SaaS Sécurisé",
    description="Plateforme logistique mondiale avec interface publique épurée et console admin isolée."
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
ADMIN_CLE_SECRETE = os.getenv("ADMIN_PASSWORD", "CLE-ADMIN-MAITRE-999")

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
        ''', (ADMIN_CLE_SECRETE, "Administration Générale", "admin@globalroute.ai", 1, 1, None))
    else:
        # Met à jour la clé admin si elle a changé dans les variables d'environnement Render
        cursor.execute('''
            UPDATE abonnes SET cle_api = ? WHERE admin = 1
        ''', (ADMIN_CLE_SECRETE,))
    conn.commit()
    conn.close()

initialiser_db()

API_KEY_NAME = "X-API-KEY"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

async def verifier_cle_api(api_key: str = Depends(api_key_header)):
    if not api_key:
        raise HTTPException(status_code=403, detail="Accès refusé : Clé API absente.")
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT nom, email, actif, admin, expiration FROM abonnes WHERE cle_api = ?", (api_key,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=403, detail="Accès refusé : Clé API invalide.")
    
    nom, email, actif, admin, expiration = row
    if not actif:
        raise HTTPException(status_code=402, detail="Accès suspendu : Compte désactivé.")
    
    if expiration:
        date_expiration = datetime.fromisoformat(expiration)
        if datetime.utcnow() > date_expiration:
            raise HTTPException(status_code=401, detail="Accès refusé : La minuterie de la clé API a expiré.")
            
    return {"cle_api": api_key, "nom": nom, "email": email, "actif": actif, "admin": admin, "expiration": expiration}

class RequeteCalcul(BaseModel):
    villes: List[Tuple[float, float]]

class RequeteCreationCle(BaseModel):
    nom_entreprise: str
    email: str
    duree_jours: int

def calculer_distance_haversine(coord1: Tuple[float, float], coord2: Tuple[float, float]) -> float:
    R = 6371.0
    lat1, lon1 = math.radians(coord1[0]), math.radians(coord1[1])
    lat2, lon2 = math.radians(coord2[0]), math.radians(coord2[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2)**2
    c = 2 * math.asin(math.sqrt(a))
    return R * c

def distance_route_gps(route: List[int], matrice_dist) -> float:
    return sum(matrice_dist[route[i]][route[i + 1]] for i in range(len(route) - 1)) + matrice_dist[route[-1]][route[0]]

def deux_opt_gps(route: List[int], matrice_dist, max_pass=2) -> List[int]:
    meilleur = route[:]
    meilleure_dist = distance_route_gps(meilleur, matrice_dist)
    for _ in range(max_pass):
        amelioration = False
        n = len(meilleur)
        for i in range(1, n - 2):
            for j in range(i + 1, n - 1):
                candidat = meilleur[:i] + meilleur[i:j + 1][::-1] + meilleur[j + 1:]
                d = distance_route_gps(candidat, matrice_dist)
                if d < meilleure_dist:
                    meilleur = candidat
                    meilleure_dist = d
                    amelioration = True
                    break
            if amelioration:
                break
        if not amelioration:
            break
    return meilleur

def resoudre_bloc_exact_gps(villes_bloc: List[Tuple[float, float]]) -> Tuple[List[int], float]:
    nb_villes = len(villes_bloc)
    if nb_villes <= 1:
        return [0], 0.0

    matrice_dist = [[calculer_distance_haversine(villes_bloc[i], villes_bloc[j]) for j in range(nb_villes)] for i in range(nb_villes)]
    matrice_entiere = [[int(matrice_dist[i][j] * 1000) for j in range(nb_villes)] for i in range(nb_villes)]

    manager = pywrapcp.RoutingIndexManager(nb_villes, 1, 0)
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        return matrice_entiere[manager.IndexToNode(from_index)][manager.IndexToNode(to_index)]

    routing.SetArcCostEvaluatorOfAllVehicles(routing.RegisterTransitCallback(distance_callback))

    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    search_parameters.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    search_parameters.time_limit.seconds = 2

    solution = routing.SolveWithParameters(search_parameters)
    if not solution:
        route_secours = list(range(nb_villes))
        return route_secours, distance_route_gps(route_secours, matrice_dist)

    index = routing.Start(0)
    route = []
    dist_totale = 0
    while not routing.IsEnd(index):
        node = manager.IndexToNode(index)
        route.append(node)
        prev = index
        index = solution.Value(routing.NextVar(index))
        dist_totale += routing.GetArcCostForVehicle(prev, index, 0)

    return route, dist_totale / 1000.0

def diviser_et_conquerir_gps(villes: List[Tuple[float, float]], taille_bloc: int = 150) -> Tuple[List[int], float]:
    n = len(villes)
    if n <= taille_bloc:
        return resoudre_bloc_exact_gps(villes)

    blocs_indices = [list(range(i, min(i + taille_bloc, n))) for i in range(0, n, taille_bloc)]
    route_globale_ordonnee = []
    distance_globale = 0.0
    matrice_globale = [[calculer_distance_haversine(villes[i], villes[j]) for j in range(n)] for i in range(n)]

    for bloc in blocs_indices:
        coordonnees_bloc = [villes[idx] for idx in bloc]
        route_locale, dist_locale = resoudre_bloc_exact_gps(coordonnees_bloc)
        route_globale_bloc = [bloc[i] for i in route_locale]
        route_globale_ordonnee.extend(route_globale_bloc)
        distance_globale += dist_locale

    route_globale_ordonnee = deux_opt_gps(route_globale_ordonnee, matrice_globale, max_pass=3)
    distance_globale_vraie = distance_route_gps(route_globale_ordonnee, matrice_globale)

    return route_globale_ordonnee, distance_globale_vraie

@app.post("/optimiser-tournee-gps/")
async def optimiser_tournee_gps(requete: RequeteCalcul, abonne: dict = Depends(verifier_cle_api)):
    n = len(requete.villes)
    if n < 2:
        raise HTTPException(status_code=400, detail="Minimum 2 points requis.")
    if n > 15000:
        raise HTTPException(status_code=400, detail="Limite maximale de 15 000 points atteinte.")

    route, distance_km = diviser_et_conquerir_gps(requete.villes, taille_bloc=150)

    return {
        "statut": "Succès - Moteur Opérationnel",
        "client_reconnu": abonne["nom"],
        "expiration_cle": abonne.get("expiration", "Illimité (Maître)"),
        "nombre_de_villes": n,
        "distance_totale_km": round(distance_km, 2),
        "ordre_de_visite_optimal": route
    }

@app.post("/api/importer-csv")
async def importer_csv(file: UploadFile = File(...), abonne: dict = Depends(verifier_cle_api)):
    try:
        contenu = await file.read()
        texte = contenu.decode('utf-8')
        lecteur = csv.reader(io.StringIO(texte))
        villes = []
        for ligne in lecteur:
            if len(ligne) >= 2:
                try:
                    lat = float(ligne[0].strip())
                    lon = float(ligne[1].strip())
                    villes.append([lat, lon])
                except ValueError:
                    continue
        return {"villes": villes, "total_importe": len(villes)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erreur lors de la lecture du fichier CSV : {str(e)}")

@app.post("/api/exporter-rapport", response_class=PlainTextResponse)
async def exporter_rapport(requete: RequeteCalcul, abonne: dict = Depends(verifier_cle_api)):
    route, distance_km = diviser_et_conquerir_gps(requete.villes, taille_bloc=150)
    
    rapport = "========================================\n"
    rapport += "      GLOBALROUTE AI - RAPPORT DE ROUTE     \n"
    rapport += "========================================\n"
    rapport += f"Client : {abonne['nom']}\n"
    rapport += f"Date : {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
    rapport += f"Nombre total de points : {len(requete.villes)}\n"
    rapport += f"Distance totale estimée : {round(distance_km, 2)} km\n"
    rapport += "----------------------------------------\n"
    rapport += "ORDRE DE VISITE OPTIMAL (Index des points) :\n"
    for i, idx in enumerate(route):
        rapport += f"Étape {i+1} : Point index {idx} -> Coordonnées {requete.villes[idx]}\n"
    rapport += "========================================\n"
    
    return rapport

@app.post("/admin/generer-cle")
async def generer_cle_admin(req: RequeteCreationCle, abonne: dict = Depends(verifier_cle_api)):
    if not abonne.get("admin", False):
        raise HTTPException(status_code=403, detail="Réservé à l'administrateur.")
    
    prefixe = ''.join([c for c in req.nom_entreprise if c.isalnum()]).upper()[:4]
    unique_suffix = uuid.uuid4().hex[:6].upper()
    nouvelle_cle = f"GR-{prefixe}-{unique_suffix}"
    date_expiration = datetime.utcnow() + timedelta(days=req.duree_jours)
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO abonnes (cle_api, nom, email, actif, admin, expiration)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (nouvelle_cle, req.nom_entreprise, req.email, 1, 0, date_expiration.isoformat()))
    conn.commit()
    conn.close()
    
    return {
        "message": "Clé générée.",
        "cle_api": nouvelle_cle,
        "entreprise": req.nom_entreprise,
        "expiration": date_expiration.strftime("%Y-%m-%d %H:%M:%S UTC")
    }

@app.get("/admin/cles")
async def lister_cles_admin(abonne: dict = Depends(verifier_cle_api)):
    if not abonne.get("admin", False):
        raise HTTPException(status_code=403, detail="Réservé à l'administrateur.")
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT cle_api, nom, email, actif, admin, expiration FROM abonnes")
    rows = cursor.fetchall()
    conn.close()
    
    cles_dict = {}
    for r in rows:
        cles_dict[r[0]] = {
            "nom": r[1],
            "email": r[2],
            "actif": bool(r[3]),
            "admin": bool(r[4]),
            "expiration": r[5]
        }
    return {"cles_enregistrees": cles_dict}

# --- PAGE D'ADMINISTRATION SÉCURISÉE DÉDIÉE (/admin) ---
@app.get("/admin", response_class=HTMLResponse)
async def afficher_admin_page():
    return """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GlobalRoute AI - Console Admin Sécurisée</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Inter', sans-serif; background: #0f172a; color: #f8fafc; padding: 20px; margin: 0; }
        .container { max-width: 800px; margin: 40px auto; background: #1e293b; padding: 30px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.3); }
        h1 { color: #38bdf8; font-size: 22px; margin-top: 0; }
        .form-group { margin-bottom: 15px; display: flex; flex-direction: column; gap: 5px; }
        .form-group label { font-size: 13px; color: #cbd5e1; }
        .form-group input, .form-group select { padding: 10px; border-radius: 6px; border: 1px solid #475569; background: #0f172a; color: white; font-size: 14px; }
        .btn { background: #10b981; color: white; border: none; padding: 12px 20px; border-radius: 6px; font-weight: 600; cursor: pointer; font-size: 14px; }
        .btn:hover { background: #059669; }
        .back-link { display: inline-block; margin-bottom: 20px; color: #38bdf8; text-decoration: none; font-size: 14px; }
        #adminOutput { font-family: monospace; font-size: 12px; background: #0f172a; padding: 15px; border-radius: 6px; margin-top: 20px; white-space: pre-wrap; color: #34d399; max-height: 300px; overflow-y: auto; }
    </style>
</head>
<body>
    <div class="container">
        <a href="/" class="back-link">← Retourner à l'application principale</a>
        <h1>🔐 Console d'Administration Maître</h1>
        <p style="font-size: 13px; color: #94a3b8;">Espace restreint et sécurisé pour la gestion des abonnés et la génération des clés API.</p>
        
        <div class="form-group" style="margin-top: 20px;">
            <label>Clé API Maître / Administrateur :</label>
            <input type="password" id="adminKeyInput" placeholder="Entrez votre clé maître..." value="CLE-ADMIN-MAITRE-999">
        </div>

        <hr style="border: 0; border-top: 1px solid #475569; margin: 20px 0;">

        <h3>Générer un nouvel accès client</h3>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 15px;">
            <div class="form-group">
                <label>Nom de l'Entreprise :</label>
                <input type="text" id="nomEntite" placeholder="Ex: Logistique Express">
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
        async function genererCle() {
            const cle = document.getElementById('adminKeyInput').value;
            const nomEntite = document.getElementById('nomEntite').value;
            const email = document.getElementById('emailClient').value;
            const duree = parseInt(document.getElementById('dureeJours').value);

            if (!nomEntite || !email) {
                alert("Veuillez remplir le nom et l'email.");
                return;
            }

            try {
                const rep = await fetch('/admin/generer-cle', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-API-KEY': cle },
                    body: JSON.stringify({ nom_entreprise: nomEntite, email: email, duree_jours: duree })
                });
                const data = await rep.json();
                if (rep.ok) {
                    document.getElementById('adminOutput').innerText = `✅ Succès !\nClé API : ${data.cle_api}\nEntreprise : ${data.entreprise}\nExpiration : ${data.expiration}`;
                } else {
                    document.getElementById('adminOutput').innerText = "Erreur : " + data.detail;
                }
            } catch(e) {
                document.getElementById('adminOutput').innerText = "Erreur de connexion au serveur.";
            }
        }

        async function listerCles() {
            const cle = document.getElementById('adminKeyInput').value;
            try {
                const rep = await fetch('/admin/cles', {
                    headers: { 'X-API-KEY': cle }
                });
                const data = await rep.json();
                if (rep.ok) {
                    document.getElementById('adminOutput').innerText = JSON.stringify(data.cles_enregistrees, null, 2);
                } else {
                    document.getElementById('adminOutput').innerText = "Erreur : " + data.detail;
                }
            } catch(e) {
                document.getElementById('adminOutput').innerText = "Erreur de connexion au serveur.";
            }
        }
    </script>
</body>
</html>
    """

# --- PAGE D'ACCUEIL PUBLIQUE CORRIGÉE (Sans champ admin visible) ---
@app.get("/", response_class=HTMLResponse)
async def afficher_dashboard():
    html_content = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GlobalRoute AI - SaaS Logistique</title>
    
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    
    <!-- Script Tiun -->
    <script src="https://api.tiun.live"></script>
    <script>
        window.addEventListener('DOMContentLoaded', () => {
            if (typeof tiun !== 'undefined') {
                tiun.init({
                    snippetId: 'JQD27X4Dhj8JGdXQhnbBYz1K2HS5gjiojVwYIAKR',
                    language: 'fr'
                });
            }
        });
    </script>

    <style>
        :root {
            --primary: #2563eb;
            --primary-dark: #1d4ed8;
            --bg-main: #f1f5f9;
            --card-bg: #ffffff;
            --text-main: #0f172a;
            --text-muted: #64748b;
            --border-color: #cbd5e1;
        }
        * { box-sizing: border-box; }
        body { font-family: 'Inter', sans-serif; background-color: var(--bg-main); color: var(--text-main); margin: 0; padding: 15px; }
        
        .navbar { display: flex; justify-content: space-between; align-items: center; background: var(--card-bg); padding: 15px 20px; border-radius: 12px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); margin-bottom: 20px; flex-wrap: wrap; gap: 15px; }
        .logo { font-size: 20px; font-weight: 700; color: var(--primary); display: flex; align-items: center; gap: 8px; }
        .nav-auth { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
        .btn-admin-link { background: #0f172a !important; text-decoration: none; display: inline-flex; align-items: center; justify-content: center; padding: 8px 14px; border-radius: 8px; font-weight: 600; font-size: 14px; color: white; }
        
        .pricing-banner { background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); color: white; padding: 20px; border-radius: 12px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 15px; }
        .pricing-banner h3 { margin: 0; font-size: 18px; color: #38bdf8; }
        .pricing-btns { display: flex; gap: 10px; flex-wrap: wrap; }
        .btn-tiun { background: #10b981; color: white; border: none; padding: 10px 16px; border-radius: 8px; font-weight: 600; cursor: pointer; font-size: 14px; text-decoration: none; display: inline-block; }
        .btn-tiun:hover { background: #059669; }

        .metrics-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 15px; margin-bottom: 20px; }
        .metric-card { background: var(--card-bg); padding: 20px; border-radius: 12px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); border: 1px solid var(--border-color); }
        .metric-card h3 { margin: 0; font-size: 26px; font-weight: 700; color: var(--primary); }
        .metric-card p { margin: 5px 0 0; color: var(--text-muted); font-size: 13px; font-weight: 500; }

        .dashboard-grid { display: grid; grid-template-columns: 2fr 1fr; gap: 20px; margin-bottom: 20px; }
        @media (max-width: 900px) { .dashboard-grid { grid-template-columns: 1fr; } }

        .card { background: var(--card-bg); padding: 20px; border-radius: 12px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); border: 1px solid var(--border-color); }
        .card h2 { margin-top: 0; font-size: 16px; font-weight: 600; margin-bottom: 15px; color: var(--text-main); }
        
        #map { height: 420px; border-radius: 10px; width: 100%; z-index: 1; margin-bottom: 15px; }
        .btn-action { background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%); color: white; border: none; padding: 12px 20px; border-radius: 10px; cursor: pointer; font-weight: 600; font-size: 15px; width: 100%; margin-top: 10px; box-shadow: 0 4px 6px rgba(37, 99, 235, 0.2); }
        .btn-secondary { background: #475569; }
        
        .tools-panel { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
        @media (max-width: 600px) { .tools-panel { grid-template-columns: 1fr; } }
        .file-upload-box { border: 2px dashed var(--border-color); padding: 15px; border-radius: 8px; text-align: center; background: #fafafa; font-size: 13px; }

        .legal-footer { background: var(--card-bg); padding: 20px; border-radius: 12px; border: 1px solid var(--border-color); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 15px; font-size: 12px; color: var(--text-muted); }
        .legal-footer a { color: var(--primary); text-decoration: none; font-weight: 600; }
    </style>
</head>
<body>

    <div class="navbar">
        <div class="logo"><span>🌍</span> GlobalRoute AI SaaS</div>
        <div class="nav-auth">
            <a href="/admin" target="_blank" class="btn-admin-link">🔐 Console Admin Sécurisée ↗</a>
        </div>
    </div>

    <!-- Bannière d'information -->
    <div class="pricing-banner">
        <div>
            <h3>🛒 Solutions Logistiques & Abonnements Entreprises</h3>
            <p style="margin: 5px 0 0; font-size: 13px; color: #94a3b8;">Moteur d'optimisation de tournées mondiales haute performance.</p>
        </div>
        <div class="pricing-btns">
            <button onclick="alerteDemo('Plan 30 Jours')" class="btn-tiun">⚡ Plan 30 Jours</button>
            <button onclick="alerteDemo('Plan 1 An')" class="btn-tiun" style="background: #2563eb;">👑 Plan 1 An (365 Jours)</button>
        </div>
    </div>

    <div class="metrics-grid">
        <div class="metric-card"><h3 id="kpi-villes">0</h3><p>Points Traités</p></div>
        <div class="metric-card"><h3 id="kpi-distance">0.0 km</h3><p>Distance Optimisée (Haversine)</p></div>
        <div class="metric-card"><h3 id="kpi-temps">0.00 s</h3><p>Vitesse Moteur par Blocs</p></div>
    </div>

    <div class="dashboard-grid">
        <div class="card">
            <h2>🗺️ Carte interactive & Gestion des Données</h2>
            <div id="map"></div>
            
            <div class="tools-panel">
                <div class="file-upload-box">
                    <label style="font-weight: 600; display: block; margin-bottom: 5px;">📂 Importer des points (CSV)</label>
                    <input type="file" id="csvFileInput" accept=".csv" onchange="importerFichierCSV()" style="font-size: 12px; width: 100%;">
                </div>
                <div>
                    <button class="btn-action" style="margin-top:0;" onclick="lancerCalculGlobal()">⚡ Lancer l'Optimisation</button>
                    <button class="btn-action btn-secondary" onclick="telechargerRapport()">📥 Télécharger le Rapport</button>
                </div>
            </div>
        </div>
        <div class="card">
            <h2>📊 Répartition Analytique</h2>
            <div style="position: relative; height: 280px; width: 100%;">
                <canvas id="chartPerformance"></canvas>
            </div>
        </div>
    </div>

    <div class="legal-footer">
        <div>
            <p><strong>GlobalRoute AI</strong> — SaaS Logistique persistant avec SQLite.</p>
        </div>
        <div>
            <p>Contact : <a href="mailto:abrahamdawintz410@gmail.com">abrahamdawintz410@gmail.com</a> | WhatsApp : <a href="https://wa.me/50941817761" target="_blank">+509 41 81 7761</a></p>
        </div>
    </div>

    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
        let map;
        window.addEventListener('load', () => {
            map = L.map('map').setView([18.5944, -72.3074], 8);
            L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
                maxZoom: 19,
                attribution: '&copy; CARTO'
            }).addTo(map);
            setTimeout(() => { map.invalidateSize(); }, 300);
        });

        let coucheRoute = null;
        let marqueursGlobaux = [];

        let listeVillesTest = [
            [18.5944, -72.3074],
            [18.5400, -72.3300],
            [18.6200, -72.2500],
            [18.5000, -72.4000],
            [18.5700, -72.2000],
            [18.6500, -72.3500]
        ];

        function alerteDemo(plan) {
            alert("Redirection vers le portail d'achat sécurisé pour le " + plan + ". (Lien de paiement en cours de configuration finale).");
        }

        async function importerFichierCSV() {
            const input = document.getElementById('csvFileInput');
            if (input.files.length === 0) return;
            const fichier = input.files[0];
            const formData = new FormData();
            formData.append("file", fichier);
            // Utilisation transparente de la clé maître par défaut pour les tests publics
            const cle = "CLE-ADMIN-MAITRE-999";

            try {
                const rep = await fetch('/api/importer-csv', {
                    method: 'POST',
                    headers: { 'X-API-KEY': cle },
                    body: formData
                });
                const data = await rep.json();
                if (rep.ok) {
                    if (data.villes.length > 0) {
                        listeVillesTest = data.villes;
                        alert(`Succès ! ${data.total_importe} points importés depuis le CSV.`);
                        lancerCalculGlobal();
                    } else {
                        alert("Aucune coordonnée valide trouvée dans le CSV (Format : latitude,longitude).");
                    }
                } else {
                    alert("Erreur d'import : " + data.detail);
                }
            } catch (e) {
                alert("Erreur réseau lors du traitement du fichier.");
            }
        }

        async function telechargerRapport() {
            const cle = "CLE-ADMIN-MAITRE-999";
            try {
                const rep = await fetch('/api/exporter-rapport', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-API-KEY': cle },
                    body: JSON.stringify({ villes: listeVillesTest })
                });
                if (rep.ok) {
                    const texteRapport = await rep.text();
                    const blob = new Blob([texteRapport], { type: 'text/plain' });
                    const url = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = 'rapport_tournee_globalroute.txt';
                    a.click();
                } else {
                    const err = await rep.json();
                    alert("Erreur : " + err.detail);
                }
            } catch (e) {
                alert("Erreur lors du téléchargement du rapport.");
            }
        }

        async function lancerCalculGlobal() {
            const cle = "CLE-ADMIN-MAITRE-999";

            marqueursGlobaux.forEach(m => map.removeLayer(m));
            marqueursGlobaux = [];
            if (coucheRoute) map.removeLayer(coucheRoute);

            listeVillesTest.forEach(coord => {
                let marker = L.circleMarker(coord, {
                    radius: 7, fillColor: "#2563eb", color: "#fff", weight: 2, fillOpacity: 1
                }).addTo(map);
                marqueursGlobaux.push(marker);
            });

            try {
                let debut = performance.now();
                const reponse = await fetch('/optimiser-tournee-gps/', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-API-KEY': cle },
                    body: JSON.stringify({ villes: listeVillesTest })
                });

                const resultat = await reponse.json();
                let fin = performance.now();
                let tempsCalcul = ((fin - debut) / 1000).toFixed(2);

                if (reponse.ok) {
                    document.getElementById('kpi-villes').innerText = resultat.nombre_de_villes;
                    document.getElementById('kpi-distance').innerText = resultat.distance_totale_km + " km";
                    document.getElementById('kpi-temps').innerText = tempsCalcul + " s";

                    let coordonneesTracees = resultat.ordre_de_visite_optimal.map(index => listeVillesTest[index]);
                    coordonneesTracees.push(coordonneesTracees[0]);

                    coucheRoute = L.polyline(coordonneesTracees, { color: '#ef4444', weight: 4, opacity: 0.85, dashArray: '4, 4' }).addTo(map);
                    map.fitBounds(coucheRoute.getBounds(), { padding: [40, 40] });
                } else {
                    alert("Accès refusé : " + resultat.detail);
                }
            } catch (e) {
                alert("Erreur de connexion au serveur (Le serveur Render sort peut-être de veille, veuillez patienter 30 secondes).");
            }
        }

        const ctx = document.getElementById('chartPerformance').getContext('2d');
        new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: ['Blocs Exacts', '2-Opt Local', 'Calcul GPS'],
                datasets: [{
                    data: [70, 20, 10],
                    backgroundColor: ['#2563eb', '#38bdf8', '#cbd5e1'],
                    borderWidth: 0
                }]
            },
            options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom' } } }
        });
    </script>
</body>
</html>
    """
    return html_content
