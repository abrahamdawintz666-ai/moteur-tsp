from fastapi import FastAPI, HTTPException, Security, Depends
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel
import jwt
import random
import math
import datetime
from typing import List, Tuple

app = FastAPI(title="Moteur d'Optimisation Automatique - Minuteur Intégré")

# La même phrase secrète que dans ton générateur
PHRASE_SECRETE_NORD = "CAP_HAITIEN_CLE_SECRETE_4_FORCES_2026"

API_KEY_NAME = "X-API-KEY"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

async def verifier_minuteur_cle_api(api_key: str = Depends(api_key_header)):
    if not api_key:
        raise HTTPException(status_code=403, detail="Accès refusé : Clé absente.")
    
    try:
        # Le serveur décrypte la clé et vérifie AUTOMATIQUEMENT le minuteur ('exp')
        # Si le temps est dépassé, la bibliothèque lève une erreur 'ExpiredSignatureError'
        informations_minuteur = jwt.decode(api_key, PHRASE_SECRETE_NORD, algorithms=["HS256"])
        return informations_minuteur
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=402, 
            detail="Le minuteur de votre clé a expiré ! Votre abonnement (semaine/mois) est terminé. Rechargez sur Meru."
        )
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=403, detail="Accès refusé : Cette clé a été falsifiée ou est invalide.")

# --- LES 4 FORCES DE CALCUL DE PRÉCISION ---
NB_FOURMIS = 30
ALPHA = 1.0
BETA = 3.0
EVAPORATION = 0.1
Q = 100.0

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
                for k in range(nb_villes):
                    v1, v2 = route[k], route[(k+1)%nb_villes]
                    pheromones[v1][v2] *= 0.2; pheromones[v2][v1] *= 0.2
        for _ in range(int(NB_FOURMIS / 2)):
            r, d = simuler_fourmi(nb_villes, distances, pheromones, det=0.8)
            toutes_routes.append(r); toutes_distances.append(d)
        for i in range(nb_villes):
            for j in range(nb_villes): pheromones[i][j] *= (1.0 - EVAPORATION)
        for route, dist in zip(toutes_routes, toutes_distances):
            depot = Q / max(dist, 0.1)
            for k in range(nb_villes):
                pheromones[route[k]][route[(k+1)%nb_villes]] += depot
                if dist < meilleure_distance:
                    meilleure_distance = dist; meilleure_route = route
        if meilleure_route:
            for k in range(nb_villes):
                pheromones[meilleure_route[k]][meilleure_route[(k+1)%nb_villes]] += 50.0

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
    
    # En plus du calcul, le serveur confirme l'identité décryptée
    return {
        "statut": "Succès",
        "client_authentifie": infos_cle["client"],
        "formule_souscrite": infos_cle["type_offre"],
        "message": "Miniteur valide. Calcul de précision effectué.",
        "ordre_optimal": ordre_villes
    }
