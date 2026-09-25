"""
================================================================================
SWIFTROUTE ENGINE — POWERED BY ANTSTRIKE LOGIC
Architecture: 4-Force Elite Ant Colony Optimization (ACO) & Constraint Pruning
Features: Secure Private Admin Dashboard, Automated Token Generator & Timers
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
from typing import List, Tuple

app = FastAPI(title="SwiftRoute Engine - AntStrike Logic")

PHRASE_SECRETE_NORD = "CAP_HAITIEN_CLE_SECRETE_4_FORCES_2026"

# --- VOS ACCÈS ADMINISTRATEUR ULTRA-SÉCURISÉS ---
NOM_UTILISATEUR_ADMIN = "Abraham"
MOT_DE_PASSE_ADMIN = "AntStrike_Cap2026!"

LIEN_PROFIL_MERU = "https://merupay.com"

# --- COORDONNÉES OFFICIELLES DU SERVICE CLIENT ET PAIEMENTS ---
VOTRE_NUMERO_WHATSAPP = "+50941817761"
VOTRE_GMAIL = "Abrahamdawintz410@gmail.com"
VOTRE_ICLOUD = "Abrahamdawintz410@gmail.com"
VOTRE_WALLET_SOLANA = "22BzBEYLewJkKe2FXD6EHJYqX4NNshMw9roNw9qFxV9d"

IPS_ESSAIS_UTILISES = set()

API_KEY_NAME = "X-API-KEY"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

# --- 1. INTERFACE CLIENT (PAGE D'ACCUEIL VIRTUELE) ---
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
                input[type="radio"] {{ transform: scale(1.4); cursor: pointer; }}
                .btn {{ background-color: #00FF00; color: black; font-weight: bold; padding: 14px 20px; border: none; border-radius: 6px; cursor: pointer; width: 100%; font-size: 16px; margin-top: 15px; text-decoration: none; display: inline-block; box-sizing: border-box; }}
                .btn-meru {{ background-color: #00E5FF; color: black; }}
                .crypto-box {{ background: #1a1a1a; padding: 15px; border-radius: 6px; margin-top: 15px; border: 2px dashed #9945FF; text-align: left; }}
                .crypto-box p {{ margin: 5px 0; font-size: 13px; color: #bbb; }}
                .wallet-address {{ font-family: monospace; background: #222; padding: 8px; border-radius: 4px; color: #ff00ff; word-break: break-all; font-size: 12px; margin-top: 5px; border: 1px solid #333; display: block; font-weight: bold; text-align: center; }}
                .contact-list {{ text-align: left; background: #1a1a1a; padding: 15px; border-radius: 6px; margin-top: 15px; border: 1px solid #333; }}
                .contact-list li {{ margin: 8px 0; font-size: 14px; color: #ccc; list-style: none; }}
                .contact-list strong {{ color: #00FF00; }}
            </style>
            <script>
                function gererSelection(nom, detail) {{
                    document.getElementById('zone_paiement').style.display = 'block';
                    document.getElementById('txt_choix').innerText = "Formule sélectionnée : " + nom + " (" + detail + ")";
                }}
            </script>
        </head>
        <body>
            <div class="container">
                <h1>AntStrike Logic 🚀</h1>
                <div class="subtitle">Industrial Route Optimization API & High-Precision Infrastructure</div>
                <hr style="border-color:#222;">
                <h3 style="text-align: left; color: #fff; margin-top: 20px;">Choisissez votre formule d'accès :</h3>
                <div class="box" onclick="document.getElementById('form_test').checked = true; gererSelection('Essai Hebdomadaire', 'Gratuit');">
                    <input type="radio" id="form_test" name="offre" value="7">
                    <div class="box-text">
                        <strong>7 Days Free Trial</strong><br><span style="color:#666; font-size:12px;">Évaluation technique unique pour flottes (Limite de 1 par entreprise)</span>
                    </div>
                    <div class="price">GRATUIT</div>
                </div>
                <div class="box" onclick="document.getElementById('form_month').checked = true; gererSelection('1 Mois Premium', '300 USD');">
                    <input type="radio" id="form_month" name="offre" value="30">
                    <div class="box-text">
                        <strong>1-Month Standard Subscription</strong><br><span style="color:#666; font-size:12px;">Accès professionnel illimité</span>
                    </div>
                    <div class="price">300 $ USD</div>
                </div>
                <div class="box" onclick="document.getElementById('form_year').checked = true; gererSelection('1 An Corporate', '3600 USD');">
                    <input type="radio" id="form_year" name="offre" value="365">
                    <div class="box-text">
                        <strong>1-Year Corporate License</strong><br><span style="color:#666; font-size:12px;">12 mois complets d'optimisation industrielle</span>
                    </div>
                    <div class="price">3600 $ USD</div>
                </div>
                <div id="zone_paiement" style="display:none; margin-top:25px; padding:20px; border:2px dashed #00FF00; background: #111; border-radius: 8px;">
                    <p id="txt_choix" style="font-weight:bold; color:#00FF00; margin-top:0;"></p>
                    
                    <p style="font-size: 13px; color: #aaa; text-align: left; font-weight: bold;">Option A : Règlement traditionnel (Carte Bancaire)</p>
                    <p style="font-size: 13px; color: #aaa; text-align: left; margin-bottom: 10px;">Cliquez sur le lien ci-dessous, effectuez votre virement sécurisé et saisissez manuellement le montant de la formule :</p>
                    <a href="{LIEN_PROFIL_MERU}" target="_blank" class="btn btn-meru">💳 Ouvrir mon profil de paiement MERU</a>
                    
                    <div class="crypto-box">
                        <p style="font-weight: bold; color: #9945FF; font-size: 14px;">Option B : Règlement Crypto Corporatif (USDC / USDT)</p>
                        <p>Idéal pour les entreprises internationales (Uber, DHL, Startups Tech). Transférez le montant exact sur notre portefeuille officiel de l'entreprise :</p>
                        <p><strong>Réseau :</strong> Solana (SOL / USDC / USDT)</p>
                        <span class="wallet-address">{VOTRE_WALLET_SOLANA}</span>
                    </div>
                    
                    <p style="margin-top:20px; font-size: 13px; color: #aaa; text-align: left; font-weight: bold;">2. Activation et support client :</p>
                    <p style="font-size: 13px; color: #aaa; text-align: left; margin-bottom: 5px;">Dès que votre transfert (Meru ou Crypto) est effectué, contactez notre direction technique pour recevoir votre clé d'accès sécurisée :</p>
                    <ul class="contact-list">
                        <li>🟢 <strong>WhatsApp Business :</strong> <a href="https://wa.me{VOTRE_NUMERO_WHATSAPP.replace('+', '')}" target="_blank" style="color: #00FF00; text-decoration: none;">{VOTRE_NUMERO_WHATSAPP}</a></li>
                        <li>📧 <strong>Email Principal :</strong> {VOTRE_GMAIL}</li>
                        <li>☁️ <strong>Support iCloud :</strong> {VOTRE_ICLOUD}</li>
                    </ul>
                </div>
                <hr style="border-color:#222; margin-top:25px;">
                <a href="/docs" class="btn" style="background:#1976D2; color:white;">⚙️ Ouvrir la console technique de calcul (API)</a>
            </div>
        </body>
    </html>
    """
    return HTMLResponse(content=html_content)

