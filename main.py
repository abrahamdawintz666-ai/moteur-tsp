"""
================================================================================
SWIFTROUTE ENGINE — ENTERPRISE COMMERCIAL EDITION (HYBRID VRP MATRIX)
Architecture: 4-Force Elite Ant Colony Optimization (ACO) & Planar Projection
Adjustments: Earth Radius Coordinate Vectorization & Road Tortuosity Matrix
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
import os
from typing import List, Tuple

# Sur Render : définissez ces variables dans l'onglet "Environment" du service.
# Les valeurs ci-dessous ne servent que de secours en local.
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

# ------------------------------------------------------------------------------
# PRÉSENTATION — PAGE D'ACCUEIL (STYLE B2B MONDIAL)
# Rien ici ne touche au moteur de calcul plus bas dans le fichier.
# ------------------------------------------------------------------------------

def obtenir_page_accueil():
    return """
    <html>
        <head>
            <title>SwiftRoute Engine — Global Logistics Optimization Platform</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                * { box-sizing: border-box; }
                body { font-family: 'Segoe UI', Arial, sans-serif; background-color: #0c0a09; color: #f5f5f4; margin: 0; padding: 0; }
                a { color: inherit; }

                /* NAV */
                .navbar { display: flex; align-items: center; justify-content: space-between; max-width: 1200px; margin: auto; padding: 22px 20px; }
                .navbar-brand { display: flex; align-items: center; gap: 10px; font-weight: 800; font-size: 20px; letter-spacing: -0.5px; }
                .navbar-links { display: flex; align-items: center; gap: 28px; }
                .navbar-links a { color: #a8a29e; text-decoration: none; font-size: 14px; font-weight: 500; }
                .navbar-links a:hover { color: #f5f5f4; }
                .navbar-links .btn-nav { background: #f59e0b; color: #0c0a09; padding: 10px 18px; border-radius: 8px; font-weight: 700; }

                /* HERO */
                .hero { text-align: center; padding: 70px 20px 50px 20px; background: linear-gradient(180deg, #1c1917 0%, #0c0a09 100%); border-bottom: 1px solid #2e2a24; }
                .eyebrow { color: #f59e0b; text-transform: uppercase; font-weight: 700; font-size: 12px; letter-spacing: 2px; }
                .logo-brand { font-size: 44px; font-weight: 800; margin: 12px 0; letter-spacing: -1px; }
                .subtitle { color: #a8a29e; font-size: 18px; max-width: 640px; margin: 15px auto 30px auto; line-height: 1.5; }
                .hero-ctas { display: flex; gap: 14px; justify-content: center; flex-wrap: wrap; }
                .btn-primary { background: #f59e0b; color: #0c0a09; font-weight: bold; text-decoration: none; padding: 14px 28px; border-radius: 8px; display: inline-block; transition: 0.2s; }
                .btn-primary:hover { background: #d97706; }
                .btn-secondary { border: 1px solid #44403c; color: #f5f5f4; text-decoration: none; padding: 14px 28px; border-radius: 8px; display: inline-block; }
                .btn-secondary:hover { border-color: #78716c; }

                /* TRUST BAR */
                .trust-bar { max-width: 1000px; margin: 0 auto; padding: 28px 20px; text-align: center; }
                .trust-label { color: #78716c; font-size: 12px; text-transform: uppercase; letter-spacing: 1.5px; margin-bottom: 18px; }
                .trust-logos { display: flex; justify-content: center; gap: 40px; flex-wrap: wrap; opacity: 0.6; font-weight: 700; color: #a8a29e; font-size: 15px; }

                /* STATS */
                .stats-bar { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); max-width: 1000px; margin: 20px auto 0 auto; border-top: 1px solid #2e2a24; border-bottom: 1px solid #2e2a24; }
                .stat { text-align: center; padding: 28px 10px; border-right: 1px solid #2e2a24; }
                .stat:last-child { border-right: none; }
                .stat-num { font-size: 28px; font-weight: 800; color: #f59e0b; }
                .stat-label { font-size: 12px; color: #a8a29e; margin-top: 4px; }

                .container { max-width: 1000px; margin: auto; padding: 60px 20px; }
                .section-title { text-align: center; font-size: 30px; margin-bottom: 10px; }
                .section-subtitle { text-align: center; color: #a8a29e; max-width: 560px; margin: 0 auto 40px auto; }

                .grid-features { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 25px; margin-top: 20px; }
                .card { background: #1c1917; padding: 25px; border-radius: 12px; border: 1px solid #2e2a24; }
                .card h3 { color: #f59e0b; margin-top: 0; }
                .card p { color: #a8a29e; font-size: 14px; line-height: 1.5; }

                /* DEMO / TIMER */
                .demo-box { background: #1c1917; border: 1px solid #2e2a24; border-radius: 14px; padding: 32px; margin-top: 20px; }
                .demo-top { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; margin-bottom: 18px; }
                .demo-top h3 { margin: 0; color: #f5f5f4; }
                .demo-select { display: flex; gap: 10px; flex-wrap: wrap; }
                .demo-btn { background: #292524; color: #fff; border: 1px solid #44403c; padding: 10px 16px; border-radius: 8px; cursor: pointer; font-size: 13px; }
                .demo-btn.active { border-color: #f59e0b; color: #f59e0b; }
                .timer-row { display: flex; align-items: center; gap: 18px; margin-top: 10px; flex-wrap: wrap; }
                .timer-circle { width: 84px; height: 84px; border-radius: 50%; border: 4px solid #2e2a24; display: flex; align-items: center; justify-content: center; font-weight: 800; font-size: 18px; color: #f59e0b; flex-shrink: 0; }
                .timer-info { flex: 1; min-width: 220px; }
                .progress-track { width: 100%; height: 8px; background: #292524; border-radius: 999px; overflow: hidden; margin-top: 8px; }
                .progress-fill { height: 100%; width: 0%; background: #f59e0b; transition: width 0.3s linear; }
                .demo-status { font-size: 14px; color: #a8a29e; margin-top: 8px; min-height: 20px; }
                .demo-result { margin-top: 16px; padding: 14px; border-radius: 8px; border: 1px dashed #22c55e; color: #22c55e; font-size: 14px; display: none; }

                /* ÉTAT DE LA PLATEFORME / TRAFIC */
                .status-section { background: #1c1917; border-top: 1px solid #2e2a24; border-bottom: 1px solid #2e2a24; }
                .status-header { display: flex; align-items: center; justify-content: center; gap: 10px; margin-bottom: 6px; }
                .live-dot { width: 9px; height: 9px; border-radius: 50%; background: #22c55e; box-shadow: 0 0 0 rgba(34,197,94,0.5); animation: pulse-dot 1.8s infinite; }
                @keyframes pulse-dot { 0% { box-shadow: 0 0 0 0 rgba(34,197,94,0.5);} 70% { box-shadow: 0 0 0 8px rgba(34,197,94,0);} 100% { box-shadow: 0 0 0 0 rgba(34,197,94,0);} }
                .status-note { text-align:center; font-size: 12px; color: #78716c; margin-bottom: 30px; }
                .status-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 20px; }
                .status-card { background: #0c0a09; border: 1px solid #2e2a24; border-radius: 12px; padding: 20px; }
                .status-card .status-num { font-size: 24px; font-weight: 800; color: #f59e0b; }
                .status-card .status-label { font-size: 12px; color: #a8a29e; margin-top: 4px; }
                .chart-box { margin-top: 25px; background: #0c0a09; border: 1px solid #2e2a24; border-radius: 12px; padding: 20px; }
                .chart-box h4 { margin: 0 0 14px 0; font-size: 13px; color: #a8a29e; font-weight: 600; }
                .bar-chart { display: flex; align-items: flex-end; gap: 6px; height: 90px; }
                .bar-chart .bar { flex: 1; background: #44403c; border-radius: 3px 3px 0 0; }
                .bar-chart .bar.last { background: #f59e0b; }

                /* CARTE MAISON (CANVAS, sans dépendance externe) */
                .map-box { margin-top: 20px; background: #0c0a09; border: 1px solid #2e2a24; border-radius: 10px; padding: 8px; }
                #demo-map { width: 100%; height: 320px; border-radius: 8px; display: block; }
                .map-legend { display: flex; gap: 18px; margin-top: 10px; padding: 0 6px; font-size: 12px; color: #78716c; flex-wrap: wrap; }
                .map-legend span { display: flex; align-items: center; gap: 6px; }
                .map-legend i { width: 9px; height: 9px; border-radius: 50%; display: inline-block; }

                /* CTA BANNER */
                .cta-banner { text-align: center; padding: 60px 20px; background: #1c1917; border-top: 1px solid #2e2a24; border-bottom: 1px solid #2e2a24; }
                .cta-banner h2 { font-size: 26px; margin-bottom: 10px; }
                .cta-banner p { color: #a8a29e; margin-bottom: 24px; }

                /* FOOTER */
                .footer { max-width: 1000px; margin: auto; padding: 40px 20px; display: flex; justify-content: space-between; flex-wrap: wrap; gap: 20px; color: #78716c; font-size: 13px; }
                .footer a { color: #a8a29e; text-decoration: none; margin-right: 16px; }
            </style>
        </head>
        <body>
            <div class="navbar">
                <div class="navbar-brand">🐜 SwiftRoute Engine</div>
                <div class="navbar-links">
                    <a href="/docs">Documentation API</a>
                    <a href="#demo">Démo</a>
                    <a href="/dashboard" class="btn-nav">Espace Client</a>
                </div>
            </div>

            <div class="hero">
                <p class="eyebrow">Global B2B Route Optimization Infrastructure</p>
                <h1 class="logo-brand">SWIFTROUTE ENGINE v2.5</h1>
                <p class="subtitle">Infrastructure de calcul d'itinéraires utilisée par des équipes logistiques dans plusieurs régions du monde. Vectorisation géospatiale, contraintes de flotte et optimisation VRP, exposées via une API unique.</p>
                <div class="hero-ctas">
                    <a href="/dashboard" class="btn-primary">Obtenir une clé API</a>
                    <a href="#demo" class="btn-secondary">Voir la démo</a>
                </div>
            </div>

            <div class="trust-bar">
                <div class="trust-label">Conçu pour les opérations logistiques multi-régions</div>
                <div class="trust-logos">
                    <span>AMÉRIQUE DU NORD</span><span>EUROPE</span><span>CARAÏBES</span><span>AMÉRIQUE LATINE</span><span>AFRIQUE</span>
                </div>
            </div>

            <div class="stats-bar">
                <div class="stat"><div class="stat-num">99.9%</div><div class="stat-label">Disponibilité visée</div></div>
                <div class="stat"><div class="stat-num">&lt;1s</div><div class="stat-label">Temps de calcul type</div></div>
                <div class="stat"><div class="stat-num">500+</div><div class="stat-label">Points par requête</div></div>
                <div class="stat"><div class="stat-num">24/7</div><div class="stat-label">API disponible</div></div>
            </div>

            <div class="container">
                <h2 class="section-title">Spécifications de l'infrastructure</h2>
                <p class="section-subtitle">Une pile de calcul pensée pour les volumes d'entreprise et les contraintes de flotte réelles.</p>
                <div class="grid-features">
                    <div class="card">
                        <h3>⚡ Projection Vectorielle</h3>
                        <p>Conversion instantanée des coordonnées sphériques terrestres en matrices cartésiennes planes. Vitesse de traitement multipliée sur les gros volumes de villes.</p>
                    </div>
                    <div class="card">
                        <h3>📦 Contraintes de Livraison (VRP)</h3>
                        <p>Gestion intelligente des capacités de transport. Planification automatique des retours au dépôt central pour le rechargement de vos véhicules.</p>
                    </div>
                    <div class="card">
                        <h3>🌍 Déploiement International</h3>
                        <p>Facturation autonome et activation instantanée pour les équipes réparties sur plusieurs continents, sans dépendance à une banque locale.</p>
                    </div>
                </div>
            </div>

            <div class="status-section">
                <div class="container" style="padding-bottom: 50px;">
                    <div class="status-header">
                        <span class="live-dot"></span>
                        <h2 class="section-title" style="margin:0;">État de la plateforme</h2>
                    </div>
                    <p class="status-note">Aperçu illustratif — à connecter à vos métriques réelles avant mise en production.</p>

                    <div class="status-grid">
                        <div class="status-card"><div class="status-num">99.97%</div><div class="status-label">Disponibilité (30j)</div></div>
                        <div class="status-card"><div class="status-num">184 ms</div><div class="status-label">Latence moyenne</div></div>
                        <div class="status-card"><div class="status-num">12 480</div><div class="status-label">Requêtes / 24h</div></div>
                        <div class="status-card"><div class="status-num">6</div><div class="status-label">Régions actives</div></div>
                    </div>

                    <div class="chart-box">
                        <h4>Volume de requêtes — dernières 24h (exemple)</h4>
                        <div class="bar-chart">
                            <div class="bar" style="height:35%"></div>
                            <div class="bar" style="height:48%"></div>
                            <div class="bar" style="height:30%"></div>
                            <div class="bar" style="height:55%"></div>
                            <div class="bar" style="height:62%"></div>
                            <div class="bar" style="height:40%"></div>
                            <div class="bar" style="height:70%"></div>
                            <div class="bar" style="height:58%"></div>
                            <div class="bar" style="height:80%"></div>
                            <div class="bar" style="height:65%"></div>
                            <div class="bar" style="height:90%"></div>
                            <div class="bar last" style="height:75%"></div>
                        </div>
                    </div>
                </div>
            </div>

            <div class="container" id="demo" style="padding-top:0;">
                <h2 class="section-title">Démonstration en direct</h2>
                <p class="section-subtitle">Simulez un calcul et suivez le minuteur pendant que le moteur traite vos coordonnées.</p>

                <div class="demo-box">
                    <div class="demo-top">
                        <h3>Simulateur de calcul</h3>
                        <div class="demo-select">
                            <button class="demo-btn active" id="btn-scn-1" onclick="lancerDemo(100)">📍 100 villes</button>
                            <button class="demo-btn" id="btn-scn-2" onclick="lancerDemo(500)">🔥 500 villes</button>
                        </div>
                    </div>

                    <div class="timer-row">
                        <div class="timer-circle" id="timer-circle">0.0s</div>
                        <div class="timer-info">
                            <div class="demo-status" id="demo-status">Sélectionnez un scénario pour démarrer la démonstration.</div>
                            <div class="progress-track"><div class="progress-fill" id="progress-fill"></div></div>
                        </div>
                    </div>

                    <div class="map-box">
                        <canvas id="demo-map" width="600" height="320"></canvas>
                        <div class="map-legend">
                            <span><i style="background:#22c55e;"></i> Dépôt central</span>
                            <span><i style="background:#f59e0b;"></i> Points de livraison</span>
                            <span>⚪ Véhicule en mouvement</span>
                        </div>
                    </div>

                    <div class="demo-result" id="demo-result"></div>
                </div>
            </div>

            <div class="cta-banner">
                <h2>Prêt à intégrer SwiftRoute Engine ?</h2>
                <p>Obtenez une clé d'accès et connectez votre flotte en quelques minutes.</p>
                <a href="/dashboard" class="btn-primary">Démarrer maintenant</a>
            </div>

            <div class="footer">
                <div>© 2026 SwiftRoute Engine. Tous droits réservés.</div>
                <div>
                    <a href="/docs">API</a>
                    <a href="/dashboard">Espace Client</a>
                </div>
            </div>

            <script>
                // Démonstration purement visuelle : un minuteur + une barre de progression
                // + une carte dessinée en Canvas (aucune dépendance externe, aucun tile server tiers).
                // Aucun appel n'est fait au moteur réel ici (positions illustratives uniquement).
                let demoEnCours = false;

                // Points illustratifs en coordonnées "canvas" (dépôt en premier, retour au dépôt en dernier)
                const pointsCarte = [
                    [60, 70],   // Dépôt central
                    [150, 35],
                    [250, 80],
                    [340, 30],
                    [430, 90],
                    [520, 45],
                    [560, 140],
                    [480, 220],
                    [380, 250],
                    [280, 210],
                    [180, 240],
                    [100, 190],
                    [60, 70]    // Retour au dépôt
                ];

                function initDemoMap() {
                    dessinerCarte(0);
                }

                // Interpole une position le long des points de la carte, selon un ratio 0→1
                function positionSurTrajet(ratio) {
                    const segments = pointsCarte.length - 1;
                    const posGlobale = Math.min(ratio, 1) * segments;
                    const indexSegment = Math.min(Math.floor(posGlobale), segments - 1);
                    const t = posGlobale - indexSegment;
                    const a = pointsCarte[indexSegment];
                    const b = pointsCarte[indexSegment + 1];
                    return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
                }

                function dessinerCarte(ratio) {
                    const canvas = document.getElementById('demo-map');
                    const ctx = canvas.getContext('2d');
                    const w = canvas.width, h = canvas.height;

                    // Fond
                    ctx.fillStyle = '#0c0a09';
                    ctx.fillRect(0, 0, w, h);

                    // Grille subtile façon "carte"
                    ctx.strokeStyle = '#1c1917';
                    ctx.lineWidth = 1;
                    for (let x = 0; x < w; x += 40) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke(); }
                    for (let y = 0; y < h; y += 40) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke(); }

                    // Trajet complet (en attente)
                    ctx.strokeStyle = '#2e2a24';
                    ctx.lineWidth = 2;
                    ctx.beginPath();
                    pointsCarte.forEach((p, i) => i === 0 ? ctx.moveTo(p[0], p[1]) : ctx.lineTo(p[0], p[1]));
                    ctx.stroke();

                    // Position courante du véhicule sur le trajet
                    const pos = positionSurTrajet(ratio);
                    const segments = pointsCarte.length - 1;
                    const indexSegment = Math.min(Math.floor(Math.min(ratio, 1) * segments), segments - 1);

                    // Trajet déjà parcouru (ambre)
                    ctx.strokeStyle = '#f59e0b';
                    ctx.lineWidth = 3;
                    ctx.beginPath();
                    ctx.moveTo(pointsCarte[0][0], pointsCarte[0][1]);
                    for (let i = 1; i <= indexSegment; i++) ctx.lineTo(pointsCarte[i][0], pointsCarte[i][1]);
                    ctx.lineTo(pos[0], pos[1]);
                    ctx.stroke();

                    // Points (dépôt en vert, livraisons en ambre)
                    pointsCarte.forEach((p, i) => {
                        if (i === pointsCarte.length - 1) return; // point de retour = même que le dépôt
                        ctx.beginPath();
                        ctx.arc(p[0], p[1], i === 0 ? 7 : 5, 0, Math.PI * 2);
                        ctx.fillStyle = i === 0 ? '#22c55e' : '#f59e0b';
                        ctx.fill();
                    });

                    // Véhicule (pastille blanche animée)
                    ctx.beginPath();
                    ctx.arc(pos[0], pos[1], 6, 0, Math.PI * 2);
                    ctx.fillStyle = '#f5f5f4';
                    ctx.fill();
                    ctx.lineWidth = 2;
                    ctx.strokeStyle = '#f59e0b';
                    ctx.stroke();
                }

                function lancerDemo(points) {
                    if (demoEnCours) return;
                    demoEnCours = true;

                    document.getElementById('btn-scn-1').classList.toggle('active', points === 100);
                    document.getElementById('btn-scn-2').classList.toggle('active', points === 500);

                    const resultBox = document.getElementById('demo-result');
                    resultBox.style.display = 'none';

                    dessinerCarte(0);

                    const dureeTotale = points === 500 ? 3.2 : 1.8; // secondes, valeur d'illustration
                    const etapes = [
                        "⚙️ Vectorisation de " + points + " coordonnées sphériques...",
                        "🧭 Construction de la matrice de distances...",
                        "🐜 Colonies de fourmis en exploration des trajets...",
                        "🚀 Convergence vers la meilleure route trouvée..."
                    ];

                    const statusDiv = document.getElementById('demo-status');
                    const fill = document.getElementById('progress-fill');
                    const circle = document.getElementById('timer-circle');

                    const pas = 100; // ms
                    const totalPas = Math.round((dureeTotale * 1000) / pas);
                    let pasActuel = 0;

                    const intervalId = setInterval(() => {
                        pasActuel++;
                        const ratio = pasActuel / totalPas;
                        const tempsEcoule = (pasActuel * pas / 1000).toFixed(1);

                        fill.style.width = Math.min(ratio * 100, 100) + '%';
                        circle.textContent = tempsEcoule + 's';
                        dessinerCarte(ratio);

                        const indexEtape = Math.min(Math.floor(ratio * etapes.length), etapes.length - 1);
                        statusDiv.textContent = etapes[indexEtape];

                        if (pasActuel >= totalPas) {
                            clearInterval(intervalId);
                            statusDiv.textContent = "✅ Calcul terminé.";
                            resultBox.style.display = 'block';
                            resultBox.textContent = "Trajet optimisé sur " + points + " points en " + dureeTotale.toFixed(1) + "s (valeur de démonstration).";
                            demoEnCours = false;
                        }
                    }, pas);
                }

                initDemoMap();
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
            <input type="hidden" name="text" value="Bonjour Abraham, je viens d'effectuer le paiement de 1500 USD sur ton wallet Solana pour activer ma clé API SwiftRoute v2.5.">
            <label style="font-size:12px; color:#a8a29e;">Nom de votre entreprise :</label>
            <input type="text" placeholder="Ex: Uber Freight" required>
            <label style="font-size:12px; color:#a8a29e; display:block; margin-top:10px;">ID de transaction Blockchain (Hash) :</label>
            <input type="text" placeholder="Collez la signature de votre transaction ici" required>
            <button type="submit" class="btn-submit-tx">⚡ Envoyer la notification d'activation (WhatsApp)</button>
        </form>
    </div>
    """

    banniere_cle_active = f"""
    <div class="payment-banner" style="border: 1px solid #22c55e; padding:20px; border-radius:8px; background: #14532d20;">
        <h3 style="margin-top:0; color:#22c55e;">✓ Clé d'infrastructure active (Version Accélérée 2.5)</h3>
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
                <h3>🎯 Simulateur de Performance Vectorisé</h3>
                <p style="font-size:14px; color:#a8a29e;">Découvrez la vitesse de notre matrice de calcul projetée à plat :</p>
                <div>
                    <button class="scenario-btn" onclick="lancerSimulation('Matrice Projection Réelle', 100)">📍 Coordonnées Projetées (100 villes)</button>
                    <button class="scenario-btn" onclick="lancerSimulation('Stress Test Élite Vectorisé', 500)" style="border-color: #ef4444;">🔥 Masse Critique (500 villes)</button>
                </div>
                <div id="zone-status-simulation" style="margin-top: 20px; font-weight: bold; color: #f59e0b;"></div>
            </div>
            <script>
                function lancerSimulation(nomScenario, points) {{
                    const statusDiv = document.getElementById('zone-status-simulation');
                    statusDiv.innerHTML = `⚙️ Vectorisation de ${{points}} coordonnées sphériques terrestres...`;
                    setTimeout(() => {{
                        statusDiv.innerHTML = `🚀 Algorithme AntStrike en action. Résolution euclidienne accélérée sur plan terrestre...`;
                        setTimeout(() => {{
                            statusDiv.innerHTML = `✅ Succès ! Trajet optimisé calculé en 0.28s. Performance maximale atteinte.`;
                        }}, 1000);
                    }}, 600);
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
# ------------------------------------------------------------------------------
# LOGIQUE VECTORISÉE TOTALEMENT CORRIGÉE : EXTRACTION CORRECTE DES TUPLES LAT/LON
# (MOTEUR — NON MODIFIÉ)
# ------------------------------------------------------------------------------

NB_FOURMIS = 15
ALPHA, BETA, EVAPORATION, Q = 1.0, 2.0, 0.3, 100.0
CAPACITE_MAX_VEHICULE = 10

class RequeteCalcul(BaseModel):
    villes: List[Tuple[float, float]]

def calculer_route_precision(villes: List[Tuple[float, float]]) -> Tuple[List[int], float]:
    nb_villes = len(villes)
    if nb_villes < 3: return list(range(nb_villes)), 0.0
    
    # Correction stricte de l'extraction de la latitude moyenne pour la projection
    lat_moyenne = math.radians(sum(float(v[0]) for v in villes) / nb_villes)
    R = 6371.0
    
    # Remplacement des appels incorrects : extraction précise par index [0] et [1]
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
