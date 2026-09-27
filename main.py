"""
================================================================================
SWIFTROUTE ENGINE — ENTERPRISE COMMERCIAL EDITION
Hybrid VRP Matrix / 4-Force ACO
Author: Abraham — Cap-Haïtien 2026

Commercial layer:
- 7-day persistent free trial
- One trial per normalized email + IP
- SQLite persistence (survives server restarts)
- HttpOnly session cookie
- API keys are never put in the URL
- Tiun snippet is public; secret credentials stay in environment variables
- Human-friendly workspace + developer API documentation
================================================================================
"""

from fastapi import (
    FastAPI, HTTPException, Security, Request, Form, Cookie
)
from fastapi.security.api_key import APIKeyHeader
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, EmailStr
import jwt
import random
import math
import datetime
import os
import sqlite3
import hashlib
import secrets
from typing import List, Tuple, Optional

# ==============================================================================
# CONFIGURATION
# ==============================================================================

PHRASE_SECRETE_NORD = os.getenv(
    "JWT_SECRET_KEY",
    "CHANGE_ME_IN_RENDER_ENVIRONMENT"
)

API_KEY_NAME = "X-API-KEY"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

NOM_UTILISATEUR_ADMIN = os.getenv("ADMIN_USERNAME", "Abraham")
MOT_DE_PASSE_ADMIN = os.getenv(
    "ADMIN_PASSWORD",
    "CHANGE_ME_IN_RENDER_ENVIRONMENT"
)

VOTRE_WALLET_SOLANA = os.getenv(
    "SOLANA_WALLET",
    "CHANGE_ME"
)

# Tiun public snippet ID.
# Keep this in the page; it is not a server secret.
TIUN_SNIPPET_ID = os.getenv(
    "TIUN_SNIPPET_ID",
    "JQD27X4Dhj8JGdXQhnbBYz1K2HS5gjiojVwYIAKR"
)

# NEVER put a Tiun secret/API key in HTML or source code.
TIUN_SECRET_KEY = os.getenv("TIUN_SECRET_KEY", "")

DATABASE_PATH = os.getenv("SWIFTROUTE_DB", "swiftroute.db")
DUREE_ESSAI_JOURS = 7

app = FastAPI(
    title="SwiftRoute Engine - AntStrike Advanced VRP",
    swagger_ui_parameters={"operationsSorter": "alpha"}
)

# ==============================================================================
# DATABASE
# ==============================================================================

