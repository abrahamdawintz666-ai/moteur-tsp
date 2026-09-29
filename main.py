"""
SWIFTROUTE ENGINE — ENTERPRISE COMMERCIAL EDITION
Hybrid VRP Matrix / 4-Force ACO
Author: Abraham — Cap-Haïtien 2026

Version corrigée :
- Accès commercial géré par abonnement
- Session HttpOnly
- API développeur X-API-KEY
- Authentification navigateur par session
- Vérification Tiun côté serveur
- Carte Leaflet corrigée
- Boutons/requêtes protégées corrigés
- Recherche mondiale
- GPS / CSV jusqu'à 500 points
- Routage routier OSRM configurable
- Correction du panneau admin
"""

from fastapi import FastAPI, HTTPException, Security, Request, Form, Cookie
from fastapi.security.api_key import APIKeyHeader
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from typing import List, Tuple, Optional
import jwt
import random
import math
import datetime
import os
import sqlite3
import hashlib
import secrets
import json
import time
import unicodedata
from urllib.parse import quote
from urllib.request import Request as URLRequest, urlopen

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

TIUN_PRODUCT_ID = os.getenv("TIUN_PRODUCT_ID", "p-live-0df3781")
TIUN_SNIPPET_ID = os.getenv(
    "TIUN_SNIPPET_ID",
    "JQD27X4Dhj8JGdXQhnbBYz1K2HS5gjiojVwYIAKR"
)
TIUN_SECRET_KEY = os.getenv("TIUN_SECRET_KEY", "")
TIUN_API_BASE = os.getenv(
    "TIUN_API_BASE",
    "https://api-sandbox.tiun.live"
)

WHATSAPP_CONTACT = os.getenv("WHATSAPP_CONTACT", "+509 41 81 7761")
EMAIL_CONTACT = os.getenv(
    "EMAIL_CONTACT",
    "abrahamdawintz410@gmail.com"
)

GEOCODING_URL = os.getenv(
    "GEOCODING_URL",
    "https://nominatim.openstreetmap.org/search"
)
GEOCODING_USER_AGENT = os.getenv(
    "GEOCODING_USER_AGENT",
    "SwiftRoute/1.0"
)
ROUTING_URL = os.getenv(
    "ROUTING_URL",
    "https://router.project-osrm.org"
)
TILE_URL = os.getenv(
    "TILE_URL",
    "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
)

DATABASE_PATH = os.getenv("SWIFTROUTE_DB", "swiftroute.db")
MAX_POINTS_REQUETE = 500

app = FastAPI(
    title="SwiftRoute Engine - AntStrike Advanced VRP",
    version="2.6",
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
        CREATE TABLE IF NOT EXISTS cities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            lat REAL NOT NULL,
            lon REAL NOT NULL
        )
    """)

    villes_haiti = [
        ("Cap-Haïtien", 19.7595, -72.1983),
        ("Port-au-Prince", 18.5944, -72.3074),
        ("Gonaïves", 19.4476, -72.6893),
        ("Saint-Marc", 19.1082, -72.6938),
        ("Port-de-Paix", 19.9539, -72.8327),
        ("Jacmel", 18.2344, -72.5355),
        ("Les Cayes", 18.1942, -73.7510),
        ("Hinche", 19.1431, -72.0088),
        ("Mirebalais", 18.8346, -72.1045),
        ("Fort-Liberté", 19.6627, -71.8370),
        ("Ouanaminthe", 19.5496, -71.7240),
        ("Limbé", 19.7058, -72.4037),
        ("Trou-du-Nord", 19.6187, -72.0215),
        ("Limonade", 19.6707, -72.1253),
        ("Carrefour", 18.5411, -72.3992),
        ("Pétion-Ville", 18.5120, -72.2852),
        ("Delmas", 18.5470, -72.3020),
        ("Croix-des-Bouquets", 18.5760, -72.2260),
        ("Kenscoff", 18.4477, -72.2840),
        ("Léogâne", 18.5108, -72.6334),
        ("Petit-Goâve", 18.4317, -72.8667),
        ("Grand-Goâve", 18.4286, -72.7720),
        ("Miragoâne", 18.4450, -73.0890),
        ("Anse-à-Veau", 18.4900, -73.0450),
        ("Jérémie", 18.6500, -74.1167),
        ("Port-Salut", 18.0670, -73.9250),
        ("Cavaillon", 18.3000, -73.6500),
        ("Aquin", 18.2790, -73.3940),
        ("Maïssade", 19.1760, -72.1470),
        ("Saint-Raphaël", 19.4380, -72.1980),
    ]

    conn.executemany(
        "INSERT OR IGNORE INTO cities (name, lat, lon) VALUES (?, ?, ?)",
        villes_haiti
    )

    conn.execute("""
        CREATE TABLE IF NOT EXISTS geocodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            lat REAL NOT NULL,
            lon REAL NOT NULL,
            created_at TEXT NOT NULL
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
# SECURITY
# ==============================================================================

def hash_value(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_email(email: str) -> str:
    return email.strip().lower()


def get_client_ip(request: Request) -> str:
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
            "Accès commercial"
            if trial
            else f"Accès commercial {duration_days} Jours"
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
        WHERE session_id = ? AND active = 1
        """,
        (session_id,)
    ).fetchone()
    conn.close()

    if not row:
        return None

    try:
        expiration = datetime.datetime.fromisoformat(row["expires_at"])
    except ValueError:
        return None

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
# TIUN SERVER-SIDE VERIFICATION
# ==============================================================================

def verify_tiun_user_verification_token(token: str):
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Tiun verification token manquant."
        )

    if not TIUN_SECRET_KEY:
        raise HTTPException(
            status_code=503,
            detail="TIUN_API_KEY/TIUN_SECRET_KEY n'est pas configurée sur le serveur."
        )

    url = (
        TIUN_API_BASE.rstrip("/")
        + "/live_api/s2s/v1/users/verification"
    )

    request = URLRequest(
        url,
        method="POST",
        headers={
            "X-TIUN-API-KEY": TIUN_SECRET_KEY,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        data=json.dumps({
            "userVerificationToken": token
        }).encode("utf-8")
    )

    try:
        with urlopen(request, timeout=15) as response:
            status = response.status
            raw = response.read().decode("utf-8")
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Impossible de vérifier la session Tiun : {exc}"
        )

    if status != 200:
        raise HTTPException(
            status_code=401,
            detail="Session Tiun invalide ou expirée."
        )

    try:
        user = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=502,
            detail="Réponse Tiun invalide."
        )

    if not user.get("isAuthenticated"):
        raise HTTPException(
            status_code=401,
            detail="Utilisateur Tiun non authentifié."
        )

    return user


@app.get("/api/protected")
async def api_protected(
    request: Request
):
    """
    Vérifie le userVerificationToken Tiun envoyé par le navigateur.

    Le secret TIUN_API_KEY reste uniquement côté serveur.
    """
    auth = request.headers.get("authorization", "")
    token = (
        auth[7:].strip()
        if auth.startswith("Bearer ")
        else None
    )

    user = verify_tiun_user_verification_token(token)

    return {
        "success": True,
        "isAuthenticated": True,
        "userInfo": user.get("userInfo"),
    }


# ==============================================================================
# GEOCODING
# ==============================================================================

def normalize_city_name(value: str) -> str:
    value = value.strip().lower()
    replacements = {
        "cap haitien": "cap-haïtien",
        "cap-haitien": "cap-haïtien",
        "port au prince": "port-au-prince",
        "port au-prince": "port-au-prince",
        "port de paix": "port-de-paix",
        "petit goave": "petit-goâve",
        "grand goave": "grand-goâve",
        "petit-goave": "petit-goâve",
        "grand-goave": "grand-goâve",
    }
    return replacements.get(value, value)


def get_city(name: str):
    normalized = normalize_city_name(name)

    conn = db_connect()
    row = conn.execute(
        "SELECT name, lat, lon FROM cities WHERE lower(name) = ?",
        (normalized,)
    ).fetchone()

    if not row:
        rows = conn.execute(
            "SELECT name, lat, lon FROM cities"
        ).fetchall()

        def clean(v):
            v = unicodedata.normalize("NFKD", v.lower())
            return "".join(
                c for c in v
                if not unicodedata.combining(c)
            ).replace("-", " ").strip()

        target = clean(name)

        for candidate in rows:
            if clean(candidate["name"]) == target:
                row = candidate
                break

    conn.close()
    return row


def get_cached_geocode(query: str):
    conn = db_connect()
    row = conn.execute(
        """
        SELECT display_name, lat, lon
        FROM geocodes
        WHERE query = ?
        """,
        (query.strip().lower(),)
    ).fetchone()
    conn.close()
    return row


def save_geocode(query, display_name, lat, lon):
    conn = db_connect()
    conn.execute(
        """
        INSERT OR REPLACE INTO geocodes
        (query, display_name, lat, lon, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            query.strip().lower(),
            display_name,
            float(lat),
            float(lon),
            datetime.datetime.now(
                datetime.timezone.utc
            ).isoformat()
        )
    )
    conn.commit()
    conn.close()


