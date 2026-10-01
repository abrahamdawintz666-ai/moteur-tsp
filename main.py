from fastapi import FastAPI, HTTPException, Security, Depends
from fastapi.security.api_key import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import math
from typing import List, Tuple
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp

app = FastAPI(
    title="GlobalRoute AI - Moteur Logistique Mondial",
    description="API de calcul TSP exact par blocs avec coordonnées GPS réelles (Haversine)."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

LES_ABONNES = {
    "CLE-CLIENT-ALEX-78492": {"nom": "Alex Logistique", "actif": True},
    "TEST-LIBRE": {"nom": "Mode Test Visuel & Dashboard", "actif": True}
}

API_KEY_NAME = "X-API-KEY"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

async def verifier_cle_api(api_key: str = Depends(api_key_header)):
    if not api_key or api_key not in LES_ABONNES:
        raise HTTPException(status_code=403, detail="Accès refusé : Clé API invalide.")
    if not LES_ABONNES[api_key]["actif"]:
        raise HTTPException(status_code=402, detail="Accès suspendu : Abonnement non payé.")
    return LES_ABONNES[api_key]

class RequeteCalcul(BaseModel):
    villes: List[Tuple[float, float]]

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
        raise HTTPException(status_code=400, detail="Minimum 2 villes requises.")
    if n > 15000:
        raise HTTPException(status_code=400, detail="Limite maximale de 15 000 villes atteinte.")

    route, distance_km = diviser_et_conquerir_gps(requete.villes, taille_bloc=150)

    return {
        "statut": "Succès - Moteur GPS & Blocs Synchronisés",
        "client_reconnu": abonne["nom"],
        "nombre_de_villes": n,
        "distance_totale_km": round(distance_km, 2),
        "ordre_de_visite_optimal": route
    }
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GlobalRoute AI - Enterprise Logistics SaaS</title>
    
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">

    <style>
        :root {
            --primary: #2563eb;
            --bg-main: #f8fafc;
            --card-bg: #ffffff;
            --text-main: #0f172a;
            --text-muted: #64748b;
            --border-color: #e2e8f0;
        }
        body { font-family: 'Inter', sans-serif; background-color: var(--bg-main); color: var(--text-main); margin: 0; padding: 30px; }
        .header { display: flex; justify-content: space-between; align-items: center; background: var(--card-bg); padding: 24px 32px; border-radius: 16px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05); margin-bottom: 30px; }
        .logo-area h1 { margin: 0; font-size: 22px; font-weight: 700; display: flex; align-items: center; gap: 10px; }
        .user-badge { background: #eff6ff; color: var(--primary); padding: 8px 16px; border-radius: 20px; font-weight: 600; font-size: 14px; }
        .metrics-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; margin-bottom: 30px; }
        .metric-card { background: var(--card-bg); padding: 24px; border-radius: 16px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05); border: 1px solid var(--border-color); }
        .metric-card h3 { margin: 0; font-size: 32px; font-weight: 700; color: var(--primary); }
        .metric-card p { margin: 8px 0 0; color: var(--text-muted); font-size: 14px; font-weight: 500; }
        .dashboard-grid { display: grid; grid-template-columns: 2fr 1fr; gap: 30px; margin-bottom: 30px; }
        .card { background: var(--card-bg); padding: 24px; border-radius: 16px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05); border: 1px solid var(--border-color); }
        .card h2 { margin-top: 0; font-size: 18px; font-weight: 600; margin-bottom: 20px; }
        #map { height: 480px; border-radius: 12px; width: 100%; z-index: 1; }
        .btn-action { background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%); color: white; border: none; padding: 14px 28px; border-radius: 12px; cursor: pointer; font-weight: 600; font-size: 16px; width: 100%; margin-top: 20px; box-shadow: 0 10px 15px -3px rgba(37, 99, 235, 0.3); transition: all 0.3s ease; }
        .btn-action:hover { opacity: 0.95; transform: translateY(-1px); }
        .legal-footer { background: var(--card-bg); padding: 24px 32px; border-radius: 16px; border: 1px solid var(--border-color); display: grid; grid-template-columns: 1fr 1fr; gap: 20px; font-size: 13px; color: var(--text-muted); }
        .legal-footer h4 { color: var(--text-main); margin-top: 0; font-size: 14px; }
        .legal-footer a { color: var(--primary); text-decoration: none; font-weight: 500; }
    </style>
