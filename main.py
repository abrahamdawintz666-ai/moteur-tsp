from fastapi import FastAPI, HTTPException, Security, Depends, Request, Form
from fastapi.security.api_key import APIKeyHeader
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
import jwt
import random
import math
import datetime
import time
import os
from typing import List, Tuple
PHRASE_SECRETE_NORD = os.getenv("JWT_SECRET_KEY", "CAP_HAITIEN_CLE_SECRETE_4_FORCES_2026")
API_KEY_NAME = "X-API-KEY"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

app = FastAPI(
    title="SwiftRoute Engine - AntStrike Advanced VRP",
    swagger_ui_parameters={"operationsSorter": "alpha"},
    security=[{API_KEY_NAME: []}]
)
NOM_UTILISATEUR_ADMIN = os.getenv("ADMIN_USERNAME", "Abraham")
MOT_DE_PASSE_ADMIN = os.getenv("ADMIN_PASSWORD", "AntStrike_Cap2026!")
VOTRE_WALLET_SOLANA = os.getenv("SOLANA_WALLET", "22BzBEYLewJkKe2FXD6EHJYqX4NNshMw9roNw9qFxV9d")

IPS_ESSAIS_UTILISES = set()
# CONFIGURATION DU COMPTE MARCHAND
TIUN_SNIPPET_ID = "JQD27X4Dhj8JGdXQhnbBYz1K2HS5gjiojVwYIAKR"
TIUN_API_KEY = "jnWv2dG6ZYaCY_YBIwvvcFEWHFQlER_JdbNlANtQm3IUPOSKuv3sfztSB0-U3ugZh6q57MeGE6RsPu79"
def obtenir_page_accueil():
    return f"""
    <html>
        <head>
            <title>SwiftRoute Engine</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <script type="module">
                import {{ tiun }} from 'https://esm.sh';
                tiun.init({{
                    snippetId: '{TIUN_SNIPPET_ID}',
                    language: 'fr'
                }});
            </script>
            <style>
                * {{ box-sizing: border-box; }}
                body {{ font-family: sans-serif; background-color: #0c0a09; color: #f5f5f4; margin: 0; padding: 0; }}
                .navbar {{ display: flex; align-items: center; justify-content: space-between; padding: 22px 20px; }}
                .navbar-brand {{ font-weight: 800; font-size: 20px; }}
                .navbar-links {{ display: flex; gap: 28px; }}
                .navbar-links a {{ color: #a8a29e; text-decoration: none; font-size: 14px; }}
                .hero {{ text-align: center; padding: 70px 20px; background: #1c1917; }}
                .logo-brand {{ font-size: 44px; font-weight: 800; margin: 12px 0; color: #f59e0b; }}
                .btn-primary {{ background: #f59e0b; color: #0c0a09; font-weight: bold; padding: 14px 28px; text-decoration: none; border-radius: 8px; }}
                .demo-box {{ background: #1c1917; padding: 32px; margin-top: 20px; }}
                .timer-circle {{ width: 84px; height: 84px; border-radius: 50%; border: 4px solid #2e2a24; display: flex; align-items: center; justify-content: center; font-weight: 800; color: #f59e0b; }}
                #demo-map {{ width: 100%; height: 320px; background: #0c0a09; }}
            </style>
        </head>
        <body>
            <div class="navbar">
                <div class="navbar-brand">🐜 SwiftRoute Engine</div>
                <div class="navbar-links"><a href="/dashboard">Espace Client</a></div>
            </div>
            <div class="hero">
                <h1 class="logo-brand">SWIFTROUTE ENGINE v2.5</h1>
                <a href="/dashboard" class="btn-primary">Obtenir une clé API</a>
            </div>
            <div class="demo-box">
                <div class="timer-circle" id="timer-circle">0.0s</div>
                <canvas id="demo-map" width="600" height="320"></canvas>
            </div>
            <script>
                const c = document.getElementById('demo-map');
                if(c) {{ const ctx = c.getContext('2d'); ctx.fillStyle = '#0c0a09'; ctx.fillRect(0, 0, 600, 320); }}
            </script>
        </body>
    </html>
    """
