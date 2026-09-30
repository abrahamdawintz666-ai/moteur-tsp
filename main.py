# SwiftRoute Engine — Enterprise Commercial Edition v3
# Modifications:
# - Espace Client: connexion avec une clé API existante
# - Session HttpOnly après connexion
# - Dashboard SaaS moderne
# - Capacité de points non plafonnée par le code applicatif
# - Carte Leaflet + tracé de secours si OSRM échoue
# - API navigateur autorisée via session cookie ou X-API-KEY
# - Correction du panneau admin

from fastapi import FastAPI, HTTPException, Security, Request, Form, Cookie
from fastapi.security.api_key import APIKeyHeader
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
import jwt
import random
import math
import datetime
import os
import sqlite3
import hashlib
import secrets
import json
import csv
import io
import time
import unicodedata
from urllib.parse import quote
from urllib.request import Request as URLRequest, urlopen
from typing import List, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

# ========================= CONFIG =========================
PHRASE_SECRETE_NORD = os.getenv("JWT_SECRET_KEY", "CHANGE_ME_IN_RENDER_ENVIRONMENT")
API_KEY_NAME = "X-API-KEY"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)
NOM_UTILISATEUR_ADMIN = os.getenv("ADMIN_USERNAME", "Abraham")
MOT_DE_PASSE_ADMIN = os.getenv("ADMIN_PASSWORD", "CHANGE_ME_IN_RENDER_ENVIRONMENT")
TIUN_PRODUCT_ID = os.getenv("TIUN_PRODUCT_ID", "p-live-0df3781")
WHATSAPP_CONTACT = os.getenv("WHATSAPP_CONTACT", "+509 41 81 7761")
EMAIL_CONTACT = os.getenv("EMAIL_CONTACT", "abrahamdawintz410@gmail.com")
TIUN_SNIPPET_ID = os.getenv("TIUN_SNIPPET_ID", "JQD27X4Dhj8JGdXQhnbBYz1K2HS5gjiojVwYIAKR")
# Tiun server-side verification. The API key must stay on Render, never in HTML/JS.
TIUN_API_BASE = os.getenv("TIUN_API_BASE", "https://api.tiun.live").rstrip("/")
TIUN_API_KEY = os.getenv("TIUN_API_KEY", "")
GEOCODING_URL = os.getenv("GEOCODING_URL", "https://nominatim.openstreetmap.org/search")
GEOCODING_USER_AGENT = os.getenv("GEOCODING_USER_AGENT", "SwiftRoute/1.0 contact=admin@swiftroute.example")
ROUTING_URL = os.getenv("ROUTING_URL", "https://router.project-osrm.org")
TILE_URL = os.getenv("TILE_URL", "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png")
DATABASE_PATH = os.getenv("SWIFTROUTE_DB", "swiftroute.db")
# Aucun plafond fixe de points dans SwiftRoute. La capacité réelle dépend du CPU/RAM,
# du temps de calcul et des limites du routeur/géocodeur utilisés.
MAX_POINTS_REQUETE = None
MAX_CSV_POINTS = None
GLOBAL_CITY_DATA_URL = os.getenv(
    "GLOBAL_CITY_DATA_URL",
    "https://gist.githubusercontent.com/StefanoFrontini/3a50afb19030b26cc6acc3cbad8d7aae/raw/worldcities.csv"
)
GLOBAL_CITY_COUNT = 1000

app = FastAPI(title="SwiftRoute Engine - AntStrike Advanced VRP", swagger_ui_parameters={"operationsSorter": "alpha"})

# ========================= DATABASE =========================
def db_connect():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    conn = db_connect()
    conn.execute("""CREATE TABLE IF NOT EXISTS cities (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
        lat REAL NOT NULL, lon REAL NOT NULL)""")
    # Remplace l'ancienne base locale d'Haïti par 1000 grandes villes mondiales.
    # La source contient des villes internationales avec population et coordonnées;
    # on prend les 1000 premières après tri décroissant de population.
    # Ce n'est pas un classement officiel des villes les plus touristiques/fréquentées.
    conn.execute("DELETE FROM cities")
    try:
        req = URLRequest(
            GLOBAL_CITY_DATA_URL,
            headers={"User-Agent": GEOCODING_USER_AGENT}
        )
        with urlopen(req, timeout=25) as response:
            raw = response.read().decode("utf-8", errors="replace")
        rows = csv.DictReader(io.StringIO(raw), delimiter=";")
        parsed = []
        for row in rows:
            try:
                name = (row.get("city") or "").strip()
                lat = float(row.get("lat"))
                lon = float(row.get("lng"))
                population = int(float(row.get("population") or 0))
                if name and -90 <= lat <= 90 and -180 <= lon <= 180:
                    parsed.append((population, name, lat, lon))
            except (TypeError, ValueError):
                continue
        parsed.sort(key=lambda x: x[0], reverse=True)
        cities = [(name, lat, lon) for _, name, lat, lon in parsed[:GLOBAL_CITY_COUNT]]
        conn.executemany(
            "INSERT OR IGNORE INTO cities (name,lat,lon) VALUES (?,?,?)",
            cities
        )
    except Exception as exc:
        # Le géocodage mondial reste disponible même si le chargement initial échoue.
        print(f"[SwiftRoute] Chargement des villes mondiales impossible: {exc}")
    conn.execute("""CREATE TABLE IF NOT EXISTS geocodes (
        id INTEGER PRIMARY KEY AUTOINCREMENT, query TEXT NOT NULL UNIQUE,
        display_name TEXT NOT NULL, lat REAL NOT NULL, lon REAL NOT NULL, created_at TEXT NOT NULL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS api_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL UNIQUE,
        client_name TEXT NOT NULL, email TEXT, token_jti TEXT, created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1)""")
    conn.commit(); conn.close()

init_database()

