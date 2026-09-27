"""
================================================================================
SWIFTROUTE ENGINE — ENTERPRISE COMMERCIAL EDITION (HYBRID VRP MATRIX)
Architecture: 4-Force Elite Ant Colony Optimization (ACO) & Planar Projection
Adjustments: Earth Radius Coordinate Vectorization & Road Tortuosity Matrix
Author: Abraham — Cap-Haïtien 2026 / Version Graphique Élite Tiun
================================================================================
"""

from fastapi import FastAPI, HTTPException, Security, Depends, Request, Form
from fastapi.security.api_key import APIKeyHeader
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
import jwt
import random
import math
import datetime
import time
from typing import List, Tuple

# Identifiant unique de votre compte Tiun en production
TIUN_SNIPPET_ID = "JQD27X4Dhj8JGdXQhnbBYz1K2HS5gjiojVwYIAKR"
PHRASE_SECRETE_TIUN = "CAP_HAITIEN_CLE_SECRETE_4_FORCES_2026"

API_KEY_NAME = "X-API-KEY"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

app = FastAPI(
    title="SwiftRoute Engine - AntStrike Advanced VRP",
    swagger_ui_parameters={"operationsSorter": "alpha"},
    security=[{API_KEY_NAME: []}]
)

NOM_UTILISATEUR_ADMIN = "Abraham"
MOT_DE_PASSE_ADMIN = "AntStrike_Cap2026!"
IPS_ESSAIS_UTILISES = set()

class RequeteCalcul(BaseModel):
    villes: List[Tuple[float, float]]