def obtenir_panneau_admin(wallet: str, cle_generee: str):
    return f"""
    <html>
        <head>
            <title>AntStrike Admin Panel</title>
            <style>
                body {{ font-family: Arial, sans-serif; background-color: #09090b; color: #fff; text-align: center; padding: 20px; }}
                .box-admin {{ max-width: 500px; margin: auto; background: #18181b; padding: 25px; border-radius: 10px; border: 1px solid #3f3f46; text-align: left; }}
                h2 {{ color: #a855f7; margin-top: 0; }}
                label {{ font-size: 13px; color: #a1a1aa; display: block; margin-top: 10px; }}
                input, select {{ width: 100%; padding: 10px; margin-top: 5px; background: #09090b; border: 1px solid #3f3f46; color: #fff; border-radius: 6px; box-sizing: border-box; }}
                .btn-gen {{ background: #a855f7; color: white; font-weight: bold; border: none; padding: 12px; margin-top: 15px; width: 100%; border-radius: 6px; cursor: pointer; }}
                .result-box {{ background: #27272a; padding: 15px; margin-top: 20px; border-radius: 6px; border: 1px dashed #a855f7; word-break: break-all; font-family: monospace; font-size: 12px; color: #e4e4e7; }}
            </style>
        </head>
        <body>
            <div class="box-admin">
                <h2>🎛️ Panneau Privé d'Administration</h2>
                <p style='font-size:12px; color:#888;'>Solana Vault Actif: {wallet}</p>
                <form action="/admin-panel/generer" method="post">
                    <label>Identifiant Administrateur :</label><input type="text" name="username" required>
                    <label>Mot de passe Secret :</label><input type="password" name="password" required>
                    <label>Nom de l'entreprise cliente :</label><input type="text" name="client_name" required>
                    <label>Formule :</label>
                    <select name="duration">
                        <option value="7">Essai Gratuit (7 Jours)</option>
                        <option value="30">Abonnement Entreprise (1 Mois — 1500 $)</option>
                    </select>
                    <button type="submit" class="btn-gen">⚡ Générer et Activer la Clé API</button>
                </form>
                {"<div class='result-box'><strong>Clé Générée :</strong><br><br>" + cle_generee + "</div>" if cle_generee else ""}
            </div>
        </body>
    </html>
    """
def obtenir_tableau_bord(token_visuel: str = ""):
    acces_cle_existante = """
    <div class="existing-key-box">
        <h3>🔑 Clé API existante ?</h3>
        <form onsubmit="return accederAvecCle(event)">
            <input type="text" id="cle-existante" placeholder="X-API-Key" required>
            <button type="submit" class="btn-existing-key">Accéder à mon espace →</button>
        </form>
    </div>
    """
    formulaire_paiement = f"""
    <div class="crypto-payment-box">
        <h3 style="color:#f59e0b;">💳 Activation via Blockchain</h3>
        <div class="wallet-address">{VOTRE_WALLET_SOLANA}</div>
        <form action="https://wa.me" target="_blank" method="get">
            <input type="hidden" name="text" value="Bonjour Abraham, paiement effectué pour SwiftRoute.">
            <input type="text" placeholder="Nom entreprise" required>
            <input type="text" placeholder="Hash de transaction" required>
            <button type="submit" class="btn-submit-tx">⚡ Envoyer la notification d'activation</button>
        </form>
    </div>
    """
    banniere_cle_active = f"""
    <div class="payment-banner" style="border: 1px solid #22c55e; padding:20px; border-radius:8px;">
        <h3 style="color:#22c55e;">✓ Clé active</h3>
        <div class="token-display">{token_visuel}</div>
        <a href="/docs" style="color:#22c55e;">Aller à la documentation API →</a>
    </div>
    """
    contenu_dynamique = banniere_cle_active if token_visuel else (acces_cle_existante + formulaire_paiement)
    return f"""
    <html>
        <head>
            <title>Espace Client</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <script type="module">
                import {{ tiun }} from 'https://esm.sh';
                tiun.init({{ snippetId: '{TIUN_SNIPPET_ID}', language: 'fr' }});
            </script>
            <style>
                body {{ font-family: sans-serif; background-color: #0c0a09; color: #f5f5f4; padding: 20px; }}
                .dashboard-box {{ max-width: 600px; margin: auto; background: #1c1917; border: 1px solid #2e2a24; padding: 20px; border-radius: 12px; }}
                .wallet-address {{ background: #0c0a09; padding: 12px; font-family: monospace; color: #f59e0b; word-break: break-all; }}
                input {{ width: 100%; padding: 10px; margin-top: 5px; background: #0c0a09; color: #fff; border: 1px solid #444; }}
                .btn-existing-key, .btn-submit-tx {{ background: #f59e0b; border: none; padding: 12px; width: 100%; font-weight: bold; cursor: pointer; margin-top: 10px; }}
                .token-display {{ background: #0c0a09; border: 1px dashed #22c55e; padding: 15px; color: #22c55e; word-break: break-all; }}
            </style>
        </head>
        <body>
            <div class="dashboard-box">
                <h2>📊 Console de Gestion Élite</h2>
                {contenu_dynamique}
            </div>
            <script>
                function accederAvecCle(e) {{
                    e.preventDefault();
                    const cle = document.getElementById('cle-existante').value.trim();
                    if (!cle) return false;
                    window.location.href = '/dashboard?token_visuel=' + encodeURIComponent(cle);
                    return false;
                }}
            </script>
        </body>
    </html>
    """
