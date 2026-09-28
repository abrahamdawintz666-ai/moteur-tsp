# SwiftRoute Engine — Enterprise Commercial Edition v3
# Modifications:
# - Espace Client: connexion avec une clé API existante
# - Session HttpOnly après connexion
# - Dashboard SaaS moderne
# - Jusqu'à 1000 points
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
TIUN_SECRET_KEY = os.getenv("TIUN_SECRET_KEY", "")
GEOCODING_URL = os.getenv("GEOCODING_URL", "https://nominatim.openstreetmap.org/search")
GEOCODING_USER_AGENT = os.getenv("GEOCODING_USER_AGENT", "SwiftRoute/1.0 contact=admin@swiftroute.example")
ROUTING_URL = os.getenv("ROUTING_URL", "https://router.project-osrm.org")
TILE_URL = os.getenv("TILE_URL", "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png")
DATABASE_PATH = os.getenv("SWIFTROUTE_DB", "swiftroute.db")
DUREE_ESSAI_JOURS = 7
MAX_POINTS_REQUETE = 1000
MAX_CSV_POINTS = 1000

app = FastAPI(title="SwiftRoute Engine - AntStrike Advanced VRP", swagger_ui_parameters={"operationsSorter": "alpha"})

# ========================= DATABASE =========================
def db_connect():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    conn = db_connect()
    conn.execute("""CREATE TABLE IF NOT EXISTS trials (
        id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT NOT NULL UNIQUE,
        email_hash TEXT NOT NULL, client_name TEXT NOT NULL, ip_hash TEXT NOT NULL,
        token_jti TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL, expires_at TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 1, usage_count INTEGER NOT NULL DEFAULT 0)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS cities (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
        lat REAL NOT NULL, lon REAL NOT NULL)""")
    cities = [
        ("Cap-Haïtien",19.7595,-72.1983),("Port-au-Prince",18.5944,-72.3074),
        ("Gonaïves",19.4476,-72.6893),("Saint-Marc",19.1082,-72.6938),
        ("Port-de-Paix",19.9539,-72.8327),("Jacmel",18.2344,-72.5355),
        ("Les Cayes",18.1942,-73.7510),("Hinche",19.1431,-72.0088),
        ("Mirebalais",18.8346,-72.1045),("Fort-Liberté",19.6627,-71.8370),
        ("Ouanaminthe",19.5496,-71.7240),("Limbé",19.7058,-72.4037),
        ("Trou-du-Nord",19.6187,-72.0215),("Limonade",19.6707,-72.1253),
        ("Carrefour",18.5411,-72.3992),("Pétion-Ville",18.5120,-72.2852),
        ("Delmas",18.5470,-72.3020),("Croix-des-Bouquets",18.5760,-72.2260),
        ("Kenscoff",18.4477,-72.2840),("Léogâne",18.5108,-72.6334),
        ("Petit-Goâve",18.4317,-72.8667),("Grand-Goâve",18.4286,-72.7720),
        ("Miragoâne",18.4450,-73.0890),("Anse-à-Veau",18.4900,-73.0450),
        ("Jérémie",18.6500,-74.1167),("Port-Salut",18.0670,-73.9250),
        ("Cavaillon",18.3000,-73.6500),("Aquin",18.2790,-73.3940),
        ("Maïssade",19.1760,-72.1470),("Saint-Raphaël",19.4380,-72.1980)]
    conn.executemany("INSERT OR IGNORE INTO cities (name,lat,lon) VALUES (?,?,?)", cities)
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


def normalize_email(email: str) -> str:
    return email.strip().lower()


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded: return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def create_client_token(client_name, email, duration_days, trial=False):
    now = datetime.datetime.now(datetime.timezone.utc)
    expiration = now + datetime.timedelta(days=duration_days)
    jti = secrets.token_urlsafe(32)
    payload = {"client":client_name,"email":email,"exp":int(expiration.timestamp()),"iat":int(now.timestamp()),
               "jti":jti,"trial":trial,"type_offre":"Essai Gratuit 7 Jours" if trial else f"Accès {duration_days} Jours"}
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
    infos=verify_token(token); jti=infos.get("jti")
    if infos.get("trial") and jti:
        conn=db_connect(); row=conn.execute("SELECT * FROM trials WHERE token_jti=? AND active=1",(jti,)).fetchone(); conn.close()
        if not row: raise HTTPException(403,"Accès d'essai révoqué.")
        expiration=datetime.datetime.fromisoformat(row["expires_at"])
        if expiration <= datetime.datetime.now(datetime.timezone.utc): raise HTTPException(402,"Votre essai a expiré.")
    return infos


def mark_trial_usage(jti):
    conn=db_connect(); conn.execute("UPDATE trials SET usage_count=usage_count+1 WHERE token_jti=?",(jti,)); conn.commit(); conn.close()


async def verifier_minuteur_cle_api(request: Request, api_key: str = Security(api_key_header), swiftroute_session: str = Cookie(default=None)):
    # 1) API directe pour les développeurs
    if api_key:
        infos=validate_api_token(api_key)
        if infos.get("trial") and infos.get("jti"): mark_trial_usage(infos["jti"])
        return infos
    # 2) Session HttpOnly pour l'interface web
    session=get_session(swiftroute_session)
    if session:
        jti=session["token_jti"]
        conn=db_connect(); trial=conn.execute("SELECT * FROM trials WHERE token_jti=? AND active=1",(jti,)).fetchone() if jti else None; conn.close()
        if trial:
            infos=validate_api_token(create_signed_token_from_jti(jti))
        else:
            # Session commerciale non-essai: les métadonnées sont suffisantes pour les routes web.
            infos={"client":session["client_name"],"email":session["email"],"jti":jti,"trial":False,"type_offre":"Accès Client"}
        if trial: mark_trial_usage(jti)
        return infos
    raise HTTPException(403,"Authentification requise. Connectez-vous avec votre clé API.")