def obtenir_page_accueil():
    return """
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <title>SwiftRoute — Optimisation de Tournées Élite</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            :root { --bg: #0c0a09; --card: #1c1917; --accent: #f59e0b; --accent-hover: #d97706; --text: #f5f5f4; --text-muted: #a8a29e; --border: #2e2a24; }
            body { font-family: 'Segoe UI', system-ui, sans-serif; background-color: var(--bg); color: var(--text); margin: 0; padding: 0; }
            .navbar { display: flex; justify-content: space-between; align-items: center; padding: 20px 40px; border-bottom: 1px solid var(--border); background: #141210; }
            .brand { font-size: 22px; font-weight: 800; color: var(--accent); text-decoration: none; }
            .nav-links a { color: var(--text-muted); text-decoration: none; margin-left: 25px; font-size: 14px; transition: 0.2s; }
            .nav-links a:hover { color: var(--accent); }
            .nav-links .btn-nav { background: var(--accent); color: var(--bg); padding: 8px 16px; border-radius: 6px; font-weight: bold; }
            
            .main-container { max-width: 900px; margin: 50px auto; padding: 0 20px; }
            .hero-section { text-align: center; margin-bottom: 40px; }
            .hero-section h1 { font-size: 36px; font-weight: 800; letter-spacing: -1px; margin-bottom: 10px; }
            .hero-section p { color: var(--text-muted); font-size: 16px; }
            
            .app-card { background: var(--card); border: 1px solid var(--border); border-radius: 16px; padding: 30px; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
            label { display: block; font-size: 14px; font-weight: 600; margin-bottom: 10px; }
            textarea { width: 100%; height: 180px; background: #0c0a09; border: 1px solid var(--border); border-radius: 10px; color: #fff; padding: 15px; font-family: monospace; font-size: 14px; box-sizing: border-box; resize: vertical; }
            textarea:focus { border-color: var(--accent); outline: none; }
            .textarea-hint { font-size: 12px; color: var(--text-muted); margin-top: 5px; display: flex; justify-content: space-between; }
            
            .btn-action { background: var(--accent); color: var(--bg); font-size: 16px; font-weight: 700; border: none; padding: 15px 30px; border-radius: 10px; width: 100%; margin-top: 20px; cursor: pointer; display: flex; justify-content: center; align-items: center; gap: 10px; transition: 0.2s; }
            .btn-action:hover { background: var(--accent-hover); }
            .btn-action:disabled { background: var(--border); color: var(--text-muted); cursor: not-allowed; }
            
            .loader { border: 3px solid #333; border-top: 3px solid var(--accent); border-radius: 50%; width: 20px; height: 20px; animation: spin 0.8s linear infinite; display: none; }
            @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
            
            .results-box { margin-top: 30px; background: #141210; border: 1px solid var(--border); border-radius: 10px; padding: 20px; display: none; }
            .results-header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); padding-bottom: 10px; margin-bottom: 15px; }
            .metric-badge { background: var(--card); border: 1px solid var(--border); padding: 6px 12px; border-radius: 6px; font-size: 13px; color: var(--accent); font-weight: bold; }
            .route-list { display: flex; flex-direction: column; gap: 8px; font-family: monospace; }
            .route-step { display: flex; align-items: center; gap: 10px; background: var(--card); padding: 10px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.02); }
            .step-number { background: var(--accent); color: var(--bg); font-weight: bold; width: 24px; height: 24px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 12px; }
            .error-box { margin-top: 20px; background: rgba(239, 68, 68, 0.1); border: 1px solid #ef4444; color: #fca5a5; padding: 15px; border-radius: 10px; display: none; font-size: 14px; }
        </style>
    </head>
    <body>
        <nav class="navbar">
            <a href="/" class="brand">🐜 SwiftRoute Engine</a>
            <div class="nav-links">
                <a href="/terms">Conditions</a>
                <a href="/privacy">Confidentialité</a>
                <a href="/dashboard" class="btn-nav">Mon Espace & Clés</a>
            </div>
        </nav>

        <div class="main-container">
            <div class="hero-section">
                <h1>Optimisez vos tournées en 1 clic</h1>
                <p>Collez simplement vos coordonnées géographiques brutes ci-dessous (séparées par une ligne). L'application gère automatiquement l'extraction.</p>
            </div>

            <div class="app-card">
                <label for="coordonnees-input">Collez vos blocs d'adresses ou coordonnées :</label>
                <textarea id="coordonnees-input" placeholder="Exemple de copier-coller direct :&#10;-72.20, 19.75&#10;-72.30, 19.80&#10;-72.15, 19.65"></textarea>
                <div class="textarea-hint">
                    <span>Format détecté automatiquement [Longitude, Latitude]</span>
                    <span id="line-counter">0 point détecté</span>
                </div>

                <button id="submit-btn" class="btn-action" onclick="analyserEtCalculer()">
                    <div id="btn-loader" class="loader"></div>
                    <span id="btn-text">⚡ Calculer le parcours optimal</span>
                </button>
                
                <div id="error-display" class="error-box"></div>
                
                <div id="results-display" class="results-box">
                    <div class="results-header">
                        <h3 style="margin: 0; font-size: 18px;">🎯 Parcours Optimisé</h3>
                        <div style="display: flex; gap: 10px;">
                            <span id="metric-villes" class="metric-badge">0 points</span>
                            <span id="metric-distance" class="metric-badge">0 km</span>
                            <span id="metric-temps" class="metric-badge" style="color: #22c55e;">0.00s</span>
                        </div>
                    </div>
                    <div id="route-steps-container" class="route-list"></div>
                </div>
            </div>
        </div>
    """

    # Complément HTML du Bloc 2 contenant toute l'intelligence JavaScript
    return obtenir_page_accueil() + """
        <script>
            const textarea = document.getElementById('coordonnees-input');
            const lineCounter = document.getElementById('line-counter');
            
            textarea.addEventListener('input', () => {
                const points = extraireCoordonnees(textarea.value);
                lineCounter.textContent = `${points.length} point(s) valide(s) détecté(s)`;
            });

            function extraireCoordonnees(texte) {
                const lignes = texte.split('\\n');
                const points = [];
                lignes.forEach(ligne => {
                    const nettoyage = ligne.replace(/[\[\]{}()]/g, '').trim();
                    if (!nettoyage) return;
                    const valeurs = nettoyage.split(/[\s,;\t]+/).map(Number).filter(n => !isNaN(n));
                    if (valeurs.length >= 2) {
                        points.push([valeurs[0], valeurs[1]]);
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

                errorBox.style.display = 'none';
                resultsBox.style.display = 'none';

                const villesExtraites = extraireCoordonnees(textarea.value);

                if (villesExtraites.length < 3) {
                    errorBox.textContent = "❌ Veuillez fournir au moins 3 coordonnées valides pour lancer la simulation.";
                    errorBox.style.display = 'block';
                    return;
                }

                btn.disabled = true;
                btnLoader.style.display = 'block';
                btnText.textContent = "Résolution par phéromones en cours...";

                try {
                    const reponse = await fetch('/api/v1/route/optimize', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-API-KEY': 'MANUAL_ADMIN_TOKEN' 
                        },
                        body: JSON.stringify({ villes: villesExtraites })
                    });

                    const data = await reponse.json();

                    if (!reponse.ok) {
                        throw new Error(data.detail || "Le serveur a refusé le calcul.");
                    }

                    document.getElementById('metric-villes').textContent = `${data.metriques.villes_traitees} points`;
                    document.getElementById('metric-distance').textContent = `${data.metriques.distance_matrice_km} km`;
                    document.getElementById('metric-temps').textContent = `⏱️ ${data.metriques.temps_execution_secondes}s`;

                    stepsContainer.innerHTML = '';
                    data.ordonnancement_indices.forEach((indexVille, ordre) => {
                        const coord = villesExtraites[indexVille];
                        const div = document.createElement('div');
                        div.className = 'route-step';
                        div.innerHTML = `
                            <div class="step-number">${ordre + 1}</div>
                            <div>
                                <strong>Point d'arrêt #${indexVille}</strong> 
                                <span style="color: #888; font-size: 12px; margin-left: 10px;">(X / Lon: ${coord[0]}, Y / Lat: ${coord[1]})</span>
                            </div>
                        `;
                        stepsContainer.appendChild(div);
                    });

                    resultsBox.style.display = 'block';

                } catch (err) {
                    errorBox.textContent = `⚠️ Alerte Système : ${err.message}`;
                    errorBox.style.display = 'block';
                } finally {
                    btn.disabled = false;
                    btnLoader.style.display = 'none';
                    btnText.textContent = "⚡ Calculer le parcours optimal";
                }
            }
        </script>
    </body>
    </html>
    """

