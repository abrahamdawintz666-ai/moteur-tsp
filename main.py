"""
================================================================================
SWIFTROUTE ENGINE — POWERED BY ANTSTRIKE LOGIC
Architecture: 4-Force Elite Ant Colony Optimization (ACO) & Constraint Pruning
Features: Secure Private Admin Dashboard, Automated Token Generator & Timers
Security: Anti-Cheat Free Trial IP Blocker & Inviolable JWT Matrix
================================================================================
"""

from fastapi import FastAPI, HTTPException, Security, Depends, Request, Form
from fastapi.security.api_key import APIKeyHeader
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import jwt
import random
import math
import datetime
import time
from typing import List, Tuple

PHRASE_SECRETE_NORD = "CAP_HAITIEN_CLE_SECRETE_4_FORCES_2026"
API_KEY_NAME = "X-API-KEY"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

app = FastAPI(
    title="SwiftRoute Engine - AntStrike Logic",
    swagger_ui_parameters={"operationsSorter": "alpha"}
)

NOM_UTILISATEUR_ADMIN = "Abraham"
MOT_DE_PASSE_ADMIN = "AntStrike_Cap2026!"
LIEN_PROFIL_MERU = "https://merupay.com"

VOTRE_NUMERO_WHATSAPP = "+50941817761"
VOTRE_GMAIL = "Abrahamdawintz410@gmail.com"
VOTRE_WALLET_SOLANA = "22BzBEYLewJkKe2FXD6EHJYqX4NNshMw9roNw9qFxV9d"

IPS_ESSAIS_UTILISES = set()