def create_signed_token_from_jti(jti):
    # Retrouve et re-signe temporairement les métadonnées d'un essai pour réutiliser
    # la validation JWT. Le token original n'est pas stocké en clair en base.
    conn=db_connect(); row=conn.execute("SELECT client_name,email,expires_at FROM trials WHERE token_jti=?",(jti,)).fetchone(); conn.close()
    if not row: raise HTTPException(403,"Session d'essai invalide.")
    exp=datetime.datetime.fromisoformat(row["expires_at"])
    payload={"client":row["client_name"],"email":row["email"],"exp":int(exp.timestamp()),"iat":int(time.time()),"jti":jti,"trial":True,"type_offre":"Essai Gratuit 7 Jours"}
    return jwt.encode(payload,PHRASE_SECRETE_NORD,algorithm="HS256")

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
    if len(requete.points)>25: raise HTTPException(400,"Maximum 25 recherches d'adresse par opération. Pour 1000 points, utilisez GPS ou CSV.")
    return {"results":[{**geocode_global(p.name),"input":p.name} for p in requete.points]}

# ========================= HOME =========================
def obtenir_page_accueil():
    return '''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SwiftRoute Engine</title>
<script type="module">import { tiun } from 'https://esm.sh/@tiun/sdk'; tiun.init({snippetId:'__TIUN_SNIPPET_ID__',language:'fr'});</script>
<style>body{margin:0;background:#09090b;color:#f4f4f5;font-family:Inter,Arial,sans-serif}a{color:inherit;text-decoration:none}.nav{max-width:1180px;margin:auto;padding:22px;display:flex;justify-content:space-between;align-items:center}.brand{font-weight:900;font-size:21px}.nav a{margin-left:18px;color:#a1a1aa}.hero{max-width:1050px;margin:auto;text-align:center;padding:100px 22px 80px}.eyebrow{color:#f59e0b;font-weight:800;letter-spacing:2px}h1{font-size:clamp(44px,8vw,82px);margin:18px 0;letter-spacing:-3px}.hero p{color:#a1a1aa;max-width:760px;margin:0 auto 32px;line-height:1.7;font-size:18px}.btn{display:inline-block;padding:14px 20px;border-radius:12px;margin:5px;font-weight:800}.primary{background:#f59e0b;color:#09090b}.ghost{border:1px solid #27272a}.grid{max-width:1050px;margin:auto;padding:20px;display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.card{background:#111113;border:1px solid #27272a;border-radius:18px;padding:25px}.card p{color:#a1a1aa;line-height:1.6}@media(max-width:800px){.grid{grid-template-columns:1fr}.nav{flex-wrap:wrap}}</style></head><body>
<div class="nav"><div class="brand">🐜 SWIFTROUTE</div><div><a href="/docs">API Docs</a><a href="/workspace">Espace Client</a><a href="/essai-gratuit">Essai</a></div></div>
<section class="hero"><div class="eyebrow">ANTSTRIKE COMMERCIAL · ROUTE OPTIMIZATION</div><h1>SWIFTROUTE ENGINE</h1><p>Une infrastructure d'optimisation de tournées conçue pour traiter jusqu'à 1 000 points et présenter le résultat sur une carte interactive.</p><a class="btn primary" href="/workspace">Ouvrir l'espace client</a><a class="btn ghost" href="/essai-gratuit">Démarrer l'essai 7 jours</a></section>
<div class="grid"><div class="card"><h3>⚡ Optimisation</h3><p>Ordonnancement des points avec le moteur SwiftRoute.</p></div><div class="card"><h3>🌍 Carte</h3><p>Visualisation interactive et tracé routier lorsque le fournisseur est disponible.</p></div><div class="card"><h3>🔑 API</h3><p>Accès développeur avec clé API ou session client sécurisée.</p></div></div></body></html>'''.replace('__TILE_URL__', TILE_URL).replace('__TIUN_SNIPPET_ID__', TIUN_SNIPPET_ID)

@app.get("/",response_class=HTMLResponse)
async def page_accueil_serveur(): return HTMLResponse(obtenir_page_accueil())

# ========================= TRIAL =========================
@app.get("/essai-gratuit",response_class=HTMLResponse)
async def page_essai_gratuit():
    return HTMLResponse('''<!doctype html><html lang="fr"><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Essai SwiftRoute</title><style>body{background:#09090b;color:#fff;font-family:Arial;padding:20px}.box{max-width:500px;margin:50px auto;background:#111113;border:1px solid #27272a;border-radius:18px;padding:28px}h1{color:#f59e0b}label{display:block;margin-top:16px}input{width:100%;padding:13px;margin-top:7px;box-sizing:border-box;background:#09090b;border:1px solid #3f3f46;color:#fff;border-radius:9px}button{width:100%;padding:14px;margin-top:20px;border:0;border-radius:9px;background:#f59e0b;font-weight:800}</style></head><body><div class="box"><h1>🐜 SwiftRoute</h1><h2>Essai gratuit — 7 jours</h2><p>Créez votre accès d'essai.</p><form method="post" action="/essai-gratuit"><label>Entreprise<input name="client_name" maxlength="120" required></label><label>E-mail<input type="email" name="email" maxlength="254" required></label><button>🚀 Commencer</button></form></div></body></html>''')

@app.post("/essai-gratuit")
async def creer_essai_gratuit(request:Request,client_name:str=Form(...),email:str=Form(...)):
    client_name=client_name.strip(); email=normalize_email(email)
    if not client_name or len(client_name)>120: raise HTTPException(400,"Nom d'entreprise invalide.")
    if "@" not in email or len(email)>254: raise HTTPException(400,"Adresse e-mail invalide.")
    ip_hash=hash_value(get_client_ip(request)); email_hash=hash_value(email); conn=db_connect()
    if conn.execute("SELECT id FROM trials WHERE email_hash=?",(email_hash,)).fetchone(): conn.close(); return HTMLResponse("<h2>Cet e-mail a déjà utilisé un essai.</h2><a href='/workspace'>Espace Client</a>",409)
    if conn.execute("SELECT id FROM trials WHERE ip_hash=?",(ip_hash,)).fetchone(): conn.close(); return HTMLResponse("<h2>Un essai a déjà été créé depuis ce réseau.</h2>",429)
    token,jti,expiration=create_client_token(client_name,email,DUREE_ESSAI_JOURS,True); now=datetime.datetime.now(datetime.timezone.utc)
    try:
        conn.execute("INSERT INTO trials(email,email_hash,client_name,ip_hash,token_jti,created_at,expires_at,active,usage_count) VALUES(?,?,?,?,?,?,?,?,?)",(email,email_hash,client_name,ip_hash,jti,now.isoformat(),expiration.isoformat(),1,0)); conn.commit()
    except sqlite3.IntegrityError: conn.close(); return HTMLResponse("<h2>Un essai existe déjà.</h2>",409)
    conn.close(); session_id=create_session(client_name,email,jti,expiration); response=RedirectResponse("/workspace",303)
    response.set_cookie("swiftroute_session",session_id,httponly=True,secure=True,samesite="lax",max_age=DUREE_ESSAI_JOURS*86400)
    return response