def obtenir_panneau_admin(cle_generee: str):
    return f"""
    <html>
        <head><title>AntStrike Admin Panel</title></head>
        <body style="font-family: Arial; background-color: #09090b; color: #fff; padding: 20px;">
            <div style="max-width: 500px; margin: auto; background: #18181b; padding: 25px; border-radius: 10px; border: 1px solid #3f3f46;">
                <h2>🎛&ufe0f; Console Privée d'Abraham</h2>
                <form action="/admin-panel/generer" method="post">
                    <label>Admin User:</label><input type="text" name="username" style="width:100%; padding:8px; margin:5px 0;" required><br>
                    <label>Password:</label><input type="password" name="password" style="width:100%; padding:8px; margin:5px 0;" required><br>
                    <label>Client Corporate:</label><input type="text" name="client_name" style="width:100%; padding:8px; margin:5px 0;" required><br>
                    <select name="duration" style="width:100%; padding:8px; margin:10px 0;">
                        <option value="7">Essai Gratuit (7 Jours)</option>
                        <option value="30">Abonnement Enterprise ($1500/Mois)</option>
                    </select>
                    <button type="submit" style="background:#f59e0b; color:#000; padding:10px; width:100%; font-weight:bold; border:none; cursor:pointer;">Émettre la clé</button>
                </form>
                {"<div style='background:#27272a; padding:10px; margin-top:15px; word-break:break-all; border:1px dashed #f59e0b;'>" + cle_generee + "</div>" if cle_generee else ""}
            </div>
        </body>
    </html>
    """

def obtenir_tableau_bord(token_visuel: str = ""):
    contenu = f"""
    <div style="border:1px solid #22c55e; padding:20px; background:#14532d20; border-radius:8px;">
        <h3 style="color:#22c55e; margin-top:0;">✓ Jeton Tiun Actif</h3>
        <div style="background:#0c0a09; padding:10px; font-family:monospace; color:#22c55e; word-break:break-all;">{token_visuel}</div>
    </div>
    """ if token_visuel else f"""
    <div style="border:1px solid #f59e0b; padding:20px; background:#292524; border-radius:8px;">
        <h3 style="color:#f59e0b; margin-top:0;">💳 Licence Commerciale Requise</h3>
        <p>L'utilisation de notre moteur de calcul à plat nécessite l'activation d'un forfait.</p>
        <button onclick="window.location.href='https://tiun.io{TIUN_SNIPPET_ID}'" style="background:#f59e0b; padding:12px; font-weight:bold; border:none; cursor:pointer; width:100%; border-radius:6px;">⚡ S'abonner via la passerelle Tiun.io</button>
    </div>
    """
    return f"""<html><body style="background:#0c0a09; color:#fff; font-family:Arial; padding:40px;"><div style="max-width:600px; margin:auto;"><h2>📊 Console de Gestion Client</h2>{contenu}</div></body></html>"""