def db_connect():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    conn = db_connect()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS trials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            email_hash TEXT NOT NULL,
            client_name TEXT NOT NULL,
            ip_hash TEXT NOT NULL,
            token_jti TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            usage_count INTEGER NOT NULL DEFAULT 0
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS api_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL UNIQUE,
            client_name TEXT NOT NULL,
            email TEXT,
            token_jti TEXT,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        )
    """)

    conn.commit()
    conn.close()


init_database()

# ==============================================================================
# SECURITY HELPERS
# ==============================================================================

def hash_value(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_email(email: str) -> str:
    return email.strip().lower()


def get_client_ip(request: Request) -> str:
    # If behind Render/reverse proxy, use the first forwarded address.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()

    return request.client.host if request.client else "unknown"


def create_client_token(
    client_name: str,
    email: str,
    duration_days: int,
    trial: bool = False
):
    now = datetime.datetime.now(datetime.timezone.utc)
    expiration = now + datetime.timedelta(days=duration_days)
    jti = secrets.token_urlsafe(32)

    payload = {
        "client": client_name,
        "email": email,
        "exp": int(expiration.timestamp()),
        "iat": int(now.timestamp()),
        "jti": jti,
        "trial": trial,
        "type_offre": (
            "Essai Gratuit 7 Jours"
            if trial
            else f"Accès {duration_days} Jours"
        )
    }

    token = jwt.encode(
        payload,
        PHRASE_SECRETE_NORD,
        algorithm="HS256"
    )

    return token, jti, expiration


def create_session(
    client_name: str,
    email: Optional[str],
    token_jti: Optional[str],
    expiration: datetime.datetime
):
    session_id = secrets.token_urlsafe(48)
    now = datetime.datetime.now(datetime.timezone.utc)

    conn = db_connect()
    conn.execute(
        """
        INSERT INTO api_sessions
        (session_id, client_name, email, token_jti,
         created_at, expires_at, active)
        VALUES (?, ?, ?, ?, ?, ?, 1)
        """,
        (
            session_id,
            client_name,
            email,
            token_jti,
            now.isoformat(),
            expiration.isoformat()
        )
    )
    conn.commit()
    conn.close()

    return session_id


def get_session(session_id: Optional[str]):
    if not session_id:
        return None

    conn = db_connect()
    row = conn.execute(
        """
        SELECT *
        FROM api_sessions
        WHERE session_id = ?
          AND active = 1
        """,
        (session_id,)
    ).fetchone()
    conn.close()

    if not row:
        return None

    expiration = datetime.datetime.fromisoformat(row["expires_at"])

    if expiration <= datetime.datetime.now(datetime.timezone.utc):
        conn = db_connect()
        conn.execute(
            "UPDATE api_sessions SET active = 0 WHERE session_id = ?",
            (session_id,)
        )
        conn.commit()
        conn.close()
        return None

    return row


def verify_token(token: str):
    try:
        return jwt.decode(
            token,
            PHRASE_SECRETE_NORD,
            algorithms=["HS256"]
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=402,
            detail="Votre accès a expiré."
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=403,
            detail="Clé invalide."
        )


def mark_trial_usage(jti: str):
    conn = db_connect()
    conn.execute(
        """
        UPDATE trials
        SET usage_count = usage_count + 1
        WHERE token_jti = ?
        """,
        (jti,)
    )
    conn.commit()
    conn.close()


# ==============================================================================
# PUBLIC HOME PAGE
# ==============================================================================

def obtenir_page_accueil():
    return f"""
    <html>
    <head>
        <title>SwiftRoute Engine — Global Logistics Optimization</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">

        <script type="module">
            import {{ tiun }} from 'https://esm.sh/@tiun/sdk';

            tiun.init({{
                snippetId: '{TIUN_SNIPPET_ID}',
                language: 'fr'
            }});
        </script>

        <style>
            * {{ box-sizing: border-box; }}

            body {{
                font-family: Arial, sans-serif;
                background: #0c0a09;
                color: #f5f5f4;
                margin: 0;
            }}

            a {{ color: inherit; }}

            .navbar {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                max-width: 1200px;
                margin: auto;
                padding: 20px;
                gap: 20px;
            }}

            .brand {{
                font-size: 20px;
                font-weight: 800;
            }}

            .links {{
                display: flex;
                gap: 12px;
                align-items: center;
                flex-wrap: wrap;
            }}

            .links a {{
                color: #a8a29e;
                text-decoration: none;
                padding: 9px 12px;
            }}

            .links .orange {{
                background: #f59e0b;
                color: #0c0a09;
                border-radius: 8px;
                font-weight: bold;
            }}

            .hero {{
                text-align: center;
                padding: 80px 20px;
                background: linear-gradient(
                    180deg,
                    #1c1917,
                    #0c0a09
                );
            }}

            .hero h1 {{
                font-size: clamp(34px, 7vw, 58px);
                margin: 15px 0;
            }}

            .hero p {{
                max-width: 700px;
                margin: 0 auto 30px;
                color: #a8a29e;
                line-height: 1.6;
            }}

            .buttons {{
                display: flex;
                justify-content: center;
                gap: 12px;
                flex-wrap: wrap;
            }}

            .btn {{
                display: inline-block;
                text-decoration: none;
                padding: 14px 24px;
                border-radius: 9px;
                font-weight: bold;
            }}

            .primary {{
                background: #f59e0b;
                color: #0c0a09;
            }}

            .secondary {{
                border: 1px solid #44403c;
            }}

            .container {{
                max-width: 1050px;
                margin: auto;
                padding: 55px 20px;
            }}

            .grid {{
                display: grid;
                grid-template-columns:
                    repeat(auto-fit, minmax(250px, 1fr));
                gap: 20px;
            }}

            .card {{
                background: #1c1917;
                border: 1px solid #2e2a24;
                padding: 24px;
                border-radius: 14px;
            }}

            .card h3 {{
                color: #f59e0b;
            }}

            .card p {{
                color: #a8a29e;
                line-height: 1.55;
            }}

            .trial {{
                border: 1px solid #22c55e;
                background: #14532d22;
            }}
        </style>
    </head>

    <body>

        <div class="navbar">
            <div class="brand">🐜 SwiftRoute Engine</div>

            <div class="links">
                <a href="/docs">Documentation</a>
                <a href="/workspace">Espace Client</a>
                <a href="/essai-gratuit" class="orange">
                    Essai gratuit
                </a>
            </div>
        </div>

        <section class="hero">

            <div style="color:#f59e0b;font-weight:bold;">
                GLOBAL ROUTE OPTIMIZATION INFRASTRUCTURE
            </div>

            <h1>SWIFTROUTE ENGINE</h1>

            <p>
                Optimisation de routes et de tournées pour les
                opérations de transport, avec une interface utilisable
                aussi bien par un développeur que par un conducteur.
            </p>

            <div class="buttons">
                <a href="/essai-gratuit" class="btn primary">
                    🎁 Tester gratuitement pendant 7 jours
                </a>

                <a href="/workspace" class="btn secondary">
                    🔐 Espace Client
                </a>

                <a href="/docs" class="btn secondary">
                    ⚙️ Documentation API
                </a>
            </div>

        </section>

        <div class="container">

            <h2>Une plateforme, deux modes d'utilisation</h2>

            <div class="grid">

                <div class="card">
                    <h3>🚗 Mode conducteur</h3>
                    <p>
                        Une interface simple pour préparer un trajet,
                        consulter les arrêts et suivre le résultat
                        de l'optimisation.
                    </p>
                </div>

                <div class="card">
                    <h3>👨‍💻 Mode développeur</h3>
                    <p>
                        API FastAPI, clé X-API-KEY, données JSON et
                        documentation interactive.
                    </p>
                </div>

                <div class="card trial">
                    <h3>🎁 Essai 7 jours</h3>
                    <p>
                        Un compte d'essai est enregistré dans la base
                        de données. Le même e-mail ne peut pas créer
                        indéfiniment de nouveaux essais.
                    </p>
                </div>

            </div>

        </div>

    </body>
    </html>
    """


@app.get("/", response_class=HTMLResponse)
async def page_accueil_serveur():
    return HTMLResponse(content=obtenir_page_accueil())


# ==============================================================================
# FREE TRIAL
# ==============================================================================

@app.get("/essai-gratuit", response_class=HTMLResponse)
async def page_essai_gratuit():

    return HTMLResponse("""
    <html>
    <head>
        <title>Essai gratuit — SwiftRoute</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">

        <style>
            body {
                background:#0c0a09;
                color:#f5f5f4;
                font-family:Arial,sans-serif;
                padding:25px;
            }

            .box {
                max-width:520px;
                margin:50px auto;
                padding:30px;
                background:#1c1917;
                border:1px solid #2e2a24;
                border-radius:16px;
            }

            h1 { color:#f59e0b; }

            p {
                color:#a8a29e;
                line-height:1.6;
            }

            label {
                display:block;
                margin-top:18px;
                color:#d6d3d1;
            }

            input {
                width:100%;
                padding:14px;
                margin-top:7px;
                box-sizing:border-box;
                border-radius:8px;
                border:1px solid #44403c;
                background:#0c0a09;
                color:white;
            }

            button {
                width:100%;
                margin-top:20px;
                padding:15px;
                border:0;
                border-radius:8px;
                background:#f59e0b;
                color:#0c0a09;
                font-weight:bold;
                font-size:16px;
            }

            .notice {
                margin-top:20px;
                padding:14px;
                border:1px solid #22c55e;
                border-radius:8px;
                color:#86efac;
            }
        </style>
    </head>

    <body>

        <div class="box">

            <h1>🐜 SwiftRoute</h1>

            <h2>Essai gratuit de 7 jours</h2>

            <p>
                Créez votre accès d'essai. Une seule période d'essai
                est autorisée par adresse e-mail.
            </p>

            <form action="/essai-gratuit" method="post">

                <label>Nom de l'entreprise</label>

                <input
                    name="client_name"
                    maxlength="120"
                    placeholder="Ex : ABC Transport"
                    required
                >

                <label>Adresse e-mail</label>

                <input
                    type="email"
                    name="email"
                    maxlength="254"
                    placeholder="vous@entreprise.com"
                    required
                >

                <button type="submit">
                    🚀 Commencer mon essai
                </button>

            </form>

            <div class="notice">
                ✓ 7 jours<br>
                ✓ Compte enregistré<br>
                ✓ Accès à l'espace SwiftRoute
            </div>

        </div>

    </body>
    </html>
    """)


@app.post("/essai-gratuit")
async def creer_essai_gratuit(
    request: Request,
    client_name: str = Form(...),
    email: str = Form(...)
):

    client_name = client_name.strip()
    email = normalize_email(email)

    if not client_name:
        raise HTTPException(
            status_code=400,
            detail="Nom de l'entreprise obligatoire."
        )

    if len(client_name) > 120:
        raise HTTPException(
            status_code=400,
            detail="Nom de l'entreprise trop long."
        )

    if "@" not in email or len(email) > 254:
        raise HTTPException(
            status_code=400,
            detail="Adresse e-mail invalide."
        )

    ip = get_client_ip(request)
    email_hash = hash_value(email)
    ip_hash = hash_value(ip)

    conn = db_connect()

    # One trial per email.
    existing_email = conn.execute(
        "SELECT id FROM trials WHERE email_hash = ?",
        (email_hash,)
    ).fetchone()

    if existing_email:
        conn.close()

        return HTMLResponse(
            """
            <html>
            <body style="background:#0c0a09;color:white;font-family:Arial;padding:40px">
                <h2>🎁 Cet e-mail a déjà utilisé un essai.</h2>
                <p>
                    Connectez-vous à votre espace client ou contactez
                    l'administration si vous pensez qu'il s'agit d'une erreur.
                </p>
                <a href="/workspace" style="color:#f59e0b">
                    Accéder à l'espace client
                </a>
            </body>
            </html>
            """,
            status_code=409
        )

    # Additional anti-abuse check: same IP cannot create unlimited trials.
    existing_ip = conn.execute(
        """
        SELECT id
        FROM trials
        WHERE ip_hash = ?
        """,
        (ip_hash,)
    ).fetchone()

    if existing_ip:
        conn.close()

        return HTMLResponse(
            """
            <html>
            <body style="background:#0c0a09;color:white;font-family:Arial;padding:40px">
                <h2>🔒 Un essai a déjà été créé depuis ce réseau.</h2>
                <p>
                    L'essai gratuit est limité afin d'éviter les créations
                    répétées de comptes.
                </p>
                <a href="/workspace" style="color:#f59e0b">
                    Espace Client
                </a>
            </body>
            </html>
            """,
            status_code=429
        )

    token, jti, expiration = create_client_token(
        client_name=client_name,
        email=email,
        duration_days=DUREE_ESSAI_JOURS,
        trial=True
    )

    now = datetime.datetime.now(datetime.timezone.utc)

    try:
        conn.execute(
            """
            INSERT INTO trials
            (
                email,
                email_hash,
                client_name,
                ip_hash,
                token_jti,
                created_at,
                expires_at,
                active,
                usage_count
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, 0)
            """,
            (
                email,
                email_hash,
                client_name,
                ip_hash,
                jti,
                now.isoformat(),
                expiration.isoformat()
            )
        )

        conn.commit()

    except sqlite3.IntegrityError:
        conn.close()

        return HTMLResponse(
            "<h2>Un essai existe déjà pour ce compte.</h2>",
            status_code=409
        )

    conn.close()

    session_id = create_session(
        client_name,
        email,
        jti,
        expiration
    )

    response = RedirectResponse(
        url="/workspace",
        status_code=303
    )

    response.set_cookie(
        key="swiftroute_session",
        value=session_id,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=DUREE_ESSAI_JOURS * 24 * 60 * 60
    )

    return response


# ==============================================================================
# CLIENT WORKSPACE
# ==============================================================================

@app.get("/workspace", response_class=HTMLResponse)
async def workspace(
    swiftroute_session: str = Cookie(default=None)
):

    session = get_session(swiftroute_session)

    if not session:
        return RedirectResponse(
            url="/essai-gratuit",
            status_code=303
        )

    expiration = datetime.datetime.fromisoformat(
        session["expires_at"]
    )

    expiration_display = expiration.strftime(
        "%d/%m/%Y à %H:%M"
    )

    email = session["email"] or ""

    return HTMLResponse(f"""
    <html>

    <head>

        <title>SwiftRoute — Espace Client</title>

        <meta name="viewport"
              content="width=device-width, initial-scale=1">

        <style>

            * {{ box-sizing:border-box; }}

            body {{
                margin:0;
                background:#0c0a09;
                color:#f5f5f4;
                font-family:Arial,sans-serif;
            }}

            .top {{
                padding:18px 20px;
                border-bottom:1px solid #2e2a24;
                display:flex;
                justify-content:space-between;
                gap:20px;
                flex-wrap:wrap;
            }}

            .container {{
                max-width:1050px;
                margin:auto;
                padding:30px 20px;
            }}

            .welcome {{
                background:#1c1917;
                border:1px solid #2e2a24;
                border-radius:16px;
                padding:25px;
            }}

            .green {{ color:#22c55e; }}
            .orange {{ color:#f59e0b; }}

            .grid {{
                display:grid;
                grid-template-columns:
                    repeat(auto-fit,minmax(240px,1fr));
                gap:20px;
                margin-top:25px;
            }}

            .card {{
                background:#1c1917;
                border:1px solid #2e2a24;
                border-radius:14px;
                padding:25px;
            }}

            .card h2 {{ margin-top:0; }}

            .card p {{
                color:#a8a29e;
                line-height:1.55;
            }}

            button {{
                width:100%;
                padding:14px;
                border:0;
                border-radius:8px;
                background:#f59e0b;
                color:#0c0a09;
                font-weight:bold;
                cursor:pointer;
            }}

            .map {{
                margin-top:25px;
                background:#11100f;
                border:1px solid #2e2a24;
                border-radius:14px;
                padding:20px;
            }}

            input {{
                width:100%;
                padding:13px;
                background:#0c0a09;
                border:1px solid #44403c;
                color:white;
                border-radius:8px;
                margin-top:7px;
                margin-bottom:12px;
            }}

            .route-result {{
                display:none;
                margin-top:18px;
                padding:18px;
                border:1px solid #22c55e;
                border-radius:10px;
            }}

        </style>

    </head>

    <body>

        <div class="top">
            <strong>🐜 SwiftRoute Engine</strong>
            <span class="green">● Session active</span>
        </div>

        <div class="container">

            <div class="welcome">

                <h1>
                    Bonjour {session["client_name"]}
                </h1>

                <p class="green">
                    ✓ Votre accès est actif
                </p>

                <p>
                    Compte :
                    <strong>{email}</strong>
                </p>

                <p>
                    Expiration :
                    <strong class="orange">
                        {expiration_display}
                    </strong>
                </p>

            </div>

            <div class="grid">

                <div class="card">

                    <h2>🚗 Planificateur</h2>

                    <p>
                        Préparez un trajet sans avoir besoin de
                        comprendre le JSON ou le code.
                    </p>

                    <button onclick="document.getElementById('gps').scrollIntoView()">
                        Ouvrir le planificateur
                    </button>

                </div>

                <div class="card">

                    <h2>🗺️ Résultat</h2>

                    <p>
                        Consultez la route, la distance et les étapes
                        dans une présentation lisible.
                    </p>

                    <button onclick="calculerDemo()">
                        Calculer un itinéraire
                    </button>

                </div>

                <div class="card">

                    <h2>👨‍💻 Développeur</h2>

                    <p>
                        Les utilisateurs techniques peuvent utiliser
                        directement l'API et Swagger.
                    </p>

                    <button onclick="location.href='/docs'">
                        Ouvrir la documentation
                    </button>

                </div>

            </div>

            <div id="gps" class="map">

                <h2>📍 Planificateur de trajet</h2>

                <label>Départ</label>
                <input id="depart"
                       placeholder="Ex : Cap-Haïtien">

                <label>Destination</label>
                <input id="destination"
                       placeholder="Ex : Port-au-Prince">

                <label>Arrêts supplémentaires</label>
                <input id="arrets"
                       placeholder="Ex : Gonaïves, Saint-Marc">

                <button onclick="calculerDemo()">
                    🚀 Optimiser le trajet
                </button>

                <div id="route-result" class="route-result"></div>

            </div>

        </div>

        <script>

            function calculerDemo() {{

                const depart =
                    document.getElementById("depart").value ||
                    "Point de départ";

                const destination =
                    document.getElementById("destination").value ||
                    "Destination";

                const arrets =
                    document.getElementById("arrets").value;

                const result =
                    document.getElementById("route-result");

                result.style.display = "block";

                result.innerHTML = `
                    <h3>🧭 Itinéraire optimisé</h3>
                    <p><strong>Départ :</strong> ${{depart}}</p>
                    <p><strong>Destination :</strong> ${{destination}}</p>
                    <p><strong>Arrêts :</strong>
                        ${{arrets || "Aucun"}}
                    </p>
                    <p class="green">
                        ✓ Le moteur SwiftRoute peut maintenant traiter
                        les coordonnées réelles via l'API.
                    </p>
                `;
            }}

        </script>

    </body>
    </html>
    """)


# ==============================================================================
# API KEY VERIFICATION
# ==============================================================================

async def verifier_minuteur_cle_api(
    api_key: str = Security(api_key_header)
):

    if not api_key:
        raise HTTPException(
            status_code=403,
            detail="API Key missing."
        )

    infos = verify_token(api_key)

    jti = infos.get("jti")

    # If this is a registered trial, verify it still exists and is active.
    if infos.get("trial") and jti:

        conn = db_connect()

        row = conn.execute(
            """
            SELECT *
            FROM trials
            WHERE token_jti = ?
              AND active = 1
            """,
            (jti,)
        ).fetchone()

        conn.close()

        if not row:
            raise HTTPException(
                status_code=403,
                detail="Trial access revoked."
            )

        mark_trial_usage(jti)

    return infos


# ==============================================================================
# API MODELS
# ==============================================================================

class RequeteCalcul(BaseModel):
    villes: List[Tuple[float, float]]


# ==============================================================================
# SWIFTROUTE ENGINE
# ==============================================================================

NB_FOURMIS = 15
ALPHA, BETA, EVAPORATION, Q = 1.0, 2.0, 0.3, 100.0
CAPACITE_MAX_VEHICULE = 10


def calculer_route_precision(
    villes: List[Tuple[float, float]]
) -> Tuple[List[int], float]:

    nb_villes = len(villes)

    if nb_villes < 3:
        return list(range(nb_villes)), 0.0

    lat_moyenne = math.radians(
        sum(float(v[0]) for v in villes) / nb_villes
    )

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

                dx = (
                    villes_planes[i][0]
                    - villes_planes[j][0]
                )

                dy = (
                    villes_planes[i][1]
                    - villes_planes[j][1]
                )

                distance_pure = math.sqrt(
                    dx * dx + dy * dy
                )

                ligne.append(
                    distance_pure * 1.23
                )

        distances.append(ligne)

    pheromones = [
        [1.0 for _ in range(nb_villes)]
        for _ in range(nb_villes)
    ]

    meilleure_distance = float("inf")
    meilleure_route = []

    iterations = 20 if nb_villes > 60 else 40

    for _ in range(iterations):

        toutes_routes = []
        toutes_distances = []

        for _ in range(NB_FOURMIS):

            r, d = simuler_fourmi_vrp(
                nb_villes,
                distances,
                pheromones
            )

            toutes_routes.append(r)
            toutes_distances.append(d)

            if d < meilleure_distance:
                meilleure_distance = d
                meilleure_route = r

        for i in range(nb_villes):

            for j in range(nb_villes):

                pheromones[i][j] *= (
                    1.0 - EVAPORATION
                )

        for route, dist in zip(
            toutes_routes,
            toutes_distances
        ):

            depot = Q / max(dist, 0.01)

            for k in range(len(route) - 1):

                pheromones[
                    route[k]
                ][
                    route[k + 1]
                ] += depot

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

                vis = 1.0 / max(
                    dists[act][p],
                    0.01
                )

                note = (
                    phero[act][p] ** ALPHA
                ) * (
                    vis ** BETA
                )

                probs.append((p, note))

                tot += note

        if tot == 0:

            restants = [
                x for x in range(nb)
                if x not in villes_visitees
            ]

            prox = (
                restants[0]
                if restants
                else depot_index
            )

        else:

            flotte = random.uniform(
                0,
                tot
            )

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


# ==============================================================================
# REAL CALCULATION API
# ==============================================================================

@app.post("/api/route")
async def api_route(
    requete: RequeteCalcul,
    infos=Security(verifier_minuteur_cle_api)
):

    if len(requete.villes) > 500:
        raise HTTPException(
            status_code=400,
            detail="Maximum 500 points par requête."
        )

    route, distance = calculer_route_precision(
        requete.villes
    )

    return {
        "success": True,
        "client": infos.get("client"),
        "type_offre": infos.get("type_offre"),
        "route": route,
        "distance_km": round(distance, 3),
        "points": len(requete.villes)
    }


# ==============================================================================
# ADMIN
# ==============================================================================

def obtenir_panneau_admin(
    wallet: str,
    cle_generee: str = ""
):

    result = ""

    if cle_generee:

        result = f"""
        <div style="
            background:#27272a;
            padding:15px;
            margin-top:20px;
            border:1px dashed #a855f7;
            border-radius:8px;
            word-break:break-all;
            font-family:monospace;
        ">
            <strong>Clé générée :</strong><br><br>
            {cle_generee}
        </div>
        """

    return f"""
    <html>
    <head>
        <title>SwiftRoute — Administration</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{
                background:#09090b;
                color:white;
                font-family:Arial;
                padding:25px;
            }}

            .box {{
                max-width:520px;
                margin:auto;
                background:#18181b;
                padding:25px;
                border-radius:12px;
            }}

            input,select {{
                width:100%;
                padding:12px;
                margin:6px 0 14px;
                box-sizing:border-box;
                background:#09090b;
                color:white;
                border:1px solid #3f3f46;
                border-radius:7px;
            }}

            button {{
                width:100%;
                padding:13px;
                background:#a855f7;
                color:white;
                border:0;
                border-radius:7px;
                font-weight:bold;
            }}
        </style>
    </head>

    <body>

        <div class="box">

            <h2>🎛️ Administration SwiftRoute</h2>

            <p style="color:#a1a1aa;">
                Wallet : {wallet}
            </p>

            <form action="/admin-panel/generer" method="post">

                <input
                    name="username"
                    placeholder="Identifiant administrateur"
                    required
                >

                <input
                    type="password"
                    name="password"
                    placeholder="Mot de passe"
                    required
                >

                <input
                    name="client_name"
                    placeholder="Entreprise cliente"
                    required
                >

                <input
                    type="email"
                    name="email"
                    placeholder="Email du client"
                    required
                >

                <select name="duration">

                    <option value="7">
                        Essai 7 jours
                    </option>

                    <option value="30">
                        Entreprise 30 jours
                    </option>

                    <option value="365">
                        Corporate 1 an
                    </option>

                </select>

                <button>
                    Générer et activer
                </button>

            </form>

            {result}

        </div>

    </body>
    </html>
    """


@app.get("/admin-panel", response_class=HTMLResponse)
async def vue_panneau_admin_serveur(
    cle_generee: str = ""
):

    return HTMLResponse(
        obtenir_panneau_admin(
            VOTRE_WALLET_SOLANA,
            cle_generee
        )
    )


@app.post("/admin-panel/generer")
async def action_generer_cle_serveur(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    client_name: str = Form(...),
    email: str = Form(...),
    duration: int = Form(...)
):

    if (
        username != NOM_UTILISATEUR_ADMIN
        or password != MOT_DE_PASSE_ADMIN
    ):

        return HTMLResponse(
            "<h2>Identifiants incorrects. Accès refusé.</h2>",
            status_code=403
        )

    if duration not in (7, 30, 365):

        raise HTTPException(
            status_code=400,
            detail="Durée invalide."
        )

    email = normalize_email(email)

    token, jti, expiration = create_client_token(
        client_name,
        email,
        duration,
        trial=(duration == 7)
    )

    if duration == 7:

        # Manual/admin trials are also persisted.
        conn = db_connect()

        email_hash = hash_value(email)
        ip_hash = hash_value(
            get_client_ip(request)
        )

        existing = conn.execute(
            """
            SELECT id FROM trials
            WHERE email_hash = ?
            """,
            (email_hash,)
        ).fetchone()

        if existing:

            conn.close()

            return HTMLResponse(
                "<h2>Cet e-mail possède déjà un essai.</h2>",
                status_code=409
            )

        now = datetime.datetime.now(
            datetime.timezone.utc
        )

        conn.execute(
            """
            INSERT INTO trials
            (
                email,
                email_hash,
                client_name,
                ip_hash,
                token_jti,
                created_at,
                expires_at,
                active,
                usage_count
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, 0)
            """,
            (
                email,
                email_hash,
                client_name,
                ip_hash,
                jti,
                now.isoformat(),
                expiration.isoformat()
            )
        )

        conn.commit()
        conn.close()

    return HTMLResponse(
        obtenir_panneau_admin(
            VOTRE_WALLET_SOLANA,
            token
        )
    )


# ==============================================================================
# HEALTH CHECK
# ==============================================================================

@app.get("/health")
async def health():

    return {
        "status": "ok",
        "service": "SwiftRoute Engine",
        "version": "2.5"
    }


# ==============================================================================
# RUN LOCALLY
# ==============================================================================

if __name__ == "__main__":

    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        reload=False
    )