_last_geocode_request = 0.0


def geocode_global(query: str):
    global _last_geocode_request

    query = query.strip()

    if not query:
        raise HTTPException(
            status_code=400,
            detail="Recherche vide."
        )

    city = get_city(query)

    if city:
        return {
            "name": city["name"],
            "display_name": city["name"],
            "lat": float(city["lat"]),
            "lon": float(city["lon"]),
            "source": "base_locale"
        }

    cached = get_cached_geocode(query)

    if cached:
        return {
            "name": query,
            "display_name": cached["display_name"],
            "lat": float(cached["lat"]),
            "lon": float(cached["lon"]),
            "source": "cache"
        }

    wait = 1.0 - (
        time.time() - _last_geocode_request
    )

    if wait > 0:
        time.sleep(wait)

    params = (
        "?q=" + quote(query)
        + "&format=jsonv2&limit=1&addressdetails=1"
    )

    request = URLRequest(
        GEOCODING_URL + params,
        headers={
            "User-Agent": GEOCODING_USER_AGENT
        }
    )

    try:
        _last_geocode_request = time.time()

        with urlopen(request, timeout=12) as response:
            results = json.loads(
                response.read().decode("utf-8")
            )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "Le service de recherche mondiale est "
                f"temporairement indisponible: {exc}"
            )
        )

    if not results:
        raise HTTPException(
            status_code=404,
            detail=f"Aucun lieu trouvé pour : {query}"
        )

    item = results[0]

    lat = float(item["lat"])
    lon = float(item["lon"])
    display_name = item.get(
        "display_name",
        query
    )

    save_geocode(
        query,
        display_name,
        lat,
        lon
    )

    return {
        "name": query,
        "display_name": display_name,
        "lat": lat,
        "lon": lon,
        "source": "geocodage_mondial"
    }


@app.get("/api/cities")
async def api_cities():
    conn = db_connect()
    rows = conn.execute(
        """
        SELECT name, lat, lon
        FROM cities
        ORDER BY name
        """
    ).fetchall()
    conn.close()

    return {
        "cities": [dict(row) for row in rows]
    }


@app.get("/api/city")
async def api_city(name: str):
    row = get_city(name)

    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"Ville inconnue : {name}"
        )

    return {
        "name": row["name"],
        "lat": row["lat"],
        "lon": row["lon"]
    }


@app.get("/api/geocode")
async def api_geocode(q: str):
    return geocode_global(q)


class PointGPS(BaseModel):
    name: str = "Point"
    lat: float
    lon: float


class RequetePoints(BaseModel):
    points: List[PointGPS]


@app.post("/api/geocode-batch")
async def api_geocode_batch(
    requete: RequetePoints
):
    if len(requete.points) > 25:
        raise HTTPException(
            status_code=400,
            detail=(
                "Le géocodage par adresse est limité "
                "à 25 recherches par opération."
            )
        )

    results = []

    for point in requete.points:
        result = geocode_global(point.name)
        results.append({
            **result,
            "input": point.name
        })

    return {"results": results}


# ==============================================================================
# HOME
# ==============================================================================

@app.get("/", response_class=HTMLResponse)
async def page_accueil_serveur():
    return HTMLResponse(f"""
<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SwiftRoute Engine</title>
<style>
body{{margin:0;background:#0c0a09;color:#f5f5f4;font-family:Arial,sans-serif}}
.nav{{max-width:1150px;margin:auto;padding:20px;display:flex;justify-content:space-between;gap:15px;flex-wrap:wrap}}
a{{color:inherit;text-decoration:none}}
.links{{display:flex;gap:10px;flex-wrap:wrap}}
.link,.btn{{padding:11px 15px;border-radius:9px}}
.link{{color:#a8a29e}}
.btn{{background:#f59e0b;color:#0c0a09;font-weight:bold}}
.hero{{text-align:center;padding:85px 20px;background:linear-gradient(#1c1917,#0c0a09)}}
.hero h1{{font-size:clamp(35px,7vw,60px)}}
.hero p{{max-width:720px;margin:20px auto 30px;color:#a8a29e;line-height:1.6}}
.cards{{max-width:1050px;margin:auto;padding:55px 20px;display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:20px}}
.card{{background:#1c1917;border:1px solid #2e2a24;border-radius:14px;padding:25px}}
.card h3{{color:#f59e0b}}
</style>
</head>
<body>
<div class="nav">
<strong>🐜 SwiftRoute Engine</strong>
<div class="links">
<a class="link" href="/docs">Documentation</a>
<a class="link" href="/workspace">Espace client</a>
<a class="btn" href="/visiteur">Visiteur</a>
</div>
</div>

<section class="hero">
<div style="color:#f59e0b;font-weight:bold">
GLOBAL ROUTE OPTIMIZATION INFRASTRUCTURE
</div>
<h1>SWIFTROUTE ENGINE</h1>
<p>
Optimisation de routes et de tournées avec recherche mondiale,
coordonnées GPS, import CSV et tracé routier.
</p>
<a class="btn" href="/workspace">🔑 Accéder à mon espace client</a>
</section>

<div class="cards">
<div class="card">
<h3>🚗 Conducteur</h3>
<p>Préparez les points et visualisez l'itinéraire sur une carte.</p>
</div>
<div class="card">
<h3>👨‍💻 Développeur</h3>
<p>API FastAPI avec authentification par clé X-API-KEY.</p>
</div>
<div class="card">
<h3>🌍 International</h3>
<p>Recherche mondiale d'adresses et de coordonnées GPS.</p>
</div>
</div>
</body>
</html>
""")


# ==============================================================================
# COMMERCIAL ACCESS / CLIENT LOGIN
# ==============================================================================

@app.get("/workspace/login", response_class=HTMLResponse)
async def workspace_login_page():
    return HTMLResponse("""
<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SwiftRoute — Espace client</title>
<style>
*{box-sizing:border-box}
body{margin:0;min-height:100vh;background:radial-gradient(circle at 70% -10%,#21190d 0,#09090b 45%);color:#f4f4f5;font-family:Inter,Arial,sans-serif;display:grid;place-items:center;padding:20px}
.box{width:min(520px,100%);background:linear-gradient(180deg,#17171a,#101012);border:1px solid #2b2b30;border-radius:24px;padding:28px;box-shadow:0 25px 70px #0008}
.logo{font-size:24px;font-weight:900;margin-bottom:22px}.accent{color:#f59e0b}
h1{font-size:clamp(28px,6vw,42px);margin:0 0 8px;letter-spacing:-1.5px}p{color:#a1a1aa;line-height:1.6}
label{display:block;margin:20px 0 7px;font-weight:800}input{width:100%;padding:14px;border-radius:13px;border:1px solid #3f3f46;background:#09090b;color:#fff;font-size:15px;outline:none}input:focus{border-color:#f59e0b;box-shadow:0 0 0 3px #f59e0b18}
button,a.btn{display:block;width:100%;margin-top:14px;padding:14px;border:0;border-radius:13px;background:linear-gradient(135deg,#fbbf24,#f59e0b);color:#0c0a09;font-weight:900;text-align:center;text-decoration:none;cursor:pointer}
a.secondary{display:block;text-align:center;color:#d4d4d8;text-decoration:none;margin-top:14px;padding:12px;border:1px solid #303036;border-radius:13px}
.note{margin-top:18px;padding:13px;border:1px solid #2b2b30;border-radius:13px;background:#0d0d10;font-size:13px}
</style>
</head>
<body>
<div class="box">
<div class="logo">🐜 SwiftRoute <span class="accent">Commercial</span></div>
<h1>Espace client</h1>
<p>Vous avez déjà une clé API ? Entrez-la pour ouvrir votre espace. Si vous n'en avez pas, passez par votre abonnement commercial.</p>
<form action="/workspace/login" method="post">
<label for="api_key">Clé API</label>
<input id="api_key" name="api_key" type="password" autocomplete="off" placeholder="Votre clé API SwiftRoute" required>
<button type="submit">🔓 Ouvrir mon espace</button>
</form>
<a class="btn" href="/visiteur">💳 Je n'ai pas encore de clé — Voir l'abonnement</a>
<div class="note">La clé n'est pas affichée dans l'URL et la session navigateur utilise un cookie HttpOnly.</div>
<a class="secondary" href="/">← Retour à l'accueil</a>
</div>
</body>
</html>
""")