@app.get("/", response_class=HTMLResponse)
async def page_accueil_serveur(): return HTMLResponse(content=obtenir_page_accueil())

@app.get("/dashboard", response_class=HTMLResponse)
async def tableau_de_bord_serveur(token_visuel: str = ""): return HTMLResponse(content=obtenir_tableau_bord(token_visuel))

@app.get("/admin-panel", response_class=HTMLResponse)
async def vue_panneau_admin_serveur(cle_generee: str = ""): return HTMLResponse(content=obtenir_panneau_admin(cle_generee))

@app.get("/terms", response_class=HTMLResponse)
async def conditions_utilisation_serveur():
    return HTMLResponse(content="<html><body style='background:#0c0a09; color:#f5f5f4; padding:40px; font-family:sans-serif;'><div style='max-width:800px; margin:auto;'><h1>Conditions d'Utilisation</h1><p>Les requêtes doivent respecter l'ordre cartésien standard des données : [Longitude (Axe X), Latitude (Axe Y)]. La facturation mondiale est gérée de bout en bout par Tiun.io.</p></div></body></html>")

@app.get("/privacy", response_class=HTMLResponse)
async def politique_confidentialite_serveur():
    return HTMLResponse(content="<html><body style='background:#0c0a09; color:#f5f5f4; padding:40px; font-family:sans-serif;'><div style='max-width:800px; margin:auto;'><h1>Politique de Confidentialité</h1><p>Vos coordonnées géographiques sont lues temporairement en mémoire vive lors du routage et ne font l'objet d'aucun stockage persistant.</p></div></body></html>")

@app.post("/admin-panel/generer")
async def action_generer_cle_serveur(request: Request, username: str = Form(...), password: str = Form(...), client_name: str = Form(...), duration: int = Form(...)):
    if username != NOM_UTILISATEUR_ADMIN or password != MOT_DE_PASSE_ADMIN:
        return HTMLResponse(content="<h2>Identifiants incorrects !</h2>", status_code=403)
    client_ip = request.client.host
    exp_date = datetime.datetime.utcnow() + datetime.timedelta(days=duration)
    payload = {"client": client_name, "exp": int(exp_date.timestamp()), "type_offre": "Licence Admin Directe", "ip_security": client_ip}
    return await vue_panneau_admin_serveur(cle_generee=jwt.encode(payload, PHRASE_SECRETE_TIUN, algorithm="HS256"))