# --- 2. PANNEAU DE CONTRÔLE ADMINISTRATEUR SÉCURISÉ ---
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
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=402, detail="Key timer expired! Please renew your subscription via Meru.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=403, detail="Access denied: Invalid key.")

NB_FOURMIS = 30
ALPHA, BETA, EVAPORATION, Q = 1.0, 3.0, 0.1, 100.0

class RequeteCalcul(BaseModel):
    villes: List[Tuple[float, float]]

def calculer_route_precision(villes: List[Tuple[float, float]]) -> Tuple[List[int], float]:
    nb_villes = len(villes)
    if nb_villes < 3: return list(range(nb_villes)), 0.0
    distances = [[math.dist(villes[i], villes[j]) for j in range(nb_villes)] for i in range(nb_villes)]
    pheromones = [[1.0 for _ in range(nb_villes)] for _ in range(nb_villes)]
    meilleure_distance = float('inf')
    meilleure_route = []
    for _ in range(40):
        toutes_routes, toutes_distances = [], []
        for _ in range(int(NB_FOURMIS / 2)):
            r, d = simuler_fourmi(nb_villes, distances, pheromones, det=0.1)
            toutes_routes.append(r); toutes_distances.append(d)
        moyenne = sum(toutes_distances) / len(toutes_distances)
        for route, dist in zip(toutes_routes, toutes_distances):
            if dist > moyenne:
                for k in range(nb_villes): pheromones[route[k]][route[(k+1)%nb_villes]] *= 0.2
        for _ in range(int(NB_FOURMIS / 2)):
            r, d = simuler_fourmi(nb_villes, distances, pheromones, det=0.8)
            toutes_routes.append(r); toutes_distances.append(d)
        for i in range(nb_villes):
            for j in range(nb_villes): pheromones[i][j] *= (1.0 - EVAPORATION)
        for route, dist in zip(toutes_routes, toutes_distances):
            depot = Q / max(dist, 0.1)
            for k in range(nb_villes):
                pheromones[route[k]][route[(k+1)%nb_villes]] += depot
                if dist < meilleure_distance: meilleure_distance = dist; meilleure_route = route
        if meilleure_route:
            for k in range(nb_villes): pheromones[meilleure_route[k]][meilleure_route[(k+1)%nb_villes]] += 50.0
    return meilleure_route, meilleure_distance

def simuler_fourmi(nb, dists, phero, det):
    path = [random.randint(0, nb-1)]
    while len(path) < nb:
        act = path[-1]; probs = []; tot = 0.0; m_note, v_perf = -1, -1
        for p in range(nb):
            if p not in path:
                vis = 1.0 / max(dists[act][p], 0.1)
                note = (phero[act][p] ** ALPHA) * (vis ** BETA)
                probs.append((p, note)); tot += note
                if note > m_note: m_note = note; v_perf = p
        if random.random() < det and v_perf != -1: prox = v_perf
        else:
            flotte = random.uniform(0, tot) if tot > 0 else 0
            cum = 0.0; prox = probs[-1] if probs else 0
            for v, p in probs:
                cum += p
                if cum >= flotte: prox = v; break
        path.append(prox)
    d_tot = sum(dists[path[k]][path[k+1]] for k in range(nb-1)) + dists[path[-1]][path]
    return path, d_tot

@app.post("/optimiser-tournee/")
async def optimiser_tournee(requete: RequeteCalcul, infos_cle: dict = Depends(verifier_minuteur_cle_api)):
    ordre_villes, distance_optimale = calculer_route_precision(requete.villes)
    return {"status": "Success", "authenticated_client": infos_cle["client"], "subscription_tier": infos_cle["type_offre"], "optimal_order": ordre_villes}