@app.get("/", response_class=HTMLResponse)
async def page_accueil_serveur():
    return HTMLResponse(content=obtenir_page_accueil())

@app.get("/dashboard", response_class=HTMLResponse)
async def tableau_de_bord_serveur(token_visuel: str = ""):
    return HTMLResponse(content=obtenir_tableau_bord(token_visuel))

@app.get("/admin-panel", response_class=HTMLResponse)
async def vue_panneau_admin_serveur(cle_generee: str = ""):
    return HTMLResponse(content=obtenir_panneau_admin(VOTRE_WALLET_SOLANA, cle_generee))
@app.post("/admin-panel/generer")
async def action_generer_cle_serveur(request: Request, username: str = Form(...), password: str = Form(...), client_name: str = Form(...), duration: int = Form(...)):
    if username != NOM_UTILISATEUR_ADMIN or password != MOT_DE_PASSE_ADMIN:
        return HTMLResponse(content="<h2>Accès refusé.</h2>", status_code=403)
    
    client_ip = request.client.host
    if duration == 7 and client_ip in IPS_ESSAIS_UTILISES:
        return HTMLResponse(content="<h2>Essai déjà consommé.</h2>", status_code=403)
        
    date_actuelle = datetime.datetime.utcnow()
    if duration == 7:
        exp_date = date_actuelle + datetime.timedelta(days=7)
        tier = "7 Jours Gratuit"
        IPS_ESSAIS_UTILISES.add(client_ip)
    else:
        exp_date = date_actuelle + datetime.timedelta(days=30)
        tier = "1 Mois Entreprise ($1500)"
        
    payload = {
        "client": client_name,
        "exp": int(exp_date.timestamp()),
        "type_offre": tier,
        "ip_security": client_ip
    }
    token_client = jwt.encode(payload, PHRASE_SECRETE_NORD, algorithm="HS256")
    return await vue_panneau_admin_serveur(cle_generee=token_client)
async def verifier_minuteur_cle_api(api_key: str = Security(api_key_header)):
    if not api_key:
        raise HTTPException(status_code=403, detail="API Key missing.")
    try:
        infos = jwt.decode(api_key, PHRASE_SECRETE_NORD, algorithms=["HS256"])
        return infos
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=402, detail="Key expired.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=403, detail="Invalid key.")
# ------------------------------------------------------------------------------
# LOGIQUE MOTEUR ACO (ANT COLONY OPTIMIZATION)
# ------------------------------------------------------------------------------
NB_FOURMIS = 15
ALPHA, BETA, EVAPORATION, Q = 1.0, 2.0, 0.3, 100.0
CAPACITE_MAX_VEHICULE = 10

class RequeteCalcul(BaseModel):
    villes: List[Tuple[float, float]]
def calculer_route_precision(villes: List[Tuple[float, float]]) -> Tuple[List[int], float]:
    nb_villes = len(villes)
    if nb_villes < 3: return list(range(nb_villes)), 0.0
    
    lat_moyenne = math.radians(sum(float(v[0]) for v in villes) / nb_villes)
    R = 6371.0
    
    villes_planes = []
    for v in villes:
        lat = math.radians(float(v[0]))
        lon = math.radians(float(v[1]))
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