@app.get("/", response_class=HTMLResponse)
async def page_accueil_abonnements():
    html_content = f"""
    <html>
        <head>
            <title>AntStrike Logic - SwiftRoute Dashboard</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body {{ font-family: 'Segoe UI', Arial, sans-serif; background-color: #0b0b0b; color: #e0e0e0; text-align: center; padding: 20px; }}
                .container {{ max-width: 550px; margin: auto; background: #141414; padding: 30px; border-radius: 12px; box-shadow: 0 6px 20px rgba(0,0,0,0.7); border: 1px solid #222; }}
                h1 {{ color: #00FF00; margin-bottom: 5px; font-size: 28px; }}
                .subtitle {{ color: #888; font-size: 14px; margin-bottom: 25px; }}
                .box {{ border: 2px solid #222; padding: 18px; margin: 12px 0; border-radius: 8px; cursor: pointer; background: #1c1c1c; transition: 0.3s; text-align: left; display: flex; align-items: center; }}
                .box:hover {{ border-color: #00FF00; background: #222; }}
                .box-text {{ margin-left: 15px; flex-grow: 1; }}
                .price {{ float: right; font-weight: bold; color: #00FF00; font-size: 18px; }}
                .btn {{ background-color: #00FF00; color: black; font-weight: bold; padding: 14px 20px; border: none; border-radius: 6px; cursor: pointer; width: 100%; font-size: 16px; margin-top: 15px; text-decoration: none; display: inline-block; box-sizing: border-box; }}
                .btn-meru {{ background-color: #00E5FF; color: black; }}
                .crypto-box {{ background: #1a1a1a; padding: 15px; border-radius: 6px; margin-top: 15px; border: 1px dashed #9945FF; text-align: left; }}
                .wallet-address {{ font-family: monospace; background: #222; padding: 8px; border-radius: 4px; color: #ff00ff; word-break: break-all; font-size: 12px; margin-top: 5px; border: 1px solid #333; display: block; font-weight: bold; text-align: center; }}
                .contact-list {{ text-align: left; background: #1a1a1a; padding: 15px; border-radius: 6px; margin-top: 15px; border: 1px solid #333; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>AntStrike Logic 🚀</h1>
                <div class="subtitle">Industrial Route Optimization API & High-Precision Infrastructure</div>
                <hr style="border-color:#222;">
                <h3 style="text-align: left; color: #fff; margin-top: 20px;">Choisissez votre formule d'accès :</h3>
                <div class="box" onclick="document.getElementById('zone_paiement').style.display='block';">
                    <div class="box-text"><strong>Standard Subscription Fleet Pack</strong><br><span style="color:#666; font-size:12px;">Accès professionnel illimité</span></div>
                    <div class="price">300 $ USD</div>
                </div>
                <div id="zone_paiement" style="display:none; margin-top:25px; padding:20px; border:2px dashed #00FF00; background: #111; border-radius: 8px;">
                    <p style="font-size: 13px; color: #aaa; text-align: left; font-weight: bold;">Option A : Carte Bancaire</p>
                    <a href="{LIEN_PROFIL_MERU}" target="_blank" class="btn btn-meru">💳 Profil de paiement MERU</a>
                    <div class="crypto-box">
                        <p style="font-weight: bold; color: #9945FF; font-size: 14px;">Option B : Règlement Crypto (Solana Network)</p>
                        <span class="wallet-address">{VOTRE_WALLET_SOLANA}</span>
                    </div>
                    <ul class="contact-list">
                        <li>🟢 WhatsApp Business : {VOTRE_NUMERO_WHATSAPP}</li>
                        <li>📧 Email Principal : {VOTRE_GMAIL}</li>
                    </ul>
                </div>
                <hr style="border-color:#222; margin-top:25px;">
                <a href="/docs" class="btn" style="background:#1976D2; color:white;">⚙️ Ouvrir la console technique (API)</a>
            </div>
        </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.get("/admin-panel", response_class=HTMLResponse)
async def vue_panneau_admin(cle_generee: str = ""):
    html_admin = f"""
    <html>
        <head>
            <title>AntStrike Admin Panel</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
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
                <h2>🎛️ Panneau Générateur — Abraham</h2>
                <form action="/admin-panel/generer" method="post">
                    <label>Identifiant Administrateur :</label>
                    <input type="text" name="username" required>
                    <label>Mot de passe Secret :</label>
                    <input type="password" name="password" required>
                    <label>Nom de l'entreprise cliente :</label>
                    <input type="text" name="client_name" required>
                    <label>Formule d'abonnement :</label>
                    <select name="duration">
                        <option value="7">Essai Gratuit (7 Jours)</option>
                        <option value="30">Abonnement Standard (1 Mois)</option>
                        <option value="365">Licence Corporate (1 An)</option>
                    </select>
                    <button type="submit" class="btn-gen">⚡ Générer la Clé API Secrète</button>
                </form>
                {"<div class='result-box'><strong>Clé Client Générée avec Succès (Copie-la) :</strong><br><br>" + cle_generee + "</div>" if cle_generee else ""}
            </div>
        </body>
    </html>
    """
    return HTMLResponse(content=html_admin)

@app.post("/admin-panel/generer")
async def action_generer_cle(request: Request, username: str = Form(...), password: str = Form(...), client_name: str = Form(...), duration: int = Form(...)):
    if username != NOM_UTILISATEUR_ADMIN or password != MOT_DE_PASSE_ADMIN:
        return HTMLResponse(content="<h2>Identifiants incorrects ! Accès refusé.</h2>", status_code=403)
    
    client_ip = request.client.host
    if duration == 7 and client_ip in IPS_ESSAIS_UTILISES:
        return HTMLResponse(content="<h2>Sécurité : Ce réseau Internet a déjà consommé son essai gratuit de 7 jours.</h2>", status_code=403)
        
    date_actuelle = datetime.datetime.utcnow()
    if duration == 7:
        exp_date = date_actuelle + datetime.timedelta(days=7)
        tier = "7 Jours Gratuit"
        IPS_ESSAIS_UTILISES.add(client_ip)
    elif duration == 30:
        exp_date = date_actuelle + datetime.timedelta(days=30)
        tier = "1 Mois Standard"
    else:
        exp_date = date_actuelle + datetime.timedelta(days=365)
        tier = "1 An Corporate"
        
    payload = {
        "client": client_name,
        "exp": int(exp_date.timestamp()),
        "type_offre": tier,
        "ip_security": client_ip
    }
    token_client = jwt.encode(payload, PHRASE_SECRETE_NORD, algorithm="HS256")
    return await vue_panneau_admin(cle_generee=token_client)
async def verifier_minuteur_cle_api(api_key: str = Security(api_key_header)):
    if not api_key:
        raise HTTPException(status_code=403, detail="API Key missing. Please use your authorized key.")
    try:
        infos = jwt.decode(api_key, PHRASE_SECRETE_NORD, algorithms=["HS256"])
        return infos
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=402, detail="Key timer expired! Please renew via Meru or Solana.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=403, detail="Access denied: Invalid key.")

# FORMULE CORRIGÉE DE HAVERSINE (Extraction parfaite de [0] et)
def calculer_distance_terrestre(v1, v2):
    lat1 = math.radians(float(v1[0]))
    lon1 = math.radians(float(v1[1]))
    lat2 = math.radians(float(v2[0]))
    lon2 = math.radians(float(v2[1]))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return 6371.0 * c 

NB_FOURMIS = 15
ALPHA, BETA, EVAPORATION, Q = 1.0, 2.0, 0.3, 100.0

class RequeteCalcul(BaseModel):
    villes: List[Tuple[float, float]]

def calculer_route_precision(villes: List[Tuple[float, float]]) -> Tuple[List[int], float]:
    nb_villes = len(villes)
    if nb_villes < 3: return list(range(nb_villes)), 0.0
    
    villes_propres = [(float(v[0]), float(v[1])) for v in villes]
    distances = [[calculer_distance_terrestre(villes_propres[i], villes_propres[j]) for j in range(nb_villes)] for i in range(nb_villes)]
    pheromones = [[1.0 for _ in range(nb_villes)] for _ in range(nb_villes)]
    meilleure_distance = float('inf')
    meilleure_route = []
    
    iterations = 10 if nb_villes > 60 else 25
    
    for _ in range(iterations):
        toutes_routes, toutes_distances = [], []
        for _ in range(NB_FOURMIS):
            r, d = simuler_fourmi(nb_villes, distances, pheromones)
            toutes_routes.append(r); toutes_distances.append(d)
            if d < meilleure_distance:
                meilleure_distance = d
                meilleure_route = r
        for i in range(nb_villes):
            for j in range(nb_villes): pheromones[i][j] *= (1.0 - EVAPORATION)
        for route, dist in zip(toutes_routes, toutes_distances):
            depot = Q / max(dist, 0.01)
            for k in range(nb_villes):
                pheromones[route[k]][route[(k+1)%nb_villes]] += depot
    return meilleure_route, meilleure_distance

def simuler_fourmi(nb, dists, phero):
    path = [random.randint(0, nb-1)]
    while len(path) < nb:
        act = path[-1]; probs = []; tot = 0.0
        for p in range(nb):
            if p not in path:
                vis = 1.0 / max(dists[act][p], 0.01)
                note = (phero[act][p] ** ALPHA) * (vis ** BETA)
                probs.append((p, note)); tot += note
        if tot == 0:
            restants = [x for x in range(nb) if x not in path]
            prox = restants if restants else 0
        else:
            flotte = random.uniform(0, tot)
            cum = 0.0; prox = probs[-1]
            for v, p in probs:
                cum += p
                if cum >= flotte: prox = v; break
        path.append(prox)
    d_tot = sum(dists[path[k]][path[k+1]] for k in range(nb-1)) + dists[path[-1]][path]
    return path, d_tot

@app.post("/optimiser-tournee/")
async def optimiser_tournee(requete: RequeteCalcul, infos_cle: dict = Depends(verifier_minuteur_cle_api)):
    temps_debut = time.time()
    ordre_villes, distance_optimale = calculer_route_precision(requete.villes)
    temps_fin = time.time()
    temps_execution = temps_fin - temps_debut
    
    return {
        "status": "Success",
        "authenticated_client": infos_cle["client"],
        "subscription_tier": infos_cle["type_offre"],
        "execution_time_seconds": round(temps_execution, 4),
        "total_distance_km": round(distance_optimale, 2),
        "optimal_order": ordre_villes
    }