# ========================= CLIENT LOGIN =========================
LOGIN_HTML='''<!doctype html><html lang="fr"><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Espace Client — SwiftRoute</title><style>body{margin:0;background:#09090b;color:#f4f4f5;font-family:Inter,Arial}.wrap{min-height:100vh;display:grid;place-items:center;padding:20px}.box{width:min(460px,100%);background:#111113;border:1px solid #27272a;border-radius:22px;padding:30px;box-shadow:0 20px 80px #0008}h1{margin:0 0 8px}.muted{color:#a1a1aa;line-height:1.6}label{display:block;margin:20px 0 7px;font-weight:700}input{width:100%;box-sizing:border-box;padding:14px;background:#09090b;border:1px solid #3f3f46;border-radius:10px;color:#fff;font-family:monospace}button{width:100%;padding:14px;margin-top:18px;border:0;border-radius:10px;background:#f59e0b;font-weight:900;cursor:pointer}.links{display:flex;justify-content:space-between;margin-top:20px}.links a{color:#f59e0b;text-decoration:none}</style></head><body><div class="wrap"><div class="box"><div style="font-size:22px;font-weight:900">🐜 SWIFTROUTE</div><h1>Espace Client</h1><p class="muted">Connectez-vous avec la clé API qui vous a été fournie. La clé n'est pas placée dans l'URL.</p><form method="post" action="/client-login"><label>Clé API</label><input name="api_key" type="password" placeholder="Votre clé API" required autocomplete="off"><button>🔐 Se connecter</button></form><div class="links"><a href="/essai-gratuit">Nouvel utilisateur</a><a href="/">Accueil</a></div></div></div></body></html>'''

@app.get("/workspace",response_class=HTMLResponse)
async def workspace(swiftroute_session:str=Cookie(default=None)):
    if not get_session(swiftroute_session): return HTMLResponse(LOGIN_HTML)
    return HTMLResponse(workspace_html())