# ========================= SECURITY =========================
def hash_value(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()

def verifier_session_tiun(session_id: str):
    """Vérifie une session Tiun directement auprès de l'API S2S.

    200 = accès valide. 404 = session invalide/expirée/sans fonds.
    Toute autre réponse est refusée par défaut (fail closed).
    """
    if not session_id:
        raise HTTPException(401, "Session Tiun manquante.")
    if not TIUN_API_KEY:
        raise HTTPException(503, "La vérification Tiun n'est pas configurée sur le serveur.")

    url = f"{TIUN_API_BASE}/live_api/s2s/v1/sessions/{quote(session_id, safe='')}/status"
    req = URLRequest(url, method="PATCH", headers={"X-TIUN-API-KEY": TIUN_API_KEY})
    try:
        with urlopen(req, timeout=12) as response:
            status = response.status
    except Exception as exc:
        # urllib expose les réponses HTTP d'erreur via HTTPError.
        status = getattr(exc, "code", None)
        if status is None:
            raise HTTPException(502, "Impossible de vérifier la session Tiun.")

    if status == 200:
        return {"valid": True, "session_id": session_id}
    if status == 404:
        raise HTTPException(403, "Abonnement Tiun invalide, expiré ou sans fonds.")
    if status == 401:
        raise HTTPException(503, "La clé API Tiun du serveur est incorrecte.")
    raise HTTPException(503, f"Tiun a retourné le statut {status}.")


async def verifier_acces_swiftroute(
    request: Request,
    api_key: str = Security(api_key_header),
    swiftroute_session: str = Cookie(default=None),
):
    """Autorise soit l'ancien accès API/session SwiftRoute, soit une session Tiun valide."""
    tiun_session = request.headers.get("x-session-id")
    if tiun_session:
        verifier_session_tiun(tiun_session)
        return {"client": "Tiun", "trial": False, "type_offre": "Abonnement Tiun", "tiun_session": tiun_session}
    return await verifier_minuteur_cle_api(request, api_key, swiftroute_session)




def normalize_email(email: str) -> str:
    return email.strip().lower()


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded: return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def create_client_token(client_name, email, duration_days):
    now = datetime.datetime.now(datetime.timezone.utc)
    expiration = now + datetime.timedelta(days=duration_days)
    jti = secrets.token_urlsafe(32)
    payload = {"client":client_name,"email":email,"exp":int(expiration.timestamp()),"iat":int(now.timestamp()),
               "jti":jti,"trial":False,"type_offre":f"Accès {duration_days} Jours"}
    token = jwt.encode(payload, PHRASE_SECRETE_NORD, algorithm="HS256")
    return token,jti,expiration


def create_session(client_name,email,token_jti,expiration):
    session_id = secrets.token_urlsafe(48)
    now = datetime.datetime.now(datetime.timezone.utc)
    conn=db_connect(); conn.execute("""INSERT INTO api_sessions
      (session_id,client_name,email,token_jti,created_at,expires_at,active)
      VALUES (?,?,?,?,?,?,1)""",(session_id,client_name,email,token_jti,now.isoformat(),expiration.isoformat()))
    conn.commit(); conn.close(); return session_id


def get_session(session_id):
    if not session_id: return None
    conn=db_connect(); row=conn.execute("SELECT * FROM api_sessions WHERE session_id=? AND active=1",(session_id,)).fetchone(); conn.close()
    if not row: return None
    expiration=datetime.datetime.fromisoformat(row["expires_at"])
    if expiration <= datetime.datetime.now(datetime.timezone.utc):
        conn=db_connect(); conn.execute("UPDATE api_sessions SET active=0 WHERE session_id=?",(session_id,)); conn.commit(); conn.close(); return None
    return row


def verify_token(token):
    try: return jwt.decode(token,PHRASE_SECRETE_NORD,algorithms=["HS256"])
    except jwt.ExpiredSignatureError: raise HTTPException(402,"Votre accès a expiré.")
    except jwt.InvalidTokenError: raise HTTPException(403,"Clé API invalide.")


def validate_api_token(token):
    # Les clés commerciales sont émises par le système d'abonnement.
    return verify_token(token)


async def verifier_minuteur_cle_api(request: Request, api_key: str = Security(api_key_header), swiftroute_session: str = Cookie(default=None)):
    # 1) API commerciale directe
    if api_key:
        return validate_api_token(api_key)
    # 2) Session HttpOnly commerciale
    session=get_session(swiftroute_session)
    if session:
        jti=session["token_jti"]
        return {"client":session["client_name"],"email":session["email"],"jti":jti,"trial":False,"type_offre":"Accès Client"}
    raise HTTPException(403,"Authentification requise. Utilisez un abonnement Tiun ou une clé API commerciale.")

# ========================= GEOCODING =========================
def normalize_city_name(value):
    value=value.strip().lower(); replacements={"cap haitien":"cap-haïtien","cap-haitien":"cap-haïtien","port au prince":"port-au-prince","port au-prince":"port-au-prince","port de paix":"port-de-paix","petit goave":"petit-goâve","grand goave":"grand-goâve","petit-goave":"petit-goâve","grand-goave":"grand-goâve"}; return replacements.get(value,value)


def get_city(name):
    normalized=normalize_city_name(name); conn=db_connect(); row=conn.execute("SELECT name,lat,lon FROM cities WHERE lower(name)=?",(normalized,)).fetchone()
    if not row:
        rows=conn.execute("SELECT name,lat,lon FROM cities").fetchall()
        def clean(v):
            v=unicodedata.normalize("NFKD",v.lower()); return "".join(c for c in v if not unicodedata.combining(c)).replace("-"," ").strip()
        target=clean(name)
        for candidate in rows:
            if clean(candidate["name"])==target: row=candidate; break
    conn.close(); return row


def get_cached_geocode(query):
    conn=db_connect(); row=conn.execute("SELECT display_name,lat,lon FROM geocodes WHERE query=?",(query.strip().lower(),)).fetchone(); conn.close(); return row


def save_geocode(query,display_name,lat,lon):
    conn=db_connect(); conn.execute("INSERT OR REPLACE INTO geocodes(query,display_name,lat,lon,created_at) VALUES(?,?,?,?,?)",(query.strip().lower(),display_name,float(lat),float(lon),datetime.datetime.now(datetime.timezone.utc).isoformat())); conn.commit(); conn.close()

_last_geocode_request=0.0

def geocode_global(query):
    global _last_geocode_request
    query=query.strip()
    if not query: raise HTTPException(400,"Recherche vide.")
    city=get_city(query)
    if city: return {"name":city["name"],"display_name":city["name"],"lat":float(city["lat"]),"lon":float(city["lon"]),"source":"base_locale"}
    cached=get_cached_geocode(query)
    if cached: return {"name":query,"display_name":cached["display_name"],"lat":float(cached["lat"]),"lon":float(cached["lon"]),"source":"cache"}
    wait=1.0-(time.time()-_last_geocode_request)
    if wait>0: time.sleep(wait)
    params=f"?q={quote(query)}&format=jsonv2&limit=1&addressdetails=1"
    req=URLRequest(GEOCODING_URL+params,headers={"User-Agent":GEOCODING_USER_AGENT})
    try:
        _last_geocode_request=time.time()
        with urlopen(req,timeout=12) as response: results=json.loads(response.read().decode("utf-8"))
    except Exception as exc: raise HTTPException(502,f"Le service de recherche mondiale est indisponible: {exc}")
    if not results: raise HTTPException(404,f"Aucun lieu trouvé pour : {query}")
    item=results[0]; lat=float(item["lat"]); lon=float(item["lon"]); display_name=item.get("display_name",query); save_geocode(query,display_name,lat,lon)
    return {"name":query,"display_name":display_name,"lat":lat,"lon":lon,"source":"geocodage_mondial"}

@app.get("/api/cities")
async def api_cities():
    conn=db_connect(); rows=conn.execute("SELECT name,lat,lon FROM cities ORDER BY name").fetchall(); conn.close(); return {"cities":[dict(r) for r in rows]}

@app.get("/api/city")
async def api_city(name:str):
    row=get_city(name)
    if not row: raise HTTPException(404,f"Ville inconnue : {name}")
    return {"name":row["name"],"lat":row["lat"],"lon":row["lon"]}

@app.get("/api/geocode")
async def api_geocode(q:str): return geocode_global(q)

class PointGPS(BaseModel):
    name:str="Point"; lat:float; lon:float
class RequetePoints(BaseModel): points:List[PointGPS]

@app.post("/api/geocode-batch")
async def api_geocode_batch(requete:RequetePoints):
    if len(requete.points)>25: raise HTTPException(400,"Maximum 25 recherches d'adresse par opération. Pour de gros volumes, utilisez GPS ou CSV.")
    return {"results":[{**geocode_global(p.name),"input":p.name} for p in requete.points]}

# ========================= TIUN SERVER-SIDE VERIFICATION =========================
class RequeteTiunSession(BaseModel):
    session_id: str


@app.post("/api/tiun/verify-session")
async def api_tiun_verify_session(requete: RequeteTiunSession):
    """Endpoint appelé après paywallHide pour vérifier la session Tiun côté serveur."""
    return verifier_session_tiun(requete.session_id)


# ========================= HOME =========================
def obtenir_page_accueil():
    return '''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SwiftRoute Engine</title>
<script type="module">import { tiun } from 'https://esm.sh/@tiun/sdk'; tiun.init({snippetId:'__TIUN_SNIPPET_ID__',language:'fr'});</script>
<style>body{margin:0;background:#09090b;color:#f4f4f5;font-family:Inter,Arial,sans-serif}a{color:inherit;text-decoration:none}.nav{max-width:1180px;margin:auto;padding:22px;display:flex;justify-content:space-between;align-items:center}.brand{font-weight:900;font-size:21px}.nav a{margin-left:18px;color:#a1a1aa}.hero{max-width:1050px;margin:auto;text-align:center;padding:100px 22px 80px}.eyebrow{color:#f59e0b;font-weight:800;letter-spacing:2px}h1{font-size:clamp(44px,8vw,82px);margin:18px 0;letter-spacing:-3px}.hero p{color:#a1a1aa;max-width:760px;margin:0 auto 32px;line-height:1.7;font-size:18px}.btn{display:inline-block;padding:14px 20px;border-radius:12px;margin:5px;font-weight:800}.primary{background:#f59e0b;color:#09090b}.ghost{border:1px solid #27272a}.grid{max-width:1050px;margin:auto;padding:20px;display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.card{background:#111113;border:1px solid #27272a;border-radius:18px;padding:25px}.card p{color:#a1a1aa;line-height:1.6}@media(max-width:800px){.grid{grid-template-columns:1fr}.nav{flex-wrap:wrap}}<style>
.seq-item{display:grid;grid-template-columns:42px minmax(0,1fr) auto;align-items:center;gap:10px;padding:9px 0}
.seq-badge{width:32px;height:32px;border-radius:50%;display:flex;align-items:center;justify-content:center;border:1px solid #39414d;background:#171b21;font-weight:800}
.seq-badge.start{border-color:#22c55e}
.seq-main{display:flex;flex-direction:column;min-width:0}
.seq-main b{font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.seq-main span{font-size:11px;color:#9ca3af;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.seq-distance{font-size:12px;font-weight:800;color:#f59e0b;white-space:nowrap}
.seq-connector{height:12px;border-left:2px solid #39414d;margin-left:15px}
.point-dot{width:14px;height:14px;border-radius:50%;background:#2563eb;border:2px solid #fff;box-shadow:0 1px 5px rgba(0,0,0,.45)}
.point-dot.start{background:#22c55e}.point-dot.end{background:#ef4444}.point-dot.water{background:#2563eb}
.point-popup{font-size:12px;line-height:1.45}.point-popup b{font-size:14px}.popup-country{font-weight:700;color:#64748b}.popup-muted{font-size:11px;color:#64748b}
@media(max-width:700px){.seq-item{grid-template-columns:38px minmax(0,1fr) auto}.seq-main b{font-size:13px}}
</style></style></head><body>
<div class="nav"><div class="brand">🐜 SWIFTROUTE</div><div><a href="/docs">API Docs</a><a href="/workspace">Espace Client</a></div></div>
<section class="hero"><div class="eyebrow">ANTSTRIKE COMMERCIAL · ROUTE OPTIMIZATION</div><h1>SWIFTROUTE ENGINE</h1><p>Une infrastructure d'optimisation de tournées dont la capacité dépend des ressources disponibles sur le serveur et présente le résultat sur une carte interactive.</p><a class="btn primary" href="/workspace">Ouvrir l'espace client</a><a class="btn ghost" href="/client-login?subscribe=1">Prendre un abonnement</a></section>
<div class="grid"><div class="card"><h3>⚡ Optimisation</h3><p>Ordonnancement des points avec le moteur SwiftRoute.</p></div><div class="card"><h3>🌍 Carte</h3><p>Visualisation interactive et tracé routier lorsque le fournisseur est disponible.</p></div><div class="card"><h3>🔑 API</h3><p>Accès développeur avec clé API ou session client sécurisée.</p></div></div></body></html>'''.replace('__TILE_URL__', TILE_URL).replace('__TIUN_SNIPPET_ID__', TIUN_SNIPPET_ID)

@app.get("/",response_class=HTMLResponse)
async def page_accueil_serveur(): return HTMLResponse(obtenir_page_accueil())

# ========================= ABONNEMENT TIUN =========================
# ========================= CLIENT LOGIN =========================
LOGIN_HTML='''<!doctype html><html lang="fr"><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Espace Client — SwiftRoute</title><style>body{margin:0;background:#09090b;color:#f4f4f5;font-family:Inter,Arial}.wrap{min-height:100vh;display:grid;place-items:center;padding:20px}.box{width:min(460px,100%);background:#111113;border:1px solid #27272a;border-radius:22px;padding:30px;box-shadow:0 20px 80px #0008}h1{margin:0 0 8px}.muted{color:#a1a1aa;line-height:1.6}label{display:block;margin:20px 0 7px;font-weight:700}input{width:100%;box-sizing:border-box;padding:14px;background:#09090b;border:1px solid #3f3f46;border-radius:10px;color:#fff;font-family:monospace}button{width:100%;padding:14px;margin-top:18px;border:0;border-radius:10px;background:#f59e0b;font-weight:900;cursor:pointer}.links{display:flex;justify-content:space-between;margin-top:20px}.links a{color:#f59e0b;text-decoration:none}</style></head><body><div class="wrap"><div class="box"><div style="font-size:22px;font-weight:900">🐜 SWIFTROUTE</div><h1>Espace Client</h1><p class="muted">Connectez-vous avec la clé API qui vous a été fournie. La clé n'est pas placée dans l'URL.</p><form method="post" action="/client-login"><label>Clé API</label><input name="api_key" type="password" placeholder="Votre clé API" required autocomplete="off"><button>🔐 Se connecter</button></form><div style="margin-top:18px;padding-top:18px;border-top:1px solid #27272a">
<div class="muted" style="font-size:13px;margin-bottom:10px">Vous n'avez pas encore de clé API ?</div>
<button type="button" onclick="openTiun()">💳 Prendre un abonnement</button>
</div><div class="links"><a href="/">Accueil</a></div></div></div>
<script type="module">import { tiun } from 'https://esm.sh/@tiun/sdk'; tiun.init({snippetId:'__TIUN_SNIPPET_ID__',language:'fr'}); window.tiun=tiun; window.openTiun=async()=>{try{if(typeof tiun.waitForReady==='function') await tiun.waitForReady(); if(typeof tiun.checkout!=='function'){alert('Le paiement Tiun n’est pas disponible dans ce snippet.');return;} await tiun.checkout({productId:'__TIUN_PRODUCT_ID__'});}catch(e){console.error(e);alert('Impossible d’ouvrir le paiement Tiun.');}};</script></body></html>'''

@app.get("/workspace",response_class=HTMLResponse)
async def workspace(swiftroute_session:str=Cookie(default=None)):
    if not get_session(swiftroute_session): return HTMLResponse(LOGIN_HTML.replace('__TIUN_SNIPPET_ID__', TIUN_SNIPPET_ID).replace('__TIUN_PRODUCT_ID__', TIUN_PRODUCT_ID))
    return HTMLResponse(workspace_html())

@app.get("/client-login",response_class=HTMLResponse)
async def client_login_page(): return HTMLResponse(LOGIN_HTML.replace('__TIUN_SNIPPET_ID__', TIUN_SNIPPET_ID).replace('__TIUN_PRODUCT_ID__', TIUN_PRODUCT_ID))

@app.post("/client-login")
async def client_login(api_key:str=Form(...)):
    infos=validate_api_token(api_key.strip())
    expiration=datetime.datetime.fromtimestamp(int(infos["exp"]),datetime.timezone.utc)
    session_id=create_session(infos.get("client","Client"),infos.get("email"),infos.get("jti"),expiration)
    response=RedirectResponse("/workspace",303); response.set_cookie("swiftroute_session",session_id,httponly=True,secure=True,samesite="lax",max_age=max(1,int((expiration-datetime.datetime.now(datetime.timezone.utc)).total_seconds())))
    return response

@app.post("/logout")
async def logout(swiftroute_session:str=Cookie(default=None)):
    if swiftroute_session:
        conn=db_connect(); conn.execute("UPDATE api_sessions SET active=0 WHERE session_id=?",(swiftroute_session,)); conn.commit(); conn.close()
    response=RedirectResponse("/client-login",303); response.delete_cookie("swiftroute_session"); return response

# ========================= WORKSPACE UI =========================
def workspace_html():
    return '''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SwiftRoute — Dashboard</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" crossorigin=""/>
<script type="module">
import { tiun } from 'https://esm.sh/@tiun/sdk';
tiun.init({
  snippetId: '__TIUN_SNIPPET_ID__',
  language: 'fr',
  onError: (error) => {
    console.error('[Tiun]', error);
    window.dispatchEvent(new CustomEvent('tiun:error', {detail: error}));
  }
});
window.tiun = tiun;
</script>
<style>
*{box-sizing:border-box}:root{--bg:#08090b;--panel:#101216;--panel2:#151820;--line:#262a33;--muted:#8d95a3;--orange:#f59e0b;--orange2:#ffb52e;--green:#22c55e;--danger:#ef4444}body{margin:0;background:radial-gradient(circle at 70% -10%,#24200f 0,#08090b 34%);color:#f5f5f5;font-family:Inter,ui-sans-serif,Arial,sans-serif}button,input{font:inherit}button{cursor:pointer}.app{min-height:100vh}.side{visibility:hidden;pointer-events:none;position:fixed;left:0;top:0;width:250px;height:100vh;z-index:1200;border-right:1px solid var(--line);background:#0b0d10f5;backdrop-filter:blur(20px);padding:14px 10px;display:flex;flex-direction:column;transform:translateX(-105%);transition:transform .24s ease;box-shadow:20px 0 60px #0008}.side.open{transform:translateX(0);visibility:visible;pointer-events:auto}.logo{font-size:16px;font-weight:950;padding:6px 6px 18px}.logo span{color:var(--orange)}.navbtn{width:100%;text-align:left;background:transparent;border:1px solid transparent;color:#aeb5c0;padding:8px 9px;border-radius:9px;margin:2px 0;font-weight:700}.navbtn:hover,.navbtn.active{background:#191b20;border-color:#2a2e37;color:#fff}.navbtn.active{box-shadow:inset 3px 0 0 var(--orange)}.bottom{margin-top:auto}.main{min-width:0;width:100%}.hamburger{display:inline-flex;align-items:center;justify-content:center;width:42px;height:42px;border:1px solid var(--line);border-radius:11px;background:#151820;color:#fff;font-size:22px;margin-right:10px}.top-left{display:flex;align-items:center;gap:8px}.menu-overlay{display:none;position:fixed;inset:0;background:#0008;z-index:1100}.menu-overlay.open{display:block}.top{height:72px;border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;padding:0 28px;background:#0b0d10b8;backdrop-filter:blur(14px);position:sticky;top:0;z-index:900}.status{color:#9ca3af;font-size:13px}.dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--green);margin-right:7px;box-shadow:0 0 12px var(--green)}.content{padding:28px;max-width:1500px;margin:auto}.hero{display:flex;justify-content:space-between;align-items:flex-end;gap:20px;margin-bottom:22px}h1{font-size:34px;margin:0 0 6px;letter-spacing:-1.5px}.muted{color:var(--muted)}.primary{background:linear-gradient(135deg,var(--orange2),var(--orange));border:0;color:#0a0a0a;font-weight:900;padding:13px 17px;border-radius:11px;box-shadow:0 8px 28px #f59e0b25}.ghost{background:#17191e;color:#fff;border:1px solid #30343e;padding:12px 15px;border-radius:10px;font-weight:800}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:18px}.stat{background:linear-gradient(145deg,#13161b,#0f1115);border:1px solid var(--line);border-radius:15px;padding:18px}.stat small{color:var(--muted);font-weight:700}.stat strong{display:block;font-size:28px;margin-top:8px;color:var(--orange)}.workspace{display:flex;flex-direction:column;gap:12px}.workspace #optimizer{scroll-margin-top:88px}.workspace>.panel{width:100%}.panel{background:var(--panel);border:1px solid var(--line);border-radius:17px;padding:14px;box-shadow:0 18px 50px #0002}.panel h2{font-size:17px;margin:0 0 15px}.workspace>.panel:first-child{padding:12px 14px}.workspace>.panel:first-child .gpslist{max-height:190px}.workspace>.panel:first-child .quality{margin-top:8px}.workspace>.panel:first-child .actions{margin-top:8px}.workspace>.panel:first-child .big{padding:11px}.tabs{display:flex;gap:7px;margin-bottom:14px}.tab{flex:1;background:#17191e;color:#aeb5c0;border:1px solid #292d36;padding:7px 8px;border-radius:8px;font-weight:800}.tab.active{color:#fff;border-color:#8b5b08;background:#211a0c}.modepanel{display:none}.modepanel.active{display:block}label{display:block;color:#d6d8dd;font-size:12px;font-weight:800;margin:13px 0 6px}input,textarea{width:100%;background:#0a0c0f;color:#fff;border:1px solid #30343d;border-radius:9px;padding:12px;outline:none}input:focus{border-color:#9b6b0c;box-shadow:0 0 0 3px #f59e0b12}.searchrow{display:grid;grid-template-columns:1fr auto;gap:7px}.searchrow button{background:#20232a;border:1px solid #343944;color:#fff;border-radius:9px;padding:0 12px}.pointshead{display:flex;justify-content:space-between;align-items:center;margin-top:14px}.counter{font-family:monospace;color:var(--orange)}.progress{height:5px;background:#262a31;border-radius:9px;overflow:hidden;margin:9px 0 12px}.progress i{display:block;height:100%;width:0;background:var(--orange);transition:width .25s}.gpslist{max-height:360px;overflow:auto;padding-right:3px}.gpsrow{display:grid;grid-template-columns:30px 1.1fr 1fr 1fr 34px;gap:5px;margin-bottom:6px}.gpsrow input{padding:9px;font-size:12px}.num{display:grid;place-items:center;color:#777f8d;font-size:11px}.remove{background:#191b20;color:#ef4444;border:1px solid #30343d;border-radius:8px}.actions{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:10px}.big{grid-column:1/-1;padding:14px;border-radius:11px;font-size:15px}.mapwrap{padding:0;overflow:hidden;min-height:590px;position:relative;order:-1;box-shadow:0 22px 70px #0005}.workspace>.mapwrap{scroll-margin-top:82px}#map{height:100%;min-height:590px;background:#111}.maptools{position:absolute;top:14px;left:14px;z-index:700;display:flex;gap:7px;flex-wrap:wrap}.maptools button{background:#0c0e12eF;border:1px solid #30343d;color:#fff;padding:9px 11px;border-radius:9px;font-weight:800;backdrop-filter:blur(10px)}.search-result{margin-top:10px;padding:12px 14px;border:1px solid #343944;border-left:3px solid var(--orange);border-radius:12px;background:linear-gradient(135deg,#14171c,#0d0f13);font-family:Georgia,"Times New Roman",serif;box-shadow:0 12px 30px #0004}.search-result .label{font-family:Inter,ui-sans-serif,Arial,sans-serif;text-transform:uppercase;letter-spacing:1.2px;font-size:10px;font-weight:900;color:var(--orange);margin-bottom:5px}.search-result .place{font-size:16px;font-weight:700;line-height:1.45;color:#fff}.search-result .coords{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11px;color:#9ca3af;margin-top:6px}.result{margin-top:14px;border:1px solid #6a4708;background:linear-gradient(145deg,#19150c,#111216);border-radius:16px;padding:17px;display:none;box-shadow:0 16px 42px #0005}.result .result-title{font-size:18px;font-weight:900;letter-spacing:-.3px}.result .result-meta{display:flex;flex-wrap:wrap;gap:7px;margin:12px 0}.result .pill{display:inline-flex;align-items:center;padding:6px 9px;border:1px solid #343944;border-radius:999px;background:#111419;color:#d8dbe1;font-size:12px;font-weight:800}.result .route-list{margin-top:12px;padding:10px 12px;border:1px solid #292d36;border-radius:12px;background:#0c0f13;max-height:360px;overflow:auto;line-height:1.8;color:#e1e4e8}.result .route-item{padding:4px 0;border-bottom:1px solid #20232a}.result .route-item:last-child{border-bottom:0}.quality{margin-top:12px;padding:15px;border:1px solid #292d36;background:linear-gradient(145deg,#111419,#0d0f13);border-radius:14px}.quality-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:10px}.quality-card{padding:10px;min-height:68px;display:flex;flex-direction:column;justify-content:center;border:1px solid #292d36;border-radius:10px;background:#101216}.quality-card b{display:block;font-size:20px;margin-top:4px}.quality-list{max-height:360px;overflow:auto;margin-top:10px}.q-valid{color:#22c55e}.q-review{color:#f59e0b}.q-invalid{color:#ef4444}.q-unknown{color:#a1a1aa}@media(max-width:650px){.quality-grid{grid-template-columns:1fr 1fr}}
.section-panel{margin-top:16px;scroll-margin-top:90px}
/* SwiftRoute visual/navigation layer */
.route-builder-compact{padding:10px 12px!important}.route-builder-compact .gpslist{max-height:120px!important}.route-builder-compact .quality{display:none}.route-builder-compact .tabs{margin-bottom:8px}.route-builder-compact .actions{grid-template-columns:1fr auto auto}.route-builder-compact .actions .big{grid-column:auto;padding:10px 14px}
.mapwrap{transition:min-height .25s ease,box-shadow .25s ease}.mapwrap.map-fullscreen{position:fixed;inset:0;width:100vw;height:100vh;min-height:100vh!important;z-index:2500;border-radius:0;margin:0;box-shadow:0 0 0 100vmax #000}.mapwrap.map-fullscreen #map{height:100vh;min-height:100vh}.map-fullscreen .maptools{top:max(14px,env(safe-area-inset-top));left:14px}.map-fullscreen .maptools .exit-map{display:inline-flex!important}.exit-map{display:none!important}
.follow-badge{position:absolute;right:14px;top:14px;z-index:701;background:#0c0e12eF;border:1px solid #30343d;color:#fff;padding:9px 11px;border-radius:9px;font-weight:900;backdrop-filter:blur(10px)}.follow-badge.on{border-color:#22c55e;color:#86efac}.point-label.water{border-color:#38bdf8!important;color:#bae6fd!important;background:#082f49!important}.point-label.review{border-color:#f59e0b!important}.point-label{background:#0c0e12eF;color:#fff;border:1px solid #4b5563;border-radius:7px;padding:3px 6px;font-size:10px;font-weight:900;white-space:nowrap;box-shadow:0 4px 14px #0006}.point-label.start{border-color:#22c55e}.point-label.end{border-color:#ef4444}.map-current-label{background:#111827;color:#fff;border:1px solid #22c55e;border-radius:999px;padding:4px 8px;font-size:11px;font-weight:900;box-shadow:0 6px 20px #0007}
.route-status{margin-top:10px;padding:11px 13px;border:1px solid #26333b;border-radius:12px;background:#0b1114;color:#dbeafe;font-size:13px}.route-status strong{color:#86efac}.analytics{display:none;margin-top:12px;padding:15px;border:1px solid #292d36;border-radius:16px;background:linear-gradient(145deg,#12161b,#0c0f13);box-shadow:0 16px 42px #0004}.analytics.visible{display:block}.analytics-head{display:flex;justify-content:space-between;align-items:center;gap:12px}.analytics-grid{display:grid;grid-template-columns:1.2fr 1fr;gap:12px;margin-top:12px}.chart-card{border:1px solid #292d36;border-radius:13px;padding:13px;background:#0b0e12}.chart-title{font-size:11px;text-transform:uppercase;letter-spacing:1px;color:#9ca3af;font-weight:900;margin-bottom:10px}.bar-row{display:grid;grid-template-columns:88px 1fr 62px;gap:8px;align-items:center;margin:9px 0;font-size:12px}.bar-track{height:9px;border-radius:999px;background:#20242c;overflow:hidden}.bar-fill{height:100%;border-radius:999px;background:linear-gradient(90deg,#f59e0b,#fcd34d);width:0;transition:width .6s ease}.sequence{display:flex;align-items:center;gap:4px;overflow:auto;padding:8px 0}.seq-node{min-width:30px;height:30px;border-radius:9px;display:grid;place-items:center;background:#171b22;border:1px solid #3a414d;color:#fff;font-size:11px;font-weight:900}.seq-node.start{border-color:#22c55e}.seq-node.end{border-color:#ef4444}.seq-line{height:2px;min-width:16px;background:#4b5563}.next-stop{margin-top:10px;padding:10px;border-radius:10px;background:#11161b;border:1px solid #26333b;font-size:12px}
@media(max-width:700px){.analytics-grid{grid-template-columns:1fr}.mapwrap{min-height:62vh!important}#map{min-height:62vh}.route-builder-compact .actions{grid-template-columns:1fr 1fr}.route-builder-compact .actions .big{grid-column:1/-1}.follow-badge{top:64px}.bar-row{grid-template-columns:72px 1fr 54px}}

.view-hidden{display:none!important}
.content{min-height:calc(100vh - 72px)}
.view-panel{margin-top:0}
#optimizer{margin-top:0}
.info-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.info-card{background:#0d0f13;border:1px solid #292d36;border-radius:13px;padding:15px}.info-card strong{display:block;font-size:22px;color:var(--orange);margin-top:5px}.quick-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px}.quick-actions button{flex:1;min-width:140px}.support-link{display:inline-flex;align-items:center;gap:8px;text-decoration:none;background:#17191e;color:#fff;border:1px solid #30343e;padding:11px 14px;border-radius:10px;font-weight:800}.navbtn .navtext{margin-left:8px}.performance-kpi{font-size:24px;font-weight:900;color:var(--orange)}.route-list{max-height:230px;overflow:auto;line-height:1.75;color:#d2d6dd;font-size:13px}.toast{position:fixed;right:20px;bottom:20px;background:#17191e;border:1px solid #343944;padding:13px 15px;border-radius:11px;z-index:2000;display:none;box-shadow:0 20px 60px #0008}.loading{display:none;position:absolute;inset:0;background:#090b0ee8;z-index:800;align-items:center;justify-content:center;flex-direction:column;gap:14px}.spinner{width:40px;height:40px;border:3px solid #343944;border-top-color:var(--orange);border-radius:50%;animation:spin .8s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}@media(max-width:1100px){#map,.mapwrap{min-height:470px}.cards{grid-template-columns:repeat(2,1fr)}.info-grid{grid-template-columns:1fr 1fr}}@media(max-width:650px){.content{padding:12px}.top{padding:0 12px}.hero{align-items:flex-start;flex-direction:column}h1{font-size:28px}.cards{grid-template-columns:1fr 1fr;gap:8px}.stat{padding:12px}.stat strong{font-size:22px}#map{min-height:380px}.gpslist{max-height:220px}.info-grid{grid-template-columns:1fr}.side{padding:15px 10px}.navbtn{padding:10px 9px}.hamburger{display:inline-flex!important}}
</style></head><body>
<div class="app"><div id="menuOverlay" class="menu-overlay" onclick="toggleMenu(false)"></div><aside class="side" id="sideMenu"><div class="logo">🐜 <span>SWIFTROUTE</span></div><button class="navbtn active" data-nav="dashboard" title="Dashboard" onclick="goSection('dashboard',this)">🏠 <span class="navtext">Dashboard</span></button><button class="navbtn" data-nav="optimizer" title="Optimizer" onclick="goSection('optimizer',this)">⚡ <span class="navtext">Optimizer</span></button><button class="navbtn" data-nav="map" title="Map" onclick="goSection('mapPanel',this)">🗺️ <span class="navtext">Map</span></button><button class="navbtn" data-nav="api" title="API" onclick="goSection('apiPanel',this)">🔑 <span class="navtext">API</span></button><button class="navbtn" data-nav="usage" title="Usage" onclick="goSection('usagePanel',this)">📊 <span class="navtext">Usage</span></button><button class="navbtn" data-nav="performance" title="Performances" onclick="goSection('performancePanel',this)">📈 <span class="navtext">Performances</span></button><button class="navbtn" data-nav="billing" title="Billing" onclick="goSection('billingPanel',this)">💳 <span class="navtext">Billing</span></button><button class="navbtn" data-nav="support" title="Support" onclick="goSection('supportPanel',this)">💬 <span class="navtext">Support</span></button><div class="bottom"><form action="/logout" method="post"><button class="navbtn" title="Déconnexion">↪️ <span class="navtext">Déconnexion</span></button></form></div></aside>
<main class="main"><header class="top"><div class="top-left"><button type="button" class="hamburger" id="hamburgerButton" aria-label="Ouvrir le menu" aria-expanded="false">☰</button><strong>Route Intelligence</strong></div><div class="status"><span class="dot"></span>Session active</div></header><div class="content">
<section class="hero" id="dashboard"><div><div class="muted" style="font-size:13px;font-weight:800">ANTSTRIKE COMMERCIAL / SWIFTROUTE ENGINE</div><h1>Route Optimization Workspace</h1><div class="muted">Prépare, optimise et visualise autant de points que les ressources du serveur peuvent traiter.</div></div><button class="primary" onclick="newOptimization()">＋ Nouvelle optimisation</button></section>
<section class="cards"><div class="stat"><small>POINTS</small><strong id="sPoints">0</strong></div><div class="stat"><small>DISTANCE ROUTIÈRE</small><strong id="sRoad">—</strong></div><div class="stat"><small>DURÉE</small><strong id="sTime">—</strong></div><div class="stat"><small>CAPACITÉ</small><strong>Serveur</strong></div></section>
<section class="workspace" id="optimizer"><div class="panel"><h2>⚡ Route Builder</h2><div class="tabs"><button class="tab active" onclick="switchMode('gps',this)">GPS</button><button class="tab" onclick="switchMode('csv',this)">CSV</button><button class="tab" onclick="switchMode('search',this)">Recherche</button></div>
<div id="mode-gps" class="modepanel active"><div class="pointshead"><b>Points</b><span class="counter"><span id="count">0</span> points</span></div><div class="progress"><i id="bar"></i></div><div id="gpslist" class="gpslist"></div><div class="actions"><button class="ghost" onclick="addPoint()">＋ Ajouter</button><button class="primary big" onclick="optimize()">⚡ OPTIMIZE ROUTE</button><button class="ghost" onclick="clearAll()">Effacer</button></div><div class="quality"><div style="display:flex;justify-content:space-between;gap:8px;align-items:center"><div><b>🧭 Validation des points</b><div class="muted" style="font-size:12px;margin-top:4px">Vérifie la proximité de chaque point avec le réseau routier.</div></div><button class="ghost" onclick="classifyPoints()">🔎 Analyser</button></div><div id="qualityBox" style="display:none"></div></div></div>
<div id="mode-csv" class="modepanel"><p class="muted">CSV accepté : <b>name,lat,lon</b> ou <b>lat,lon</b>.</p><input id="csv" type="file" accept=".csv,text/csv"><button class="primary big" onclick="importCSV()">Importer les points</button></div>
<div id="mode-search" class="modepanel"><label>Départ</label><div class="searchrow"><input id="departQ" placeholder="New York, USA"><button onclick="searchPlace('depart')">Chercher</button></div><label>Arrêt</label><div class="searchrow"><input id="stopQ" placeholder="Paris, France"><button onclick="searchPlace('stop')">Ajouter</button></div><label>Destination</label><div class="searchrow"><input id="destQ" placeholder="Tokyo, Japan"><button onclick="searchPlace('dest')">Chercher</button></div><div id="searchStatus" class="muted" style="margin-top:12px"></div></div>
<div id="result" class="result"></div><div class="analytics" id="analyticsPanel"><div class="analytics-head"><div><b>📈 Route Intelligence</b><div class="muted" style="font-size:12px;margin-top:4px">Lecture visuelle de l’itinéraire après optimisation.</div></div><button class="ghost" onclick="focusMap()">🗺️ Voir la carte</button></div><div class="analytics-grid"><div class="chart-card"><div class="chart-title">Performance</div><div id="distanceChart"></div></div><div class="chart-card"><div class="chart-title">Ordre des étapes</div><div id="sequenceChart" class="sequence"></div><div id="nextStopInfo" class="next-stop">Aucun itinéraire suivi.</div></div></div></div></div>
<div class="panel mapwrap" id="mapPanel"><div class="maptools"><button onclick="fitAll()">⌖ Recentrer</button><button id="markerToggle" onclick="toggleMarkers()">● Points ON</button><button id="followToggle" onclick="toggleFollow()">📍 Suivre</button><button onclick="toggleMapFullscreen()">⛶ Agrandir</button><button class="exit-map" onclick="toggleMapFullscreen(false)">✕ Fermer</button></div><div id="followBadge" class="follow-badge">GPS : inactif</div><div class="loading" id="loading"><div class="spinner"></div><b id="loadingText">Optimisation...</b><span class="muted">SwiftRoute Engine</span></div><div id="map"></div></div></section>
<section class="panel section-panel" id="apiPanel"><h2>🔑 Developer Access</h2><p class="muted">Utilisez votre clé avec <code>X-API-KEY</code> pour les appels directs. L'interface web utilise une session HttpOnly.</p><div style="background:#090b0e;border:1px solid #2d3139;border-radius:10px;padding:12px;font-family:monospace;overflow:auto">POST /api/route<br>X-API-KEY: YOUR_API_KEY<br>Content-Type: application/json</div><div class="quick-actions"><button class="ghost" onclick="copyApiExample()">📋 Copier l'exemple API</button><button class="ghost" onclick="toast('La clé API reste protégée dans votre espace client.')">🔒 Sécurité</button></div></section>
<section class="panel section-panel" id="usagePanel"><h2>📊 Usage</h2><p class="muted">Suivi de cette session et de la dernière optimisation effectuée.</p><div class="info-grid"><div class="info-card"><small class="muted">Points chargés</small><strong id="usagePoints">0</strong></div><div class="info-card"><small class="muted">Optimisations</small><strong id="usageRuns">0</strong></div><div class="info-card"><small class="muted">Dernier résultat</small><strong id="usageDistance">—</strong></div></div><div class="quick-actions"><button class="ghost" onclick="goSection('optimizer')">⚡ Nouvelle optimisation</button><button class="ghost" onclick="resetUsageView()">↻ Réinitialiser l'affichage</button></div></section>
<section class="panel section-panel" id="performancePanel"><div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap"><div><h2>📈 Performances</h2><p class="muted">Mesures de la dernière optimisation : distance, durée, nombre de points et ordre calculé.</p></div><button class="ghost" onclick="renderPerformancePanel()">↻ Actualiser</button></div><div class="info-grid"><div class="info-card"><small class="muted">Distance</small><strong id="perfDistance">—</strong></div><div class="info-card"><small class="muted">Durée estimée</small><strong id="perfTime">—</strong></div><div class="info-card"><small class="muted">Points</small><strong id="perfPoints">0</strong></div></div><div class="analytics-grid" style="margin-top:14px"><div class="chart-card"><div class="chart-title">Répartition du parcours</div><div id="perfChart"><div class="muted">Lancez une optimisation pour afficher les données.</div></div></div><div class="chart-card"><div class="chart-title">Ordre calculé</div><div id="perfSequence" class="sequence"></div><div id="perfNext" class="next-stop">Aucun itinéraire calculé.</div></div></div></section>
<section class="panel section-panel" id="billingPanel"><h2>💳 Billing & Tiun</h2><p class="muted">Gérez votre abonnement SwiftRoute avec Tiun, notre Merchant of Record.</p><div class="info-grid"><div class="info-card"><small class="muted">Statut</small><strong id="billingStatus" style="color:var(--green)">NON VÉRIFIÉ</strong></div><div class="info-card"><small class="muted">Abonnement</small><strong>Tiun</strong></div><div class="info-card"><small class="muted">Accès</small><strong>Selon votre offre</strong></div><div class="info-card"><small class="muted">Produit</small><strong style="font-size:16px">SwiftRoute</strong></div></div><div class="quick-actions"><button class="primary" onclick="startTiunCheckout()">💳 Prendre l'abonnement</button><button class="ghost" onclick="tiunLogin()">🔐 J'ai déjà un abonnement</button><a class="support-link" href="mailto:__EMAIL_CONTACT__?subject=SwiftRoute%20Billing">✉️ Contacter la facturation</a></div><p class="muted" style="font-size:12px;margin:12px 0 0">Tiun gère l’abonnement et les droits commerciaux. SwiftRoute applique uniquement les limites techniques réelles du serveur et des services cartographiques.</p><div id="tiunStatus" class="result" style="display:none"></div></section>
<section class="panel section-panel" id="supportPanel"><h2>💬 Support</h2><p class="muted">Besoin d'aide pour l'API, la carte ou l'optimisation ? Contactez directement SwiftRoute.</p><div class="quick-actions"><a class="support-link" href="mailto:__EMAIL_CONTACT__?subject=Support%20SwiftRoute">✉️ E-mail support</a><a class="support-link" target="_blank" rel="noopener" href="https://wa.me/__WHATSAPP_DIGITS__?text=Bonjour%20SwiftRoute%2C%20j%27ai%20besoin%20d%27aide.">💬 WhatsApp</a><button class="ghost" onclick="showHelp()">❓ Aide rapide</button></div><div id="helpBox" class="result" style="display:none">1. Ajoutez vos points GPS, CSV ou via Recherche.<br>2. Vérifiez les coordonnées.<br>3. Lancez <b>OPTIMIZE ROUTE</b>.<br>4. Utilisez la carte pour contrôler l'itinéraire.</div></section>
</div></main></div><div id="toast" class="toast"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script><script>
let map=L.map('map').setView([19.5,-72.3],8);
window.addEventListener('load',()=>goSection('dashboard',document.querySelector('.navbtn[data-nav="dashboard"]'))); let routeLayer=null,markers=[],gpsPoints=[],searchPoints={depart:null,destination:null,stops:[]}; let markerVisible=true; let optimizationRuns=0; let lastDistance='—'; let orderedRoute=[]; let watchId=null; let followMode=false; let currentMarker=null; let currentAccuracyCircle=null; let nextStopIndex=1;
L.tileLayer('__TILE_URL__',{maxZoom:19,subdomains:['a','b','c'],attribution:'&copy; OpenStreetMap contributors'}).on('tileerror',()=>{}).addTo(map);
function toast(t){let x=document.getElementById('toast');x.textContent=t;x.style.display='block';clearTimeout(window._toast);window._toast=setTimeout(()=>x.style.display='none',3000)}

async function startTiunCheckout(){
  const status=document.getElementById('tiunStatus');
  const showStatus=(message)=>{if(status){status.textContent=message;status.style.display='block';}};
  try{
    if(!window.tiun){showStatus("Tiun se charge encore. Réessaie dans un instant.");return;}
    if(typeof window.tiun.waitForReady==='function') await window.tiun.waitForReady();
    if(typeof window.tiun.checkout!=='function'){console.error('[Tiun] checkout indisponible',window.tiun);showStatus("Le paiement Tiun n'est pas disponible dans ce snippet.");return;}
    showStatus('Ouverture du paiement Tiun…');
    await window.tiun.checkout({productId:'__TIUN_PRODUCT_ID__'});
  }catch(error){console.error('[Tiun checkout]',error);showStatus("Impossible d'ouvrir Tiun. Vérifie le produit Live et le snippet.");}
}

function tiunLogin(){
  if(!window.tiun || typeof window.tiun.login !== 'function'){
    toast("Tiun n'est pas encore prêt.");
    return;
  }
  try{
    window.tiun.login();
  }catch(error){
    console.error('[Tiun login]', error);
    toast("Impossible d'ouvrir la connexion Tiun.");
  }
}

let currentTiunSessionId = localStorage.getItem('swiftroute_tiun_session') || '';

async function verifyTiunSession(sessionId){
  if(!sessionId) return false;
  try{
    const response = await fetch('/api/tiun/verify-session',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({session_id:sessionId})
    });
    if(!response.ok){
      currentTiunSessionId='';
      localStorage.removeItem('swiftroute_tiun_session');
      return false;
    }
    currentTiunSessionId=sessionId;
    localStorage.setItem('swiftroute_tiun_session',sessionId);
    const status=document.getElementById('billingStatus');
    if(status) status.textContent='ABONNÉ';
    const box=document.getElementById('tiunStatus');
    if(box){box.textContent='✓ Abonnement Tiun vérifié par le serveur.';box.style.display='block';}
    return true;
  }catch(error){
    console.error('[Tiun verification]',error);
    return false;
  }
}

function apiHeaders(extra={}){
  const headers={...extra};
  if(currentTiunSessionId) headers['X-Session-Id']=currentTiunSessionId;
  return headers;
}

async function apiFetch(url,options={}){
  const opts={...options,headers:apiHeaders(options.headers||{})};
  return fetch(url,opts);
}

if(window.tiun && typeof window.tiun.on === 'function'){
  window.tiun.on('paywallHide', async (data) => {
    const sessionId=data?.sessionId;
    if(sessionId){
      const ok=await verifyTiunSession(sessionId);
      const status=document.getElementById('billingStatus');
      if(status) status.textContent=ok?'ABONNÉ':'NON VÉRIFIÉ';
    }
  });
  window.tiun.on('error', (error) => console.error('[Tiun event]', error));
}

if(currentTiunSessionId) verifyTiunSession(currentTiunSessionId);

// Menu mobile robuste : aucun défilement nécessaire pour afficher les options.
document.addEventListener('DOMContentLoaded', () => {
  const hamburger = document.getElementById('hamburgerButton');
  const overlay = document.getElementById('menuOverlay');
  hamburger?.addEventListener('click', (event) => {
    event.preventDefault();
    event.stopPropagation();
    toggleMenu();
  });
  overlay?.addEventListener('click', () => toggleMenu(false));
});
function toggleMenu(force){
  const side=document.getElementById('sideMenu');
  const overlay=document.getElementById('menuOverlay');
  const button=document.getElementById('hamburgerButton');
  if(!side) return;
  const open=typeof force==='boolean'?force:!side.classList.contains('open');
  side.classList.toggle('open',open);
  if(overlay) overlay.classList.toggle('open',open);
  if(button) button.setAttribute('aria-expanded',String(open));
  document.body.classList.toggle('menu-open',open);
}
function setActiveNav(key){
  document.querySelectorAll('.navbtn[data-nav]').forEach(b => b.classList.toggle('active', b.dataset.nav === key));
}
function goSection(id,btn){
  const dashboard=document.getElementById('dashboard');
  const optimizer=document.getElementById('optimizer');
  const mapPanel=document.getElementById('mapPanel');
  const apiPanel=document.getElementById('apiPanel');
  const usagePanel=document.getElementById('usagePanel');
  const billingPanel=document.getElementById('billingPanel');
  const supportPanel=document.getElementById('supportPanel');
  const performancePanel=document.getElementById('performancePanel');
  const cards=document.querySelector('.cards');
  const routeBuilder=optimizer ? optimizer.querySelector('.panel:first-child') : null;
  [dashboard,optimizer,apiPanel,usagePanel,performancePanel,billingPanel,supportPanel].filter(Boolean).forEach(el=>el.classList.add('view-hidden'));
  routeBuilder?.classList.add('view-hidden');
  mapPanel?.classList.add('view-hidden');
  cards?.classList.add('view-hidden');
  if(id==='dashboard'){ dashboard?.classList.remove('view-hidden'); cards?.classList.remove('view-hidden'); }
  else if(id==='optimizer'){ optimizer?.classList.remove('view-hidden'); routeBuilder?.classList.remove('view-hidden'); mapPanel?.classList.remove('view-hidden'); setTimeout(()=>map.invalidateSize(),120); }
  else if(id==='mapPanel'){ optimizer?.classList.remove('view-hidden'); routeBuilder?.classList.remove('view-hidden'); mapPanel?.classList.remove('view-hidden'); setTimeout(()=>map.invalidateSize(),120); }
  else { document.getElementById(id)?.classList.remove('view-hidden'); if(id==='performancePanel') renderPerformancePanel(); }
  const key=btn?.dataset?.nav || ({dashboard:'dashboard',optimizer:'optimizer',mapPanel:'map',apiPanel:'api',usagePanel:'usage',billingPanel:'billing',supportPanel:'support',performancePanel:'performance'}[id] || 'dashboard');
  setActiveNav(key);
  toggleMenu(false);
  window.scrollTo({top:0,behavior:'smooth'});
}
function newOptimization(){clearAll();goSection('optimizer');toast('Nouvelle optimisation prête.')}
function copyApiExample(){const text=`POST /api/route\nX-API-KEY: YOUR_API_KEY\nContent-Type: application/json`; if(navigator.clipboard){navigator.clipboard.writeText(text).then(()=>toast('Exemple API copié.')).catch(()=>fallbackCopy(text))}else{fallbackCopy(text)}}
function fallbackCopy(text){const ta=document.createElement('textarea');ta.value=text;ta.style.position='fixed';ta.style.opacity='0';document.body.appendChild(ta);ta.focus();ta.select();try{document.execCommand('copy');toast('Exemple API copié.')}catch(e){toast('Copie non disponible sur ce navigateur.')}ta.remove()}
function resetUsageView(){optimizationRuns=0;lastDistance='—';document.getElementById('usageRuns').textContent='0';document.getElementById('usageDistance').textContent='—';toast('Affichage Usage réinitialisé.')}
function updateUsage(){document.getElementById('usagePoints').textContent=gpsPoints.length;document.getElementById('usageRuns').textContent=optimizationRuns;document.getElementById('usageDistance').textContent=lastDistance}
function renderPerformancePanel(){
  const d=document.getElementById('perfDistance'), t=document.getElementById('perfTime'), p=document.getElementById('perfPoints');
  if(!d)return;
  d.textContent=lastDistance||'—';
  t.textContent=document.getElementById('sTime')?.textContent||'—';
  p.textContent=orderedRoute.length||gpsPoints.length||0;
  const chart=document.getElementById('perfChart');
  if(chart){
    const raw=String(lastDistance||'').replace(',','.'); const n=parseFloat(raw);
    const width=Number.isFinite(n)?Math.max(8,Math.min(100,n/10)):0;
    chart.innerHTML=Number.isFinite(n)
      ? `<div class="bar-row"><span>Distance</span><div class="bar-track"><div class="bar-fill" style="width:${width}%"></div></div><b>${esc(lastDistance)}</b></div><div class="bar-row"><span>Points</span><div class="bar-track"><div class="bar-fill" style="width:${Math.min(100,(gpsPoints.length||orderedRoute.length)*2)}%"></div></div><b>${gpsPoints.length||orderedRoute.length}</b></div>`
      : '<div class="muted">Aucune optimisation disponible.</div>';
  }
  const seq=document.getElementById('perfSequence');
  const arr=orderedRoute.length?orderedRoute:gpsPoints.map((x,i)=>({name:x.name||('Point '+(i+1)),lat:Number(x.lat),lon:Number(x.lon),country:x.country||''}));
  if(seq){
    if(!arr.length){seq.innerHTML='<div class="muted">Aucun itinéraire calculé.</div>';}
    else{
      seq.innerHTML=arr.slice(0,600).map((pt,i)=>{
        const next=arr[i+1], km=next?haversineKm(pt,next):null;
        const parts=String(pt.name||('Point '+(i+1))).split(',').map(x=>x.trim()).filter(Boolean);
        const place=parts[0]||('Point '+(i+1));
        const country=pt.country||parts[parts.length-1]||'Lieu GPS';
        return `<div class="seq-item"><div class="seq-badge ${i===0?'start':''}">${i+1}</div><div class="seq-main"><b>${esc(place)}</b><span>${esc(country)}</span></div><div class="seq-distance">${km!==null?esc(km.toFixed(km<100?1:0))+' km':'FIN'}</div></div>${i<arr.length-1?'<div class="seq-connector"></div>':''}`;
      }).join('');
    }
  }
  const next=document.getElementById('perfNext');
  if(next) next.textContent=arr.length>1?`Ordre optimal : ${arr.length} points · distances géométriques entre étapes.`:'Aucun itinéraire calculé.';
}
function showHelp(){let x=document.getElementById('helpBox');x.style.display=x.style.display==='none'?'block':'none'}

function switchMode(name,btn){document.querySelectorAll('.modepanel').forEach(x=>x.classList.remove('active'));document.getElementById('mode-'+name).classList.add('active');document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));btn.classList.add('active')}
function esc(v){return String(v??'').replace(/[&<>'\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','\"':'&quot;'}[c]))}
let mapEditTimer=null;
function refreshMapFromInputs(focusFirst=false){
  clearTimeout(mapEditTimer);
  mapEditTimer=setTimeout(()=>{
    const pts=gpsPoints.filter(valid).map((p,i)=>({name:p.name||('Point '+(i+1)),lat:Number(p.lat),lon:Number(p.lon),country:p.country||''}));
    drawMarkers(pts);
    if(focusFirst&&pts.length)map.setView([pts[0].lat,pts[0].lon],14,{animate:true});
  },120);
}
function renderGPS(){
  let box=document.getElementById('gpslist');box.innerHTML='';
  gpsPoints.forEach((p,i)=>{
    let r=document.createElement('div');r.className='gpsrow';
    r.innerHTML=`<div class="num">${i+1}</div><input value="${esc(p.name||'')}" placeholder="Ville / nom" onchange="gpsPoints[${i}].name=this.value;refreshMapFromInputs(${i===0})"><input value="${esc(p.lat)}" placeholder="latitude" onchange="gpsPoints[${i}].lat=this.value;refreshMapFromInputs(${i===0})"><input value="${esc(p.lon)}" placeholder="longitude" onchange="gpsPoints[${i}].lon=this.value;refreshMapFromInputs(${i===0})"><button class="remove" onclick="gpsPoints.splice(${i},1);renderGPS();refreshMapFromInputs(false)">×</button>`;
    box.appendChild(r);
  });
  document.getElementById('count').textContent=gpsPoints.length;
  document.getElementById('bar').style.width=(gpsPoints.length?'100%':'0%');
  document.getElementById('sPoints').textContent=gpsPoints.length;
  updateUsage();
}
function addPoint(p={name:'',lat:'',lon:''}){gpsPoints.push(p);renderGPS();if(valid(p)){drawMarkers(gpsPoints);if(gpsPoints.length===1)focusFirstPoint()}}
function clearAll(){stopFollowing();orderedRoute=[];document.getElementById('analyticsPanel')?.classList.remove('visible');document.querySelector('#optimizer .panel:first-child')?.classList.remove('route-builder-compact');gpsPoints=[];searchPoints={depart:null,destination:null,stops:[]};renderGPS();if(routeLayer){map.removeLayer(routeLayer);routeLayer=null};markers.forEach(m=>map.removeLayer(m));markers=[];document.getElementById('result').style.display='none';document.getElementById('qualityBox').style.display='none';document.getElementById('qualityBox').innerHTML='';document.getElementById('sRoad').textContent='—';document.getElementById('sTime').textContent='—';lastDistance='—';updateUsage()}
function valid(p){return Number.isFinite(Number(p.lat))&&Number.isFinite(Number(p.lon))&&Number(p.lat)>=-90&&Number(p.lat)<=90&&Number(p.lon)>=-180&&Number(p.lon)<=180}
function getPoints(){let points;if(document.getElementById('mode-search').classList.contains('active')){if(!searchPoints.depart||!searchPoints.destination)throw Error('Ajoutez un départ et une destination.');points=[searchPoints.depart,...searchPoints.stops,searchPoints.destination]}else points=gpsPoints.map((p,i)=>({name:p.name||'Point '+(i+1),lat:Number(p.lat),lon:Number(p.lon)}));if(points.length<2)throw Error('Il faut au moins 2 points.');if(points.some(p=>!valid(p)))throw Error('Une coordonnée est invalide.');return points}
async function importCSV(){let f=document.getElementById('csv').files[0];if(!f)return toast('Choisissez un fichier CSV.');let text=await f.text();let lines=text.split(/\\r?\\n/).map(x=>x.trim()).filter(Boolean);let start=/lat.*lon/i.test(lines[0])?1:0;let arr=[];for(let i=start;i<lines.length;i++){let a=lines[i].split(',').map(x=>x.trim());if(a.length<2)continue;let hasName=a.length>=3&&!Number.isFinite(Number(a[0]));let name=hasName?a[0]:'Point '+(arr.length+1);let lat=Number(hasName?a[1]:a[0]),lon=Number(hasName?a[2]:a[1]);if(Number.isFinite(lat)&&Number.isFinite(lon))arr.push({name,lat,lon})}gpsPoints=arr;renderGPS();switchMode('gps',document.querySelector('.tab'));drawMarkers(gpsPoints);focusFirstPoint();toast(arr.length+' points importés.')}
async function searchPlace(type){let id=type==='depart'?'departQ':type==='dest'?'destQ':'stopQ';let q=document.getElementById(id).value.trim();if(!q)return;const status=document.getElementById('searchStatus');if(status){status.className='search-result';status.innerHTML='<div class="label">Recherche en cours</div><div class="place">'+esc(q)+'</div>';}try{let r=await fetch('/api/geocode?q='+encodeURIComponent(q));let d=await r.json();if(!r.ok)throw Error(d.detail||'Lieu introuvable');let p={name:d.display_name,lat:Number(d.lat),lon:Number(d.lon)};if(type==='depart')searchPoints.depart=p;else if(type==='dest')searchPoints.destination=p;else searchPoints.stops.push(p);if(status){status.className='search-result';status.innerHTML='<div class="label">Résultat trouvé</div><div class="place">✓ '+esc(p.name)+'</div><div class="coords">LAT '+p.lat.toFixed(6)+' · LON '+p.lon.toFixed(6)+'</div>';}toast('Lieu ajouté à la route');drawSearchPreview();focusMap();}catch(e){if(status){status.className='search-result';status.innerHTML='<div class="label" style="color:#ef4444">Recherche</div><div class="place">'+esc(e.message)+'</div>';}toast(e.message)}}
function drawSearchPreview(){const pts=[];if(searchPoints.depart)pts.push(searchPoints.depart);pts.push(...searchPoints.stops);if(searchPoints.destination)pts.push(searchPoints.destination);if(pts.length){drawMarkers(pts);fitAll();}}

function showLoading(t){document.getElementById('loadingText').textContent=t;document.getElementById('loading').style.display='flex'}function hideLoading(){document.getElementById('loading').style.display='none'}
function clearMarkers(){markers.forEach(m=>map.removeLayer(m));markers=[]}
function makePointIcon(i,p,total){
  const base=i===0?'start':(i===total-1?'end':'');
  const status=p.classification?.status==='invalid'?'water':(p.classification?.status==='review'?'review':'');
  const cls=(base+' '+status).trim();
  return L.divIcon({className:'',html:'<div class="point-dot '+cls+'"></div>',iconSize:[18,18],iconAnchor:[9,9]});
}
function popupForPoint(p,i){
  const rawName=p.name||('Point '+(i+1));
  const parts=rawName.split(',').map(x=>x.trim()).filter(Boolean);
  const place=parts[0]||rawName;
  const country=p.country||p.classification?.country||parts[parts.length-1]||'Lieu GPS';
  const extra=p.classification?'<br><span class="popup-muted">'+esc(p.classification.label)+'</span>':'';
  return '<div class="point-popup"><b>'+esc(place)+'</b><br><span class="popup-country">'+esc(country)+'</span><br>Latitude : '+Number(p.lat).toFixed(6)+'<br>Longitude : '+Number(p.lon).toFixed(6)+extra+'</div>';
}
function drawMarkers(points){
  clearMarkers();
  points.forEach((p,i)=>{
    let m=L.marker([p.lat,p.lon],{icon:makePointIcon(i,p,points.length),title:(i+1)+'. '+(p.name||'Point')}).addTo(map);
    m.bindPopup(popupForPoint(p,i),{maxWidth:260});
    markers.push(m);
  });
}
function fitAll(){if(routeLayer)map.fitBounds(routeLayer.getBounds(),{padding:[45,45]});else if(markers.length){let g=L.featureGroup(markers);map.fitBounds(g.getBounds(),{padding:[45,45]})}}
function focusFirstPoint(){if(!gpsPoints.length||!valid(gpsPoints[0]))return;const p=gpsPoints[0];map.setView([Number(p.lat),Number(p.lon)],14,{animate:true});setTimeout(()=>map.invalidateSize(),180)}
function toggleMarkers(){markerVisible=!markerVisible;markers.forEach(m=>markerVisible?m.addTo(map):map.removeLayer(m));let b=document.getElementById('markerToggle');if(b)b.textContent=markerVisible?'● Points ON':'○ Points OFF';toast(markerVisible?'Points affichés':'Points masqués')}
function focusMap(){goSection('mapPanel');setTimeout(()=>{map.invalidateSize();if(routeLayer||markers.length)fitAll();},250)}
function toggleMapFullscreen(force){const panel=document.getElementById('mapPanel');if(!panel)return;const open=typeof force==='boolean'?force:!panel.classList.contains('map-fullscreen');panel.classList.toggle('map-fullscreen',open);document.body.style.overflow=open?'hidden':'';setTimeout(()=>map.invalidateSize(),80);if(open)toast('Carte plein écran : portrait ou paysage pris en charge.')}
function scrollToOpt(){goSection('optimizer')} function showApi(){goSection('apiPanel')}
function straightGeo(points){return {type:'Feature',properties:{fallback:true},geometry:{type:'LineString',coordinates:points.map(p=>[p.lon,p.lat])}}}
async function classifyPoints(){
  const box=document.getElementById('qualityBox');
  try{
    const points=getPoints();
    showLoading('Analyse de la qualité géographique...');
    const r=await apiFetch('/api/classify-points',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({points})});
    const data=await r.json();
    if(!r.ok) throw Error(data.detail||'Erreur de classification');
    const byKey=new Map(data.results.map(x=>[x.lat.toFixed(7)+'|'+x.lon.toFixed(7),x]));
    points.forEach(p=>p.classification=byKey.get(Number(p.lat).toFixed(7)+'|'+Number(p.lon).toFixed(7)));
    const c=data.summary;
    box.style.display='block';
    box.innerHTML='<div style="margin-top:12px"><div class="result-title">Qualité géographique · '+data.quality_score+'%</div><div class="quality-grid"><div class="quality-card q-valid">Sur route<b>'+c.valid+'</b></div><div class="quality-card q-review">À vérifier<b>'+c.review+'</b></div><div class="quality-card q-invalid">Non routable probable<b>'+c.invalid+'</b></div><div class="quality-card q-unknown">Non vérifiable<b>'+c.unknown+'</b></div></div><div class="quality-list">'+data.results.map((x,i)=>'<div style="padding:8px 0;border-bottom:1px solid #20232a"><b>'+(i+1)+'. '+esc(x.name)+'</b><br><span class="q-'+x.status+'">'+esc(x.label)+'</span> · '+x.confidence+'%'+(x.road_distance_m!=null?' · '+x.road_distance_m+' m de la route':'')+'</div>').join('')+'</div></div>';
    drawMarkers(points);
    hideLoading();toast('Analyse terminée : '+data.points+' points.');
  }catch(e){hideLoading();toast(e.message)}
}

function haversineKm(a,b){const R=6371.0088,p1=Number(a.lat)*Math.PI/180,p2=Number(b.lat)*Math.PI/180,dp=p2-p1,dl=(Number(b.lon)-Number(a.lon))*Math.PI/180;const x=Math.sin(dp/2)**2+Math.cos(p1)*Math.cos(p2)*Math.sin(dl/2)**2;return 2*R*Math.asin(Math.min(1,Math.sqrt(x)))}
function updateCharts(points,road){const panel=document.getElementById('analyticsPanel');if(!panel)return;panel.classList.add('visible');const distance=Number(road.distance_km)||0;const duration=road.duration_min==='—'?0:Number(road.duration_min)||0;const direct=points.reduce((sum,p,i)=>i?sum+haversineKm(points[i-1],p):0,0);const vals=[['Route',distance],['Distance directe',direct],['Durée',duration]];const max=Math.max(...vals.map(x=>x[1]),1);document.getElementById('distanceChart').innerHTML=vals.map(([label,v])=>'<div class="bar-row"><span>'+esc(label)+'</span><div class="bar-track"><div class="bar-fill" style="width:'+Math.max(4,(v/max)*100)+'%"></div></div><b>'+v.toFixed(v<100?1:0)+(label==='Durée'?' min':' km')+'</b></div>').join('');document.getElementById('sequenceChart').innerHTML=points.map((p,i)=>(i?'<span class="seq-line"></span>':'')+'<div class="seq-node '+(i===0?'start':i===points.length-1?'end':'')+'" title="'+esc(p.name||'Point '+(i+1))+'">'+(i+1)+'</div>').join('');updateNextStopInfo()}
function updateNextStopInfo(){const box=document.getElementById('nextStopInfo');if(!box)return;if(!orderedRoute.length){box.textContent='Aucun itinéraire suivi.';return}const next=orderedRoute[Math.min(nextStopIndex,orderedRoute.length-1)];box.innerHTML='<b>Prochaine étape :</b> '+esc(next?.name||('Point '+(nextStopIndex+1)))+' · '+Number(next?.lat).toFixed(5)+', '+Number(next?.lon).toFixed(5)}
function stopFollowing(){if(watchId!==null&&navigator.geolocation){navigator.geolocation.clearWatch(watchId);watchId=null}followMode=false;const b=document.getElementById('followToggle');if(b)b.textContent='📍 Suivre';const badge=document.getElementById('followBadge');if(badge){badge.textContent='GPS : inactif';badge.classList.remove('on')}}
let lastRoadDistanceAt=0;
async function refreshRoadDistance(here,target){
  const now=Date.now();
  if(now-lastRoadDistanceAt<5000)return;
  lastRoadDistanceAt=now;
  try{
    const r=await apiFetch('/api/next-distance',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({current:{name:'Vous',lat:here.lat,lon:here.lon},target})});
    const d=await r.json();
    if(r.ok){const badge=document.getElementById('followBadge');if(badge)badge.textContent='GPS : '+Number(d.distance_km).toFixed(2)+' km · '+Number(d.duration_min).toFixed(0)+' min';}
  }catch(e){}
}
function toggleFollow(){if(followMode){stopFollowing();toast('Suivi GPS arrêté.');return}if(!navigator.geolocation){toast('Le GPS du navigateur n’est pas disponible.');return}if(!orderedRoute.length){toast('Lance d’abord une optimisation.');return}followMode=true;const b=document.getElementById('followToggle');if(b)b.textContent='⛔ Arrêter';const badge=document.getElementById('followBadge');if(badge){badge.textContent='GPS : recherche…';badge.classList.add('on')}watchId=navigator.geolocation.watchPosition(pos=>{const here={lat:pos.coords.latitude,lon:pos.coords.longitude};if(!currentMarker)currentMarker=L.marker([here.lat,here.lon],{icon:L.divIcon({className:'',html:'<div class="map-current-label">● Vous êtes ici</div>',iconAnchor:[0,18]})}).addTo(map);else currentMarker.setLatLng([here.lat,here.lon]);if(currentAccuracyCircle)currentAccuracyCircle.setLatLng([here.lat,here.lon]).setRadius(pos.coords.accuracy||30);else currentAccuracyCircle=L.circle([here.lat,here.lon],{radius:pos.coords.accuracy||30,color:'#22c55e',weight:1,fillOpacity:.08}).addTo(map);let bestI=nextStopIndex,bestD=Infinity;for(let i=Math.max(1,nextStopIndex);i<orderedRoute.length;i++){const d=haversineKm(here,orderedRoute[i]);if(d<bestD){bestD=d;bestI=i}}nextStopIndex=bestI;if(bestD<0.15&&nextStopIndex<orderedRoute.length-1)nextStopIndex++;refreshRoadDistance(here,orderedRoute[Math.min(nextStopIndex,orderedRoute.length-1)]);const badge=document.getElementById('followBadge');if(badge)badge.textContent='GPS : '+bestD.toFixed(2)+' km';updateNextStopInfo();if(followMode)map.panTo([here.lat,here.lon],{animate:true,duration:.35})},err=>{const badge=document.getElementById('followBadge');if(badge)badge.textContent='GPS : indisponible';toast('GPS : '+(err.message||'position non disponible'));stopFollowing()},{enableHighAccuracy:true,maximumAge:5000,timeout:15000})}
window.addEventListener('orientationchange',()=>setTimeout(()=>map.invalidateSize(),250));

async function optimize(){let result=document.getElementById('result');try{let points=getPoints();orderedRoute=[];showLoading("Calcul de l’ordre optimal...");let r=await apiFetch('/api/route',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({villes:points.map(p=>[p.lat,p.lon])})});let data=await r.json();if(!r.ok)throw Error(data.detail||'Erreur moteur');let ordered=data.route.filter((v,i,a)=>i===0||v!==0).map(i=>points[i]);if(ordered[ordered.length-1]!==points[points.length-1])ordered.push(points[points.length-1]);orderedRoute=ordered;nextStopIndex=1;drawMarkers(ordered);focusMap();showLoading('Vérification du réseau routier...');
let qc=await apiFetch('/api/classify-points',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({points:ordered})});
let qd=await qc.json();
if(qc.ok&&Array.isArray(qd.results)){
  const byKey=new Map(qd.results.map(x=>[x.lat.toFixed(7)+'|'+x.lon.toFixed(7),x]));
  ordered.forEach(p=>p.classification=byKey.get(Number(p.lat).toFixed(7)+'|'+Number(p.lon).toFixed(7)));
  drawMarkers(ordered);
  const bad=qd.results.filter(x=>x.status==='invalid');
  if(bad.length){
    hideLoading();result.style.display='block';
    result.innerHTML='<div class="result-title">⚠ Points non routables détectés</div><div class="route-status">'+bad.length+' point(s) sont trop éloignés du réseau routier. Ils sont affichés en bleu sur la carte. SwiftRoute ne dessine pas une fausse route routière à travers ces points.</div><div class="route-list">'+bad.map(x=>'<div class="route-item"><b>'+esc(x.name)+'</b> · '+esc(x.label)+'</div>').join('')+'</div>';
    toast('Route routable interrompue : point(s) à vérifier.');return;
  }
}
showLoading('Calcul du tracé routier...');let rr=await apiFetch('/api/road-route',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({points:ordered})});let road=await rr.json();if(!rr.ok){toast('Routeur indisponible : aucun faux tracé silencieux.');throw Error(road.detail||'Le service routier n’a pas trouvé de route.')}if(routeLayer)map.removeLayer(routeLayer);routeLayer=L.geoJSON(road.geometry,{style:{color:'#f59e0b',weight:7,opacity:.96,lineCap:'round',lineJoin:'round',smoothFactor:1.1}}).addTo(map);fitAll();document.getElementById('sRoad').textContent=road.distance_km+' km';document.getElementById('sTime').textContent=(road.duration_min==='—'?'—':road.duration_min+' min');optimizationRuns++;lastDistance=road.distance_km+' km';updateUsage();result.style.display='block';result.innerHTML='<div class="result-title">✓ Itinéraire optimisé</div><div class="result-meta"><span class="pill">📍 '+ordered.length+' points</span><span class="pill">🛣️ Route routable</span><span class="pill">📏 '+road.distance_km+' km</span><span class="pill">⏱️ '+(road.duration_min==='—'?'—':road.duration_min+' min')+'</span></div><div class="route-status"><strong>Navigation prête.</strong> Appuyez sur « Suivre » pour utiliser le GPS du téléphone et calculer automatiquement la distance jusqu’à la prochaine étape.</div><div class="route-list">'+ordered.map((p,i)=>'<div class="route-item"><b>'+String(i+1).padStart(2,'0')+'</b> · '+esc(p.name||('Point '+(i+1)))+' <span class="muted">('+Number(p.lat).toFixed(5)+', '+Number(p.lon).toFixed(5)+')</span></div>').join('')+'</div>';updateCharts(ordered,road);renderPerformancePanel();document.querySelector('#optimizer .panel:first-child')?.classList.add('route-builder-compact');hideLoading();toast('Optimisation terminée.');focusMap()}catch(e){hideLoading();result.style.display='block';result.innerHTML='<span style="color:#ef4444">Erreur :</span> '+esc(e.message);toast(e.message)}}

window.addEventListener('resize',()=>map.invalidateSize());
</script></body></html>'''.replace('__TIUN_SNIPPET_ID__', TIUN_SNIPPET_ID).replace('__TIUN_PRODUCT_ID__', TIUN_PRODUCT_ID).replace('__EMAIL_CONTACT__', EMAIL_CONTACT).replace('__WHATSAPP_DIGITS__', ''.join(c for c in WHATSAPP_CONTACT if c.isdigit())).replace('__TILE_URL__', TILE_URL).replace('__EMAIL_CONTACT__', EMAIL_CONTACT).replace('__WHATSAPP_DIGITS__', ''.join(c for c in WHATSAPP_CONTACT if c.isdigit()))

# ========================= ENGINE =========================
# SwiftRoute FAST: ACO + adaptive 2-opt + early stopping.
# L'objectif est d'améliorer la qualité sans multiplier inutilement le temps de calcul.
NB_FOURMIS=15
ALPHA,BETA,EVAPORATION,Q=1.0,2.0,0.3,100.0
CAPACITE_MAX_VEHICULE=10


def _distance_route(route, dists):
    return sum(dists[a][b] for a,b in zip(route, route[1:]))


def ameliorer_2opt(route, dists, max_passes=2):
    """Amélioration locale 2-opt. Rapide et limitée pour conserver la vitesse."""
    if len(route) < 5:
        return route, _distance_route(route, dists)
    best=list(route)
    best_dist=_distance_route(best,dists)
    for _ in range(max_passes):
        improved=False
        # On conserve le dépôt au début et à la fin.
        for i in range(1,len(best)-2):
            a,b=best[i-1],best[i]
            for j in range(i+1,len(best)-1):
                c,d=best[j],best[j+1]
                delta=(dists[a][c]+dists[b][d])-(dists[a][b]+dists[c][d])
                if delta < -1e-9:
                    candidate=best[:i]+best[i:j+1][::-1]+best[j+1:]
                    candidate_dist=best_dist+delta
                    if candidate_dist < best_dist:
                        best,best_dist=candidate,candidate_dist
                        improved=True
        if not improved:
            break
    return best,best_dist


def simuler_fourmi_vrp(nb,dists,phero):
    path=[0]; visited={0}; load=0; total=0.0
    while len(visited)<nb:
        act=path[-1]
        if load>=CAPACITE_MAX_VEHICULE:
            total+=dists[act][0]; path.append(0); act=0; load=0
        probs=[]; tot=0.0
        for p in range(nb):
            if p not in visited:
                note=(phero[act][p]**ALPHA)*((1/max(dists[act][p],0.01))**BETA)
                probs.append((p,note)); tot+=note
        if not probs: break
        if tot<=0:
            nxt=min(probs,key=lambda x:dists[act][x[0]])[0]
        else:
            pick=random.uniform(0,tot); cum=0.0; nxt=probs[-1][0]
            for v,prob in probs:
                cum+=prob
                if cum>=pick:
                    nxt=v; break
        total+=dists[act][nxt]; path.append(nxt); visited.add(nxt); load+=1
    total+=dists[path[-1]][0]; path.append(0)
    return path,total


def distance_directe_km(a, b):
    """Distance géographique approximative entre deux points GPS."""
    lat1, lon1 = float(a[0]), float(a[1])
    lat2, lon2 = float(b[0]), float(b[1])
    mean_lat = math.radians((lat1 + lat2) / 2.0)
    return math.hypot(
        (lat2 - lat1) * 111.0,
        (lon2 - lon1) * 111.0 * math.cos(mean_lat)
    ) * 1.23


def calculer_route_scalable(villes):
    """Mode gros volume sans matrice n×n.

    Il n'impose pas de plafond de points : la mémoire reste O(n).
    Pour les très gros volumes, on utilise un balayage angulaire autour du
    centre géographique, beaucoup plus léger qu'une matrice de distances.
    """
    n = len(villes)
    if n < 2:
        return list(range(n)), 0.0
    if n == 2:
        return [0, 1], distance_directe_km(villes[0], villes[1])

    dest = n - 1
    middle = []
    center_lat = sum(float(v[0]) for v in villes[1:dest]) / max(1, dest - 1)
    center_lon = sum(float(v[1]) for v in villes[1:dest]) / max(1, dest - 1)
    cos_lat = max(0.05, abs(math.cos(math.radians(center_lat))))

    for idx in range(1, dest):
        lat, lon = float(villes[idx][0]), float(villes[idx][1])
        x = (lon - center_lon) * cos_lat
        y = lat - center_lat
        angle = math.atan2(y, x)
        radius = x * x + y * y
        middle.append((angle, radius, idx))

    middle.sort(key=lambda item: (item[0], item[1]))
    route = [0] + [idx for _, _, idx in middle] + [dest]

    distance = sum(
        distance_directe_km(villes[a], villes[b])
        for a, b in zip(route, route[1:])
    )
    return route, distance


def calculer_route_precision(villes):
    n=len(villes)
    if n<3:
        if n == 2:
            return [0, 1], distance_directe_km(villes[0], villes[1])
        return list(range(n)),0.0

    # Au-delà de ce seuil, on ne construit plus de matrice n×n.
    # Le nombre de points reste libre ; seul l'algorithme devient plus léger.
    if n > 1200:
        return calculer_route_scalable(villes)
    latm=math.radians(sum(float(v[0]) for v in villes)/n); R=6371.0
    plane=[(R*math.radians(float(lat))*0 + R*math.radians(float(lon))*math.cos(latm), R*math.radians(float(lat))) for lat,lon in villes]
    dist=[[0.0 if i==j else math.hypot(plane[i][0]-plane[j][0],plane[i][1]-plane[j][1])*1.23 for j in range(n)] for i in range(n)]
    pher=[[1.0]*n for _ in range(n)]
    best_route=[]; best_distance=float('inf')

    # Adaptation au nombre de points: assez de recherche pour les petits cas,
    # Le moteur utilise un mode précis pour les tailles raisonnables et un mode
    # spatial scalable pour les très gros volumes, sans plafond fixe de points.
    if n <= 30: iterations, ants, patience, local_passes = 35, 18, 8, 3
    elif n <= 100: iterations, ants, patience, local_passes = 24, 15, 6, 2
    elif n <= 300: iterations, ants, patience, local_passes = 14, 10, 4, 1
    elif n <= 600: iterations, ants, patience, local_passes = 9, 8, 3, 1
    else: iterations, ants, patience, local_passes = 7, 6, 2, 1

    stagnant=0
    for _ in range(iterations):
        iteration_best=None; iteration_distance=float('inf'); all_routes=[]
        for _ in range(ants):
            route,d=simuler_fourmi_vrp(n,dist,pher)
            all_routes.append((route,d))
            if d < iteration_distance:
                iteration_best,iteration_distance=route,d

        # Recherche locale uniquement sur la meilleure fourmi de l'itération.
        if iteration_best:
            improved, improved_d=ameliorer_2opt(iteration_best,dist,local_passes)
            if improved_d < iteration_distance:
                iteration_best,iteration_distance=improved,improved_d

        if iteration_distance < best_distance - 1e-9:
            best_route=list(iteration_best); best_distance=iteration_distance; stagnant=0
        else:
            stagnant+=1

        # Évaporation
        evap=1.0-EVAPORATION
        for i in range(n):
            row=pher[i]
            for j in range(n): row[j]*=evap

        # Dépôt limité aux meilleures solutions de l'itération pour réduire le bruit.
        all_routes.sort(key=lambda x:x[1])
        elite=all_routes[:max(2,min(4,len(all_routes)))]
        if iteration_best:
            elite.append((iteration_best,iteration_distance))
        for route,d in elite:
            deposit=Q/max(d,0.01)
            for k in range(len(route)-1):
                pher[route[k]][route[k+1]] += deposit

        # Arrêt anticipé: si aucune amélioration récente, inutile de consommer
        # du temps de calcul supplémentaire.
        if stagnant >= patience:
            break

    # Une dernière amélioration très limitée protège la qualité finale.
    if best_route:
        best_route,best_distance=ameliorer_2opt(best_route,dist,1)
    return best_route,best_distance


class RequeteCalcul(BaseModel): villes:List[Tuple[float,float]]

@app.post('/api/route')
async def api_route(requete:RequeteCalcul,infos=Security(verifier_acces_swiftroute)):
    if len(requete.villes)<2: raise HTTPException(400,'Il faut au moins 2 points.')
    for lat,lon in requete.villes:
        if not(-90<=float(lat)<=90 and -180<=float(lon)<=180): raise HTTPException(400,'Coordonnées GPS invalides.')
    if len(requete.villes)==2:
        route=[0,1]; distance=calculer_route_precision(requete.villes)[1]
    else:
        dest=len(requete.villes)-1
        inter=[requete.villes[0]]+requete.villes[1:dest]
        ordre,_=calculer_route_precision(inter)
        ordre=[i for i in ordre if i!=0]
        route=[0]+ordre+[dest]
        distance=0.0
        for a,b in zip(route,route[1:]):
            va,vb=requete.villes[a],requete.villes[b]
            distance+=math.hypot((float(va[0])-float(vb[0]))*111.0,(float(va[1])-float(vb[1]))*111.0*math.cos(math.radians((float(va[0])+float(vb[0]))/2)))
    return {'success':True,'client':infos.get('client'),'type_offre':infos.get('type_offre'),'route':route,'distance_km':round(distance,3),'points':len(requete.villes)}

# ========================= POINT QUALITY / CLASSIFICATION =========================
def _haversine_km(lat1, lon1, lat2, lon2):
    R=6371.0088
    p1=math.radians(float(lat1)); p2=math.radians(float(lat2))
    dp=math.radians(float(lat2)-float(lat1)); dl=math.radians(float(lon2)-float(lon1))
    a=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*R*math.asin(min(1.0,math.sqrt(a)))

def _classify_one_point(point):
    """Validation de routabilité par distance au réseau routier OSRM.
    Le résultat n'affirme pas qu'un point est physiquement dans l'eau.
    """
    lat,lon=float(point.lat),float(point.lon)
    url=f"{ROUTING_URL.rstrip('/')}/nearest/v1/driving/{lon},{lat}?number=1"
    req=URLRequest(url,headers={'User-Agent':GEOCODING_USER_AGENT})
    try:
        with urlopen(req,timeout=12) as response:
            data=json.loads(response.read().decode('utf-8'))
        if data.get('code')!='Ok' or not data.get('waypoints'):
            return {'name':point.name,'lat':lat,'lon':lon,'status':'unknown','label':'Non vérifiable','confidence':50,'road_distance_m':None}
        wp=data['waypoints'][0]; coords=wp.get('location') or []
        if len(coords)<2: raise ValueError('Réponse routière incomplète')
        d=_haversine_km(lat,lon,float(coords[1]),float(coords[0]))*1000
        if d<=75:
            status,label='valid','Valide — sur route'; confidence=round(99-(d/75)*9)
        elif d<=250:
            status,label='review','À vérifier — proche d’une route'; confidence=round(89-((d-75)/175)*24)
        else:
            status,label='invalid','Non routable probable — point éloigné d’une route'; confidence=round(min(97,76+(d-250)/1000*20))
        return {'name':point.name,'lat':lat,'lon':lon,'status':status,'label':label,'confidence':max(1,min(99,confidence)),'road_distance_m':round(d,1)}
    except Exception as exc:
        return {'name':point.name,'lat':lat,'lon':lon,'status':'unknown','label':'Non vérifiable','confidence':50,'road_distance_m':None,'error':str(exc)}

class RequeteClassification(BaseModel):
    points:List[PointGPS]

@app.post('/api/classify-points')
async def api_classify_points(requete:RequeteClassification,infos=Security(verifier_acces_swiftroute)):
    if len(requete.points)<1: raise HTTPException(400,'Il faut au moins 1 point.')
    for p in requete.points:
        if not(-90<=p.lat<=90 and -180<=p.lon<=180): raise HTTPException(400,f'Coordonnée invalide pour {p.name}.')
    results=[None]*len(requete.points)
    workers=min(12,max(2,len(requete.points)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures={pool.submit(_classify_one_point,p):i for i,p in enumerate(requete.points)}
        for future in as_completed(futures): results[futures[future]]=future.result()
    counts={'valid':0,'review':0,'invalid':0,'unknown':0}
    for item in results: counts[item['status']]=counts.get(item['status'],0)+1
    verified=[x for x in results if x['status']!='unknown']
    quality=round(sum(x['confidence'] for x in verified)/len(verified),1) if verified else 0
    return {'success':True,'client':infos.get('client'),'points':len(results),'summary':counts,'quality_score':quality,'results':results}

# ========================= ROAD ROUTING =========================
class RequeteRoadRoute(BaseModel): points:List[PointGPS]

def _fetch_osrm_chunk(points):
    coords=';'.join(f'{p.lon},{p.lat}' for p in points); url=f"{ROUTING_URL.rstrip('/')}/route/v1/driving/{coords}?overview=full&geometries=geojson&steps=false"; req=URLRequest(url,headers={'User-Agent':GEOCODING_USER_AGENT})
    try:
        with urlopen(req,timeout=30) as response:return json.loads(response.read().decode('utf-8'))
    except Exception as exc:raise HTTPException(502,f'Service de routage indisponible : {exc}')

def _combine_geojson_lines(routes):
    coordinates=[]
    for route in routes:
        seg=route['geometry']['coordinates']
        if not coordinates:coordinates.extend(seg)
        elif coordinates[-1]==seg[0]:coordinates.extend(seg[1:])
        else:coordinates.extend(seg)
    return {'type':'Feature','properties':{},'geometry':{'type':'LineString','coordinates':coordinates}}

class RequeteNextDistance(BaseModel):
    current: PointGPS
    target: PointGPS

@app.post('/api/next-distance')
async def api_next_distance(requete: RequeteNextDistance, infos=Security(verifier_acces_swiftroute)):
    for p in (requete.current, requete.target):
        if not(-90 <= p.lat <= 90 and -180 <= p.lon <= 180):
            raise HTTPException(400, 'Coordonnée GPS invalide.')
    data = _fetch_osrm_chunk([requete.current, requete.target])
    if data.get('code') != 'Ok' or not data.get('routes'):
        raise HTTPException(502, 'Aucune route routable trouvée vers la prochaine étape.')
    route = data['routes'][0]
    return {'success': True, 'distance_km': round(float(route.get('distance', 0))/1000, 2),
            'duration_min': round(float(route.get('duration', 0))/60), 'client': infos.get('client')}

@app.post('/api/road-route')
async def api_road_route(requete:RequeteRoadRoute,infos=Security(verifier_acces_swiftroute)):
    if len(requete.points)<2:raise HTTPException(400,'Il faut au moins 2 points.')
    for p in requete.points:
        if not(-90<=p.lat<=90 and -180<=p.lon<=180):raise HTTPException(400,f'Coordonnée invalide pour {p.name}.')
    # Le routeur public est sollicité par blocs pour éviter des URL trop longues.
    chunk_size=60; chunks=[]; start=0
    while start<len(requete.points)-1:
        end=min(start+chunk_size,len(requete.points)-1); chunks.append(_fetch_osrm_chunk(requete.points[start:end+1])); start=end
    total_distance=0.0; total_duration=0.0; valid=[]
    for data in chunks:
        if data.get('code')!='Ok' or not data.get('routes'):raise HTTPException(502,'Le service routier n’a pas trouvé de route.')
        r=data['routes'][0];total_distance+=float(r.get('distance',0));total_duration+=float(r.get('duration',0));valid.append(r)
    return {'success':True,'points':len(requete.points),'distance_km':round(total_distance/1000,2),'duration_min':round(total_duration/60),'geometry':_combine_geojson_lines(valid),'client':infos.get('client')}

# ========================= ADMIN =========================
def obtenir_panneau_admin(cle_generee=''):
    result=f'''<div style="background:#27272a;padding:15px;margin-top:20px;border:1px dashed #a855f7;border-radius:8px;word-break:break-all;font-family:monospace"><strong>Clé générée :</strong><br><br>{cle_generee}</div>''' if cle_generee else ''
    return f'''<html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>SwiftRoute Admin</title></head><body style="background:#09090b;color:#fff;font-family:Arial;padding:25px"><div style="max-width:520px;margin:auto;background:#18181b;padding:25px;border-radius:12px"><h2>🎛️ Administration SwiftRoute</h2><p>Produit Tiun : {TIUN_PRODUCT_ID}</p><form action="/admin-panel/generer" method="post"><input name="username" placeholder="Identifiant" required style="width:100%;padding:12px;box-sizing:border-box"><br><br><input type="password" name="password" placeholder="Mot de passe" required style="width:100%;padding:12px;box-sizing:border-box"><br><br><input name="client_name" placeholder="Entreprise" required style="width:100%;padding:12px;box-sizing:border-box"><br><br><input type="email" name="email" placeholder="Email" required style="width:100%;padding:12px;box-sizing:border-box"><br><br><select name="duration" style="width:100%;padding:12px"><option value="7">Accès 7 jours</option><option value="30">Entreprise 30 jours</option><option value="365">Corporate 1 an</option></select><br><br><button style="width:100%;padding:13px;background:#a855f7;color:#fff;border:0;border-radius:7px">Générer et activer</button></form>{result}</div></body></html>'''

@app.get('/admin-panel',response_class=HTMLResponse)
async def vue_panneau_admin_serveur(cle_generee:str=''):return HTMLResponse(obtenir_panneau_admin(cle_generee))

@app.post('/admin-panel/generer')
async def action_generer_cle_serveur(request:Request,username:str=Form(...),password:str=Form(...),client_name:str=Form(...),email:str=Form(...),duration:int=Form(...)):
    if username!=NOM_UTILISATEUR_ADMIN or password!=MOT_DE_PASSE_ADMIN:return HTMLResponse('<h2>Identifiants incorrects.</h2>',403)
    if duration not in (7,30,365):raise HTTPException(400,'Durée invalide.')
    email=normalize_email(email);token,jti,expiration=create_client_token(client_name,email,duration)
    # Correction: un seul argument pour obtenir_panneau_admin.
    return HTMLResponse(obtenir_panneau_admin(token))

@app.get('/health')
async def health():return {'status':'ok','service':'SwiftRoute Engine','version':'3.2','max_points':None,'capacity':'server_cpu_ram'}

if __name__=='__main__':
    import uvicorn
    uvicorn.run('main:app',host='0.0.0.0',port=int(os.getenv('PORT','8000')),reload=False)