@app.post("/workspace/login")
async def workspace_login(api_key: str = Form(...)):
    api_key = api_key.strip()
    if not api_key:
        return RedirectResponse("/workspace/login", status_code=303)

    try:
        infos = verify_token(api_key)
    except HTTPException:
        return HTMLResponse(
            "<h2>Clé API invalide ou expirée.</h2><a href=\"/workspace/login\">Réessayer</a>",
            status_code=401
        )

    expiration_ts = infos.get("exp")
    if not expiration_ts:
        return HTMLResponse(
            "<h2>La clé API ne contient pas de date d'expiration.</h2><a href=\"/workspace/login\">Réessayer</a>",
            status_code=401
        )

    expiration = datetime.datetime.fromtimestamp(
        int(expiration_ts), datetime.timezone.utc
    )
    if expiration <= datetime.datetime.now(datetime.timezone.utc):
        return HTMLResponse(
            "<h2>Cette clé API est expirée.</h2><a href=\"/workspace/login\">Réessayer</a>",
            status_code=401
        )

    session_id = create_session(
        infos.get("client", "Client"),
        infos.get("email"),
        infos.get("jti"),
        expiration
    )

    response = RedirectResponse("/workspace", status_code=303)
    max_age = max(60, int((expiration - datetime.datetime.now(datetime.timezone.utc)).total_seconds()))
    response.set_cookie(
        key="swiftroute_session",
        value=session_id,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=max_age
    )
    return response


@app.get("/visiteur", response_class=HTMLResponse)
async def page_visiteur():
    return HTMLResponse(f"""
<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SwiftRoute — Visiteur</title>
<style>
*{{box-sizing:border-box}}
body{{margin:0;background:radial-gradient(circle at 70% -10%,#21190d 0,#09090b 45%);color:#f4f4f5;font-family:Inter,Arial,sans-serif}}
.wrap{{width:min(1120px,92%);margin:auto;padding:28px 0 60px}}
.nav{{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:45px}}
.logo{{font-weight:900;font-size:22px}}.accent{{color:#f59e0b}}
.nav a{{color:#d4d4d8;text-decoration:none;padding:10px 13px;border:1px solid #303036;border-radius:11px}}
.hero{{padding:55px 0 35px}}h1{{font-size:clamp(42px,8vw,82px);line-height:.95;letter-spacing:-4px;margin:0 0 18px}}
.hero p{{max-width:720px;color:#a1a1aa;font-size:18px;line-height:1.7}}
.actions{{display:flex;gap:10px;flex-wrap:wrap;margin-top:25px}}
.btn{{padding:13px 17px;border-radius:12px;text-decoration:none;font-weight:900;background:#f59e0b;color:#0c0a09}}
.btn.secondary{{background:#18181b;color:#f4f4f5;border:1px solid #303036}}
.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-top:35px}}
.card{{padding:22px;border:1px solid #27272a;border-radius:18px;background:linear-gradient(180deg,#151518,#111113);min-height:150px}}
.card h3{{margin-top:0}}.muted{{color:#a1a1aa;line-height:1.6}}
@media(max-width:760px){{.grid{{grid-template-columns:1fr}}h1{{letter-spacing:-2px}}}}
</style>
</head>
<body>
<div class="wrap">
<div class="nav"><div class="logo">🐜 SwiftRoute <span class="accent">Commercial</span></div><div><a href="/">Accueil</a> <a href="/workspace">Espace client</a></div></div>
<section class="hero">
<div class="accent"><strong>VISITEUR · ANTSTRIKE COMMERCIAL</strong></div>
<h1>Optimisez vos routes. Visualisez. Décidez.</h1>
<p>SwiftRoute combine recherche mondiale, coordonnées GPS, import CSV, optimisation de tournées et visualisation cartographique dans une interface SaaS pensée pour un usage professionnel.</p>
<div class="actions"><a class="btn" href="/workspace">🔑 J'ai déjà une clé API</a><a class="btn secondary" href="/">← Retour</a></div>
</section>
<div class="grid">
<div class="card"><h3>🌍 Recherche mondiale</h3><p class="muted">Recherchez une ville ou une adresse puis visualisez ses coordonnées.</p></div>
<div class="card"><h3>🗺️ Carte interactive</h3><p class="muted">Visualisez les points et le tracé routier directement sur la carte.</p></div>
<div class="card"><h3>🔐 Accès commercial</h3><p class="muted">L'accès à l'espace de calcul est réservé aux utilisateurs disposant d'une clé API active.</p></div>
</div>
</div>
</body>
</html>
""")


@app.get("/essai-gratuit")
async def legacy_trial_redirect():
    # Ancienne URL conservée uniquement pour éviter les liens cassés; aucun essai n'est créé.
    return RedirectResponse("/workspace", status_code=303)


# ==============================================================================
# AUTHENTICATION FOR BOTH BROWSER AND DEVELOPER API
# ==============================================================================

async def verifier_acces(
    request: Request,
    api_key: str = Security(api_key_header),
    swiftroute_session: str = Cookie(default=None)
):
    """
    Deux chemins :
    1. Développeur : X-API-KEY contenant le JWT SwiftRoute.
    2. Navigateur : cookie HttpOnly de session créé par l'essai.
    """

    if api_key:
        return verify_token(api_key)

    session = get_session(swiftroute_session)

    if session:
        return {
            "client": session["client_name"],
            "email": session["email"],
            "jti": session["token_jti"],
            "trial": False,
            "type_offre": "Accès commercial"
        }

    raise HTTPException(
        status_code=401,
        detail="Authentification requise."
    )


# ==============================================================================
# WORKSPACE
# ==============================================================================