async def verifier_minuteur_cle_api(api_key: str = Security(api_key_header)):
    # Tolérance de secours pour permettre l'affichage visuel immédiat en local ou test anonyme
    if api_key in [None, "", "MANUAL_ADMIN_TOKEN"]:
        return {"client": "Utilisateur Démo", "type_offre": "Session d'Évaluation Graphique"}
    try:
        return jwt.decode(api_key, PHRASE_SECRETE_TIUN, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=402, detail="Abonnement Tiun expiré. Veuillez renouveler.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=403, detail="Accès refusé : Jeton invalide.")

@app.post("/api/v1/route/optimize")
async def optimiser_trajet_api(donnees: RequeteCalcul, jeton_valide: dict = Depends(verifier_minuteur_cle_api)):
    if not donnees.villes or len(donnees.villes) == 0:
        raise HTTPException(status_code=400, detail="La liste des points ne peut pas être vide.")
        
    # Enclenchement du minuteur de performance pour Render
    temps_debut = time.time()
    
    # Exécution de l'algorithme spatial
    route_ordonnee, distance_totale = calculer_route_precision(donnees.villes)
    
    # Arrêt du minuteur de performance
    temps_fin = time.time()
    duree_calcul = temps_fin - temps_debut
    
    return {
        "statut": "success",
        "client_autorise": jeton_valide.get("client"),
        "formule_tiun": jeton_valide.get("type_offre"),
        "metriques": {
            "villes_traitees": len(donnees.villes),
            "distance_matrice_km": round(distance_totale, 2),
            "temps_execution_secondes": round(duree_calcul, 4)
        },
        "ordonnancement_indices": route_ordonnee
    }

NB_FOURMIS = 15
ALPHA, BETA, EVAPORATION, Q = 1.0, 2.0, 0.3, 100.0
CAPACITE_MAX_VEHICULE = 10

def calculer_route_precision(villes: List[Tuple[float, float]]) -> Tuple[List[int], float]:
    nb_villes = len(villes)
    if nb_villes < 3: return list(range(nb_villes)), 0.0
    
    # Protection stricte contre l'Erreur 500 : extraction sécurisée de l'index 1 (Latitude)
    lat_moyenne = math.radians(sum(float(v[1]) for v in villes) / nb_villes)
    R = 6371.0
    
    villes_planes = []
    for v in villes:
        lon = math.radians(float(v[0]))  # Index 0 = Axe X / Longitude
        lat = math.radians(float(v[1]))  # Index 1 = Axe Y / Latitude
        x = R * lon * math.cos(lat_moyenne)
        y = R * lat
        villes_planes.append((x, y))
        
    distances = []
    for i in range(nb_villes):
        ligne = []
        for j in range(nb_villes):
            if i == j:
                ligne.append(0.0)
            else:
                dx = villes_planes[i][0] - villes_planes[j][0]
                dy = villes_planes[i][1] - villes_planes[j][1]
                distance_pure = math.sqrt(dx*dx + dy*dy)
                ligne.append(distance_pure * 1.23)
        distances.append(ligne)
        
    pheromones = [[1.0 for _ in range(nb_villes)] for _ in range(nb_villes)]
    meilleure_distance = float('inf')
    meilleure_route = []
    iterations = 20 if nb_villes > 60 else 40
    
    for _ in range(iterations):
        toutes_routes, toutes_distances = [], []
        for _ in range(NB_FOURMIS):
            r, d = simuler_fourmi_vrp(nb_villes, distances, pheromones)
            toutes_routes.append(r); toutes_distances.append(d)
            if d < meilleure_distance:
                meilleure_distance = d
                meilleure_route = r
        for i in range(nb_villes):
            for j in range(nb_villes): pheromones[i][j] *= (1.0 - EVAPORATION)
        for route, dist in zip(toutes_routes, toutes_distances):
            depot = Q / max(dist, 0.01)
            for k in range(len(route) - 1):
                pheromones[route[k]][route[k+1]] += depot
    return meilleure_route, meilleure_distance

def simuler_fourmi_vrp(nb, dists, phero):
    depot_index = 0
    path = [depot_index]
    villes_visitees = set([depot_index])
    charge_actuelle = 0
    d_tot = 0.0
    
    while len(villes_visitees) < nb:
        act = path[-1]
        if charge_actuelle >= CAPACITE_MAX_VEHICULE:
            d_tot += dists[act][depot_index]
            path.append(depot_index)
            act = depot_index
            charge_actuelle = 0
            
        probs = []
        tot = 0.0
        for p in range(nb):
            if p not in villes_visitees:
                vis = 1.0 / max(dists[act][p], 0.01)
                note = (phero[act][p] ** ALPHA) * (vis ** BETA)
                probs.append((p, note))
                tot += note
                
        if tot == 0:
            restants = [x for x in range(nb) if x not in villes_visitees]
            prox = restants[0] if restants else depot_index
        else:
            flotte = random.uniform(0, tot)
            cum = 0.0
            prox = probs[-1][0]
            for v, p in probs:
                cum += p
                if cum >= flotte:
                    prox = v
                    break
                    
        d_tot += dists[act][prox]
        path.append(prox)
        villes_visitees.add(prox)
        charge_actuelle += 1
        
    d_tot += dists[path[-1]][depot_index]
    path.append(depot_index)
    return path, d_tot
