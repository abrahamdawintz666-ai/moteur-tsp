from fastapi import FastAPI, HTTPException, Security, Depends
from fastapi.security.api_key import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import math
from datetime import datetime, timedelta
import uuid
from typing import List, Tuple
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp

app = FastAPI(
    title="GlobalRoute AI - Enterprise SaaS",
    description="Moteur d'optimisation TSP mondial avec gestion dynamique des abonnements et minuterie."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Base de données en mémoire des abonnés (Évolutive vers une BDD PostgreSQL/MongoDB)
LES_ABONNES = {
    "CLE-ADMIN-MAÎTRE-999": {
        "nom": "Administration Générale", 
        "email": "admin@globalroute.ai", 
        "actif": True, 
        "admin": True,
        "expiration": None # Illimité pour le maître
    }
}

API_KEY_NAME = "X-API-KEY"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

async def verifier_cle_api(api_key: str = Depends(api_key_header)):
    if not api_key or api_key not in LES_ABONNES:
        raise HTTPException(status_code=403, detail="Accès refusé : Clé API invalide ou absente.")
    
    abonne = LES_ABONNES[api_key]
    if not abonne["actif"]:
        raise HTTPException(status_code=402, detail="Accès suspendu : Compte désactivé.")
    
    # Vérification de la minuterie mondiale (Expiration)
    if abonne.get("expiration"):
        date_expiration = datetime.fromisoformat(abonne["expiration"])
        if datetime.utcnow() > date_expiration:
            raise HTTPException(status_code=401, detail="Accès refusé : La minuterie de la clé API a expiré.")
            
    return abonne

class RequeteCalcul(BaseModel):
    villes: List[Tuple[float, float]]

class RequeteCreationCle(BaseModel):
    nom_entreprise: str
    email: str
    duree_jours: int  # 30 ou 365

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

@app.post("/admin/generer-cle")
async def generer_cle_admin(req: RequeteCreationCle, abonne: dict = Depends(verifier_cle_api)):
    if not abonne.get("admin", False):
        raise HTTPException(status_code=403, detail="Action interdite : Réservé à l'administrateur.")
    
    # Génération d'une clé unique structurée
    prefixe = ''.join([c for c in req.nom_entreprise if c.isalnum()]).upper()[:4]
    unique_suffix = uuid.uuid4().hex[:6].upper()
    nouvelle_cle = f"GR-{prefixe}-{unique_suffix}"
    
    # Calcul de la minuterie mondiale (date d'expiration UTC)
    date_expiration = datetime.utcnow() + timedelta(days=req.duree_jours)
    
    LES_ABONNES[nouvelle_cle] = {
        "nom": req.nom_entreprise,
        "email": req.email,
        "actif": True,
        "admin": False,
        "expiration": date_expiration.isoformat()
    }
    
    return {
        "message": "Clé API générée avec succès.",
        "cle_api": nouvelle_cle,
        "entreprise": req.nom_entreprise,
        "email": req.email,
        "expiration": date_expiration.strftime("%Y-%m-%d %H:%M:%S UTC")
    }

@app.get("/admin/cles")
async def lister_cles_admin(abonne: dict = Depends(verifier_cle_api)):
    if not abonne.get("admin", False):
        raise HTTPException(status_code=403, detail="Réservé à l'administrateur.")
    return {"cles_enregistrees": LES_ABONNES}

@app.get("/", response_class=HTMLResponse)
async def afficher_dashboard():
    html_content = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GlobalRoute AI - Enterprise Logistics</title>
    
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">

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
        .nav-auth input { padding: 8px 12px; border: 1px solid var(--border-color); border-radius: 8px; font-size: 14px; width: 220px; }
        .nav-auth button { background: var(--primary); color: white; border: none; padding: 8px 14px; border-radius: 8px; cursor: pointer; font-weight: 600; font-size: 14px; }
        
        .metrics-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 15px; margin-bottom: 20px; }
        .metric-card { background: var(--card-bg); padding: 20px; border-radius: 12px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); border: 1px solid var(--border-color); }
        .metric-card h3 { margin: 0; font-size: 26px; font-weight: 700; color: var(--primary); }
        .metric-card p { margin: 5px 0 0; color: var(--text-muted); font-size: 13px; font-weight: 500; }

        .dashboard-grid { display: grid; grid-template-columns: 2fr 1fr; gap: 20px; margin-bottom: 20px; }
        @media (max-width: 900px) { .dashboard-grid { grid-template-columns: 1fr; } }

        .card { background: var(--card-bg); padding: 20px; border-radius: 12px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); border: 1px solid var(--border-color); }
        .card h2 { margin-top: 0; font-size: 16px; font-weight: 600; margin-bottom: 15px; color: var(--text-main); }
        
        #map { height: 420px; border-radius: 10px; width: 100%; z-index: 1; }
        .btn-action { background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%); color: white; border: none; padding: 12px 20px; border-radius: 10px; cursor: pointer; font-weight: 600; font-size: 15px; width: 100%; margin-top: 15px; box-shadow: 0 4px 6px rgba(37, 99, 235, 0.2); }
        .btn-action:hover { opacity: 0.9; }

        /* Console Admin Pro */
        .admin-panel { background: #1e293b; color: #f8fafc; padding: 20px; border-radius: 12px; margin-bottom: 20px; display: none; }
        .admin-panel h3 { margin-top: 0; color: #38bdf8; font-size: 16px; }
        .form-group { margin-bottom: 12px; display: flex; flex-direction: column; gap: 5px; }
        .form-group label { font-size: 13px; color: #cbd5e1; }
        .form-group input, .form-group select { padding: 8px 10px; border-radius: 6px; border: 1px solid #475569; background: #0f172a; color: white; font-size: 14px; }
        .btn-admin-submit { background: #10b981; color: white; border: none; padding: 10px; border-radius: 6px; font-weight: 600; cursor: pointer; margin-top: 5px; }
        .btn-admin-submit:hover { background: #059669; }
        #adminOutput { font-family: monospace; font-size: 12px; background: #0f172a; padding: 12px; border-radius: 6px; margin-top: 15px; white-space: pre-wrap; color: #34d399; max-height: 200px; overflow-y: auto; }

        .legal-footer { background: var(--card-bg); padding: 20px; border-radius: 12px; border: 1px solid var(--border-color); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 15px; font-size: 12px; color: var(--text-muted); }
        .legal-footer a { color: var(--primary); text-decoration: none; font-weight: 600; }
    </style>
</head>
<body>

    <div class="navbar">
        <div class="logo"><span>🌍</span> GlobalRoute AI SaaS</div>
        <div class="nav-auth">
            <input type="text" id="apiKeyInput" value="CLE-ADMIN-MAÎTRE-999" placeholder="Entrez votre Clé API...">
            <button onclick="verifierAcces()">Valider</button>
            <button onclick="basculerAdmin()" style="background: #0f172a;">Console Admin</button>
        </div>
    </div>

    <!-- Console d'Administration pour Génération de Clés -->
    <div id="adminSection" class="admin-panel">
        <h3>🔐 Console d'Administration & Minuterie Mondiale</h3>
        <p style="font-size: 13px; color: #94a3b8;">Générez des clés d'accès sur mesure avec une validité programmée pour vos clients SaaS.</p>
        
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-top: 15px;">
            <div class="form-group">
                <label>Nom de l'Entreprise :</label>
                <input type="text" id="adminNomEntite" placeholder="Ex: Port-au-Prince Logistique">
            </div>
            <div class="form-group">
                <label>Adresse Email :</label>
                <input type="email" id="adminEmail" placeholder="client@entreprise.com">
            </div>
            <div class="form-group">
                <label>Durée de l'Abonnement :</label>
                <select id="adminDuree">
                    <option value="30">30 Jours (1 mois)</option>
                    <option value="365">365 Jours (1 an)</option>
                </select>
            </div>
        </div>
        <button class="btn-admin-submit" onclick="genererNouvelleCle()">⚡ Générer la Clé API & Minuterie</button>
        
        <div id="adminOutput">Résultat de la génération ou liste des abonnés apparaîtra ici...</div>
    </div>

    <div class="metrics-grid">
        <div class="metric-card"><h3 id="kpi-villes">0</h3><p>Points Traités</p></div>
        <div class="metric-card"><h3 id="kpi-distance">0.0 km</h3><p>Distance Optimisée (Haversine)</p></div>
        <div class="metric-card"><h3 id="kpi-temps">0.00 s</h3><p>Vitesse Moteur par Blocs</p></div>
    </div>

    <div class="dashboard-grid">
        <div class="card">
            <h2>🗺️ Carte interactive des tournées mondiales</h2>
            <div id="map"></div>
            <button id="btnLancer" class="btn-action" onclick="lancerCalculGlobal()">⚡ Lancer l'Optimisation Globale</button>
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
            <p><strong>GlobalRoute AI</strong> — Architecture Logistique & Théorie de l'Optimisation.</p>
        </div>
        <div>
            <p>Contact : <a href="mailto:abrahamdawintz410@gmail.com">abrahamdawintz410@gmail.com</a> | WhatsApp : <a href="https://wa.me/50941817761" target="_blank">+509 41 81 7761</a></p>
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

        function verifierAcces() {
            const cle = document.getElementById('apiKeyInput').value;
            alert("Clé prête pour les requêtes : " + cle);
        }

        async function basculerAdmin() {
            const section = document.getElementById('adminSection');
            if (section.style.display === 'block') {
                section.style.display = 'none';
                return;
            }
            section.style.display = 'block';
            
            // Charger la liste actuelle des abonnés à l'ouverture
            const cleAdmin = document.getElementById('apiKeyInput').value;
            try {
                const rep = await fetch('/admin/cles', {
                    headers: { 'X-API-KEY': cleAdmin }
                });
                const data = await rep.json();
                if (rep.ok) {
                    document.getElementById('adminOutput').innerText = "CLÉS ACTIVES ENREGISTRÉES :\n" + JSON.stringify(data.cles_enregistrees, null, 2);
                } else {
                    document.getElementById('adminOutput').innerText = "Erreur d'accès admin : " + data.detail;
                }
            } catch(e) {
                document.getElementById('adminOutput').innerText = "Impossible de joindre la base des clés.";
            }
        }

        async function genererNouvelleCle() {
            const cleAdmin = document.getElementById('apiKeyInput').value;
            const nomEntite = document.getElementById('adminNomEntite').value;
            const email = document.getElementById('adminEmail').value;
            const duree = parseInt(document.getElementById('adminDuree').value);

            if (!nomEntite || !email) {
                alert("Veuillez remplir le nom de l'entreprise et l'email.");
                return;
            }

            try {
                const rep = await fetch('/admin/generer-cle', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-API-KEY': cleAdmin
                    },
                    body: JSON.stringify({
                        nom_entreprise: nomEntite,
                        email: email,
                        duree_jours: duree
                    })
                });

                const resultat = await rep.json();
                if (rep.ok) {
                    document.getElementById('adminOutput').innerText = 
                        `✅ CLÉ GÉNÉRÉE AVEC SUCCÈS !\n\n` +
                        `Entreprise : ${resultat.entreprise}\n` +
                        `Email : ${resultat.email}\n` +
                        `Clé API : ${resultat.cle_api}\n` +
                        `Expiration (Minuterie) : ${resultat.expiration}`;
                } else {
                    alert("Erreur : " + resultat.detail);
                }
            } catch (e) {
                alert("Erreur réseau lors de la génération de la clé.");
            }
        }

        async function lancerCalculGlobal() {
            const bouton = document.getElementById('btnLancer');
            const cle = document.getElementById('apiKeyInput').value;
            bouton.disabled = true;
            bouton.innerText = "⏳ Optimisation mathématique en cours...";

            marqueursGlobaux.forEach(m => map.removeLayer(m));
            marqueursGlobaux = [];
            if (coucheRoute) map.removeLayer(coucheRoute);

            listeVillesTest.forEach(coord => {
                let marker = L.circleMarker(coord, {
                    radius: 7,
                    fillColor: "#2563eb",
                    color: "#fff",
                    weight: 2,
                    fillOpacity: 1
                }).addTo(map);
                marqueursGlobaux.push(marker);
            });

            try {
                let debut = performance.now();
                const reponse = await fetch('/optimiser-tournee-gps/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-API-KEY': cle
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
                        dashArray: '4, 4' 
                    }).addTo(map);
                    
                    map.fitBounds(coucheRoute.getBounds(), { padding: [40, 40] });
                } else {
                    alert("Accès refusé ou Expiré : " + resultat.detail);
                }
            } catch (e) {
                console.error(e);
                alert("Erreur de connexion au serveur.");
            } finally {
                bouton.disabled = false;
                bouton.innerText = "⚡ Lancer l'Optimisation Globale";
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
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: 'bottom', labels: { boxWidth: 12, font: { family: 'Inter' } } }
                }
            }
        });
    </script>
</body>
</html>
    """
    return html_content