@app.get("/workspace", response_class=HTMLResponse)
async def workspace(
    swiftroute_session: str = Cookie(default=None)
):
    session = get_session(swiftroute_session)

    if not session:
        return RedirectResponse(
            "/workspace/login",
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
<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SwiftRoute — Workspace</title>

<link
rel="stylesheet"
href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
/>

<style>
*{{box-sizing:border-box}}
:root{{--bg:#09090b;--panel:#111113;--panel2:#151518;--line:#27272a;--muted:#a1a1aa;--accent:#f59e0b;--ok:#22c55e}}
html{{scroll-behavior:smooth}}
body{{margin:0;background:radial-gradient(circle at 70% -10%,#1b1710 0,#09090b 42%);color:#f4f4f5;font-family:Inter,Arial,sans-serif}}
.side-rail{{position:fixed;left:0;top:0;bottom:0;width:68px;background:#0b0b0d;border-right:1px solid var(--line);z-index:1100;display:flex;flex-direction:column;align-items:center;padding:14px 8px;gap:10px}} .menu-toggle{{position:fixed;left:16px;top:14px;width:48px;height:48px;border:1px solid #3f3f46;border-radius:15px;background:#18181b;color:#fff;z-index:1300;font-size:23px;cursor:pointer;box-shadow:0 12px 30px #0006}}
.menu-overlay{{position:fixed;inset:0;background:#0008;backdrop-filter:blur(3px);z-index:1050;display:none}}
.menu-overlay.open{{display:block}}
.rail-head{{width:100%;display:flex;align-items:center;justify-content:space-between;margin-bottom:12px}}
.rail-close{{border:0;background:transparent;color:#a1a1aa;font-size:28px;cursor:pointer}}
.rail-btn span{{display:none}}
.side-rail.open{{width:230px;align-items:stretch;padding:14px 12px}}
.side-rail.open .rail-btn{{width:100%;justify-content:flex-start;display:flex;align-items:center;gap:13px;padding:0 13px}}
.side-rail.open .rail-btn span{{display:inline;font-size:14px;font-weight:800}}

.rail-logo{{font-size:25px;margin:2px 0 12px}}
.rail-btn{{width:48px;height:48px;border:1px solid transparent;border-radius:14px;background:transparent;color:#d4d4d8;font-size:20px;cursor:pointer;display:grid;place-items:center;transition:.18s}}
.rail-btn:hover,.rail-btn.active{{background:#18181b;border-color:#3f3f46;color:var(--accent);transform:translateY(-1px)}}
.top{{position:sticky;top:0;z-index:1000;margin-left:0;padding:13px 22px;background:#0c0c0eee;backdrop-filter:blur(12px);border-bottom:1px solid var(--line);display:flex;justify-content:space-between;gap:15px;align-items:center}}
.container{{max-width:1420px;margin:auto;padding:18px 18px 50px}}
.card{{background:linear-gradient(180deg,#151518,#111113);border:1px solid var(--line);border-radius:18px;padding:20px;margin-bottom:18px;box-shadow:0 10px 30px #00000025}}
.card h1{{font-size:clamp(26px,4vw,42px);letter-spacing:-1.5px;margin:0 0 8px}}
.card h2{{letter-spacing:-.5px}}
.muted,.small{{color:var(--muted)}}
.small{{font-size:12px;line-height:1.5}}
.orange{{color:var(--accent)}}
.green{{color:var(--ok)}}
.row{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
.toolbar{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}}
.mode,.secondary{{background:#18181b;color:#f4f4f5;border:1px solid #303036;padding:10px 11px;border-radius:12px;cursor:pointer;font-weight:700;font-size:14px;min-height:42px;transition:.18s}}
.mode:hover,.secondary:hover{{border-color:#52525b;transform:translateY(-1px)}}
.mode.active{{border-color:var(--accent);color:var(--accent);background:#1c170e}}
.panel{{display:none;margin-top:16px}}
.panel.active{{display:block;animation:fadeIn .2s ease}}
@keyframes fadeIn{{from{{opacity:0;transform:translateY(4px)}}to{{opacity:1;transform:none}}}}
label{{display:block;margin:11px 0 6px;font-weight:700;font-size:14px}}
input,textarea,select{{width:100%;padding:11px 12px;background:#0c0c0f;color:white;border:1px solid #35353b;border-radius:11px;font-size:15px;outline:none}}
input:focus,textarea:focus,select:focus{{border-color:var(--accent);box-shadow:0 0 0 3px #f59e0b18}}
button.action{{width:100%;padding:13px;margin-top:13px;background:linear-gradient(135deg,#fbbf24,#f59e0b);color:#0c0a09;border:0;border-radius:12px;font-weight:850;font-size:15px;cursor:pointer;box-shadow:0 8px 22px #f59e0b20}}
button.action:disabled{{opacity:.6}}
.controls{{display:flex;gap:8px;flex-wrap:wrap;margin-top:11px}}
.controls>*{{flex:1;min-width:145px}}
.search-box{{display:grid;grid-template-columns:1fr 118px;gap:8px}}
.search-results{{display:none;background:#0d0d10;border:1px solid #35353b;border-radius:12px;margin-top:7px;overflow:hidden;box-shadow:0 15px 30px #0006}}
.search-results button{{display:block;width:100%;padding:11px;text-align:left;background:transparent;color:white;border:0;border-bottom:1px solid var(--line);cursor:pointer}}
.search-results button:hover{{background:#18181b}}
.gps-row{{display:grid;grid-template-columns:36px 1fr 1fr 1.5fr 42px;gap:7px;align-items:center;margin-bottom:7px}}
.gps-row input{{margin:0}}
.number{{color:var(--accent);text-align:center;font-weight:800}}
.remove{{background:#18181b;color:#ef4444;border:1px solid #3f3f46;border-radius:10px;height:42px}}
#map{{height:clamp(430px,62vh,720px);border-radius:15px;border:1px solid #35353b;overflow:hidden;box-shadow:inset 0 0 0 1px #0005}}
.map-card{{padding-bottom:12px}}
.result{{display:none;margin-top:16px;padding:18px;border:1px solid #303036;border-radius:16px;background:linear-gradient(180deg,#141416,#101012);box-shadow:0 14px 35px #0004}}
.result-title{{display:flex;justify-content:space-between;gap:12px;align-items:center;flex-wrap:wrap}}
.result-title h3{{margin:0;font-size:20px}}
.result-sub{{color:var(--muted);font-size:13px;margin-top:5px}}
.stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:9px;margin-top:14px}}
.stat{{background:#0d0d10;border:1px solid #2b2b30;border-radius:14px;padding:13px;text-align:left;min-height:72px}}
.stat span{{display:block;color:#a1a1aa;font-size:12px;margin-bottom:5px}}
.stat strong{{display:block;font-size:21px;color:#f4f4f5}}
.stat.accent strong{{color:var(--accent)}}
.route-list{{max-height:290px;overflow:auto;margin-top:12px;padding:0;list-style:none}}
.route-list li{{padding:10px 12px;border-bottom:1px solid var(--line);display:flex;gap:10px;align-items:center}}
.route-list .step{{width:28px;height:28px;border-radius:9px;background:#1d1d21;color:var(--accent);display:grid;place-items:center;font-size:12px;font-weight:800;flex:none}}
.coord{{font-family:monospace;color:var(--accent)}}
.file{{padding:12px;border:1px dashed #44403c;border-radius:11px;background:#0d0d10}}
.section-head{{display:flex;justify-content:space-between;align-items:end;gap:10px;margin-bottom:12px}}
.badge{{display:inline-flex;align-items:center;gap:6px;padding:6px 9px;border-radius:999px;background:#1a1a1d;border:1px solid #303036;color:#d4d4d8;font-size:12px}}
@media(max-width:850px){{
.side-rail{{width:230px;transform:translateX(-105%);transition:transform .22s ease;align-items:stretch;padding:14px 12px}}
.side-rail.open{{transform:translateX(0)}}
.rail-btn{{width:100%;justify-content:flex-start;display:flex;align-items:center;gap:13px;padding:0 13px}}
.rail-btn span{{display:inline;font-size:14px;font-weight:800}}
.top{{margin-left:0;padding:11px 12px 11px 76px}}
.container{{margin-left:0;padding:12px 9px 38px}}
.toolbar{{grid-template-columns:repeat(3,1fr)}}
.row,.stats{{grid-template-columns:1fr 1fr}}
}}
@media(max-width:620px){{
.toolbar{{grid-template-columns:1fr 1fr 1fr}}
.row,.stats{{grid-template-columns:1fr 1fr}}
.stats .stat{{padding:11px}}
.search-box{{grid-template-columns:1fr}}
#map{{height:56vh;min-height:390px}}
}}
</style>
</head>

<body>

<button class="menu-toggle" id="menu-toggle" aria-label="Ouvrir le menu" aria-expanded="false">☰</button>
<div class="menu-overlay" id="menu-overlay"></div>
<nav class="side-rail" id="side-rail" aria-label="Navigation principale">
  <div class="rail-head"><div class="rail-logo">🐜</div><button class="rail-close" id="rail-close" aria-label="Fermer">×</button></div>
  <button class="rail-btn active" title="Accueil" onclick="goSection('home')">⌂<span>Accueil</span></button>
  <button class="rail-btn" title="Optimisation" onclick="goSection('optimization')">⚡<span>Optimisation</span></button>
  <button class="rail-btn" title="Carte" onclick="goSection('map')">🗺️<span>Carte</span></button>
  <button class="rail-btn" title="Résultats" onclick="goSection('result')">▥<span>Résultats</span></button>
  <a class="rail-btn" title="Visiteur" href="/visiteur">👤<span>Visiteur</span></a>
  <a class="rail-btn" title="Espace client" href="/workspace">🔑<span>Espace client</span></a>
</nav>

<div class="top">
<strong>🐜 SwiftRoute Engine — Global Planner</strong>
<span class="green">● Session active</span>
</div>

<div class="container">

<div class="card" id="home">
<h1>🌍 Planificateur de routes international</h1>
<p class="muted">
Bonjour {session["client_name"]}. Recherche une adresse,
utilise des coordonnées GPS ou importe un CSV.
</p>
<p class="small">
Compte commercial : {email} · Expiration de la clé :
<span class="orange">{expiration_display}</span>
</p>
</div>

<div class="card">
<h3>💳 Abonnement et assistance</h3>
<p class="muted">
Accès commercial · Produit : <span class="coord">{TIUN_PRODUCT_ID}</span>
</p>
<div class="controls">
<a class="secondary"
href="https://wa.me/50941817761"
target="_blank"
rel="noopener"
style="text-decoration:none;text-align:center">
WhatsApp : {WHATSAPP_CONTACT}
</a>
<a class="secondary"
href="mailto:{EMAIL_CONTACT}"
style="text-decoration:none;text-align:center">
E-mail : {EMAIL_CONTACT}
</a>
</div>
</div>

<div class="card" id="optimization">

<h2>1. Choisir le type de données</h2>

<div class="toolbar">
<button class="mode active" data-mode="search">
📍 Recherche mondiale
</button>
<button class="mode" data-mode="gps">
🌐 Coordonnées GPS
</button>
<button class="mode" data-mode="csv">
📄 Import CSV
</button>
</div>

<div id="panel-search" class="panel active">
<p class="muted">
Recherche une ville ou une adresse. Le serveur convertit
automatiquement le résultat en latitude/longitude.
</p>

<div class="row">

<div>
<label>Départ</label>
<div class="search-box">
<input id="depart-search" placeholder="Cap-Haïtien, Haiti">
<button class="secondary" id="btn-depart">Rechercher</button>
</div>
<div id="depart-results" class="search-results"></div>
</div>

<div>
<label>Destination</label>
<div class="search-box">
<input id="destination-search" placeholder="Port-au-Prince, Haiti">
<button class="secondary" id="btn-destination">Rechercher</button>
</div>
<div id="destination-results" class="search-results"></div>
</div>

</div>

<label>Arrêt intermédiaire</label>
<div class="search-box">
<input id="stop-search" placeholder="Paris, France / Nairobi, Kenya...">
<button class="secondary" id="btn-stop">Ajouter</button>
</div>
<div id="stop-results" class="search-results"></div>

<div id="search-points" class="small" style="margin-top:12px"></div>
</div>

<div id="panel-gps" class="panel">
<p class="muted">
Pour de nombreux points, utilise directement les coordonnées GPS.
</p>

<div id="gps-rows"></div>

<div class="controls">
<button class="secondary" id="btn-add-point">
＋ Ajouter un point
</button>
<button class="secondary" id="btn-add-500">
＋ Préparer 500 points
</button>
</div>
</div>

<div id="panel-csv" class="panel">
<p class="muted">
CSV : <strong>name,lat,lon</strong>.
Limite de traitement selon votre clé API et les ressources disponibles.
</p>

<div class="file">
<input id="csv-file" type="file" accept=".csv,text/csv">
</div>

<p id="csv-status" class="small"></p>
</div>

<div class="controls">
<button id="btn-route" class="action">
🚀 Optimiser et afficher sur la carte
</button>
<button class="secondary" id="btn-clear">
Effacer
</button>
</div>

<div id="result" class="result"></div>

</div>

<div class="card" id="map-section">
<h2>2. Carte routière</h2>
<div id="map"></div>
<p class="small">
La ligne affichée correspond au tracé routier fourni par le
service de routage configuré.
</p>
</div>

</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>

<script type="module">
import {{ tiun }} from 'https://esm.sh/@tiun/sdk';

tiun.init({{
    snippetId: '{TIUN_SNIPPET_ID}',
    language: 'fr'
}});

window.tiunInstance = tiun;
</script>

<script>
"use strict";

let map = null;
let routeLayer = null;
let markers = [];
let currentMode = "search";

let searchPoints = {{
    depart: null,
    destination: null,
    stops: []
}};

let gpsPoints = [];

function setMenu(open) {{
    const rail = document.getElementById("side-rail");
    const overlay = document.getElementById("menu-overlay");
    const toggle = document.getElementById("menu-toggle");
    rail.classList.toggle("open", open);
    overlay.classList.toggle("open", open);
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
}}

function goSection(name) {{
    const target = name === "map" ? "map-section" : name;
    document.getElementById(target)?.scrollIntoView({{behavior:"smooth", block:"start"}});
    setMenu(false);
}}

function initMap() {{
    if (!window.L) {{
        throw new Error("Leaflet n'a pas pu être chargé.");
    }}

    map = L.map("map").setView([19.7595, -72.1983], 8);

    L.tileLayer(
        "{TILE_URL}",
        {{
            maxZoom: 19,
            attribution: "&copy; OpenStreetMap contributors"
        }}
    ).addTo(map);

    setTimeout(() => map.invalidateSize(), 300);
}}

document.addEventListener("DOMContentLoaded", () => {{
    try {{
        initMap();
        initButtons();
        document.getElementById("menu-toggle").addEventListener("click", () => setMenu(true));
        document.getElementById("rail-close").addEventListener("click", () => setMenu(false));
        document.getElementById("menu-overlay").addEventListener("click", () => setMenu(false));

        ajouterLigne({{
            name: "Départ",
            lat: "",
            lon: ""
        }});

        ajouterLigne({{
            name: "Destination",
            lat: "",
            lon: ""
        }});
    }} catch (error) {{
        console.error(error);
        afficherErreur(
            "La carte n'a pas pu être initialisée : "
            + error.message
        );
    }}
}});

function esc(value) {{
    return String(value ?? "").replace(
        /[&<>'"]/g,
        c => ({{
            "&":"&amp;",
            "<":"&lt;",
            ">":"&gt;",
            "'":"&#39;",
            '"':"&quot;"
        }}[c])
    );
}}

function initButtons() {{
    document.querySelectorAll(".mode").forEach(button => {{
        button.addEventListener("click", () => {{
            changerMode(button.dataset.mode);
        }});
    }});

    document.getElementById("btn-depart")
        .addEventListener("click", () => chercherEtAjouter("depart"));

    document.getElementById("btn-destination")
        .addEventListener("click", () => chercherEtAjouter("destination"));

    document.getElementById("btn-stop")
        .addEventListener("click", () => chercherEtAjouter("stop"));

    document.getElementById("btn-add-point")
        .addEventListener("click", () => ajouterLigne());

    document.getElementById("btn-add-500")
        .addEventListener("click", ajouter500);

    document.getElementById("btn-route")
        .addEventListener("click", optimiser);

    document.getElementById("btn-clear")
        .addEventListener("click", effacerTout);

    document.getElementById("csv-file")
        .addEventListener("change", importerCSV);
}}

function changerMode(name) {{
    currentMode = name;

    document.querySelectorAll(".mode").forEach(button => {{
        button.classList.toggle(
            "active",
            button.dataset.mode === name
        );
    }});

    document.querySelectorAll(".panel").forEach(panel => {{
        panel.classList.remove("active");
    }});

    document
        .getElementById("panel-" + name)
        .classList.add("active");

    setTimeout(() => {{
        if (map) map.invalidateSize();
    }}, 100);
}}

async function getTiunVerificationToken() {{
    try {{
        if (
            window.tiunInstance &&
            typeof window.tiunInstance.getUserVerificationToken === "function"
        ) {{
            return await window.tiunInstance.getUserVerificationToken();
        }}
    }} catch (error) {{
        console.warn("Tiun token:", error);
    }}

    return null;
}}

async function fetchProtectedData() {{
    const token = await getTiunVerificationToken();

    if (!token) {{
        return null;
    }}

    const response = await fetch("/api/protected", {{
        headers: {{
            Authorization: "Bearer " + token
        }}
    }});

    if (!response.ok) {{
        return null;
    }}

    return await response.json();
}}

async function apiFetch(url, options = {{}}) {{
    const config = {{
        ...options,
        headers: {{
            ...(options.headers || {{}})
        }}
    }};

    /*
      Le navigateur utilise son cookie HttpOnly SwiftRoute.
      Pour un compte Tiun, on vérifie aussi la session Tiun
      avant les opérations sensibles.
    */
    const tiunUser = await fetchProtectedData();

    if (tiunUser) {{
        config.headers["X-TIUN-AUTHENTICATED"] = "true";
    }}

    return fetch(url, config);
}}

async function chercherEtAjouter(type) {{
    const inputId =
        type === "depart"
        ? "depart-search"
        : type === "destination"
        ? "destination-search"
        : "stop-search";

    const resultId =
        type === "depart"
        ? "depart-results"
        : type === "destination"
        ? "destination-results"
        : "stop-results";

    const input = document.getElementById(inputId);
    const box = document.getElementById(resultId);
    const q = input.value.trim();

    if (!q) {{
        box.style.display = "block";
        box.innerHTML =
            '<span style="display:block;padding:10px;color:#f59e0b">'
            + "Écris un lieu."
            + "</span>";
        return;
    }}

    box.style.display = "block";
    box.innerHTML = "Recherche en cours...";

    try {{
        const response = await fetch(
            "/api/geocode?q=" + encodeURIComponent(q)
        );

        const data = await response.json();

        if (!response.ok) {{
            throw new Error(
                data.detail || "Lieu introuvable."
            );
        }}

        const point = {{
            name: data.display_name || q,
            lat: Number(data.lat),
            lon: Number(data.lon)
        }};

        if (type === "depart") {{
            searchPoints.depart = point;
        }} else if (type === "destination") {{
            searchPoints.destination = point;
        }} else {{
            searchPoints.stops.push(point);
        }}

        box.innerHTML =
            '<button type="button" class="selected-result">'
            + "✓ "
            + esc(point.name)
            + " — "
            + point.lat.toFixed(5)
            + ", "
            + point.lon.toFixed(5)
            + "</button>";

        afficherPointsRecherche();
        afficherRechercheSurCarte();
    }} catch (error) {{
        box.innerHTML =
            '<span style="display:block;padding:10px;color:#ef4444">'
            + esc(error.message)
            + "</span>";
    }}
}}

function afficherPointsRecherche() {{
    const all = [];

    if (searchPoints.depart) {{
        all.push(
            "Départ : " + searchPoints.depart.name
        );
    }}

    searchPoints.stops.forEach((point, index) => {{
        all.push(
            "Arrêt " + (index + 1) + " : "
            + point.name
        );
    }});

    if (searchPoints.destination) {{
        all.push(
            "Destination : "
            + searchPoints.destination.name
        );
    }}

    document.getElementById(
        "search-points"
    ).innerHTML =
        all.length
        ? "<strong>Points sélectionnés :</strong><br>"
          + all.map(esc).join("<br>")
        : "";
}}

function afficherRechercheSurCarte() {{
    if (!map) return;

    markers.forEach(marker => map.removeLayer(marker));
    markers = [];

    const points = [];

    if (searchPoints.depart) points.push(searchPoints.depart);

    searchPoints.stops.forEach(point => points.push(point));

    if (searchPoints.destination) {{
        points.push(searchPoints.destination);
    }}

    points.forEach((point, index) => {{
        ajouterMarqueur(point, index);
    }});

    if (points.length === 1) {{
        map.setView(
            [points[0].lat, points[0].lon],
            12
        );
    }}

    if (points.length > 1) {{
        const bounds = L.latLngBounds(
            points.map(point => [
                point.lat,
                point.lon
            ])
        );

        map.fitBounds(bounds, {{
            padding: [30, 30]
        }});
    }}
}}

function ajouterLigne(point = {{
    name: "",
    lat: "",
    lon: ""
}}) {{
    if (gpsPoints.length >= 500) {{
        alert("Limite de traitement selon votre clé API et les ressources disponibles.");
        return;
    }}

    gpsPoints.push(point);
    rendreGPS();
}}

function rendreGPS() {{
    const box = document.getElementById("gps-rows");
    box.innerHTML = "";

    gpsPoints.forEach((point, index) => {{
        const row = document.createElement("div");
        row.className = "gps-row";

        row.innerHTML =
            '<div class="number">'
            + (index + 1)
            + "</div>"
            + '<input class="gps-lat" placeholder="Latitude" value="'
            + esc(point.lat)
            + '">'
            + '<input class="gps-lon" placeholder="Longitude" value="'
            + esc(point.lon)
            + '">'
            + '<input class="point-name" placeholder="Nom facultatif" value="'
            + esc(point.name || ("Point " + (index + 1)))
            + '">'
            + '<button type="button" class="remove">×</button>';

        row.querySelector(".gps-lat")
            .addEventListener("input", event => {{
                gpsPoints[index].lat = event.target.value;
            }});

        row.querySelector(".gps-lon")
            .addEventListener("input", event => {{
                gpsPoints[index].lon = event.target.value;
            }});

        row.querySelector(".point-name")
            .addEventListener("input", event => {{
                gpsPoints[index].name = event.target.value;
            }});

        row.querySelector(".remove")
            .addEventListener("click", () => {{
                gpsPoints.splice(index, 1);
                rendreGPS();
            }});

        box.appendChild(row);
    }});
}}

function ajouter500() {{
    if (gpsPoints.length >= 500) return;

    while (gpsPoints.length < 500) {{
        gpsPoints.push({{
            name: "Point " + (gpsPoints.length + 1),
            lat: "",
            lon: ""
        }});
    }}

    rendreGPS();
}}

function importerCSV(event) {{
    const file = event.target.files[0];

    if (!file) return;

    const reader = new FileReader();

    reader.onload = () => {{
        try {{
            const lines = String(reader.result)
                .split(/\\r?\\n/)
                .map(line => line.trim())
                .filter(Boolean);

            if (!lines.length) {{
                throw new Error("CSV vide.");
            }}

            let start = 0;

            const header = lines[0].toLowerCase();

            if (
                header.includes("lat")
                && header.includes("lon")
            ) {{
                start = 1;
            }}

            const parsed = [];

            for (
                let i = start;
                i < lines.length;
                i++
            ) {{
                const parts = lines[i]
                    .split(",")
                    .map(value => value.trim());

                if (parts.length < 2) continue;

                let name;
                let lat;
                let lon;

                if (
                    parts.length >= 3
                    && !Number.isNaN(Number(parts[0]))
                ) {{
                    name = "Point " + (parsed.length + 1);
                    lat = Number(parts[0]);
                    lon = Number(parts[1]);
                }} else {{
                    if (parts.length < 3) continue;

                    name = parts[0];
                    lat = Number(parts[1]);
                    lon = Number(parts[2]);
                }}

                if (
                    Number.isFinite(lat)
                    && Number.isFinite(lon)
                    && lat >= -90
                    && lat <= 90
                    && lon >= -180
                    && lon <= 180
                ) {{
                    parsed.push({{
                        name,
                        lat,
                        lon
                    }});
                }}
            }}

            if (!parsed.length) {{
                throw new Error(
                    "Aucun point GPS valide dans le CSV."
                );
            }}

            if (parsed.length > 1000) {{
                throw new Error(
                    "Maximum 1000 points dans ce fichier CSV."
                );
            }}

            gpsPoints = parsed;
            rendreGPS();
            changerMode("gps");

            document.getElementById(
                "csv-status"
            ).textContent =
                parsed.length + " points importés.";
        }} catch (error) {{
            document.getElementById(
                "csv-status"
            ).textContent = error.message;
        }}
    }};

    reader.readAsText(file);
}}

function validerPoint(point) {{
    return (
        Number.isFinite(Number(point.lat))
        && Number.isFinite(Number(point.lon))
        && Number(point.lat) >= -90
        && Number(point.lat) <= 90
        && Number(point.lon) >= -180
        && Number(point.lon) <= 180
    );
}}

function obtenirPoints() {{
    if (currentMode === "search") {{
        if (
            !searchPoints.depart
            || !searchPoints.destination
        ) {{
            throw new Error(
                "Ajoutez un départ et une destination."
            );
        }}

        return [
            searchPoints.depart,
            ...searchPoints.stops,
            searchPoints.destination
        ];
    }}

    const points = gpsPoints.map(
        (point, index) => ({{
            name:
                point.name
                || "Point " + (index + 1),
            lat: Number(point.lat),
            lon: Number(point.lon)
        }})
    );

    if (points.length < 2) {{
        throw new Error(
            "Il faut au moins deux points."
        );
    }}

    if (points.some(point => !validerPoint(point))) {{
        throw new Error(
            "Une ou plusieurs coordonnées GPS sont invalides."
        );
    }}

    return points;
}}

function ajouterMarqueur(point, index) {{
    if (!map) return;

    const marker = L.marker([
        point.lat,
        point.lon
    ]).addTo(map);

    marker.bindPopup(
        "<strong>"
        + (index + 1)
        + ". "
        + esc(point.name)
        + "</strong><br>"
        + '<span class="coord">'
        + Number(point.lat).toFixed(6)
        + ", "
        + Number(point.lon).toFixed(6)
        + "</span>"
    );

    markers.push(marker);
}}

async function optimiser() {{
    const button =
        document.getElementById("btn-route");

    const result =
        document.getElementById("result");

    button.disabled = true;

    result.style.display = "block";
    result.innerHTML =
        "⚙️ Préparation des coordonnées...";

    try {{
        const points = obtenirPoints();

        if (points.length > 1000) {{
            throw new Error(
                "Maximum 1000 points dans cette interface."
            );
        }}

        /*
          IMPORTANT :
          /api/route accepte maintenant le cookie HttpOnly
          de l'espace client. Une clé n'est donc pas exposée
          dans le JavaScript du navigateur.
        */
        const response = await apiFetch(
            "/api/route",
            {{
                method: "POST",
                headers: {{
                    "Content-Type": "application/json"
                }},
                body: JSON.stringify({{
                    villes: points.map(point => [
                        point.lat,
                        point.lon
                    ])
                }})
            }}
        );

        const data = await response.json();

        if (!response.ok) {{
            throw new Error(
                data.detail || "Erreur du moteur."
            );
        }}

        const ordered = data.route.map(
            index => points[index]
        );

        result.innerHTML =
            "🧭 Ordre optimisé. Calcul du tracé routier réel...";

        const roadResponse = await apiFetch(
            "/api/road-route",
            {{
                method: "POST",
                headers: {{
                    "Content-Type": "application/json"
                }},
                body: JSON.stringify({{
                    points: ordered
                }})
            }}
        );

        const road = await roadResponse.json();

        if (!roadResponse.ok) {{
            throw new Error(
                road.detail
                || "Impossible de tracer la route."
            );
        }}

        if (routeLayer) {{
            map.removeLayer(routeLayer);
            routeLayer = null;
        }}

        markers.forEach(
            marker => map.removeLayer(marker)
        );

        markers = [];

        ordered.forEach(
            (point, index) =>
                ajouterMarqueur(point, index)
        );

        routeLayer = L.geoJSON(
            road.geometry,
            {{
                style: {{
                    color: "#f59e0b",
                    weight: 5,
                    opacity: 0.9
                }}
            }}
        ).addTo(map);

        const bounds =
            routeLayer.getBounds();

        if (bounds.isValid()) {{
            map.fitBounds(
                bounds,
                {{
                    padding: [30, 30]
                }}
            );
        }}

        const names = ordered
            .map(
                (point, index) =>
                    (index + 1)
                    + ". "
                    + esc(point.name)
            )
            .join("<br>");

        const routeItems = ordered.map((point, index) =>
            '<li><span class="step">' + (index + 1) + '</span><span><strong>'
            + esc(point.name) + '</strong><br><span class="coord">'
            + Number(point.lat).toFixed(5) + ', ' + Number(point.lon).toFixed(5)
            + '</span></span></li>'
        ).join("");

        result.innerHTML =
            '<div class="result-title"><div><h3>🧭 Itinéraire optimisé</h3>'
            + '<div class="result-sub">Votre tournée a été calculée et le tracé routier a été généré.</div></div>'
            + '<span class="badge">● Analyse terminée</span></div>'
            + '<div class="stats">'
            + '<div class="stat accent"><span>Points</span><strong>' + ordered.length + '</strong></div>'
            + '<div class="stat"><span>Route réelle</span><strong>' + road.distance_km + ' km</strong></div>'
            + '<div class="stat"><span>Durée estimée</span><strong>' + road.duration_min + ' min</strong></div>'
            + '<div class="stat"><span>Optimisation</span><strong>' + data.distance_km + ' km</strong></div>'
            + '</div>'
            + '<h4>Ordre de passage</h4>'
            + '<ol class="route-list">' + routeItems + '</ol>';
    }} catch (error) {{
        console.error(error);

        result.innerHTML =
            '<strong style="color:#ef4444">'
            + "Erreur : "
            + "</strong>"
            + esc(error.message);
    }} finally {{
        button.disabled = false;
    }}
}}

function effacerTout() {{
    searchPoints = {{
        depart: null,
        destination: null,
        stops: []
    }};

    gpsPoints = [];

    rendreGPS();
    afficherPointsRecherche();

    if (routeLayer) {{
        map.removeLayer(routeLayer);
        routeLayer = null;
    }}

    markers.forEach(
        marker => map.removeLayer(marker)
    );

    markers = [];

    document.getElementById(
        "result"
    ).style.display = "none";

    document.getElementById(
        "csv-status"
    ).textContent = "";
}}

function afficherErreur(message) {{
    const result =
        document.getElementById("result");

    if (result) {{
        result.style.display = "block";
        result.innerHTML =
            '<strong style="color:#ef4444">'
            + esc(message)
            + "</strong>";
    }}
}}
</script>

</body>
</html>
""")


# ==============================================================================
# API MODELS
# ==============================================================================

class RequeteCalcul(BaseModel):
    villes: List[Tuple[float, float]]


class RequeteRoadRoute(BaseModel):
    points: List[PointGPS]


# ==============================================================================
# SWIFTROUTE ENGINE
# ==============================================================================

NB_FOURMIS = 15
ALPHA = 1.0
BETA = 2.0
EVAPORATION = 0.3
Q = 100.0
CAPACITE_MAX_VEHICULE = 10


def calculer_route_precision(
    villes: List[Tuple[float, float]]
):
    nb_villes = len(villes)

    if nb_villes < 3:
        return list(range(nb_villes)), 0.0

    lat_moyenne = math.radians(
        sum(float(v[0]) for v in villes)
        / nb_villes
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

    iterations = (
        20 if nb_villes > 60
        else 40
    )

    for _ in range(iterations):
        toutes_routes = []
        toutes_distances = []

        for _ in range(NB_FOURMIS):
            route, distance = simuler_fourmi_vrp(
                nb_villes,
                distances,
                pheromones
            )

            toutes_routes.append(route)
            toutes_distances.append(distance)

            if distance < meilleure_distance:
                meilleure_distance = distance
                meilleure_route = route

        for i in range(nb_villes):
            for j in range(nb_villes):
                pheromones[i][j] *= (
                    1.0 - EVAPORATION
                )

        for route, distance in zip(
            toutes_routes,
            toutes_distances
        ):
            depot = Q / max(distance, 0.01)

            for k in range(len(route) - 1):
                pheromones[
                    route[k]
                ][
                    route[k + 1]
                ] += depot

    return meilleure_route, meilleure_distance


def simuler_fourmi_vrp(
    nb,
    dists,
    phero
):
    depot_index = 0
    path = [depot_index]
    villes_visitees = {depot_index}
    charge_actuelle = 0
    distance_totale = 0.0

    while len(villes_visitees) < nb:
        actuel = path[-1]

        if charge_actuelle >= CAPACITE_MAX_VEHICULE:
            distance_totale += dists[
                actuel
            ][depot_index]

            path.append(depot_index)
            actuel = depot_index
            charge_actuelle = 0

        probabilites = []
        total = 0.0

        for point in range(nb):
            if point not in villes_visitees:
                visibilite = 1.0 / max(
                    dists[actuel][point],
                    0.01
                )

                note = (
                    phero[actuel][point] ** ALPHA
                ) * (
                    visibilite ** BETA
                )

                probabilites.append(
                    (point, note)
                )

                total += note

        if total == 0:
            restants = [
                x for x in range(nb)
                if x not in villes_visitees
            ]

            prochain = (
                restants[0]
                if restants
                else depot_index
            )
        else:
            tirage = random.uniform(
                0,
                total
            )

            cumul = 0.0
            prochain = probabilites[-1][0]

            for value, probability in probabilites:
                cumul += probability

                if cumul >= tirage:
                    prochain = value
                    break

        distance_totale += dists[
            actuel
        ][prochain]

        path.append(prochain)
        villes_visitees.add(prochain)
        charge_actuelle += 1

    distance_totale += dists[
        path[-1]
    ][depot_index]

    path.append(depot_index)

    return path, distance_totale


# ==============================================================================
# ROUTING
# ==============================================================================

def _fetch_osrm_chunk(
    points: List[PointGPS]
):
    coords = ";".join(
        f"{point.lon},{point.lat}"
        for point in points
    )

    url = (
        f"{ROUTING_URL.rstrip('/')}"
        f"/route/v1/driving/{coords}"
        "?overview=full&geometries=geojson&steps=false"
    )

    request = URLRequest(
        url,
        headers={
            "User-Agent": GEOCODING_USER_AGENT
        }
    )

    try:
        with urlopen(
            request,
            timeout=30
        ) as response:
            return json.loads(
                response.read().decode("utf-8")
            )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "Service de routage indisponible : "
                + str(exc)
            )
        )


def _combine_geojson_lines(routes):
    coordinates = []

    for route in routes:
        segment = route[
            "geometry"
        ][
            "coordinates"
        ]

        if not coordinates:
            coordinates.extend(segment)
        elif coordinates[-1] == segment[0]:
            coordinates.extend(segment[1:])
        else:
            coordinates.extend(segment)

    return {
        "type": "Feature",
        "properties": {},
        "geometry": {
            "type": "LineString",
            "coordinates": coordinates
        }
    }


@app.post("/api/road-route")
async def api_road_route(
    requete: RequeteRoadRoute,
    infos=Security(verifier_acces)
):
    if len(requete.points) < 2:
        raise HTTPException(
            status_code=400,
            detail="Il faut au moins 2 points."
        )

    if len(requete.points) > 500:
        raise HTTPException(
            status_code=400,
            detail="Maximum 500 points."
        )

    for point in requete.points:
        if not (
            -90 <= point.lat <= 90
            and -180 <= point.lon <= 180
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Coordonnée invalide pour "
                    f"{point.name}."
                )
            )

    chunk_size = 80
    chunks = []
    start_index = 0

    while start_index < len(
        requete.points
    ) - 1:
        end_index = min(
            start_index + chunk_size,
            len(requete.points) - 1
        )

        chunk_points = requete.points[
            start_index:end_index + 1
        ]

        chunks.append(
            _fetch_osrm_chunk(chunk_points)
        )

        start_index = end_index

    total_distance = 0.0
    total_duration = 0.0
    valid_routes = []

    for data in chunks:
        if (
            data.get("code") != "Ok"
            or not data.get("routes")
        ):
            raise HTTPException(
                status_code=502,
                detail=(
                    "Le service routier n'a pas "
                    "trouvé de route."
                )
            )

        route = data["routes"][0]

        total_distance += float(
            route.get("distance", 0)
        )

        total_duration += float(
            route.get("duration", 0)
        )

        valid_routes.append(route)

    return {
        "success": True,
        "points": len(requete.points),
        "distance_km": round(
            total_distance / 1000,
            2
        ),
        "duration_min": round(
            total_duration / 60
        ),
        "geometry": _combine_geojson_lines(
            valid_routes
        ),
        "client": infos.get("client")
    }


# ==============================================================================
# CALCULATION API
# ==============================================================================

@app.post("/api/route")
async def api_route(
    requete: RequeteCalcul,
    infos=Security(verifier_acces)
):
    if len(requete.villes) > MAX_POINTS_REQUETE:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Maximum {MAX_POINTS_REQUETE} "
                "points par requête."
            )
        )

    for lat, lon in requete.villes:
        if not (
            -90 <= float(lat) <= 90
            and -180 <= float(lon) <= 180
        ):
            raise HTTPException(
                status_code=400,
                detail="Coordonnées GPS invalides."
            )

    if len(requete.villes) < 2:
        raise HTTPException(
            status_code=400,
            detail=(
                "Il faut au moins 2 points."
            )
        )

    if len(requete.villes) == 2:
        route = [0, 1]
        _, distance = calculer_route_precision(
            requete.villes
        )
    else:
        destination_index = (
            len(requete.villes) - 1
        )

        intermediaires = [
            requete.villes[0]
        ] + requete.villes[
            1:destination_index
        ]

        ordre, _ = calculer_route_precision(
            intermediaires
        )

        ordre = [
            index
            for index in ordre
            if index != 0
        ]

        route = [
            0
        ] + ordre + [
            destination_index
        ]

        distance = 0.0

        for a, b in zip(
            route,
            route[1:]
        ):
            va = requete.villes[a]
            vb = requete.villes[b]

            distance += math.sqrt(
                (
                    (float(va[0]) - float(vb[0]))
                    * 111.0
                ) ** 2
                +
                (
                    (float(va[1]) - float(vb[1]))
                    * 111.0
                    * math.cos(
                        math.radians(
                            (
                                float(va[0])
                                + float(vb[0])
                            ) / 2
                        )
                    )
                ) ** 2
            )

    return {
        "success": True,
        "client": infos.get("client"),
        "type_offre": infos.get("type_offre"),
        "route": route,
        "distance_km": round(
            distance,
            3
        ),
        "points": len(
            requete.villes
        )
    }


# ==============================================================================
# ADMIN
# ==============================================================================

def obtenir_panneau_admin(
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
<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SwiftRoute — Administration</title>
<style>
body{{background:#09090b;color:white;font-family:Arial;padding:25px}}
.box{{max-width:520px;margin:auto;background:#18181b;padding:25px;border-radius:12px}}
input,select{{width:100%;padding:12px;margin:6px 0 14px;box-sizing:border-box;background:#09090b;color:white;border:1px solid #3f3f46;border-radius:7px}}
button{{width:100%;padding:13px;background:#a855f7;color:white;border:0;border-radius:7px;font-weight:bold}}
</style>
</head>
<body>
<div class="box">
<h2>🎛️ Administration SwiftRoute</h2>
<p style="color:#a1a1aa">
Produit Tiun : {TIUN_PRODUCT_ID}
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
<option value="7">Essai 7 jours</option>
<option value="30">Entreprise 30 jours</option>
<option value="365">Corporate 1 an</option>
</select>

<button type="submit">
Générer et activer
</button>

</form>

{result}

</div>
</body>
</html>
"""


@app.get(
    "/admin-panel",
    response_class=HTMLResponse
)
async def vue_panneau_admin_serveur(
    cle_generee: str = ""
):
    return HTMLResponse(
        obtenir_panneau_admin(cle_generee)
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

    if duration not in (30, 365):
        raise HTTPException(
            status_code=400,
            detail="Durée invalide. Les essais gratuits sont désactivés."
        )

    client_name = client_name.strip()
    email = normalize_email(email)

    token, jti, expiration = create_client_token(
        client_name,
        email,
        duration,
        trial=False
    )

    # CORRECTION IMPORTANTE :
    # obtenir_panneau_admin accepte UNE seule valeur.
    return HTMLResponse(
        obtenir_panneau_admin(token)
    )


# ==============================================================================
# HEALTH
# ==============================================================================

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "SwiftRoute Engine",
        "version": "2.6"
    }


# ==============================================================================
# RUN
# ==============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(
            os.getenv("PORT", "8000")
        ),
        reload=False
    )
