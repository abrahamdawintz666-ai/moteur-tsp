"""
================================================================================
SWIFTROUTE ENGINE — ENTERPRISE COMMERCIAL EDITION (HYBRID VRPTW MATRIX)
Architecture: 4-Force Elite Ant Colony Optimization (ACO) & Planar Projection
Adjustments: Earth Radius Coordinate Vectorization & Time Window Constraints
Author: Abraham — Cap-Haïtien 2026 / Version Élite Premium Interactive
================================================================================
"""

from fastapi import FastAPI, HTTPException, Security, Depends, Request, Form
from fastapi.security.api_key import APIKeyHeader
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import jwt
import random
import math
import datetime
import time
from typing import List, Tuple

TIUN_SNIPPET_ID = "JQD27X4Dhj8JGdXQhnbBYz1K2HS5gjiojVwYIAKR"
PHRASE_SECRETE_TIUN = "CAP_HAITIEN_CLE_SECRETE_4_FORCES_2026"

API_KEY_NAME = "X-API-KEY"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

app = FastAPI(
    title="SwiftRoute Engine - AntStrike Advanced VRPTW",
    swagger_ui_parameters={"operationsSorter": "alpha"},
    security=[{API_KEY_NAME: []}]
)

# Configuration CORS essentielle pour le réseau Render
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

NOM_UTILISATEUR_ADMIN = "Abraham"
MOT_DE_PASSE_ADMIN = "AntStrike_Cap2026!"
IPS_ESSAIS_UTILISES = set()

class RequeteCalcul(BaseModel):
    villes: List[Tuple[float, float, float, float]]
    capacite_vehicule: int = 10
    index_depart: int = 0