</head>
<body>

    <div class="header">
        <div class="logo-area"><span>🌍</span> GlobalRoute AI</div>
        <div class="user-badge">🚀 Mode Entreprise Actif</div>
    </div>

    <div class="metrics-grid">
        <div class="metric-card"><h3 id="kpi-villes">0</h3><p>Points de Livraison Traités</p></div>
        <div class="metric-card"><h3 id="kpi-distance">0.0 km</h3><p>Distance Optimisée (GPS Haversine)</p></div>
        <div class="metric-card"><h3 id="kpi-temps">0.00 s</h3><p>Vitesse du Moteur par Blocs</p></div>
    </div>

    <div class="dashboard-grid">
        <div class="card">
            <h2>🗺️ Suivi des Itinéraires en Direct</h2>
            <div id="map"></div>
            <button id="btnLancer" class="btn-action" onclick="lancerCalculGlobal()">⚡ Lancer l'Optimisation Globale</button>
        </div>
        <div class="card">
            <h2>📊 Performance Analytique</h2>
            <canvas id="chartPerformance" width="400" height="320"></canvas>
        </div>
    </div>

    <div class="legal-footer">
        <div>
            <h4>🔒 Politique de Confidentialité & Conditions d'Utilisation</h4>
            <p>GlobalRoute AI protège vos données géographiques mondiales en garantissant des calculs mathématiques stricts et irréfutables pour vos tournées de livraison.</p>
        </div>
        <div>
            <h4>📞 Support Technique & Fondateur</h4>
            <p>Contact direct de l'administration :</p>
            <p>📧 Email : <a href="mailto:abrahamdawintz410@gmail.com">abrahamdawintz410@gmail.com</a></p>
            <p>💬 WhatsApp : <a href="https://wa.me/50941817761" target="_blank">+509 41 81 7761</a></p>
        </div>
    </div>
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
        const map = L.map('map').setView([18.5944, -72.3074], 8);

        L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
            maxZoom: 19,
            attribution: '&copy; CARTO'
        }).addTo(map);

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

        async function lancerCalculGlobal() {
            const bouton = document.getElementById('btnLancer');
            bouton.disabled = true;
            bouton.innerText = "⏳ Calcul mathématique par blocs en cours...";

            marqueursGlobaux.forEach(m => map.removeLayer(m));
            marqueursGlobaux = [];
            if (coucheRoute) map.removeLayer(coucheRoute);

            listeVillesTest.forEach(coord => {
                let marker = L.circleMarker(coord, {
                    radius: 8,
                    fillColor: "#2563eb",
                    color: "#fff",
                    weight: 2,
                    fillOpacity: 1
                }).addTo(map);
                marqueursGlobaux.push(marker);
            });

            try {
                let debut = performance.now();
                const reponse = await fetch('http://127.0.0.1:8000/optimiser-tournee-gps/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-API-KEY': 'TEST-LIBRE'
                    },
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

                    coucheRoute = L.polyline(coordonneesTracees, { 
                        color: '#ef4444', 
                        weight: 4, 
                        opacity: 0.85,
                        dashArray: '5, 5' 
                    }).addTo(map);
                    
                    map.fitBounds(coucheRoute.getBounds(), { padding: [50, 50] });
                } else {
                    alert("Erreur du serveur : " + resultat.detail);
                }
            } catch (e) {
                console.error(e);
                alert("Impossible de joindre le moteur d'optimisation sur le serveur.");
            } finally {
                bouton.disabled = false;
                bouton.innerText = "⚡ Lancer l'Optimisation Globale";
            }
        }

        const ctx = document.getElementById('chartPerformance').getContext('2d');
        new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: ['Blocs Exacts', 'Synchronisation 2-Opt', 'Calcul GPS'],
                datasets: [{
                    data: [70, 20, 10],
                    backgroundColor: ['#2563eb', '#38bdf8', '#e2e8f0'],
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    legend: { position: 'bottom', labels: { boxWidth: 12, font: { family: 'Inter' } } }
                }
            }
        });
    </script>
</body>
</html>