@app.get("/client-login",response_class=HTMLResponse)
async def client_login_page(): return HTMLResponse(LOGIN_HTML)

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
<style>
*{box-sizing:border-box}:root{--bg:#08090b;--panel:#101216;--panel2:#151820;--line:#262a33;--muted:#8d95a3;--orange:#f59e0b;--orange2:#ffb52e;--green:#22c55e;--danger:#ef4444}body{margin:0;background:radial-gradient(circle at 70% -10%,#24200f 0,#08090b 34%);color:#f5f5f5;font-family:Inter,ui-sans-serif,Arial,sans-serif}button,input{font:inherit}button{cursor:pointer}.app{display:grid;grid-template-columns:240px 1fr;min-height:100vh}.side{position:sticky;top:0;height:100vh;border-right:1px solid var(--line);background:#0b0d10eF;backdrop-filter:blur(16px);padding:20px 14px;display:flex;flex-direction:column}.logo{font-size:20px;font-weight:950;padding:8px 10px 28px}.logo span{color:var(--orange)}.navbtn{width:100%;text-align:left;background:transparent;border:1px solid transparent;color:#aeb5c0;padding:12px 13px;border-radius:10px;margin:3px 0;font-weight:700}.navbtn:hover,.navbtn.active{background:#191b20;border-color:#2a2e37;color:#fff}.navbtn.active{box-shadow:inset 3px 0 0 var(--orange)}.bottom{margin-top:auto}.main{min-width:0}.top{height:72px;border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;padding:0 28px;background:#0b0d10b8;backdrop-filter:blur(14px);position:sticky;top:0;z-index:900}.status{color:#9ca3af;font-size:13px}.dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--green);margin-right:7px;box-shadow:0 0 12px var(--green)}.content{padding:28px;max-width:1500px;margin:auto}.hero{display:flex;justify-content:space-between;align-items:flex-end;gap:20px;margin-bottom:22px}h1{font-size:34px;margin:0 0 6px;letter-spacing:-1.5px}.muted{color:var(--muted)}.primary{background:linear-gradient(135deg,var(--orange2),var(--orange));border:0;color:#0a0a0a;font-weight:900;padding:13px 17px;border-radius:11px;box-shadow:0 8px 28px #f59e0b25}.ghost{background:#17191e;color:#fff;border:1px solid #30343e;padding:12px 15px;border-radius:10px;font-weight:800}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:18px}.stat{background:linear-gradient(145deg,#13161b,#0f1115);border:1px solid var(--line);border-radius:15px;padding:18px}.stat small{color:var(--muted);font-weight:700}.stat strong{display:block;font-size:28px;margin-top:8px;color:var(--orange)}.workspace{display:grid;grid-template-columns:410px minmax(0,1fr);gap:16px}.panel{background:var(--panel);border:1px solid var(--line);border-radius:17px;padding:18px;box-shadow:0 18px 50px #0002}.panel h2{font-size:17px;margin:0 0 15px}.tabs{display:flex;gap:7px;margin-bottom:14px}.tab{flex:1;background:#17191e;color:#aeb5c0;border:1px solid #292d36;padding:10px;border-radius:9px;font-weight:800}.tab.active{color:#fff;border-color:#8b5b08;background:#211a0c}.modepanel{display:none}.modepanel.active{display:block}label{display:block;color:#d6d8dd;font-size:12px;font-weight:800;margin:13px 0 6px}input,textarea{width:100%;background:#0a0c0f;color:#fff;border:1px solid #30343d;border-radius:9px;padding:12px;outline:none}input:focus{border-color:#9b6b0c;box-shadow:0 0 0 3px #f59e0b12}.searchrow{display:grid;grid-template-columns:1fr auto;gap:7px}.searchrow button{background:#20232a;border:1px solid #343944;color:#fff;border-radius:9px;padding:0 12px}.pointshead{display:flex;justify-content:space-between;align-items:center;margin-top:14px}.counter{font-family:monospace;color:var(--orange)}.progress{height:5px;background:#262a31;border-radius:9px;overflow:hidden;margin:9px 0 12px}.progress i{display:block;height:100%;width:0;background:var(--orange);transition:width .25s}.gpslist{max-height:360px;overflow:auto;padding-right:3px}.gpsrow{display:grid;grid-template-columns:30px 1fr 1fr 34px;gap:5px;margin-bottom:6px}.gpsrow input{padding:9px;font-size:12px}.num{display:grid;place-items:center;color:#777f8d;font-size:11px}.remove{background:#191b20;color:#ef4444;border:1px solid #30343d;border-radius:8px}.actions{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:10px}.big{grid-column:1/-1;padding:14px;border-radius:11px;font-size:15px}.mapwrap{padding:0;overflow:hidden;min-height:650px;position:relative}#map{height:100%;min-height:650px;background:#111}.maptools{position:absolute;top:14px;left:14px;z-index:700;display:flex;gap:7px;flex-wrap:wrap}.maptools button{background:#0c0e12eF;border:1px solid #30343d;color:#fff;padding:9px 11px;border-radius:9px;font-weight:800;backdrop-filter:blur(10px)}.result{margin-top:14px;border:1px solid #6a4708;background:#17130a;border-radius:12px;padding:13px;display:none}.quality{margin-top:12px;padding:13px;border:1px solid #292d36;background:#0d0f13;border-radius:12px}.quality-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:10px}.quality-card{padding:10px;border:1px solid #292d36;border-radius:10px;background:#101216}.quality-card b{display:block;font-size:20px;margin-top:4px}.quality-list{max-height:240px;overflow:auto;margin-top:10px}.q-valid{color:#22c55e}.q-review{color:#f59e0b}.q-invalid{color:#ef4444}.q-unknown{color:#a1a1aa}@media(max-width:650px){.quality-grid{grid-template-columns:1fr 1fr}}.section-panel{margin-top:16px;scroll-margin-top:90px}.info-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.info-card{background:#0d0f13;border:1px solid #292d36;border-radius:13px;padding:15px}.info-card strong{display:block;font-size:22px;color:var(--orange);margin-top:5px}.quick-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px}.quick-actions button{flex:1;min-width:140px}.support-link{display:inline-flex;align-items:center;gap:8px;text-decoration:none;background:#17191e;color:#fff;border:1px solid #30343e;padding:11px 14px;border-radius:10px;font-weight:800}.navbtn .navtext{margin-left:8px}.route-list{max-height:230px;overflow:auto;line-height:1.75;color:#d2d6dd;font-size:13px}.toast{position:fixed;right:20px;bottom:20px;background:#17191e;border:1px solid #343944;padding:13px 15px;border-radius:11px;z-index:2000;display:none;box-shadow:0 20px 60px #0008}.loading{display:none;position:absolute;inset:0;background:#090b0ee8;z-index:800;align-items:center;justify-content:center;flex-direction:column;gap:14px}.spinner{width:40px;height:40px;border:3px solid #343944;border-top-color:var(--orange);border-radius:50%;animation:spin .8s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}@media(max-width:1100px){.app{grid-template-columns:76px 1fr}.logo{font-size:0;text-align:center}.logo:first-letter{font-size:22px}.navbtn{font-size:0;text-align:center}.navbtn:first-letter{font-size:20px}.navbtn .navtext{display:none}.workspace{grid-template-columns:1fr}#map,.mapwrap{min-height:520px}.cards{grid-template-columns:repeat(2,1fr)}.info-grid{grid-template-columns:1fr 1fr}}@media(max-width:650px){.content{padding:15px}.top{padding:0 15px}.hero{align-items:flex-start;flex-direction:column}h1{font-size:28px}.cards{grid-template-columns:1fr 1fr;gap:8px}.stat{padding:12px}.stat strong{font-size:22px}.workspace{display:flex;flex-direction:column}.mapwrap{order:-1}#map{min-height:420px}.gpslist{max-height:280px}.info-grid{grid-template-columns:1fr}.side{padding:15px 10px}.navbtn{padding:12px 8px}}
</style></head><body>
<div class="app"><aside class="side"><div class="logo">🐜 <span>SWIFTROUTE</span></div><button class="navbtn active" data-nav="dashboard" title="Dashboard" onclick="goSection('dashboard',this)">🏠 <span class="navtext">Dashboard</span></button><button class="navbtn" data-nav="optimizer" title="Optimizer" onclick="goSection('optimizer',this)">⚡ <span class="navtext">Optimizer</span></button><button class="navbtn" data-nav="map" title="Map" onclick="goSection('mapPanel',this)">🗺️ <span class="navtext">Map</span></button><button class="navbtn" data-nav="api" title="API" onclick="goSection('apiPanel',this)">🔑 <span class="navtext">API</span></button><button class="navbtn" data-nav="usage" title="Usage" onclick="goSection('usagePanel',this)">📊 <span class="navtext">Usage</span></button><button class="navbtn" data-nav="billing" title="Billing" onclick="goSection('billingPanel',this)">💳 <span class="navtext">Billing</span></button><button class="navbtn" data-nav="support" title="Support" onclick="goSection('supportPanel',this)">💬 <span class="navtext">Support</span></button><div class="bottom"><form action="/logout" method="post"><button class="navbtn" title="Déconnexion">↪️ <span class="navtext">Déconnexion</span></button></form></div></aside>
<main class="main"><header class="top"><strong>Route Intelligence</strong><div class="status"><span class="dot"></span>Session active</div></header><div class="content">
<section class="hero" id="dashboard"><div><div class="muted" style="font-size:13px;font-weight:800">ANTSTRIKE COMMERCIAL / SWIFTROUTE ENGINE</div><h1>Route Optimization Workspace</h1><div class="muted">Prépare, optimise et visualise jusqu'à 1 000 points.</div></div><button class="primary" onclick="newOptimization()">＋ Nouvelle optimisation</button></section>
<section class="cards"><div class="stat"><small>POINTS</small><strong id="sPoints">0</strong></div><div class="stat"><small>DISTANCE ROUTIÈRE</small><strong id="sRoad">—</strong></div><div class="stat"><small>DURÉE</small><strong id="sTime">—</strong></div><div class="stat"><small>LIMIT</small><strong>1000</strong></div></section>
<section class="workspace" id="optimizer"><div class="panel"><h2>⚡ Route Builder</h2><div class="tabs"><button class="tab active" onclick="switchMode('gps',this)">GPS</button><button class="tab" onclick="switchMode('csv',this)">CSV</button><button class="tab" onclick="switchMode('search',this)">Recherche</button></div>
<div id="mode-gps" class="modepanel active"><div class="pointshead"><b>Points</b><span class="counter"><span id="count">0</span> / 1000</span></div><div class="progress"><i id="bar"></i></div><div id="gpslist" class="gpslist"></div><div class="actions"><button class="ghost" onclick="addPoint()">＋ Ajouter</button><button class="ghost" onclick="prepare1000()">＋ Préparer 1000</button><button class="primary big" onclick="optimize()">⚡ OPTIMIZE ROUTE</button><button class="ghost" onclick="clearAll()">Effacer</button></div><div class="quality"><div style="display:flex;justify-content:space-between;gap:8px;align-items:center"><div><b>🧭 Validation des points</b><div class="muted" style="font-size:12px;margin-top:4px">Vérifie la proximité de chaque point avec le réseau routier.</div></div><button class="ghost" onclick="classifyPoints()">🔎 Analyser</button></div><div id="qualityBox" style="display:none"></div></div></div>
<div id="mode-csv" class="modepanel"><p class="muted">CSV accepté : <b>name,lat,lon</b> ou <b>lat,lon</b>.</p><input id="csv" type="file" accept=".csv,text/csv"><button class="primary big" onclick="importCSV()">Importer les points</button></div>
<div id="mode-search" class="modepanel"><label>Départ</label><div class="searchrow"><input id="departQ" placeholder="Cap-Haïtien, Haiti"><button onclick="searchPlace('depart')">Chercher</button></div><label>Arrêt</label><div class="searchrow"><input id="stopQ" placeholder="Paris, France"><button onclick="searchPlace('stop')">Ajouter</button></div><label>Destination</label><div class="searchrow"><input id="destQ" placeholder="Port-au-Prince, Haiti"><button onclick="searchPlace('dest')">Chercher</button></div><div id="searchStatus" class="muted" style="margin-top:12px"></div></div>
<div id="result" class="result"></div></div>
<div class="panel mapwrap" id="mapPanel"><div class="maptools"><button onclick="fitAll()">⌖ Recentrer</button><button id="markerToggle" onclick="toggleMarkers()">● Points ON</button><button onclick="focusMap()">Carte</button></div><div class="loading" id="loading"><div class="spinner"></div><b id="loadingText">Optimisation...</b><span class="muted">SwiftRoute Engine</span></div><div id="map"></div></div></section>
<section class="panel section-panel" id="apiPanel"><h2>🔑 Developer Access</h2><p class="muted">Utilisez votre clé avec <code>X-API-KEY</code> pour les appels directs. L'interface web utilise une session HttpOnly.</p><div style="background:#090b0e;border:1px solid #2d3139;border-radius:10px;padding:12px;font-family:monospace;overflow:auto">POST /api/route<br>X-API-KEY: YOUR_API_KEY<br>Content-Type: application/json</div><div class="quick-actions"><button class="ghost" onclick="copyApiExample()">📋 Copier l'exemple API</button><button class="ghost" onclick="toast('La clé API reste protégée dans votre espace client.')">🔒 Sécurité</button></div></section>
<section class="panel section-panel" id="usagePanel"><h2>📊 Usage</h2><p class="muted">Suivi de cette session et de la dernière optimisation effectuée.</p><div class="info-grid"><div class="info-card"><small class="muted">Points chargés</small><strong id="usagePoints">0</strong></div><div class="info-card"><small class="muted">Optimisations</small><strong id="usageRuns">0</strong></div><div class="info-card"><small class="muted">Dernier résultat</small><strong id="usageDistance">—</strong></div></div><div class="quick-actions"><button class="ghost" onclick="goSection('optimizer')">⚡ Nouvelle optimisation</button><button class="ghost" onclick="resetUsageView()">↻ Réinitialiser l'affichage</button></div></section>
<section class="panel section-panel" id="billingPanel"><h2>💳 Billing</h2><p class="muted">Gestion de votre accès SwiftRoute.</p><div class="info-grid"><div class="info-card"><small class="muted">Statut</small><strong style="color:var(--green)">ACTIF</strong></div><div class="info-card"><small class="muted">Limite</small><strong>1 000</strong></div><div class="info-card"><small class="muted">Offre</small><strong style="font-size:16px">Client API</strong></div></div><div class="quick-actions"><button class="ghost" onclick="toast('Pour modifier votre offre, contactez le support.')">Modifier l'offre</button><a class="support-link" href="mailto:__EMAIL_CONTACT__?subject=SwiftRoute%20Billing">✉️ Contacter la facturation</a></div></section>
<section class="panel section-panel" id="supportPanel"><h2>💬 Support</h2><p class="muted">Besoin d'aide pour l'API, la carte ou l'optimisation ? Contactez directement SwiftRoute.</p><div class="quick-actions"><a class="support-link" href="mailto:__EMAIL_CONTACT__?subject=Support%20SwiftRoute">✉️ E-mail support</a><a class="support-link" target="_blank" rel="noopener" href="https://wa.me/__WHATSAPP_DIGITS__?text=Bonjour%20SwiftRoute%2C%20j%27ai%20besoin%20d%27aide.">💬 WhatsApp</a><button class="ghost" onclick="showHelp()">❓ Aide rapide</button></div><div id="helpBox" class="result" style="display:none">1. Ajoutez vos points GPS, CSV ou via Recherche.<br>2. Vérifiez les coordonnées.<br>3. Lancez <b>OPTIMIZE ROUTE</b>.<br>4. Utilisez la carte pour contrôler l'itinéraire.</div></section>
</div></main></div><div id="toast" class="toast"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script><script>
let map=L.map('map').setView([19.5,-72.3],8); let routeLayer=null,markers=[],gpsPoints=[],searchPoints={depart:null,destination:null,stops:[]}; let markerVisible=true; let optimizationRuns=0; let lastDistance='—';
L.tileLayer('__TILE_URL__',{maxZoom:19,subdomains:['a','b','c'],attribution:'&copy; OpenStreetMap contributors'}).on('tileerror',()=>{}).addTo(map);
function toast(t){let x=document.getElementById('toast');x.textContent=t;x.style.display='block';clearTimeout(window._toast);window._toast=setTimeout(()=>x.style.display='none',3000)}
function setActiveNav(key){document.querySelectorAll('.navbtn[data-nav]').forEach(b=>b.classList.toggle('active',b.dataset.nav===key))}
function goSection(id,btn){let el=document.getElementById(id);if(!el)return;if(id==='mapPanel')setTimeout(()=>map.invalidateSize(),350);el.scrollIntoView({behavior:'smooth',block:'start'});let key=btn?.dataset?.nav||({dashboard:'dashboard',optimizer:'optimizer',mapPanel:'map',apiPanel:'api',usagePanel:'usage',billingPanel:'billing',supportPanel:'support'}[id]||'dashboard');setActiveNav(key)}
function newOptimization(){clearAll();goSection('optimizer');toast('Nouvelle optimisation prête.')}
function copyApiExample(){const text=`POST /api/route\nX-API-KEY: YOUR_API_KEY\nContent-Type: application/json`; if(navigator.clipboard){navigator.clipboard.writeText(text).then(()=>toast('Exemple API copié.')).catch(()=>fallbackCopy(text))}else{fallbackCopy(text)}}
function fallbackCopy(text){const ta=document.createElement('textarea');ta.value=text;ta.style.position='fixed';ta.style.opacity='0';document.body.appendChild(ta);ta.focus();ta.select();try{document.execCommand('copy');toast('Exemple API copié.')}catch(e){toast('Copie non disponible sur ce navigateur.')}ta.remove()}
function resetUsageView(){optimizationRuns=0;lastDistance='—';document.getElementById('usageRuns').textContent='0';document.getElementById('usageDistance').textContent='—';toast('Affichage Usage réinitialisé.')}
function updateUsage(){document.getElementById('usagePoints').textContent=gpsPoints.length;document.getElementById('usageRuns').textContent=optimizationRuns;document.getElementById('usageDistance').textContent=lastDistance}
function showHelp(){let x=document.getElementById('helpBox');x.style.display=x.style.display==='none'?'block':'none'}

function switchMode(name,btn){document.querySelectorAll('.modepanel').forEach(x=>x.classList.remove('active'));document.getElementById('mode-'+name).classList.add('active');document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));btn.classList.add('active')}
function esc(v){return String(v??'').replace(/[&<>'\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','\"':'&quot;'}[c]))}
function renderGPS(){let box=document.getElementById('gpslist');box.innerHTML='';gpsPoints.forEach((p,i)=>{let r=document.createElement('div');r.className='gpsrow';r.innerHTML=`<div class="num">${i+1}</div><input value="${esc(p.lat)}" placeholder="lat" onchange="gpsPoints[${i}].lat=this.value"><input value="${esc(p.lon)}" placeholder="lon" onchange="gpsPoints[${i}].lon=this.value"><button class="remove" onclick="gpsPoints.splice(${i},1);renderGPS()">×</button>`;box.appendChild(r)});document.getElementById('count').textContent=gpsPoints.length;document.getElementById('bar').style.width=(Math.min(gpsPoints.length,1000)/10)+'%';document.getElementById('sPoints').textContent=gpsPoints.length;updateUsage()}
function addPoint(p={name:'',lat:'',lon:''}){if(gpsPoints.length>=1000) return toast('Limite de 1000 points atteinte.');gpsPoints.push(p);renderGPS()}
function prepare1000(){if(gpsPoints.length>=1000)return toast('Les 1000 points sont déjà prêts.');let start=gpsPoints.length;for(let i=start;i<1000;i++){let angle=(i*137.508)%360;let radius=0.01+((i%100)*0.0012);let lat=19.7595+Math.sin(angle*Math.PI/180)*radius;let lon=-72.1983+Math.cos(angle*Math.PI/180)*radius;gpsPoints.push({name:'Point '+(i+1),lat:lat.toFixed(6),lon:lon.toFixed(6)})}renderGPS();toast('1000 points de test prêts autour de Cap-Haïtien.')}
function clearAll(){gpsPoints=[];searchPoints={depart:null,destination:null,stops:[]};renderGPS();if(routeLayer){map.removeLayer(routeLayer);routeLayer=null};markers.forEach(m=>map.removeLayer(m));markers=[];document.getElementById('result').style.display='none';document.getElementById('qualityBox').style.display='none';document.getElementById('qualityBox').innerHTML='';document.getElementById('sRoad').textContent='—';document.getElementById('sTime').textContent='—';lastDistance='—';updateUsage()}
function valid(p){return Number.isFinite(Number(p.lat))&&Number.isFinite(Number(p.lon))&&Number(p.lat)>=-90&&Number(p.lat)<=90&&Number(p.lon)>=-180&&Number(p.lon)<=180}
function getPoints(){let points;if(document.getElementById('mode-search').classList.contains('active')){if(!searchPoints.depart||!searchPoints.destination)throw Error('Ajoutez un départ et une destination.');points=[searchPoints.depart,...searchPoints.stops,searchPoints.destination]}else points=gpsPoints.map((p,i)=>({name:p.name||'Point '+(i+1),lat:Number(p.lat),lon:Number(p.lon)}));if(points.length<2)throw Error('Il faut au moins 2 points.');if(points.length>1000)throw Error('Maximum 1000 points.');if(points.some(p=>!valid(p)))throw Error('Une coordonnée est invalide.');return points}
async function importCSV(){let f=document.getElementById('csv').files[0];if(!f)return toast('Choisissez un fichier CSV.');let text=await f.text();let lines=text.split(/\\r?\\n/).map(x=>x.trim()).filter(Boolean);if(lines.length>1001)throw toast('Maximum 1000 points.');let start=/lat.*lon/i.test(lines[0])?1:0;let arr=[];for(let i=start;i<lines.length;i++){let a=lines[i].split(',').map(x=>x.trim());if(a.length<2)continue;let hasName=a.length>=3&&!Number.isFinite(Number(a[0]));let name=hasName?a[0]:'Point '+(arr.length+1);let lat=Number(hasName?a[1]:a[0]),lon=Number(hasName?a[2]:a[1]);if(Number.isFinite(lat)&&Number.isFinite(lon))arr.push({name,lat,lon})}gpsPoints=arr;renderGPS();switchMode('gps',document.querySelector('.tab'));toast(arr.length+' points importés.')}
async function searchPlace(type){let id=type==='depart'?'departQ':type==='dest'?'destQ':'stopQ';let q=document.getElementById(id).value.trim();if(!q)return;try{let r=await fetch('/api/geocode?q='+encodeURIComponent(q));let d=await r.json();if(!r.ok)throw Error(d.detail||'Lieu introuvable');let p={name:d.display_name,lat:Number(d.lat),lon:Number(d.lon)};if(type==='depart')searchPoints.depart=p;else if(type==='dest')searchPoints.destination=p;else searchPoints.stops.push(p);document.getElementById('searchStatus').textContent='✓ '+p.name;toast('Lieu ajouté')}catch(e){toast(e.message)}}
function showLoading(t){document.getElementById('loadingText').textContent=t;document.getElementById('loading').style.display='flex'}function hideLoading(){document.getElementById('loading').style.display='none'}
function clearMarkers(){markers.forEach(m=>map.removeLayer(m));markers=[]}
function drawMarkers(points){clearMarkers();points.forEach((p,i)=>{let m=L.marker([p.lat,p.lon]).addTo(map);let extra=p.classification?'<br><b>'+esc(p.classification.label)+'</b><br>Confiance: '+p.classification.confidence+'%'+(p.classification.road_distance_m!=null?'<br>Distance route: '+p.classification.road_distance_m+' m':''):'';m.bindPopup('<b>'+(i+1)+'. '+esc(p.name)+'</b><br>'+Number(p.lat).toFixed(6)+', '+Number(p.lon).toFixed(6)+extra);markers.push(m)})}
function fitAll(){if(routeLayer)map.fitBounds(routeLayer.getBounds(),{padding:[30,30]});else if(markers.length){let g=L.featureGroup(markers);map.fitBounds(g.getBounds(),{padding:[30,30]})}}
function toggleMarkers(){markerVisible=!markerVisible;markers.forEach(m=>markerVisible?m.addTo(map):map.removeLayer(m));let b=document.getElementById('markerToggle');if(b)b.textContent=markerVisible?'● Points ON':'○ Points OFF';toast(markerVisible?'Points affichés':'Points masqués')}
function focusMap(){goSection('mapPanel');setTimeout(()=>map.invalidateSize(),300)}
function scrollToOpt(){goSection('optimizer')} function showApi(){goSection('apiPanel')}
function straightGeo(points){return {type:'Feature',properties:{fallback:true},geometry:{type:'LineString',coordinates:points.map(p=>[p.lon,p.lat])}}}
async function classifyPoints(){
  const box=document.getElementById('qualityBox');
  try{
    const points=getPoints();
    showLoading('Analyse de la qualité géographique...');
    const r=await fetch('/api/classify-points',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({points})});
    const data=await r.json();
    if(!r.ok) throw Error(data.detail||'Erreur de classification');
    const byKey=new Map(data.results.map(x=>[x.lat.toFixed(7)+'|'+x.lon.toFixed(7),x]));
    points.forEach(p=>p.classification=byKey.get(Number(p.lat).toFixed(7)+'|'+Number(p.lon).toFixed(7)));
    const c=data.summary;
    box.style.display='block';
    box.innerHTML='<div style="margin-top:12px"><b>Score de qualité géographique : '+data.quality_score+'%</b><div class="quality-grid"><div class="quality-card q-valid">Sur route<b>'+c.valid+'</b></div><div class="quality-card q-review">À vérifier<b>'+c.review+'</b></div><div class="quality-card q-invalid">Non routable probable<b>'+c.invalid+'</b></div><div class="quality-card q-unknown">Non vérifiable<b>'+c.unknown+'</b></div></div><div class="quality-list">'+data.results.map((x,i)=>'<div style="padding:7px 0;border-bottom:1px solid #20232a"><b>'+(i+1)+'. '+esc(x.name)+'</b> — <span class="q-'+x.status+'">'+esc(x.label)+'</span> · '+x.confidence+'%'+(x.road_distance_m!=null?' · '+x.road_distance_m+' m de la route':'')+'</div>').join('')+'</div></div>';
    drawMarkers(points);
    hideLoading();toast('Analyse terminée : '+data.points+' points.');
  }catch(e){hideLoading();toast(e.message)}
}