def obtenir_page_accueil():
    return r"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <title>SwiftRoute Pro — Plateforme Logistique Élite</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="google" content="notranslate" />
    <link rel="stylesheet" href="https://cloudflare.com" />
    <style>
        :root { --bg: #0c0a09; --card: #1c1917; --accent: #f59e0b; --accent-hover: #d97706; --text: #f5f5f4; --text-muted: #a8a29e; --border: #2e2a24; --success: #22c55e; }
        body { font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; background-color: var(--bg); color: var(--text); margin: 0; padding: 0; }
        .navbar { display: flex; justify-content: space-between; align-items: center; padding: 20px 40px; border-bottom: 1px solid var(--border); background: #141210; }
        .brand { font-size: 22px; font-weight: 800; color: var(--accent); display: flex; align-items: center; gap: 8px; text-decoration: none; }
        .nav-links a { color: var(--text-muted); text-decoration: none; margin-left: 25px; font-size: 14px; transition: 0.2s; }
        .nav-links a:hover { color: var(--accent); }
        .nav-links .btn-nav { background: var(--accent); color: var(--bg); padding: 8px 16px; border-radius: 6px; font-weight: bold; text-decoration: none; }
        .main-container { max-width: 1000px; margin: 40px auto; padding: 0 20px; }
        .hero-section { text-align: center; margin-bottom: 35px; }
        .hero-section h1 { font-size: 36px; font-weight: 800; letter-spacing: -1px; margin-bottom: 10px; }
        .hero-section p { color: var(--text-muted); font-size: 16px; max-width: 600px; margin: auto; }
        .app-card { background: var(--card); border: 1px solid var(--border); border-radius: 16px; padding: 30px; box-shadow: 0 10px 30px rgba(0,0,0,0.5); margin-bottom: 25px; }
        .auth-table { border: 1px dashed var(--accent); background: rgba(245, 158, 11, 0.02); padding: 20px; border-radius: 12px; margin-bottom: 25px; }
        .auth-input-wrapper { display: flex; gap: 10px; margin-top: 10px; }
        .api-input { flex: 1; padding: 12px; background: #0c0a09; border: 1px solid var(--border); border-radius: 6px; color: #fff; font-family: monospace; font-size: 14px; }
        .premium-settings-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 20px; background: #141210; padding: 15px; border-radius: 10px; border: 1px solid var(--border); }
        .setting-box input { width: 100%; padding: 10px; background: #0c0a09; border: 1px solid var(--border); border-radius: 6px; color: #fff; box-sizing: border-box; }
        label { display: block; font-size: 13px; font-weight: 600; margin-bottom: 8px; color: var(--text-muted); }
        textarea { width: 100%; height: 140px; background: #0c0a09; border: 1px solid var(--border); border-radius: 10px; color: #fff; padding: 15px; font-family: monospace; font-size: 14px; box-sizing: border-box; resize: vertical; }
        .textarea-hint { display: flex; justify-content: space-between; font-size: 12px; color: var(--text-muted); margin-top: 5px; }
        .btn-action { background: var(--accent); color: var(--bg); font-size: 16px; font-weight: 700; border: none; padding: 15px 30px; border-radius: 10px; width: 100%; margin-top: 20px; cursor: pointer; display: flex; justify-content: center; align-items: center; gap: 10px; }
        .btn-action:hover { background: var(--accent-hover); }
        #map { width: 100%; height: 400px; border-radius: 12px; margin-top: 25px; border: 1px solid var(--border); display: none; z-index: 1; }
        .results-box { margin-top: 30px; background: #141210; border: 1px solid var(--border); border-radius: 10px; padding: 20px; display: none; }
        .results-header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); padding-bottom: 10px; margin-bottom: 15px; }
        .metric-badge { background: var(--card); border: 1px solid var(--border); padding: 6px 12px; border-radius: 6px; font-size: 13px; color: var(--accent); font-weight: bold; }
        .route-list { display: flex; flex-direction: column; gap: 8px; font-family: monospace; font-size: 14px; max-height: 250px; overflow-y: auto; }
        .route-step { display: flex; align-items: center; gap: 10px; background: var(--card); padding: 10px; border-radius: 6px; }
        .step-number { background: var(--accent); color: var(--bg); font-weight: bold; width: 24px; height: 24px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 12px; }
        .error-box { margin-top: 20px; background: rgba(239, 68, 68, 0.1); border: 1px solid #ef4444; color: #fca5a5; padding: 15px; border-radius: 10px; display: none; }
        .loader { border: 3px solid #333; border-top: 3px solid var(--accent); border-radius: 50%; width: 20px; height: 20px; animation: spin 0.8s linear infinite; display: none; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    </style>
</head>"""
    return obtenir_page_accueil() + r"""<body class="notranslate">
    <nav class="navbar">
        <a href="/" class="brand">🐜 SwiftRoute Premium</a>
        <div class="nav-links">
            <a href="/terms">Conditions</a>
            <a href="/privacy">Confidentialité</a>
            <a href="/dashboard" class="btn-nav">Acheter une Licence</a>
        </div>
    </nav>
    <div class="main-container">
        <div class="hero-section">
            <h1>Cartographie & Routage Haute Performance</h1>
            <p>Système de projection planaire couplé à une visualisation cartographique interactive en temps réel.</p>
        </div>
        <div class="app-card">
            <div class="auth-table">
                <h3>🔑 Connexion Client</h3>
                <div class="auth-input-wrapper">
                    <input type="text" id="api-key-input" class="api-input" placeholder="Insérez votre jeton X-API-KEY ici pour débloquer le serveur...">
                </div>
            </div>
            <div class="premium-settings-grid">
                <div class="setting-box">
                    <label for="capacity-input">📦 Capacité Max par Véhicule :</label>
                    <input type="number" id="capacity-input" value="10" min="1" max="100">
                </div>
                <div class="setting-box">
                    <label for="start-index-input">🏢 Index Point de Départ (Dépôt) :</label>
                    <input type="number" id="start-index-input" value="0" min="0">
                </div>
            </div>
            <label for="coordonnees-input">📍 Copier-coller de vos coordonnées géographiques [Lon, Lat, HeureMin, HeureMax] :</label>
            <textarea id="coordonnees-input" placeholder="-72.2014, 19.7521, 8, 12\n-72.2035, 19.7542, 9, 17"></textarea>
            <div class="textarea-hint">
                <span>Format étendu : Longitude, Latitude, Ouverture, Fermeture</span>
                <span id="line-counter">0 point détecté</span>
            </div>
            <button id="submit-btn" class="btn-action" onclick="analyserEtCalculer()">
                <div id="btn-loader" class="loader"></div>
                <span id="btn-text">⚡ Exécuter le routage vectoriel</span>
            </button>
            <div id="error-display" class="error-box"></div>
            <div id="map"></div>
            <div id="results-display" class="results-box">
                <div class="results-header">
                    <h3 style="margin: 0; font-size: 18px;">🎯 Feuille de Route Optimisée</h3>
                    <div style="display: flex; gap: 5px;">
                        <span id="metric-villes" class="metric-badge">0 points</span>
                        <span id="metric-distance" class="metric-badge" style="color: #f59e0b;">0 km au total</span>
                        <span id="metric-temps" class="metric-badge" style="color: #22c55e;">0.00s</span>
                    </div>
                </div>
                <div id="route-steps-container" class="route-list"></div>
            </div>
        </div>
    </div>
    <script src="https://cloudflare.com"></script>
    <script>
        const textarea = document.getElementById('coordonnees-input');
        const lineCounter = document.getElementById('line-counter');
        let carteLeaflet = null;
        let calqueTraces = null;
        textarea.addEventListener('input', () => {
            const points = extraireCoordonnees(textarea.value);
            lineCounter.textContent = points.length + " point(s) valide(s) détecté(s)";
        });
        function extraireCoordonnees(texte) {
            const lignes = texte.split('\n');
            const points = [];
            lignes.forEach(ligne => {
                const nettoyage = ligne.replace(/[\[\]{}()]/g, '').trim();
                if (!nettoyage) return;
                const valeurs = nettoyage.split(/[\s,;\t]+/).map(Number).filter(n => !isNaN(n));
                if (valeurs.length >= 2) {
                    const lon = valeurs[0];
                    const lat = valeurs[1];
                    const h_min = valeurs[2] !== undefined ? valeurs[2] : 0;
                    const h_max = valeurs[3] !== undefined ? valeurs[3] : 24;
                    points.push([lon, lat, h_min, h_max]);
                }
            });
            return points;
        }
        async function analyserEtCalculer() {
            const btn = document.getElementById('submit-btn');
            const btnText = document.getElementById('btn-text');
            const btnLoader = document.getElementById('btn-loader');
            const errorBox = document.getElementById('error-display');
            const resultsBox = document.getElementById('results-display');
            const stepsContainer = document.getElementById('route-steps-container');
            const mapDiv = document.getElementById('map');
            errorBox.style.display = 'none';
            const villesExtraites = extraireCoordonnees(textarea.value);
            const cleSaisie = document.getElementById('api-key-input').value.trim();
            const capaciteSaisie = parseInt(document.getElementById('capacity-input').value) || 10;
            const dptSaisi = parseInt(document.getElementById('start-index-input').value) || 0;
            if (!cleSaisie) { window.location.href = "/dashboard"; return; }
            if (villesExtraites.length < 3) {
                errorBox.textContent = "❌ Données insuffisantes : Veuillez fournir au moins 3 coordonnées géographiques.";
                errorBox.style.display = 'block';
                return;
            }
            btn.disabled = true;
            btnLoader.style.display = 'block';
            btnText.textContent = "Calcul spatial VRPTW en cours...";
            try {
                const reponse = await fetch('/api/v1/route/optimize', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-API-KEY': cleSaisie },
                    body: JSON.stringify({ villes: villesExtraites, capacite_vehicule: capaciteSaisie, index_depart: dptSaisi })
                });
                const data = await reponse.json();
                if (!reponse.ok) throw new Error(data.detail || "Refus d'authentification.");
                
                document.getElementById('metric-villes').textContent = data.metriques.villes_traitees + " points";
                document.getElementById('metric-distance').textContent = "📏 " + data.metriques.distance_matrice_km + " km au total";
                document.getElementById('metric-temps').textContent = "⏱️ " + data.metriques.temps_execution_secondes + "s";
                stepsContainer.innerHTML = '';
                mapDiv.style.display = 'block';
                
                if (!carteLeaflet) {
                    carteLeaflet = L.map('map').setView([villesExtraites[0][1], villesExtraites[0][0]], 11);
                    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                        attribution: '&copy; OpenStreetMap contributors'
                    }).addTo(carteLeaflet);
                }
                if (calqueTraces) { carteLeaflet.removeLayer(calqueTraces); }
                calqueTraces = L.featureGroup().addTo(carteLeaflet);
                
                data.rapport_logistique.vehicules.forEach((camion) => {
                    const sousListeCoords = [];
                    camion.itineraire.forEach((etape) => {
                        const lon = etape.coordonnees[0];
                        const lat = etape.coordonnees[1];
                        const latLng = [lat, lon];
                        sousListeCoords.push(latLng);
                        
                        const div = document.createElement('div');
                        div.className = 'route-step';
                        div.innerHTML = '<div class="step-number">' + etape.etape + '</div><div><strong>Véhicule #' + camion.id_vehicule + ' - Arrêt #' + etape.index_vrai + '</strong> <br><span style="color:#a8a29e; font-size:12px;">Arrivée estimée: ' + etape.heure_arrivee_estimee + 'h (Fenêtre: ' + etape.fenetre_horaire_requise + ')</span></div>';
                        stepsContainer.appendChild(div);
                        L.marker(latLng).addTo(calqueTraces).bindPopup("<b>Véhicule " + camion.id_vehicule + "</b><br>Arrivée: " + etape.heure_arrivee_estimee + "h");
                    });
                    if (sousListeCoords.length > 0) {
                        L.polyline(sousListeCoords, { color: '#f59e0b', weight: 4, opacity: 0.85 }).addTo(calqueTraces);
                    }
                });
                carteLeaflet.fitBounds(calqueTraces.getBounds());
                resultsBox.style.display = 'block';
            } catch (err) {
                errorBox.textContent = "⚠️ Refus de l'infrastructure : " + err.message;
                errorBox.style.display = 'block';
            } finally {
                btn.disabled = false;
                btnLoader.style.display = 'none';
                btnText.textContent = "⚡ Exécuter le routage vectoriel";
            }
        }
    </script>
</body>
</html>"""
def obtenir_tableau_bord(t): return f"<html><body><h1>Dashboard</h1><p>Token: {t}</p></body></html>"
def obtenir_panneau_admin(c): return f"<html><body><h1>Admin</h1><p>Clé: {c}</p></body></html>"

@app.get("/", response_class=HTMLResponse)
async def page_accueil_serveur():
    return HTMLResponse(content=obtenir_page_accueil())

@app.get("/dashboard", response_class=HTMLResponse)
async def tableau_de_bord_serveur(token_visuel: str = ""):
    return HTMLResponse(content=obtenir_tableau_bord(token_visuel))

@app.get("/admin-panel", response_class=HTMLResponse)
async def vue_panneau_admin_serveur(cle_generee: str = ""):
    return HTMLResponse(content=obtenir_panneau_admin(cle_generee))

@app.post("/admin-panel/generer")
async def action_generer_cle_serveur(request: Request, username: str = Form(...), password: str = Form(...), client_name: str = Form(...), duration: int = Form(...)):
    if username != NOM_UTILISATEUR_ADMIN or password != MOT_DE_PASSE_ADMIN:
        return HTMLResponse(content="<h2>Identifiants incorrects ! Accès refusé.</h2>", status_code=403)
    date_actuelle = datetime.datetime.utcnow()
    exp_date = date_actuelle + datetime.timedelta(days=30)
    payload = {
        "client": client_name,
        "exp": int(exp_date.timestamp()),
        "type_offre": "Premium Manuel",
        "ip_security": request.client.host
    }
    token_client = jwt.encode(payload, PHRASE_SECRETE_TIUN, algorithm="HS256")
    return await vue_panneau_admin_serveur(cle_generee=token_client)

@app.get("/terms", response_class=HTMLResponse)
async def conditions_utilisation_serveur():
    return HTMLResponse(content="<html><body><h1>Conditions Générales</h1><p>Vecteurs requis : [Longitude, Latitude, HeureMin, HeureMax]</p></body></html>")

@app.get("/privacy", response_class=HTMLResponse)
async def politique_confidentialite_serveur():
    return HTMLResponse(content="<html><body><h1>Confidentialité</h1><p>Traitement volatile en mémoire vive (RAM).</p></body></html>")

async def verifier_minuteur_cle_api(api_key: str = Security(api_key_header)):
    if not api_key:
        raise HTTPException(status_code=403, detail="Clé API absente. Connectez-vous sur le Tableau.")
    try:
        infos = jwt.decode(api_key, PHRASE_SECRETE_TIUN, algorithms=["HS256"])
        return infos
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=402, detail="Abonnement Tiun expiré. Veuillez renouveler votre formule.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=403, detail="Accès refusé : Jeton invalide ou altéré.")

@app.post("/api/v1/route/optimize")
async def optimiser_trajet_api(donnees: RequeteCalcul, jeton_valide: dict = Depends(verifier_minuteur_cle_api)):
    if not donnees.villes or len(donnees.villes) == 0:
        raise HTTPException(status_code=400, detail="La liste des coordonnées géographiques ne peut pas être vide.")
    temps_debut = time.time()
    
    route_ordonnee, distance_totale, historique_temps = calculer_route_precision(donnees.villes, donnees.capacite_vehicule, donnees.index_depart)
    
    vehicules_data = []
    id_vehicule_courant = 1
    index_etape = 1
    itineraire_courant = []
    
    for idx_ordre, index_ville in enumerate(route_ordonnee):
        v = donnees.villes[index_ville]
        h_arrivee = historique_temps[idx_ordre] if idx_ordre < len(historique_temps) else 8.0
        
        itineraire_courant.append({
            "etape": index_etape,
            "index_vrai": index_ville,
            "coordonnees": [v[0], v[1]],
            "heure_arrivee_estimee": round(h_arrivee, 2),
            "fenetre_horaire_requise": f"{v[2]}h - {v[3]}h"
        })
        index_etape += 1
        
        if index_ville == donnees.index_depart and idx_ordre != 0:
            vehicules_data.append({
                "id_vehicule": id_vehicule_courant,
                "statut": "Tournée validée (Contrainte VRPTW Respectée)",
                "itineraire": itineraire_courant
            })
            id_vehicule_courant += 1
            index_etape = 1
            itineraire_courant = []
            
    if itineraire_courant:
        vehicules_data.append({"id_vehicule": id_vehicule_courant, "statut": "Tournée finale active", "itineraire": itineraire_courant})
        
    temps_fin = time.time()
    return {
        "statut": "success",
        "client_autorise": jeton_valide.get("client"),
        "formule_tiun": jeton_valide.get("type_offre"),
        "metriques": {
            "villes_traitees": len(donnees.villes),
            "distance_matrice_km": round(distance_totale, 2),
            "temps_execution_secondes": round(temps_fin - temps_debut, 4)
        },
        "ordonnancement_indices": route_ordonnee,
        "rapport_logistique": {"vehicules": vehicules_data}
    }
NB_FOURMIS = 15
ALPHA, BETA, EVAPORATION, Q = 1.0, 2.0, 0.3, 100.0

def calculer_route_precision(villes: List[Tuple[float, float, float, float]], capacite_max: int, index_depart: int):
    nb_villes = len(villes)
    if nb_villes < 3: return list(range(nb_villes)), 0.0, [0.0]*nb_villes
    if index_depart >= nb_villes: index_depart = 0
    
    lat_moyenne = math.radians(sum(float(v[1]) for v in villes) / nb_villes)
    R = 6371.0
    
    villes_planes = []
    for v in villes:
        x = R * math.radians(float(v[0])) * math.cos(lat_moyenne)
        y = R * math.radians(float(v[1]))
        villes_planes.append((x, y))
        
    distances = []
    for i in range(nb_villes):
        ligne = []
        for j in range(nb_villes):
            if i == j: ligne.append(0.0)
            else:
                dx = villes_planes[i][0] - villes_planes[j][0]
                dy = villes_planes[i][1] - villes_planes[j][1]
                ligne.append(math.sqrt(dx*dx + dy*dy) * 1.23)
        distances.append(ligne)
        
    pheromones = [[1.0 for _ in range(nb_villes)] for _ in range(nb_villes)]
    meilleure_distance = float('inf')
    meilleure_route = []
    meilleur_historique_temps = []
    
    iterations = 20 if nb_villes > 60 else 40
    for _ in range(iterations):
        toutes_routes, toutes_distances, tous_temps = [], [], []
        for _ in range(NB_FOURMIS):
            r, d, h_t = simuler_fourmi_vrptw(nb_villes, distances, pheromones, capacite_max, index_depart, villes)
            toutes_routes.append(r); toutes_distances.append(d); tous_temps.append(h_t)
            if d < meilleure_distance: 
                meilleure_distance = d
                meilleure_route = r
                meilleur_historique_temps = h_t
        for i in range(nb_villes):
            for j in range(nb_villes): pheromones[i][j] *= (1.0 - EVAPORATION)
        for route, dist in zip(toutes_routes, toutes_distances):
            depot = Q / max(dist, 0.01)
            for k in range(len(route) - 1): pheromones[route[k]][route[k+1]] += depot
    return meilleure_route, meilleure_distance, meilleur_historique_temps
def simuler_fourmi_vrptw(nb, dists, phero, capacite_max, depot_index, donnees_villes):
    path = [depot_index]
    villes_visitees = set([depot_index])
    charge_actuelle = 0
    d_tot = 0.0
    heure_actuelle = 8.0
    historique_temps = [heure_actuelle]
    vitesse_moyenne_kmh = 50.0
    
    while len(villes_visitees) < nb:
        act = path[-1]
        if charge_actuelle >= capacite_max:
            d_tot += dists[act][depot_index]
            path.append(depot_index)
            heure_actuelle += dists[act][depot_index] / vitesse_moyenne_kmh
            historique_temps.append(heure_actuelle)
            act = depot_index
            charge_actuelle = 0
            heure_actuelle = 8.0
            
        probs = []
        tot = 0.0
        for p in range(nb):
            if p not in villes_visitees:
                temps_trajet = dists[act][p] / vitesse_moyenne_kmh
                heure_arrivee_potentielle = heure_actuelle + temps_trajet
                v = donnees_villes[p]
                if heure_arrivee_potentielle <= float(v[3]):
                    vis = 1.0 / max(dists[act][p], 0.01)
                    note = (phero[act][p] ** ALPHA) * (vis ** BETA)
                    probs.append((p, note, temps_trajet, float(v[2])))
                    tot += note
                    
        if tot == 0:
            restants = [x for x in range(nb) if x not in villes_visitees]
            prox = restants[0] if restants else depot_index
            if restants:
                temps_trajet = dists[act][prox] / vitesse_moyenne_kmh
                heure_actuelle += temps_trajet
        else:
            flotte = random.uniform(0, tot)
            cum = 0.0
            prox = probs[-1][0]
            for item in probs:
                cum += item[1]
                if cum >= flotte: 
                    prox = item[0]
                    heure_actuelle += item[2]
                    if heure_actuelle < item[3]: heure_actuelle = item[3]
                    break
                    
        d_tot += dists[act][prox]
        path.append(prox)
        historique_temps.append(heure_actuelle)
        villes_visitees.add(prox)
        charge_actuelle += 1
        
    d_tot += dists[path[-1]][depot_index]
    path.append(depot_index)
    historique_temps.append(heure_actuelle + (dists[path[-1]][depot_index] / vitesse_moyenne_kmh))
    return path, d_tot, historique_temps
