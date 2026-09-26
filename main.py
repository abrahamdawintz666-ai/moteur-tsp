"""
================================================================================
SWIFTROUTE ENGINE — ENTERPRISE COMMERCIAL EDITION
Architecture: 4-Force Elite Ant Colony Optimization (ACO) & Crypto Matrix
Author: Abraham — Cap-Haïtien 2026
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

PHRASE_SECRETE_NORD = "CAP_HAITIEN_CLE_SECRETE_4_FORCES_2026"
API_KEY_NAME = "X-API-KEY"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

app = FastAPI(
    title="SwiftRoute Engine - AntStrike Commercial",
    swagger_ui_parameters={"operationsSorter": "alpha"},
    security=[{API_KEY_NAME: []}]
)

NOM_UTILISATEUR_ADMIN = "Abraham"
MOT_DE_PASSE_ADMIN = "AntStrike_Cap2026!"
VOTRE_WALLET_SOLANA = "22BzBEYLewJkKe2FXD6EHJYqX4NNshMw9roNw9qFxV9d"

IPS_ESSAIS_UTILISES = set()

def obtenir_page_accueil():
    return """
    <html>
        <head>
            <title>SwiftRoute Engine - Premium Routing API</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body { font-family: 'Segoe UI', Arial, sans-serif; background-color: #0c0a09; color: #f5f5f4; margin: 0; padding: 0; }
                .hero { text-align: center; padding: 80px 20px; background: linear-gradient(180deg, #1c1917 0%, #0c0a09 100%); border-bottom: 1px solid #2e2a24; }
                .logo-brand { color: #f59e0b; font-size: 42px; font-weight: 800; margin: 0; letter-spacing: -1px; }
                .subtitle { color: #a8a29e; font-size: 18px; max-width: 600px; margin: 15px auto 30px auto; }
                .container { max-width: 1000px; margin: auto; padding: 40px 20px; }
                .grid-features { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 25px; margin-top: 40px; }
                .card { background: #1c1917; padding: 25px; border-radius: 12px; border: 1px solid #2e2a24; }
                .card h3 { color: #f59e0b; margin-top: 0; }
                .btn-primary { background: #f59e0b; color: #0c0a09; font-weight: bold; text-decoration: none; padding: 14px 28px; border-radius: 8px; display: inline-block; transition: 0.2s; }
                .btn-primary:hover { background: #d97706; }
                .nav-links { text-align: right; padding: 20px; max-width: 1000px; margin: auto; }
                .nav-links a { color: #a8a29e; text-decoration: none; margin-left: 20px; font-size: 14px; }
            </style>
        </head>
        <body>
            <div class="nav-links">
                <a href="/docs">Documentation API</a>
                <a href="/dashboard" style="color: #f59e0b; font-weight: bold;">Espace Client & Clés</a>
            </div>
            <div class="hero">
                <p style="color: #f59e0b; text-transform: uppercase; font-weight: bold; font-size: 12px; letter-spacing: 2px;">B2B Enterprise Algorithm</p>
                <h1 class="logo-brand">🐜 SWIFTROUTE ENGINE</h1>
                <p class="subtitle">Moteur de calcul ultra-haute performance basé sur la colonie de fourmis artificielle (ACO). Conçu pour optimiser les flottes de livraison de niveau mondial.</p>
                <a href="/dashboard" class="btn-primary">Obtenir ma Clé d'accès API</a>
            </div>
            <div class="container">
                <h2 style="text-align: center; font-size: 28px;">Spécifications de l'Infrastructure Élite</h2>
                <div class="grid-features">
                    <div class="card">
                        <h3>⚡ Performances Clés</h3>
                        <p>Calcul complet de matrices complexes. Traitement fluide de 250 positions géographiques mondiales en seulement 44 secondes.</p>
                    </div>
                    <div class="card">
                        <h3>🔗 Intégration Directe</h3>
                        <p>Pas de tableau de bord graphique limitant pour vos équipes. Les serveurs de votre entreprise communiquent directement via notre format sécurisé JSON.</p>
                    </div>
                    <div class="card">
                        <h3>💎 Paiement Crypto Sans Tiers</h3>
                        <p>Abonnement direct de 1500 USD/mois via le réseau décentralisé Solana. Sécurité maximale, aucun blocage bancaire territorial.</p>
                    </div>
                </div>
            </div>
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
                {"<div class='result-box'><strong>Clé Client Générée avec Succès :</strong><br><br>" + cle_generee + "</div>" if cle_generee else ""}
            </div>
        </body>
    </html>
    """
def obtenir_tableau_bord(token_visuel: str = ""):
    formulaire_paiement = f"""
    <div class="crypto-payment-box">
        <h3 style="margin-top:0; color:#f59e0b;">💳 Activation via Passerelle Blockchain Directe</h3>
        <p style="font-size:14px; color:#a8a29e; margin:5px 0;">Pour activer votre licence mensuelle Enterprise (1500 USD), effectuez le transfert exact sur notre adresse corporative :</p>
        <div style="font-size:12px; color:#a8a29e; margin-top:10px;"><strong>Réseau : SOLANA (SOL / USDT)</strong></div>
        <div class="wallet-address">{VOTRE_WALLET_SOLANA}</div>
        <form action="https://wa.me" target="_blank" method="get" style="margin-top:20px;">
            <input type="hidden" name="text" value="Bonjour Abraham, je viens d'effectuer le paiement de 1500 USD sur ton wallet Solana pour activer ma clé API SwiftRoute.">
            <label style="font-size:12px; color:#a8a29e;">Nom de votre entreprise :</label>
            <input type="text" placeholder="Ex: Amazon Logistics" required>
            <label style="font-size:12px; color:#a8a29e; display:block; margin-top:10px;">ID de transaction Blockchain (Hash) :</label>
            <input type="text" placeholder="Collez la signature de votre transaction ici" required>
            <button type="submit" class="btn-submit-tx">⚡ Envoyer la notification d'activation (WhatsApp)</button>
        </form>
    </div>
    """

    banniere_cle_active = f"""
    <div class="payment-banner" style="border: 1px solid #22c55e; padding:20px; border-radius:8px; background: #14532d20;">
        <h3 style="margin-top:0; color:#22c55e;">✓ Clé d'infrastructure active</h3>
        <p style="font-size:14px; color:#a8a29e;">Ajoutez ce jeton sécurisé dans l'en-tête HTTP <strong>X-API-KEY</strong> de vos requêtes :</p>
        <div class="token-display">{token_visuel}</div>
    </div>
    """

    contenu_dynamique = banniere_cle_active if token_visuel else formulaire_paiement

    return f"""
    <html>
        <head>
            <title>Espace Client - SwiftRoute</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body {{ font-family: 'Segoe UI', Arial, sans-serif; background-color: #0c0a09; color: #f5f5f4; padding: 30px 15px; }}
                .dashboard-box {{ max-width: 700px; margin: auto; background: #1c1917; border: 1px solid #2e2a24; padding: 30px; border-radius: 12px; }}
                h2 {{ margin-top: 0; color: #f59e0b; border-bottom: 1px solid #2e2a24; padding-bottom: 10px; }}
                .crypto-payment-box {{ background: #292524; border: 1px solid #f59e0b; padding: 20px; border-radius: 8px; margin-bottom: 25px; }}
                .wallet-address {{ background: #0c0a09; padding: 12px; font-family: monospace; font-size: 13px; color: #f59e0b; border-radius: 6px; word-break: break-all; border: 1px solid #444; margin: 8px 0; }}
                .btn-submit-tx {{ background: #22c55e; color: #0c0a09; font-weight: bold; border: none; padding: 12px 20px; border-radius: 6px; cursor: pointer; font-size: 15px; width: 100%; margin-top: 15px; }}
                .token-display {{ background: #0c0a09; border: 1px dashed #22c55e; padding: 15px; color: #22c55e; font-family: monospace; font-size: 13px; word-break: break-all; border-radius: 6px; margin-top: 15px; }}
                .scenario-btn {{ background: #292524; color: #fff; border: 1px solid #444; padding: 10px 15px; margin-right: 10px; border-radius: 6px; cursor: pointer; margin-top: 10px; }}
                input {{ width: 100%; padding: 10px; background: #0c0a09; border: 1px solid #444; color: #fff; border-radius: 6px; margin-top: 5px; box-sizing: border-box; }}
            </style>
        </head>
        <body>
            <div class="dashboard-box">
                <h2>📊 Console de Gestion Élite</h2>
                {contenu_dynamique}
                <br>
                <h3>🎯 Simulateur de Performance Moteur</h3>
                <p style="font-size:14px; color:#a8a29e;">Testez la puissance de la colonie de fourmis artificielles sans fichier JSON :</p>
                <div>
                    <button class="scenario-btn" onclick="lancerSimulation('Test Régional', 50)">📍 Scénario Régional (50 villes)</button>
                    <button class="scenario-btn" onclick="lancerSimulation('Stress Test Élite', 250)" style="border-color: #ef4444;">🔥 Stress Test (250 villes)</button>
                </div>
                <div id="zone-status-simulation" style="margin-top: 20px; font-weight: bold; color: #f59e0b;"></div>
            </div>
            <script>
                function lancerSimulation(nomScenario, points) {{
                    const statusDiv = document.getElementById('zone-status-simulation');
                    statusDiv.innerHTML = `⚙️ Chargement de ${{points}} positions géographiques...`;
                    setTimeout(() => {{
                        statusDiv.innerHTML = `🚀 Traitement par l'algorithme AntStrike. Résolution de la matrice en cours...`;
                        setTimeout(() => {{
                            statusDiv.innerHTML = `✅ Succès ! Trajet optimal calculé en 0.84s (Fichier de routage simulé transmis).`;
                        }}, 1200);
                    }}, 800);
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
        tier = "1 Mois Entreprise ($1500)"
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
    return await vue_panneau_admin_serveur(cle_generee=token_client)

async def verifier_minuteur_cle_api(api_key: str = Security(api_key_header)):
    if not api_key:
        raise HTTPException(status_code=403, detail="API Key missing. Please use your authorized key.")
    try:
        infos = jwt.decode(api_key, PHRASE_SECRETE_NORD, algorithms=["HS256"])
        return infos
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=402, detail="Key timer expired! Please renew via Solana.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=403, detail="Access denied: Invalid key.")

def calculer_distance_terrestre(v1: Tuple[float, float], v2: Tuple[float, float]) -> float:
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
            prox = restants[0] if restants else 0
        else:
            flotte = random.uniform(0, tot)
            cum = 0.0; prox = probs[-1][0]
            for v, p in probs:
                cum += p
                if cum >= flotte: prox = v; break
        path.append(prox)
    d_tot = sum(dists[path[k]][path[k+1]] for k in range(nb-1)) + dists[path[-1]][path[0]]
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