async function optimize(){let result=document.getElementById('result');try{let points=getPoints();showLoading("Calcul de l’ordre optimal...");let r=await fetch('/api/route',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({villes:points.map(p=>[p.lat,p.lon])})});let data=await r.json();if(!r.ok)throw Error(data.detail||'Erreur moteur');let ordered=data.route.filter((v,i,a)=>i===0||v!==0).map(i=>points[i]);if(ordered[ordered.length-1]!==points[points.length-1])ordered.push(points[points.length-1]);drawMarkers(ordered);fitAll();showLoading('Calcul du tracé routier...');let rr=await fetch('/api/road-route',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({points:ordered})});let road=await rr.json();if(!rr.ok){toast('Routeur indisponible : tracé SwiftRoute affiché.');road={geometry:straightGeo(ordered),distance_km:data.distance_km,duration_min:'—',fallback:true}}if(routeLayer)map.removeLayer(routeLayer);routeLayer=L.geoJSON(road.geometry,{style:{color:'#f59e0b',weight:5,opacity:.95}}).addTo(map);fitAll();document.getElementById('sRoad').textContent=road.distance_km+' km';document.getElementById('sTime').textContent=(road.duration_min==='—'?'—':road.duration_min+' min');optimizationRuns++;lastDistance=road.distance_km+' km';updateUsage();result.style.display='block';result.innerHTML='<b>✓ Itinéraire optimisé</b><div style="margin-top:7px;color:#a1a1aa">'+ordered.length+' points · '+(road.fallback?'tracé de secours':'tracé routier')+'</div><hr style="border-color:#292d36"><div class="route-list">'+ordered.map((p,i)=>(i+1)+'. '+esc(p.name)).join('<br>')+'</div>';hideLoading();toast('Optimisation terminée.')}catch(e){hideLoading();result.style.display='block';result.innerHTML='<span style="color:#ef4444">Erreur :</span> '+esc(e.message);toast(e.message)}}
addPoint({name:'Départ',lat:'',lon:''});addPoint({name:'Destination',lat:'',lon:''});window.addEventListener('resize',()=>map.invalidateSize());
</script></body></html>'''.replace('__TILE_URL__', TILE_URL).replace('__EMAIL_CONTACT__', EMAIL_CONTACT).replace('__WHATSAPP_DIGITS__', ''.join(c for c in WHATSAPP_CONTACT if c.isdigit()))

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


def calculer_route_precision(villes):
    n=len(villes)
    if n<3:
        return list(range(n)),0.0
    latm=math.radians(sum(float(v[0]) for v in villes)/n); R=6371.0
    plane=[(R*math.radians(float(lat))*0 + R*math.radians(float(lon))*math.cos(latm), R*math.radians(float(lat))) for lat,lon in villes]
    dist=[[0.0 if i==j else math.hypot(plane[i][0]-plane[j][0],plane[i][1]-plane[j][1])*1.23 for j in range(n)] for i in range(n)]
    pher=[[1.0]*n for _ in range(n)]
    best_route=[]; best_distance=float('inf')

    # Adaptation au nombre de points: assez de recherche pour les petits cas,
    # mais budget borné pour rester rapide à 1000 points.
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
async def api_route(requete:RequeteCalcul,infos=Security(verifier_minuteur_cle_api)):
    if len(requete.villes)>MAX_POINTS_REQUETE: raise HTTPException(400,'Maximum 1000 points par requête.')
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
async def api_classify_points(requete:RequeteClassification,infos=Security(verifier_minuteur_cle_api)):
    if len(requete.points)<1: raise HTTPException(400,'Il faut au moins 1 point.')
    if len(requete.points)>MAX_POINTS_REQUETE: raise HTTPException(400,'Maximum 1000 points par requête.')
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

@app.post('/api/road-route')
async def api_road_route(requete:RequeteRoadRoute,infos=Security(verifier_minuteur_cle_api)):
    if len(requete.points)<2:raise HTTPException(400,'Il faut au moins 2 points.')
    if len(requete.points)>1000:raise HTTPException(400,'Maximum 1000 points par requête.')
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
    return f'''<html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>SwiftRoute Admin</title></head><body style="background:#09090b;color:#fff;font-family:Arial;padding:25px"><div style="max-width:520px;margin:auto;background:#18181b;padding:25px;border-radius:12px"><h2>🎛️ Administration SwiftRoute</h2><p>Produit Tiun : {TIUN_PRODUCT_ID}</p><form action="/admin-panel/generer" method="post"><input name="username" placeholder="Identifiant" required style="width:100%;padding:12px;box-sizing:border-box"><br><br><input type="password" name="password" placeholder="Mot de passe" required style="width:100%;padding:12px;box-sizing:border-box"><br><br><input name="client_name" placeholder="Entreprise" required style="width:100%;padding:12px;box-sizing:border-box"><br><br><input type="email" name="email" placeholder="Email" required style="width:100%;padding:12px;box-sizing:border-box"><br><br><select name="duration" style="width:100%;padding:12px"><option value="7">Essai 7 jours</option><option value="30">Entreprise 30 jours</option><option value="365">Corporate 1 an</option></select><br><br><button style="width:100%;padding:13px;background:#a855f7;color:#fff;border:0;border-radius:7px">Générer et activer</button></form>{result}</div></body></html>'''

@app.get('/admin-panel',response_class=HTMLResponse)
async def vue_panneau_admin_serveur(cle_generee:str=''):return HTMLResponse(obtenir_panneau_admin(cle_generee))

@app.post('/admin-panel/generer')
async def action_generer_cle_serveur(request:Request,username:str=Form(...),password:str=Form(...),client_name:str=Form(...),email:str=Form(...),duration:int=Form(...)):
    if username!=NOM_UTILISATEUR_ADMIN or password!=MOT_DE_PASSE_ADMIN:return HTMLResponse('<h2>Identifiants incorrects.</h2>',403)
    if duration not in (7,30,365):raise HTTPException(400,'Durée invalide.')
    email=normalize_email(email);token,jti,expiration=create_client_token(client_name,email,duration,duration==7)
    if duration==7:
        conn=db_connect();
        if conn.execute('SELECT id FROM trials WHERE email_hash=?',(hash_value(email),)).fetchone():conn.close();return HTMLResponse('<h2>Cet e-mail possède déjà un essai.</h2>',409)
        now=datetime.datetime.now(datetime.timezone.utc);conn.execute('INSERT INTO trials(email,email_hash,client_name,ip_hash,token_jti,created_at,expires_at,active,usage_count) VALUES(?,?,?,?,?,?,?,?,?)',(email,hash_value(email),client_name,hash_value(get_client_ip(request)),jti,now.isoformat(),expiration.isoformat(),1,0));conn.commit();conn.close()
    # Correction: un seul argument pour obtenir_panneau_admin.
    return HTMLResponse(obtenir_panneau_admin(token))

@app.get('/health')
async def health():return {'status':'ok','service':'SwiftRoute Engine','version':'3.1','max_points':1000}

if __name__=='__main__':
    import uvicorn
    uvicorn.run('main:app',host='0.0.0.0',port=int(os.getenv('PORT','8000')),reload=False)
