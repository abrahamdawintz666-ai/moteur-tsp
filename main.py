import os
import io
import csv
import json
import secrets
import base64
import math
import random
import hashlib
import urllib.parse
import urllib.request
import urllib.error
import smtplib
import re
from email.message import EmailMessage
from datetime import datetime, timedelta, timezone

from flask import (
    Flask, render_template_string, request, redirect, url_for,
    flash, session, jsonify, make_response, abort
)
from flask_sqlalchemy import SQLAlchemy
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.exc import IntegrityError
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

try:
    from ortools.constraint_solver import pywrapcp, routing_enums_pb2
    HAS_ORTOOLS = True
except ImportError:
    HAS_ORTOOLS = False

# ============================================================
# GLOBALROUTE AI — GLOBAL B2B SAAS
# ============================================================
# Real road routing:
#   - OSRM driving network, never straight-line fallback
#   - OSRM Table matrix for road distances
#   - OR-Tools when installed for large route optimization
#   - OSRM Trip fallback when OR-Tools is unavailable
#
# Data integrity:
#   - strict coordinate validation
#   - duplicate detection
#   - bounded point count
#   - no silent conversion of invalid rows
#
# Security:
#   - password hashing
#   - strong API keys
#   - secure session configuration
#   - server-side subscription/quota enforcement
#   - signed/hashed driver access codes
# ============================================================

app = Flask(__name__)

app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY") or secrets.token_hex(32)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.getenv("COOKIE_SECURE", "0") == "1"
app.config["SESSION_COOKIE_NAME"] = "globalroute_session"

APP_NAME = "GlobalRoute AI — Global Enterprise Logistics"

SOLANA_RECEIVING_WALLET = "22BzBEYLewJkKe2FXD6EHJYqX4NNshMw9roNw9qFxV9d"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGkZwyTDt1v"
SOLANA_RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.mainnet.solana.com")

# OSRM public/default endpoint. On production, use your own OSRM server
# for higher capacity and predictable limits.
ROUTING_URL = os.getenv(
    "ROUTING_URL", "https://router.project-osrm.org"
).rstrip("/")
OSRM_PROFILE = os.getenv("OSRM_PROFILE", "driving")
OSRM_TIMEOUT = int(os.getenv("OSRM_TIMEOUT", "45"))

# Keep below common public OSRM coordinate limits.
OSRM_MATRIX_BLOCK = int(os.getenv("OSRM_MATRIX_BLOCK", "50"))
OSRM_TRIP_LIMIT = int(os.getenv("OSRM_TRIP_LIMIT", "80"))

# Account activation / password reset security
ACTIVATION_KEY_DAYS = int(os.getenv("ACTIVATION_KEY_DAYS", "30"))
PASSWORD_RESET_MINUTES = int(os.getenv("PASSWORD_RESET_MINUTES", "30"))
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USERNAME)

# Maximum accepted points for one optimization request.
MAX_ROUTE_POINTS = int(os.getenv("MAX_ROUTE_POINTS", "1000"))

# Optional OR-Tools search time per optimization.
OR_TOOLS_SECONDS = int(os.getenv("OR_TOOLS_SECONDS", "30"))

# AntStrike / ACO road-optimization engine. The algorithm operates ONLY on
# real road distances returned by the routing matrix; it never invents a
# distance from latitude/longitude.
ACO_ANTS = int(os.getenv("ACO_ANTS", "24"))
ACO_WORKER_WAVES = int(os.getenv("ACO_WORKER_WAVES", "4"))
ACO_ENGINEER_WAVES = int(os.getenv("ACO_ENGINEER_WAVES", "3"))
ACO_ITERATIONS_PER_WAVE = int(os.getenv("ACO_ITERATIONS_PER_WAVE", "12"))
ACO_EVAPORATION = float(os.getenv("ACO_EVAPORATION", "0.18"))
ACO_ALPHA = float(os.getenv("ACO_ALPHA", "1.0"))
ACO_BETA = float(os.getenv("ACO_BETA", "3.0"))
ACO_ELITE = int(os.getenv("ACO_ELITE", "4"))
ACO_2OPT_PASSES = int(os.getenv("ACO_2OPT_PASSES", "3"))
ROUTE_BLOCK_SIZE = int(os.getenv("ROUTE_BLOCK_SIZE", "100"))


# Admin password MUST be configured in Render/environment.
ADMIN_SECRET_PASSWORD = os.getenv("ADMIN_SECRET_PASSWORD")
if not ADMIN_SECRET_PASSWORD:
    ADMIN_SECRET_PASSWORD = secrets.token_urlsafe(32)
    print("WARNING: ADMIN_SECRET_PASSWORD is not configured.")

limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=["200 per minute", "20 per second"],
    storage_uri="memory://"
)

TRANSLATIONS = {
    "fr": {
        "home_title": "Optimisation mondiale de tournées pour entreprises B2B.",
        "dashboard": "Tableau de bord",
        "import": "Importer",
        "plans": "Abonnements",
        "logout": "Déconnexion",
        "login": "Connexion",
        "register": "Créer un compte",
        "admin": "Admin",
        "driver_space": "Espace livreur",
    },
    "en": {
        "home_title": "Global route optimization for modern B2B enterprises.",
        "dashboard": "Dashboard",
        "import": "Import",
        "plans": "Plans",
        "logout": "Logout",
        "login": "Login",
        "register": "Register",
        "admin": "Admin",
        "driver_space": "Driver Space",
    },
    "es": {
        "home_title": "Optimización global de rutas para empresas B2B.",
        "dashboard": "Panel",
        "import": "Importar",
        "plans": "Planes",
        "logout": "Cerrar sesión",
        "login": "Iniciar sesión",
        "register": "Registrarse",
        "admin": "Admin",
        "driver_space": "Espacio repartidor",
    },
}

PLANS = {
    "standard": {
        "name": "Standard",
        "monthly_price": 99.00,
        "tour_limit": 500,
        "point_limit": 500,
    },
    "pro": {
        "name": "Pro",
        "monthly_price": 300.00,
        "tour_limit": 2500,
        "point_limit": 1000,
    },
}

DURATIONS = {30: 1.0, 90: 2.7, 180: 5.0, 365: 9.0}


# ============================================================
# DATABASE
# ============================================================

database_url = os.getenv("DATABASE_URL")
if database_url:
    if database_url.startswith("postgres://"):
        database_url = database_url.replace(
            "postgres://", "postgresql+psycopg2://", 1
        )
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace(
            "postgresql://", "postgresql+psycopg2://", 1
        )
else:
    database_url = "sqlite:///globalroute.db"

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Render PostgreSQL can close an idle TLS connection while SQLAlchemy still
# has it in the pool. Without pre-ping, the next innocent SELECT can become
# the exact error seen in production: psycopg2.OperationalError /
# "SSL SYSCALL error: EOF detected" -> HTTP 500/502.
# Keep the pool small on the free instance, recycle old connections, and
# validate a connection before handing it to a request.
if "postgresql" in database_url:
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_pre_ping": True,
        "pool_recycle": 240,
        "pool_size": 3,
        "max_overflow": 2,
        "pool_timeout": 20,
        "pool_reset_on_return": "rollback",
        "connect_args": {
            "connect_timeout": 15,
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 3,
            "sslmode": "require",
        },
    }
else:
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_pre_ping": True,
    }

db = SQLAlchemy(app)


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(160), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(30), default="dispatcher")
    language = db.Column(db.String(10), default="fr")
    address = db.Column(db.String(250), default="")
    city = db.Column(db.String(100), default="")
    country = db.Column(db.String(100), default="")
    tax_id = db.Column(db.String(50), default="")
    # Compatibility with older production schemas that already contain this field.
    # A Python default prevents PostgreSQL NOT NULL failures on legacy databases.
    payment_method = db.Column(db.String(40), nullable=False, default="unknown", server_default="unknown")
    plan = db.Column(db.String(30), default="standard")
    subscription_started_at = db.Column(db.DateTime, nullable=True)
    subscription_expires_at = db.Column(db.DateTime, nullable=True)
    credits = db.Column(db.Integer, default=0)
    unlimited = db.Column(db.Boolean, default=False)
    tour_limit = db.Column(db.Integer, default=500)
    tours_used = db.Column(db.Integer, default=0)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    api_keys = db.relationship(
        "ApiKey", backref="owner", lazy=True,
        cascade="all, delete-orphan"
    )
    deliveries = db.relationship(
        "DeliveryRoute", backref="company", lazy=True,
        cascade="all, delete-orphan"
    )
    payments = db.relationship(
        "PaymentOrder", backref="customer", lazy=True,
        cascade="all, delete-orphan"
    )


class ApiKey(db.Model):
    __tablename__ = "api_keys"

    id = db.Column(db.Integer, primary_key=True)
    key_string = db.Column(db.String(255), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=True)
    revoked = db.Column(db.Boolean, default=False)


class AccountInvitation(db.Model):
    __tablename__ = "account_invitations"

    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(180), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    used_at = db.Column(db.DateTime, nullable=True)


class PasswordResetToken(db.Model):
    __tablename__ = "password_reset_tokens"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    token_hash = db.Column(db.String(255), unique=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    used_at = db.Column(db.DateTime, nullable=True)


class PaymentOrder(db.Model):
    __tablename__ = "payment_orders"

    id = db.Column(db.Integer, primary_key=True)
    order_code = db.Column(db.String(80), unique=True, nullable=False, index=True)
    reference = db.Column(db.String(64), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    plan = db.Column(db.String(30), nullable=False)
    duration_days = db.Column(db.Integer, nullable=False)
    amount_usdc = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(10), default="USDC")
    status = db.Column(db.String(20), default="pending")
    transaction_signature = db.Column(db.String(160), unique=True, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    paid_at = db.Column(db.DateTime, nullable=True)


class DeliveryRoute(db.Model):
    __tablename__ = "delivery_routes"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    route_name = db.Column(db.Text, default="Tournée")
    driver_name = db.Column(db.String(100), nullable=False)
    access_code = db.Column(db.String(120), nullable=False, index=True)
    access_code_hash = db.Column(db.String(255), nullable=True)
    stops_data = db.Column(db.Text, nullable=False)
    stops_summary = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default="En cours")
    optimized = db.Column(db.Boolean, default=False)
    optimization_engine = db.Column(db.String(40), default="OSRM")
    total_road_distance_m = db.Column(db.Float, nullable=True)
    road_geometry_json = db.Column(db.Text, nullable=True)
    optimization_id = db.Column(db.String(80), nullable=True, unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(120), nullable=False)
    details = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


def migrate_existing_database():
    """Safely add columns introduced by newer GlobalRoute versions.

    The old version silently ignored ALTER TABLE failures. That can leave
    columns such as api_keys.key_type missing and turn normal Admin actions
    into HTTP 500 errors. This version reports migration failures clearly.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(db.engine)
    existing_tables = set(inspector.get_table_names())
    models = (
        ("users", User),
        ("api_keys", ApiKey),
        ("account_invitations", AccountInvitation),
        ("password_reset_tokens", PasswordResetToken),
        ("payment_orders", PaymentOrder),
        ("delivery_routes", DeliveryRoute),
        ("audit_logs", AuditLog),
    )

    for table_name, model in models:
        if table_name not in existing_tables:
            continue

        existing_columns = {
            col["name"] for col in inspector.get_columns(table_name)
        }

        for column in model.__table__.columns:
            if column.name in existing_columns or column.primary_key:
                continue

            try:
                type_sql = column.type.compile(
                    dialect=db.engine.dialect
                )
                # New columns are nullable here so existing production rows
                # remain valid on both SQLite and PostgreSQL.
                sql = (
                    f'ALTER TABLE "{table_name}" ADD COLUMN '
                    f'"{column.name}" {type_sql}'
                )
                db.session.execute(text(sql))
                db.session.commit()
            except Exception as exc:
                db.session.rollback()
                # Re-inspect: another worker may have added it concurrently.
                refreshed = inspect(db.engine)
                names = {c["name"] for c in refreshed.get_columns(table_name)}
                if column.name not in names:
                    raise RuntimeError(
                        f"Migration base de données impossible : "
                        f"{table_name}.{column.name}: {exc}"
                    ) from exc


with app.app_context():
    db.create_all()
    migrate_existing_database()



# ============================================================
# GENERAL UTILITIES
# ============================================================

ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def base58_encode(raw: bytes) -> str:
    number = int.from_bytes(raw, "big")
    result = ""

    while number:
        number, remainder = divmod(number, 58)
        result = ALPHABET[remainder] + result

    leading_zeroes = sum(1 for byte in raw if byte == 0)
    return "1" * leading_zeroes + (result or "")


def generate_reference():
    return base58_encode(secrets.token_bytes(32))


def utcnow():
    return datetime.utcnow()


def get_current_lang():
    lang = session.get("lang", "fr")
    return lang if lang in TRANSLATIONS else "fr"


def t(key):
    lang = get_current_lang()
    return TRANSLATIONS.get(
        lang, TRANSLATIONS["fr"]
    ).get(key, key)


def calculate_price(plan, duration_days):
    if plan not in PLANS or duration_days not in DURATIONS:
        raise ValueError("Paramètres invalides.")

    return round(
        PLANS[plan]["monthly_price"] *
        DURATIONS[duration_days],
        2
    )


def parse_coordinate(value):
    try:
        value = str(value).strip().replace(",", ".")
        return float(value)
    except (ValueError, TypeError):
        return None


def normalize_text(value, max_length=500):
    value = str(value or "").strip()
    return value[:max_length]


def validate_stop(point, index):
    if not isinstance(point, dict):
        raise ValueError(f"Point #{index + 1}: format invalide.")

    lat = parse_coordinate(point.get("lat"))
    lng = parse_coordinate(
        point.get("lng", point.get("lon"))
    )

    if lat is None or lng is None:
        raise ValueError(
            f"Point #{index + 1}: latitude/longitude manquante."
        )

    if not (-90 <= lat <= 90):
        raise ValueError(
            f"Point #{index + 1}: latitude hors limites."
        )

    if not (-180 <= lng <= 180):
        raise ValueError(
            f"Point #{index + 1}: longitude hors limites."
        )

    name = normalize_text(point.get("name"), 150)
    address = normalize_text(point.get("address"), 500)

    if not name:
        name = f"Point {index + 1}"

    return {
        "name": name,
        "address": address,
        "lat": lat,
        "lng": lng,
    }


def validate_stops(stops, max_points=MAX_ROUTE_POINTS):
    if not isinstance(stops, list):
        raise ValueError("Les étapes doivent être une liste.")

    if len(stops) < 2:
        raise ValueError("Au moins 2 points sont nécessaires.")

    if len(stops) > max_points:
        raise ValueError(
            f"Maximum autorisé : {max_points} points "
            f"par optimisation."
        )

    clean = []
    seen = set()
    duplicates = []

    for i, point in enumerate(stops):
        clean_point = validate_stop(point, i)

        key = (
            round(clean_point["lat"], 7),
            round(clean_point["lng"], 7),
        )

        if key in seen:
            duplicates.append(i + 1)
        else:
            seen.add(key)

        clean.append(clean_point)

    if duplicates:
        raise ValueError(
            "Coordonnées dupliquées aux lignes : "
            + ", ".join(map(str, duplicates))
            + ". Corrigez les doublons avant optimisation."
        )

    return clean


def hash_access_code(value):
    return generate_password_hash(
        value,
        method="pbkdf2:sha256:600000"
    )


def check_access_code(route, supplied):
    if not supplied:
        return False

    if route.access_code_hash:
        return check_password_hash(
            route.access_code_hash,
            supplied
        )

    # Compatibilité avec les anciennes tournées.
    return secrets.compare_digest(
        str(route.access_code or ""),
        str(supplied)
    )


def generate_driver_code():
    return "GR-" + secrets.token_urlsafe(12)


def create_api_key(user, expires_at, revoke_existing=False, prefix="gr_live_"):
    """Create a strong B2B API key. Invitations are stored separately."""
    if revoke_existing:
        ApiKey.query.filter_by(
            user_id=user.id,
            revoked=False
        ).update(
            {"revoked": True},
            synchronize_session=False
        )

    for _ in range(5):
        key_str = prefix + secrets.token_urlsafe(36)
        if not ApiKey.query.filter_by(key_string=key_str).first():
            key = ApiKey(
                key_string=key_str,
                user_id=user.id,
                expires_at=expires_at,
                revoked=False,
            )
            db.session.add(key)
            db.session.flush()
            return key
    raise RuntimeError("Impossible de générer une clé API unique.")

def active_api_key(user):
    now = utcnow()

    for key in user.api_keys:
        if (
            not key.revoked
            and (
                not key.expires_at
                or key.expires_at >= now
            )
        ):
            return key

    return None


def add_subscription(user, plan, duration_days):
    now = utcnow()

    same_plan = bool(
        user.subscription_expires_at
        and user.subscription_expires_at > now
        and user.plan == plan
    )

    if same_plan:
        expiry = (
            user.subscription_expires_at
            + timedelta(days=duration_days)
        )

        user.tour_limit = (
            int(user.tour_limit or 0)
            + int(PLANS[plan]["tour_limit"])
        )

    else:
        expiry = now + timedelta(days=duration_days)

        user.plan = plan
        user.subscription_started_at = now
        user.subscription_expires_at = expiry
        user.tour_limit = int(PLANS[plan]["tour_limit"])
        user.tours_used = 0
        user.credits = user.tour_limit

    key = active_api_key(user)

    if key:
        key.expires_at = expiry
    else:
        create_api_key(
            user,
            expiry,
            revoke_existing=True
        )

    return expiry


# ============================================================
# OSRM REAL ROAD ENGINE
# ============================================================

def osrm_request(service, stops, params=None):
    """
    Call OSRM.

    IMPORTANT:
    This function never falls back to Haversine or a straight line.
    """
    if not stops:
        raise RuntimeError("Aucun point à envoyer à OSRM.")

    coordinates = ";".join(
        f"{float(p['lng'])},{float(p['lat'])}"
        for p in stops
    )

    query = urllib.parse.urlencode(params or {})

    url = (
        f"{ROUTING_URL}/"
        f"{service}/v1/{OSRM_PROFILE}/"
        f"{coordinates}"
    )

    if query:
        url += "?" + query

    request_obj = urllib.request.Request(
        url,
        headers={
            "User-Agent": "GlobalRoute-AI/1.0"
        }
    )

    last_error = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(
                request_obj,
                timeout=OSRM_TIMEOUT
            ) as response:
                data = json.loads(
                    response.read().decode("utf-8")
                )
            break
        except urllib.error.HTTPError as exc:
            # A 400 is normally a malformed/too-large OSRM request; retrying
            # the identical request cannot repair it and only wastes time.
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:500]
            except Exception:
                detail = str(exc)
            raise RuntimeError(
                f"OSRM HTTP {exc.code}: {detail or exc.reason}"
            ) from exc
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                import time
                time.sleep(0.8 * (attempt + 1))
    else:
        raise RuntimeError(
            "Connexion au moteur routier OSRM impossible après 3 essais. "
            f"Vérifiez ROUTING_URL dans Render. Détail : {last_error}"
        )

    if data.get("code") != "Ok":
        code = data.get("code", "erreur inconnue")
        message = data.get("message", code)
        # Keep the routing error structured so the caller can distinguish
        # a disconnected road network (NoRoute) from an HTTP/service error.
        err = RuntimeError(f"OSRM {code}: {message}")
        setattr(err, "osrm_code", code)
        setattr(err, "osrm_message", message)
        raise err

    return data


def build_osrm_pairwise_matrix(stops):
    """Reliable small-job fallback using individual OSRM road routes."""
    n = len(stops)
    matrix = [[None for _ in range(n)] for _ in range(n)]
    for i in range(n):
        matrix[i][i] = 0
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            data = osrm_request("route", [stops[i], stops[j]], {
                "overview": "false",
                "steps": "false",
                "alternatives": "false",
            })
            routes = data.get("routes") or []
            if not routes:
                raise RuntimeError(f"OSRM n'a pas trouvé de route entre les points {i+1} et {j+1}.")
            matrix[i][j] = int(round(float(routes[0].get("distance", 0))))
    return matrix


def build_osrm_table(stops):
    """
    Builds a road-distance matrix in meters.

    OSRM Table is called in blocks so hundreds of points can be
    processed without a huge single HTTP request.
    """
    n = len(stops)
    matrix = [
        [None for _ in range(n)]
        for _ in range(n)
    ]

    # Keep source + destination coordinates <= 100 for common public OSRM limits.
    block = max(10, min(OSRM_MATRIX_BLOCK, 50))

    for source_start in range(0, n, block):
        source_end = min(source_start + block, n)
        source_indices = list(
            range(source_start, source_end)
        )

        for dest_start in range(0, n, block):
            dest_end = min(dest_start + block, n)
            dest_indices = list(
                range(dest_start, dest_end)
            )

            # All points must be in the coordinate list.
            combined_indices = list(
                dict.fromkeys(
                    source_indices + dest_indices
                )
            )

            local_stops = [
                stops[i]
                for i in combined_indices
            ]

            source_positions = [
                combined_indices.index(i)
                for i in source_indices
            ]

            destination_positions = [
                combined_indices.index(i)
                for i in dest_indices
            ]

            try:
                data = osrm_request(
                    "table",
                    local_stops,
                    {
                        "sources": ";".join(
                            map(str, source_positions)
                        ),
                        "destinations": ";".join(
                            map(str, destination_positions)
                        ),
                        "annotations": "distance,duration",
                    }
                )
            except RuntimeError as exc:
                # OSRM Table can fail with NoRoute when one or more submitted
                # coordinates are not connected in the driving graph. Do not
                # silently substitute straight-line distances. Re-run the
                # affected block as small direct routes so we can identify
                # the exact disconnected pair and give the user a useful
                # diagnostic.
                if getattr(exc, "osrm_code", None) == "NoRoute":
                    bad_pairs = []
                    for gi in source_indices:
                        for gj in dest_indices:
                            if gi == gj:
                                continue
                            try:
                                pair = osrm_request("route", [stops[gi], stops[gj]], {
                                    "overview": "false",
                                    "steps": "false",
                                    "alternatives": "false",
                                })
                                routes = pair.get("routes") or []
                                if not routes:
                                    bad_pairs.append((gi, gj))
                            except RuntimeError as pair_exc:
                                if getattr(pair_exc, "osrm_code", None) == "NoRoute":
                                    bad_pairs.append((gi, gj))
                                else:
                                    raise
                    if bad_pairs:
                        sample = []
                        for gi, gj in bad_pairs[:5]:
                            a, b = stops[gi], stops[gj]
                            sample.append(
                                f"#{gi+1} ({a['lat']:.6f},{a['lng']:.6f}) -> "
                                f"#{gj+1} ({b['lat']:.6f},{b['lng']:.6f})"
                            )
                        raise RuntimeError(
                            "OSRM NoRoute : certaines coordonnées ne sont pas "
                            "reliées par le réseau routier 'driving'. "
                            "Points concernés : " + "; ".join(sample) +
                            (" …" if len(bad_pairs) > 5 else "") +
                            ". Vérifiez les coordonnées/adresses ou utilisez "
                            "un moteur routier couvrant cette zone."
                        ) from exc
                raise

            distances = data.get("distances") or []

            for si, row in enumerate(distances):
                global_i = source_indices[si]

                for di, value in enumerate(row):
                    global_j = dest_indices[di]
                    matrix[global_i][global_j] = value

    for i in range(n):
        matrix[i][i] = 0

    missing = [
        (i, j)
        for i in range(n)
        for j in range(n)
        if matrix[i][j] is None
    ]

    if missing:
        raise RuntimeError(
            f"OSRM n'a pas fourni {len(missing)} "
            "distances routières."
        )

    return [
        [int(round(float(x))) for x in row]
        for row in matrix
    ]


def route_cost(order, distance_matrix):
    """Cost of an index order using the real OSRM road-distance matrix."""
    return sum(
        int(distance_matrix[order[i]][order[i + 1]])
        for i in range(len(order) - 1)
    )


def two_opt_indices(order, distance_matrix, max_passes=ACO_2OPT_PASSES):
    """Deterministic 2-opt improvement while preserving fixed endpoints."""
    route = list(order)
    if len(route) < 4:
        return route

    for _ in range(max(1, max_passes)):
        improved = False
        for i in range(1, len(route) - 2):
            a, b = route[i - 1], route[i]
            for j in range(i + 1, len(route) - 1):
                c, d = route[j], route[j + 1]
                old = distance_matrix[a][b] + distance_matrix[c][d]
                new = distance_matrix[a][c] + distance_matrix[b][d]
                if new < old:
                    route[i:j + 1] = reversed(route[i:j + 1])
                    improved = True
                    break
            if improved:
                break
        if not improved:
            break
    return route


def _aco_construct_solution(distance_matrix, pheromone, rng):
    """One ant constructs a route from first node to last node."""
    n = len(distance_matrix)
    if n <= 2:
        return list(range(n))

    current = 0
    destination = n - 1
    unvisited = set(range(1, destination))
    order = [0]

    while unvisited:
        candidates = list(unvisited)
        weights = []
        for nxt in candidates:
            d = max(float(distance_matrix[current][nxt]), 1.0)
            tau = max(float(pheromone[current][nxt]), 1e-12)
            weight = (tau ** ACO_ALPHA) * ((1.0 / d) ** ACO_BETA)
            weights.append(weight)

        total = sum(weights)
        if total <= 0 or not math.isfinite(total):
            nxt = min(candidates, key=lambda x: distance_matrix[current][x])
        else:
            pick = rng.random() * total
            cumulative = 0.0
            nxt = candidates[-1]
            for candidate, weight in zip(candidates, weights):
                cumulative += weight
                if cumulative >= pick:
                    nxt = candidate
                    break

        order.append(nxt)
        unvisited.remove(nxt)
        current = nxt

    order.append(destination)
    return order


def ant_colony_optimize_indices(distance_matrix, seed=None):
    """AntStrike ACO with worker, saboteur and engineer waves.

    Worker waves construct candidate routes using pheromones and road
    distance. Saboteur phases remove weak trails and apply 2-opt cleanup.
    Engineer waves reinforce the best routes and run another construction
    round. A final saboteur pass performs deterministic corrections.
    First and last nodes remain fixed throughout.
    """
    n = len(distance_matrix)
    if n <= 2:
        return list(range(n))

    rng = random.Random(seed if seed is not None else 20261007)

    # Adaptive workload: keep the same AntStrike architecture, but prevent
    # a web request from spending tens of seconds doing Python-side ACO on
    # larger matrices. The algorithm is still executed; only the number of
    # ants/waves/iterations is scaled to the problem size.
    if n <= 20:
        ants, worker_waves, engineer_waves, iterations = (12, 2, 1, 4)
    elif n <= 50:
        ants, worker_waves, engineer_waves, iterations = (12, 2, 1, 5)
    elif n <= 100:
        ants, worker_waves, engineer_waves, iterations = (12, 2, 1, 4)
    elif n <= 150:
        ants, worker_waves, engineer_waves, iterations = (10, 2, 1, 3)
    else:
        ants, worker_waves, engineer_waves, iterations = (8, 1, 1, 3)

    finite_edges = [
        float(distance_matrix[i][j])
        for i in range(n)
        for j in range(n)
        if i != j and distance_matrix[i][j] and distance_matrix[i][j] > 0
    ]
    base = (sum(finite_edges) / len(finite_edges)) if finite_edges else 1.0
    initial_pheromone = 1.0 / max(base, 1.0)
    pheromone = [
        [initial_pheromone for _ in range(n)]
        for _ in range(n)
    ]

    best = list(range(n))
    best = two_opt_indices(best, distance_matrix)
    best_cost = route_cost(best, distance_matrix)

    def wave(iterations, phase):
        nonlocal best, best_cost, pheromone
        for _ in range(max(1, iterations)):
            candidates = []
            for _ant in range(max(2, ants)):
                route = _aco_construct_solution(distance_matrix, pheromone, rng)
                route = two_opt_indices(route, distance_matrix, ACO_2OPT_PASSES)
                cost = route_cost(route, distance_matrix)
                candidates.append((cost, route))

            candidates.sort(key=lambda x: x[0])
            if candidates and candidates[0][0] < best_cost:
                best_cost, best = candidates[0]

            # Evaporation = the saboteur's cleanup of weak/old trails.
            evaporation = min(max(ACO_EVAPORATION, 0.01), 0.90)
            for i in range(n):
                for j in range(n):
                    pheromone[i][j] *= (1.0 - evaporation)

            elite_count = max(1, min(ACO_ELITE, len(candidates)))
            selected = candidates[:elite_count]
            if phase == "engineer" and best:
                selected = selected + [(best_cost, best)]

            for cost, route in selected:
                deposit = 1.0 / max(float(cost), 1.0)
                for k in range(len(route) - 1):
                    a, b = route[k], route[k + 1]
                    pheromone[a][b] += deposit
                    pheromone[b][a] += deposit * 0.5

    # Worker waves: exploration.
    for _ in range(max(1, worker_waves)):
        wave(iterations, "worker")

    # Saboteur correction: strongest deterministic 2-opt cleanup.
    best = two_opt_indices(best, distance_matrix, ACO_2OPT_PASSES + 2)
    best_cost = route_cost(best, distance_matrix)

    # Engineer waves: intensification around the best discovered route.
    for _ in range(max(1, engineer_waves)):
        wave(iterations, "engineer")
        best = two_opt_indices(best, distance_matrix, ACO_2OPT_PASSES + 1)
        best_cost = route_cost(best, distance_matrix)

    # Final saboteur/rectification wave.
    best = two_opt_indices(best, distance_matrix, ACO_2OPT_PASSES + 3)
    return best


def optimize_exact_small(stops, distance_matrix):
    """Exact road-distance TSP for very small jobs; used as a benchmark."""
    from itertools import permutations
    n = len(stops)
    if n <= 2:
        return list(stops)
    if n > 9:
        return None
    best_order = None
    best_cost = None
    middle = list(range(1, n - 1))
    for perm in permutations(middle):
        order = [0, *perm, n - 1]
        cost = route_cost(order, distance_matrix)
        if best_cost is None or cost < best_cost:
            best_cost = cost
            best_order = order
    return [stops[i] for i in best_order] if best_order is not None else None


def optimize_with_ortools(stops, distance_matrix):
    """Second-opinion optimizer using the same real OSRM road matrix."""
    if not HAS_ORTOOLS:
        return None
    n = len(stops)
    if n <= 2:
        return list(stops)

    manager = pywrapcp.RoutingIndexManager(n, 1, [0], [n - 1])
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        a = manager.IndexToNode(from_index)
        b = manager.IndexToNode(to_index)
        value = distance_matrix[a][b]
        return int(value) if value is not None else 10**12

    callback = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(callback)
    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    # Keep a single web request bounded on Render. Small jobs may use the full
    # configured budget; large synchronized blocks get a shorter second-opinion
    # pass so one HTTP request does not sit behind OR-Tools for minutes.
    # Hard web-request budget. OR-Tools remains the second opinion, but it
    # must not hold the Flask request open long enough for Render/Chrome to
    # return 502.
    block_seconds = min(OR_TOOLS_SECONDS, 4)
    if n <= 20:
        block_seconds = min(block_seconds, 2)
    elif n <= 50:
        block_seconds = min(block_seconds, 3)
    elif n <= 150:
        block_seconds = min(block_seconds, 4)
    else:
        block_seconds = min(block_seconds, 2)
    params.time_limit.seconds = max(1, block_seconds)

    solution = routing.SolveWithParameters(params)
    if not solution:
        return None

    ordered = []
    index = routing.Start(0)
    while not routing.IsEnd(index):
        ordered.append(stops[manager.IndexToNode(index)])
        index = solution.Value(routing.NextVar(index))
    ordered.append(stops[manager.IndexToNode(index)])
    return ordered if len(ordered) == n else None


def route_to_indices(ordered_stops, original_stops):
    """Map route objects back to original indices without guessing."""
    lookup = {
        (p["lat"], p["lng"]): i
        for i, p in enumerate(original_stops)
    }
    result = []
    for p in ordered_stops:
        key = (p["lat"], p["lng"])
        if key not in lookup:
            raise RuntimeError("Le moteur a retourné un point inconnu.")
        result.append(lookup[key])
    return result


def validate_route_order(order, n):
    if len(order) != n or sorted(order) != list(range(n)):
        raise RuntimeError("La solution du moteur ne contient pas exactement tous les points.")
    if order[0] != 0 or order[-1] != n - 1:
        raise RuntimeError("Le départ et la destination doivent rester fixes.")


def compare_candidate_orders(candidates, distance_matrix):
    """Choose the shortest candidate according to the same road matrix."""
    valid = []
    n = len(distance_matrix)
    for label, order in candidates:
        try:
            validate_route_order(order, n)
            valid.append((route_cost(order, distance_matrix), label, order))
        except Exception:
            continue
    if not valid:
        return None, None
    valid.sort(key=lambda x: x[0])
    return valid[0][2], valid[0][1]


def optimize_matrix_block(stops, matrix, seed=20261007):
    """Run ACO + 2-opt, then OR-Tools as a second opinion on a block."""
    n = len(stops)
    aco_order = ant_colony_optimize_indices(matrix, seed=seed)
    aco_order = two_opt_indices(aco_order, matrix, ACO_2OPT_PASSES + 2)
    candidates = [("AntStrike ACO + 2-opt", aco_order)]

    if HAS_ORTOOLS:
        ortools_stops = optimize_with_ortools(stops, matrix)
        if ortools_stops:
            candidates.append(("OR-Tools", route_to_indices(ortools_stops, stops)))

    # Exact benchmark for very small blocks; this catches regressions.
    if n <= 9:
        exact = optimize_exact_small(stops, matrix)
        if exact:
            candidates.append(("Exact road TSP", route_to_indices(exact, stops)))

    order, winner = compare_candidate_orders(candidates, matrix)
    if order is None:
        raise RuntimeError("Aucune solution routière valide n'a été produite.")
    return [stops[i] for i in order], winner


def optimize_stops_order(stops):
    """Global road engine: OSRM matrix -> AntStrike ACO/2-opt -> OR-Tools.

    For <= matrix_limit points, the complete road matrix is used.
    Larger jobs are processed in synchronized blocks. Each next block starts
    from the previous block's boundary point, so blocks are connected rather
    than independently reordered. This is scalable, but it is not a
    mathematical guarantee of a globally optimal 1000-point TSP.
    """
    stops = validate_stops(stops)
    n = len(stops)

    if n == 2:
        geometry, distance = get_route_geometry(stops)
        return stops, geometry, distance, "OSRM Road Route"

    matrix_limit = int(os.getenv("OR_TOOLS_MATRIX_MAX_POINTS", "250"))

    if n <= matrix_limit:
        try:
            matrix = build_osrm_table(stops)
        except Exception as table_exc:
            app.logger.warning("OSRM Table failed; pairwise recovery: %s", table_exc)
            if n <= 12:
                matrix = build_osrm_pairwise_matrix(stops)
            else:
                raise

        optimized, winner = optimize_matrix_block(stops, matrix)
        geometry, distance = get_route_geometry(optimized)
        return optimized, geometry, distance, f"OSRM Road Matrix + {winner}"

    # Large route: synchronized road blocks. The boundary point is carried
    # into the next block, preserving continuity between consecutive blocks.
    block_size = max(20, min(ROUTE_BLOCK_SIZE, matrix_limit))
    optimized_all = []
    boundary = None
    pos = 0
    block_number = 0
    winners = []

    while pos < n:
        end = min(pos + block_size, n)
        raw_block = stops[pos:end]
        if boundary is not None:
            raw_block = [boundary] + raw_block

        try:
            block_matrix = build_osrm_table(raw_block)
        except Exception as exc:
            raise RuntimeError(
                f"Bloc {block_number + 1}: matrice routière indisponible. {exc}"
            ) from exc

        ordered_block, winner = optimize_matrix_block(
            raw_block,
            block_matrix,
            seed=20261007 + block_number,
        )

        if boundary is not None:
            # The carried boundary is the first point of the block and must
            # not be duplicated in the global sequence.
            if ordered_block[0]["lat"] == boundary["lat"] and ordered_block[0]["lng"] == boundary["lng"]:
                ordered_block = ordered_block[1:]

        if not ordered_block:
            raise RuntimeError(f"Bloc {block_number + 1}: aucun point produit.")

        optimized_all.extend(ordered_block)
        boundary = optimized_all[-1]
        winners.append(winner)
        pos = end
        block_number += 1

    if len(optimized_all) != n:
        raise RuntimeError(
            "Le moteur routier n'a pas pu reconstruire exactement tous les points."
        )

    # Final global 2-opt is intentionally limited: a complete 1000-point
    # matrix is not available here, so no fabricated cross-block distances.
    geometry, distance = get_route_geometry(optimized_all)
    return optimized_all, geometry, distance, (
        "OSRM Synchronized Blocks + AntStrike ACO/2-opt + OR-Tools"
    )


def get_route_geometry(stops):
    """Get real OSRM road geometry for the final ordered route."""
    if len(stops) < 2:
        return [], 0.0

    geometries = []
    total_distance = 0.0
    # Public OSRM instances can reject large coordinate lists. Keeping the
    # final geometry request at <=50 points is conservative and matches the
    # matrix block strategy used above.
    chunk_size = max(10, min(OSRM_TRIP_LIMIT, 50))

    for start in range(0, len(stops) - 1, chunk_size - 1):
        end = min(start + chunk_size, len(stops))
        chunk = stops[start:end]
        if len(chunk) < 2:
            continue

        data = osrm_request("route", chunk, {
            "overview": "full",
            "geometries": "geojson",
            "steps": "false",
            "alternatives": "false",
        })
        routes = data.get("routes") or []
        if not routes:
            raise RuntimeError("OSRM n'a pas retourné la géométrie routière finale.")

        route = routes[0]
        total_distance += float(route.get("distance", 0))
        geometry = route.get("geometry", {}).get("coordinates", [])
        if geometries and geometry:
            geometries.extend(geometry[1:])
        else:
            geometries.extend(geometry)

        if end == len(stops):
            break

    if not geometries:
        raise RuntimeError("OSRM n'a fourni aucune géométrie routière finale.")

    leaflet_geometry = [
        [float(coord[1]), float(coord[0])]
        for coord in geometries if len(coord) >= 2
    ]
    return leaflet_geometry, total_distance


# ============================================================
# SOLANA PAYMENTS
# ============================================================

def rpc_call(method, params):
    payload = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params,
    }).encode("utf-8")

    req = urllib.request.Request(
        SOLANA_RPC_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "GlobalRoute-AI/1.0",
        },
        method="POST",
    )

    with urllib.request.urlopen(
        req,
        timeout=20
    ) as response:
        data = json.loads(
            response.read().decode("utf-8")
        )

    if "error" in data:
        raise RuntimeError(str(data["error"]))

    return data.get("result")


def find_signature_by_reference(reference):
    result = rpc_call(
        "getSignaturesForAddress",
        [reference, {"limit": 20}]
    )

    if not result:
        return None

    for item in result:
        if not item.get("err"):
            return item.get("signature")

    return None


def verify_usdc_payment(order):
    signature = find_signature_by_reference(
        order.reference
    )

    if not signature:
        return (
            False,
            None,
            "Paiement non trouvé sur la blockchain."
        )

    existing_order = PaymentOrder.query.filter_by(
        transaction_signature=signature
    ).first()

    if (
        existing_order
        and existing_order.id != order.id
    ):
        return (
            False,
            signature,
            "Cette transaction est déjà utilisée."
        )

    tx = rpc_call(
        "getTransaction",
        [
            signature,
            {
                "encoding": "jsonParsed",
                "commitment": "confirmed",
                "maxSupportedTransactionVersion": 0,
            },
        ]
    )

    if not tx or (
        tx.get("meta")
        and tx["meta"].get("err") is not None
    ):
        return (
            False,
            None,
            "Transaction Solana invalide."
        )

    meta = tx.get("meta") or {}

    expected_raw = int(
        round(order.amount_usdc * 1_000_000)
    )

    received_raw = sum(
        int(
            balance.get(
                "uiTokenAmount", {}
            ).get("amount", "0")
        )
        for balance in (
            meta.get("postTokenBalances") or []
        )
        if (
            balance.get("mint") == USDC_MINT
            and balance.get("owner")
            == SOLANA_RECEIVING_WALLET
        )
    )

    pre_raw = sum(
        int(
            balance.get(
                "uiTokenAmount", {}
            ).get("amount", "0")
        )
        for balance in (
            meta.get("preTokenBalances") or []
        )
        if (
            balance.get("mint") == USDC_MINT
            and balance.get("owner")
            == SOLANA_RECEIVING_WALLET
        )
    )

    if received_raw - pre_raw < expected_raw:
        return (
            False,
            signature,
            f"Montant USDC insuffisant. "
            f"Attendu : {order.amount_usdc} USDC."
        )

    return True, signature, "Paiement vérifié."


def activate_paid_order(order, signature):
    if order.status == "paid":
        return

    user = User.query.get(order.user_id)

    if not user:
        raise RuntimeError("Utilisateur introuvable.")

    add_subscription(
        user,
        order.plan,
        order.duration_days
    )

    order.status = "paid"
    order.transaction_signature = signature
    order.paid_at = utcnow()

    db.session.add(
        AuditLog(
            action="PAYMENT_CONFIRMED",
            details=(
                f"order={order.order_code}; "
                f"user={user.email}; "
                f"sig={signature}"
            )
        )
    )

    db.session.commit()


# ============================================================
# SECURITY / AUTH HELPERS
# ============================================================

def current_user():
    user_id = session.get("user_id")

    if not user_id:
        return None

    # A stale PostgreSQL connection can still fail during the actual SELECT
    # even with pool_pre_ping. Retry once after disposing the broken pool.
    # This keeps a transient Render/Postgres disconnect from becoming a
    # customer-facing HTTP 500/502 on every dashboard request.
    from sqlalchemy.exc import OperationalError

    for attempt in range(2):
        try:
            user = db.session.get(User, user_id)
            if not user or not user.active:
                session.pop("user_id", None)
                return None
            return user
        except OperationalError as exc:
            db.session.rollback()
            if attempt == 0:
                app.logger.warning(
                    "PostgreSQL connection dropped while loading user; "
                    "disposing pool and retrying: %s",
                    exc,
                )
                db.engine.dispose()
                continue
            app.logger.exception("PostgreSQL unavailable after retry")
            raise

    return None


def strong_password(password):
    if len(password) < 12:
        return False

    checks = [
        any(c.islower() for c in password),
        any(c.isupper() for c in password),
        any(c.isdigit() for c in password),
        any(not c.isalnum() for c in password),
    ]

    return all(checks)


def send_email(to_email, subject, body_text):
    """Send transactional email through Gmail SMTP when configured.

    Render must provide SMTP_USERNAME and SMTP_PASSWORD. For Gmail,
    SMTP_PASSWORD should be a Google App Password, not the normal password.
    """
    if not SMTP_USERNAME or not SMTP_PASSWORD:
        raise RuntimeError("SMTP non configuré dans Render (SMTP_USERNAME/SMTP_PASSWORD).")
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM or SMTP_USERNAME
    msg["To"] = to_email
    msg.set_content(body_text)
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
        server.starttls()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.send_message(msg)


def hash_reset_token(raw_token):
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def safe_db_commit(action="database commit", retries=1):
    """Commit with one controlled reconnect for transient PostgreSQL EOFs."""
    from sqlalchemy.exc import OperationalError

    for attempt in range(retries + 1):
        try:
            db.session.commit()
            return
        except OperationalError as exc:
            db.session.rollback()
            if attempt >= retries:
                raise
            app.logger.warning(
                "%s failed with a transient DB connection error; retrying: %s",
                action, exc,
            )
            db.engine.dispose()


def admin_required():
    return bool(session.get("is_admin"))


# ============================================================
# DESIGN
# ============================================================

BASE_STYLE = """
:root {
  --navy:#0f172a;
  --blue:#2563eb;
  --blue2:#1d4ed8;
  --green:#059669;
  --red:#dc2626;
  --bg:#f8fafc;
  --card:#ffffff;
  --text:#0f172a;
  --muted:#64748b;
  --border:#e2e8f0;
}
* { box-sizing:border-box; }
html,body {
  margin:0;
  padding:0;
  background:var(--bg);
  color:var(--text);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  overflow-x:hidden;
}
header {
  background:var(--navy);
  color:white;
  padding:12px 20px;
  display:flex;
  align-items:center;
  gap:15px;
  position:relative;
}
header h1 {
  margin:0;
  font-size:18px;
  flex:1;
  overflow:hidden;
  text-overflow:ellipsis;
  white-space:nowrap;
}
.lang-selector {
  background:rgba(255,255,255,.1);
  color:white;
  border:1px solid rgba(255,255,255,.2);
  border-radius:6px;
  padding:6px;
  font-size:12px;
}
.menu-toggle {
  width:40px;
  height:40px;
  border:1px solid rgba(255,255,255,.2);
  border-radius:8px;
  background:rgba(255,255,255,.1);
  color:white;
  font-size:20px;
  cursor:pointer;
}
nav {
  display:none;
  position:absolute;
  top:60px;
  left:15px;
  z-index:1000;
  min-width:220px;
  padding:10px;
  background:var(--navy);
  border:1px solid rgba(255,255,255,.15);
  border-radius:12px;
  box-shadow:0 10px 30px rgba(0,0,0,.3);
  flex-direction:column;
  gap:6px;
}
nav.open { display:flex; }
nav a {
  color:#e2e8f0;
  text-decoration:none;
  font-size:13px;
  padding:10px;
  border-radius:8px;
}
nav a:hover { background:rgba(255,255,255,.1); }
.container {
  width:100%;
  max-width:1150px;
  margin:0 auto;
  padding:16px;
}
.card {
  background:var(--card);
  border:1px solid var(--border);
  border-radius:14px;
  padding:18px;
  margin-bottom:20px;
  box-shadow:0 4px 15px rgba(0,0,0,.03);
  word-break:break-word;
}
.hero { text-align:center; padding:30px 15px; }
.btn {
  display:inline-block;
  border:0;
  border-radius:8px;
  padding:12px 16px;
  font-weight:600;
  text-decoration:none;
  cursor:pointer;
  background:var(--blue);
  color:white;
  text-align:center;
  font-size:14px;
}
.btn:hover { background:var(--blue2); }
.btn-secondary { background:#e2e8f0; color:var(--navy); }
.btn-green { background:var(--green); color:white; }
.btn-red { background:var(--red); color:white; }
.btn-block { width:100%; display:block; }
label {
  display:block;
  margin:12px 0 6px;
  font-size:13px;
  font-weight:700;
}
input,select,textarea {
  width:100%;
  max-width:100%;
  border:1px solid #cbd5e1;
  border-radius:8px;
  padding:11px;
  font-size:14px;
  background:white;
}
.table-responsive {
  width:100%;
  overflow-x:auto;
  -webkit-overflow-scrolling:touch;
}
table {
  width:100%;
  border-collapse:collapse;
  font-size:13px;
  white-space:nowrap;
}
th,td {
  border-bottom:1px solid var(--border);
  padding:12px 10px;
  text-align:left;
}
th { background:#f1f5f9; }
.alert {
  padding:12px;
  border-radius:8px;
  margin-bottom:15px;
  font-size:13px;
}
.alert-success { background:#dcfce7; color:#166534; }
.alert-danger { background:#fee2e2; color:#991b1b; }
.grid {
  display:grid;
  grid-template-columns:repeat(3,1fr);
  gap:15px;
}
.stat {
  background:#f8fafc;
  border:1px solid var(--border);
  border-radius:10px;
  padding:15px;
}
.stat strong {
  display:block;
  font-size:20px;
  margin-top:4px;
  word-break:break-all;
}
.muted { color:var(--muted); font-size:12px; }
.mono {
  font-family:monospace;
  word-break:break-all;
}
#map {
  width:100%;
  height:500px;
  border-radius:10px;
  margin-top:15px;
  z-index:1;
}
.plan-grid {
  display:grid;
  grid-template-columns:repeat(2,1fr);
  gap:20px;
}
.plan-card {
  background:white;
  border:1px solid var(--border);
  border-radius:14px;
  padding:20px;
}
.plan-card.featured {
  border:2px solid var(--blue);
}
.badge {
  display:inline-block;
  padding:5px 8px;
  border-radius:999px;
  font-size:11px;
  font-weight:700;
  background:#dbeafe;
  color:#1d4ed8;
}
@media(max-width:768px) {
  .grid,.plan-grid { grid-template-columns:1fr; }
  .container { padding:10px; }
  .card { padding:14px; }
}
"""

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ title or APP_NAME }}</title>
{% if map_needed %}
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
{% endif %}
<style>{{ style }}</style>
</head>
<body>
<header>
  <button class="menu-toggle" onclick="toggleMenu()">☰</button>
  <h1>{{ APP_NAME }}</h1>
  <select class="lang-selector"
          onchange="location.href='/set-lang/' + this.value">
    <option value="fr" {% if session.get('lang','fr') == 'fr' %}selected{% endif %}>Français</option>
    <option value="en" {% if session.get('lang','fr') == 'en' %}selected{% endif %}>English</option>
    <option value="es" {% if session.get('lang','fr') == 'es' %}selected{% endif %}>Español</option>
  </select>
  <nav id="global-menu">
    <a href="{{ url_for('index') }}">⌂ &nbsp;Accueil</a>
    {% if session.get("user_id") %}
    <a href="{{ url_for('dashboard') }}">▣ &nbsp;{{ t('dashboard') }}</a>
    <a href="{{ url_for('import_space') }}">⇧ &nbsp;{{ t('import') }}</a>
    <a href="{{ url_for('plans') }}">◈ &nbsp;{{ t('plans') }}</a>
    <a href="{{ url_for('logout') }}">⏻ &nbsp;{{ t('logout') }}</a>
    {% else %}
    <a href="{{ url_for('login_form') }}">↪ &nbsp;{{ t('login') }}</a>
    <a href="{{ url_for('register_form') }}">＋ &nbsp;{{ t('register') }}</a>
    {% endif %}
    <a href="{{ url_for('activate_account') }}">🔑 &nbsp;Activer un compte</a>
    <a href="{{ url_for('admin_panel') }}">⚙ &nbsp;{{ t('admin') }}</a>
    <a href="{{ url_for('driver_login') }}">🚚 &nbsp;{{ t('driver_space') }}</a>
  </nav>
</header>
<script>
function toggleMenu() {
  document.getElementById("global-menu").classList.toggle("open");
}
</script>
<div class="container">
{% with messages = get_flashed_messages(with_categories=true) %}
{% for cat,msg in messages %}
<div class="alert alert-{{ 'success' if cat == 'success' else 'danger' }}">
{{ msg }}
</div>
{% endfor %}
{% endwith %}
{{ body|safe }}
</div>
<footer style="text-align:center;padding:20px;color:#64748b;font-size:12px;">
© 2026 GlobalRoute AI — Global Enterprise B2B Logistics
</footer>
</body>
</html>
"""


def page(body, title=APP_NAME, map_needed=False):
    return render_template_string(
        HTML_TEMPLATE,
        body=body,
        title=title,
        style=BASE_STYLE,
        APP_NAME=APP_NAME,
        map_needed=map_needed,
        session=session,
        t=t,
    )


# ============================================================
# HOME / LANGUAGE
# ============================================================

@app.route("/set-lang/<lang>")
def set_lang(lang):
    if lang in TRANSLATIONS:
        session["lang"] = lang

    return redirect(
        request.referrer or url_for("index")
    )


@app.route("/")
def index():
    body = f"""
    <div class="hero card">
      <h2>{t('home_title')}</h2>
      <p class="muted">
        GlobalRoute AI calcule des itinéraires sur le réseau routier réel
        et optimise les tournées B2B à partir de données géographiques
        validées.
      </p>
      <div style="margin-top:20px;display:flex;gap:10px;justify-content:center;flex-wrap:wrap;">
        <a href="{url_for('register_form')}" class="btn">
          Créer un compte entreprise
        </a>
        <a href="{url_for('login_form')}" class="btn btn-secondary">
          Connexion
        </a>
      </div>
    </div>

    <div class="grid">
      <div class="card">
        <h3>🛣️ Routage réel</h3>
        <p class="muted">OSRM / Driving Network</p>
        <p>Les itinéraires suivent les routes disponibles.</p>
      </div>

      <div class="card">
        <h3>🌍 B2B mondial</h3>
        <p class="muted">Multi-pays / Multi-entreprises</p>
        <p>Architecture conçue pour des tournées internationales.</p>
      </div>

      <div class="card">
        <h3>🔐 Enterprise</h3>
        <p class="muted">Sécurité / API / Audit</p>
        <p>Données isolées et accès contrôlés côté serveur.</p>
      </div>
    </div>
    """

    return page(body)


# ============================================================
# REGISTER / LOGIN
# ============================================================

@app.route("/register-form")
def register_form():
    body = f"""
    <div class="card" style="max-width:500px;margin:0 auto;">
      <h2>Créer un compte entreprise B2B</h2>

      <form method="POST" action="{url_for('register')}">
        <label>Nom de l'entreprise</label>
        <input type="text" name="company_name" maxlength="150" required>

        <label>E-mail professionnel</label>
        <input type="email" name="email" maxlength="160" required>

        <label>Mot de passe sécurisé</label>
        <input
          type="password"
          name="password"
          minlength="12"
          autocomplete="new-password"
          required
          placeholder="12 caractères, majuscule, chiffre et symbole"
        >

        <p class="muted">
          Minimum 12 caractères avec majuscule, minuscule,
          chiffre et symbole.
        </p>

        <label>Adresse</label>
        <input type="text" name="address">

        <label>Ville</label>
        <input type="text" name="city">

        <label>Pays</label>
        <input type="text" name="country">

        <label>Numéro de TVA / Tax ID</label>
        <input type="text" name="tax_id">

        <div style="margin-top:20px;">
          <button type="submit" class="btn btn-block">
            Créer le compte
          </button>
        </div>
      </form>
    </div>
    """

    return page(body)


@app.route("/register", methods=["POST"])
@limiter.limit("5 per minute")
def register():
    company = normalize_text(
        request.form.get("company_name"),
        150
    )

    email = normalize_text(
        request.form.get("email"),
        160
    ).lower()

    password = request.form.get("password", "")

    if not company or not email:
        flash(
            "Nom d'entreprise et e-mail requis.",
            "danger"
        )
        return redirect(url_for("register_form"))

    if not strong_password(password):
        flash(
            "Mot de passe insuffisant : minimum 12 caractères "
            "avec majuscule, minuscule, chiffre et symbole.",
            "danger"
        )
        return redirect(url_for("register_form"))

    if User.query.filter_by(email=email).first():
        flash(
            "Cet e-mail est déjà associé à un compte.",
            "danger"
        )
        return redirect(url_for("register_form"))

    user = User(
        company_name=company,
        email=email,
        password_hash=generate_password_hash(
            password,
            method="pbkdf2:sha256:600000"
        ),
        address=normalize_text(
            request.form.get("address"), 250
        ),
        city=normalize_text(
            request.form.get("city"), 100
        ),
        country=normalize_text(
            request.form.get("country"), 100
        ),
        tax_id=normalize_text(
            request.form.get("tax_id"), 50
        ),
        role="dispatcher",
    )

    db.session.add(user)
    db.session.commit()

    session.clear()
    session["user_id"] = user.id
    session["lang"] = "fr"

    flash(
        "Compte créé avec succès. Choisissez votre abonnement.",
        "success"
    )

    return redirect(url_for("plans"))


@app.route("/login-form")
def login_form():
    body = f"""
    <div class="card" style="max-width:400px;margin:0 auto;">
      <h2>Connexion Entreprise</h2>

      <form method="POST" action="{url_for('login')}">
        <label>E-mail</label>
        <input type="email" name="email" autocomplete="email" required>

        <label>Mot de passe</label>
        <input type="password" name="password"
               autocomplete="current-password" required>

        <div style="margin-top:20px;">
          <button type="submit" class="btn btn-block">
            Connexion
          </button>
        </div>
        <p style="margin-top:15px;text-align:center;">
          <a href="{url_for('forgot_password_form')}">Mot de passe oublié ?</a>
        </p>
      </form>
    </div>
    """

    return page(body)


@app.route("/login", methods=["POST"])
@limiter.limit("10 per minute")
def login():
    email = normalize_text(
        request.form.get("email"),
        160
    ).lower()

    password = request.form.get("password", "")

    user = db.session.execute(
        db.select(User).filter_by(email=email)
    ).scalar_one_or_none()

    if user and user.active and check_password_hash(
        user.password_hash,
        password
    ):
        session.clear()
        session["user_id"] = user.id
        session["lang"] = user.language or "fr"

        return redirect(url_for("dashboard"))

    flash(
        "Identifiants incorrects.",
        "danger"
    )

    return redirect(url_for("login_form"))


@app.route("/forgot-password", methods=["GET"])
def forgot_password_form():
    return page(f"""
    <div class="card" style="max-width:450px;margin:0 auto;">
      <h2>Réinitialiser le mot de passe</h2>
      <p class="muted">Un lien à usage unique sera envoyé à l'adresse e-mail du compte.</p>
      <form method="POST" action="{url_for('forgot_password')}">
        <label>E-mail du compte</label>
        <input type="email" name="email" required autocomplete="email">
        <div style="margin-top:20px"><button class="btn btn-block" type="submit">Envoyer le lien</button></div>
      </form>
    </div>
    """, title="Mot de passe oublié")


@app.route("/forgot-password", methods=["POST"])
@limiter.limit("5 per hour")
def forgot_password():
    email = normalize_text(request.form.get("email"), 160).lower()
    # Always return the same message to avoid revealing whether an account exists.
    generic = "Si ce compte existe, un lien de réinitialisation vient d'être envoyé."
    user = User.query.filter_by(email=email).first()
    if not user or not user.active:
        flash(generic, "success")
        return redirect(url_for("login_form"))

    PasswordResetToken.query.filter_by(user_id=user.id, used_at=None).update(
        {"used_at": utcnow()}, synchronize_session=False
    )
    raw = secrets.token_urlsafe(48)
    token = PasswordResetToken(
        user_id=user.id,
        token_hash=hash_reset_token(raw),
        expires_at=utcnow() + timedelta(minutes=PASSWORD_RESET_MINUTES),
    )
    db.session.add(token)
    db.session.commit()
    reset_url = url_for("reset_password", token=raw, _external=True)
    body = (
        f"Bonjour {user.company_name},\n\n"
        "Une demande de réinitialisation de votre mot de passe GlobalRoute AI a été reçue.\n\n"
        f"Utilisez ce lien dans les {PASSWORD_RESET_MINUTES} prochaines minutes :\n{reset_url}\n\n"
        "Ce lien est à usage unique. Si vous n'êtes pas à l'origine de la demande, ignorez cet e-mail."
    )
    try:
        send_email(user.email, "GlobalRoute AI — Réinitialisation du mot de passe", body)
    except Exception as exc:
        db.session.rollback()
        app.logger.exception("SMTP reset password failed")
        flash("Le compte est valide, mais l'e-mail n'a pas pu être envoyé. Configurez SMTP dans Render.", "danger")
        return redirect(url_for("login_form"))
    flash(generic, "success")
    return redirect(url_for("login_form"))


@app.route("/reset-password/<token>", methods=["GET", "POST"])
@limiter.limit("10 per hour")
def reset_password(token):
    record = PasswordResetToken.query.filter_by(token_hash=hash_reset_token(token), used_at=None).first()
    if not record or record.expires_at < utcnow():
        flash("Lien de réinitialisation invalide ou expiré.", "danger")
        return redirect(url_for("forgot_password_form"))
    if request.method == "GET":
        return page(f"""
        <div class="card" style="max-width:450px;margin:0 auto;">
          <h2>Nouveau mot de passe</h2>
          <form method="POST">
            <label>Nouveau mot de passe</label>
            <input type="password" name="password" minlength="12" required autocomplete="new-password">
            <label>Confirmer</label>
            <input type="password" name="password_confirm" minlength="12" required autocomplete="new-password">
            <p class="muted">12 caractères minimum : majuscule, minuscule, chiffre et symbole.</p>
            <button class="btn btn-block" type="submit">Enregistrer</button>
          </form>
        </div>
        """, title="Nouveau mot de passe")
    password = request.form.get("password", "")
    confirm = request.form.get("password_confirm", "")
    if not strong_password(password):
        flash("Mot de passe trop faible.", "danger")
        return redirect(url_for("reset_password", token=token))
    if password != confirm:
        flash("Les deux mots de passe ne correspondent pas.", "danger")
        return redirect(url_for("reset_password", token=token))
    user = User.query.get(record.user_id)
    if not user or not user.active:
        flash("Compte indisponible.", "danger")
        return redirect(url_for("login_form"))
    user.password_hash = generate_password_hash(password, method="pbkdf2:sha256:600000")
    record.used_at = utcnow()
    db.session.add(AuditLog(action="PASSWORD_RESET", details=f"user={user.email}"))
    db.session.commit()
    flash("Mot de passe modifié avec succès. Vous pouvez vous connecter.", "success")
    return redirect(url_for("login_form"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/dashboard")
def dashboard():
    user = current_user()

    if not user:
        return redirect(url_for("login_form"))

    key = active_api_key(user)

    key_text = (
        key.key_string
        if key
        else "Aucune clé API active"
    )

    expiry = (
        user.subscription_expires_at.strftime("%Y-%m-%d")
        if user.subscription_expires_at
        else "—"
    )

    remaining = max(
        0,
        int(user.tour_limit or 0)
        - int(user.tours_used or 0)
    )

    try:
        routes = (
            DeliveryRoute.query
            .filter_by(user_id=user.id)
            .order_by(DeliveryRoute.id.desc())
            .limit(30)
            .all()
        )
    except Exception as exc:
        # Do not expose a raw SQLAlchemy traceback to the customer. The most
        # common Render failure here is a dropped PostgreSQL SSL connection.
        db.session.rollback()
        app.logger.exception("Dashboard database read failed")
        flash(
            "Connexion temporaire à la base de données. "
            "Actualisez la page dans quelques secondes.",
            "danger",
        )
        return redirect(url_for("dashboard"))

    route_rows = ""

    for route in routes:
        try:
            stops = json.loads(
                route.stops_data or "[]"
            )
            count = len(stops)
        except Exception:
            count = 0

        route_rows += f"""
        <tr>
          <td>{route.route_name}</td>
          <td>{route.driver_name}</td>
          <td>{count}</td>
          <td>{route.optimization_engine}</td>
          <td>
            <a href="{url_for('driver_space', code=route.access_code)}"
               class="btn"
               style="padding:6px 10px;font-size:12px;">
              Ouvrir
            </a>
          </td>
        </tr>
        """

    body = f"""
    <div class="card">
      <h2>{user.company_name}</h2>
      <p class="muted">
        {user.email}
        · {user.city or '—'}
        · {user.country or '—'}
      </p>

      <div class="grid" style="margin-top:20px;">
        <div class="stat">
          <span>Abonnement</span>
          <strong>{user.plan.title()}</strong>
        </div>

        <div class="stat">
          <span>Tournées</span>
          <strong>{user.tours_used}/{user.tour_limit}</strong>
        </div>

        <div class="stat">
          <span>Restantes</span>
          <strong>{remaining}</strong>
        </div>
      </div>

      <p class="muted" style="margin-top:15px;">
        Expiration : {expiry}
      </p>
    </div>

    <div class="card">
      <h3>🚀 Optimisation routière</h3>
      <p class="muted">
        Importez des coordonnées propres. Le moteur valide les données,
        construit les distances routières OSRM et recherche un ordre
        optimisé sur le réseau routier.
      </p>

      <a href="{url_for('import_space')}" class="btn">
        Importer / Créer une tournée
      </a>
    </div>

    <div class="card">
      <h3>📋 Historique des tournées</h3>

      <div class="table-responsive">
        <table>
          <thead>
            <tr>
              <th>Tournée</th>
              <th>Livreur</th>
              <th>Points</th>
              <th>Moteur</th>
              <th>Action</th>
            </tr>
          </thead>

          <tbody>
            {route_rows or '<tr><td colspan="5" style="text-align:center;" class="muted">Aucune tournée.</td></tr>'}
          </tbody>
        </table>
      </div>
    </div>

    <div class="card">
      <h3>🔑 API B2B</h3>
      <p class="muted">
        POST /api/v1/route avec X-API-KEY.
      </p>

      <div class="mono"
           style="background:#f1f5f9;padding:10px;border-radius:6px;">
        {key_text}
      </div>
    </div>
    """

    return page(
        body,
        title="Dashboard B2B"
    )


# ============================================================
# IMPORT
# ============================================================

@app.route("/import-space")
def import_space():
    if not current_user():
        return redirect(url_for("login_form"))

    return render_template_string(
        IMPORT_FORM_HTML,
        style=BASE_STYLE,
        APP_NAME=APP_NAME
    )


IMPORT_FORM_HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GlobalRoute AI — Import</title>
<style>{{ style }}</style>
</head>

<body>
<div class="container" style="max-width:760px;margin-top:30px;">

<div class="card">
<h2>🛣️ Optimisation routière réelle</h2>

<p class="muted">
Format : Nom | Adresse | Latitude | Longitude
</p>

<form method="POST" action="/create-driver-route">

<label>Nom de la tournée</label>
<input type="text" name="route_name"
       value="Tournée Principale"
       maxlength="200" required>

<label>Nom du livreur</label>
<input type="text" name="driver_name"
       maxlength="100" required>

<label>Code d'accès du livreur</label>
<input type="text" name="access_code"
       value=""
       placeholder="Laisser vide pour générer automatiquement">

<label>Fichier CSV / TXT</label>
<input type="file"
       id="file-input"
       accept=".csv,.txt">

<label>Données</label>
<textarea id="manual-stops"
          name="manual_stops"
          rows="16"
          placeholder="Client A | Paris | 48.8566 | 2.3522
Client B | Lyon | 45.7640 | 4.8357"
          required></textarea>

<div class="card"
     style="background:#eff6ff;margin-top:15px;">
<strong>Important</strong>
<p class="muted">
Les coordonnées sont vérifiées avant le calcul.
Les doublons ou coordonnées invalides sont refusés.
Aucune ligne droite n'est utilisée comme route de secours.
</p>
</div>

<div style="margin-top:20px;display:flex;gap:10px;flex-wrap:wrap;">
<button type="submit" class="btn">
Optimiser sur les vraies routes
</button>

<a href="/dashboard"
   class="btn btn-secondary">
Retour
</a>
</div>

</form>
</div>
</div>

<script>
document.getElementById("file-input").addEventListener(
  "change",
  function(event) {
    const file = event.target.files[0];
    if (!file) return;

    const reader = new FileReader();

    reader.onload = function(e) {
      document.getElementById(
        "manual-stops"
      ).value = e.target.result;
    };

    reader.readAsText(file, "UTF-8");
  }
);
</script>

</body>
</html>
"""


def parse_manual_stops(text):
    stops = []

    for line_number, line in enumerate(
        text.splitlines(),
        start=1
    ):
        line = line.strip()

        if not line:
            continue

        # Accept | separated data.
        parts = [
            x.strip()
            for x in line.split("|")
        ]

        if len(parts) < 4:
            raise ValueError(
                f"Ligne {line_number}: "
                "format attendu Nom | Adresse | Lat | Lng."
            )

        stops.append({
            "name": parts[0],
            "address": parts[1],
            "lat": parts[2],
            "lng": parts[3],
        })

    return stops


@app.route("/create-driver-route", methods=["POST"])
@limiter.limit("10 per minute")
def create_driver_route():
    user = current_user()

    if not user:
        return redirect(url_for("login_form"))

    if (
        user.subscription_expires_at
        and user.subscription_expires_at < utcnow()
    ):
        flash(
            "Votre abonnement a expiré.",
            "danger"
        )
        return redirect(url_for("plans"))

    if user.tours_used >= user.tour_limit:
        flash(
            "Quota de tournées atteint.",
            "danger"
        )
        return redirect(url_for("dashboard"))

    route_name = normalize_text(
        request.form.get("route_name"),
        200
    )

    driver_name = normalize_text(
        request.form.get("driver_name"),
        100
    )

    access_code = normalize_text(
        request.form.get("access_code"),
        100
    )

    manual = request.form.get(
        "manual_stops",
        ""
    ).strip()

    if not access_code:
        access_code = generate_driver_code()

    if not manual:
        flash(
            "Aucune donnée de tournée.",
            "danger"
        )
        return redirect(url_for("import_space"))

    try:
        raw_stops = parse_manual_stops(manual)
        stops = validate_stops(raw_stops)
        app.logger.info("ROUTE_OPTIMIZATION_START points=%s user=%s", len(stops), user.email)

        if len(stops) > MAX_ROUTE_POINTS:
            raise ValueError(
                f"Maximum : {MAX_ROUTE_POINTS} points."
            )

        optimized, geometry, distance, engine = (
            optimize_stops_order(stops)
        )
        app.logger.info("ROUTE_OPTIMIZATION_DONE points=%s distance_m=%s engine=%s", len(optimized), distance, engine)

    except Exception as exc:
        flash(
            "Optimisation impossible : " + str(exc),
            "danger"
        )
        return redirect(url_for("import_space"))

    optimization_id = (
        "OPT-"
        + datetime.utcnow().strftime("%Y%m%d%H%M%S")
        + "-"
        + secrets.token_hex(4).upper()
    )

    summary = json.dumps({
        "optimization_id": optimization_id,
        "engine": engine,
        "points": len(optimized),
        "road_distance_m": distance,
        "created_at": datetime.utcnow().isoformat(),
    })

    route = DeliveryRoute(
        user_id=user.id,
        route_name=route_name or "Tournée",
        driver_name=driver_name or "Livreur",
        access_code=access_code,
        access_code_hash=hash_access_code(access_code),
        stops_data=json.dumps(
            optimized,
            ensure_ascii=False
        ),
        stops_summary=summary,
        optimized=True,
        optimization_engine=engine,
        total_road_distance_m=distance,
        road_geometry_json=json.dumps(geometry, ensure_ascii=False),
        optimization_id=optimization_id,
        status="Optimisée",
    )

    user.tours_used += 1

    db.session.add(route)

    db.session.add(
        AuditLog(
            action="ROUTE_OPTIMIZED",
            details=(
                f"user={user.email}; "
                f"optimization={optimization_id}; "
                f"points={len(optimized)}; "
                f"engine={engine}; "
                f"distance_m={distance}"
            )
        )
    )

    try:
        safe_db_commit("route persistence", retries=1)
    except Exception as exc:
        db.session.rollback()
        app.logger.exception("Erreur DB après optimisation")
        flash(
            "La route a été calculée, mais l'enregistrement en base a échoué : "
            + str(exc),
            "danger"
        )
        return redirect(url_for("dashboard"))

    flash(
        f"Tournée optimisée : {len(optimized)} points · "
        f"{distance / 1000:.2f} km · {engine}.",
        "success"
    )

    return redirect(
        url_for(
            "driver_space",
            code=access_code
        )
    )


# ============================================================
# PLANS / PAYMENTS
# ============================================================

@app.route("/activate-account", methods=["GET", "POST"])
def activate_account():
    if request.method == "GET":
        return page(f"""
        <div class="card" style="max-width:520px;margin:0 auto;">
          <h2>Activer votre compte entreprise</h2>
          <p class="muted">Entrez la clé reçue de l'administrateur, puis choisissez votre mot de passe.</p>
          <form method="POST">
            <label>Clé d'activation</label>
            <input type="text" name="invite_key" required autocomplete="off" spellcheck="false">
            <label>Nouveau mot de passe</label>
            <input type="password" name="password" minlength="12" required autocomplete="new-password">
            <label>Confirmer le mot de passe</label>
            <input type="password" name="password_confirm" minlength="12" required autocomplete="new-password">
            <p class="muted">12 caractères minimum : majuscule, minuscule, chiffre et caractère spécial.</p>
            <button type="submit" class="btn btn-block">Créer le mot de passe et activer</button>
          </form>
        </div>
        """, title="Activation du compte")

    import re
    invite_key = request.form.get("invite_key", "").strip()
    password = request.form.get("password", "")
    confirm = request.form.get("password_confirm", "")
    invitation = AccountInvitation.query.filter_by(
        token=invite_key,
        used_at=None,
    ).first()
    if not invitation or invitation.expires_at < utcnow():
        flash("Clé d'activation invalide ou expirée.", "danger")
        return redirect(url_for("activate_account"))
    user = User.query.get(invitation.user_id)
    if not user or user.active:
        flash("Cette invitation n'est plus disponible.", "danger")
        return redirect(url_for("login_form"))
    strong = (len(password) >= 12 and re.search(r"[A-Z]", password) and re.search(r"[a-z]", password)
              and re.search(r"\d", password) and re.search(r"[^A-Za-z0-9]", password))
    if not strong:
        flash("Mot de passe trop faible. Utilisez 12 caractères minimum avec majuscule, minuscule, chiffre et caractère spécial.", "danger")
        return redirect(url_for("activate_account"))
    if password != confirm:
        flash("Les deux mots de passe ne correspondent pas.", "danger")
        return redirect(url_for("activate_account"))
    user.password_hash = generate_password_hash(password)
    user.active = True
    invitation.used_at = utcnow()
    db.session.add(AuditLog(action="ACCOUNT_ACTIVATED", details=f"user={user.email}; invitation_id={invitation.id}"))
    db.session.commit()
    session.clear()
    session["user_id"] = user.id
    flash("Compte activé avec succès.", "success")
    return redirect(url_for("dashboard"))

@app.route("/plans")
def plans():
    if not current_user():
        return redirect(url_for("login_form"))

    body = f"""
    <div class="hero card">
      <h2>Abonnements B2B Mondiaux</h2>
      <p class="muted">
        Paiement USDC sur Solana.
      </p>
    </div>

    <div class="plan-grid">

      <div class="plan-card">
        <h3>Standard</h3>
        <p class="muted">99 USDC / mois</p>
        <p>500 tournées / mois</p>
        <p>Jusqu'à 500 points par optimisation</p>

        <form method="POST"
              action="{url_for('create_payment')}">

          <input type="hidden"
                 name="plan"
                 value="standard">

          <label>Durée</label>

          <select name="duration_days">
            <option value="30">
              30 jours — 99 USDC
            </option>
            <option value="90">
              90 jours — 267.30 USDC
            </option>
          </select>

          <div style="margin-top:15px;">
            <button type="submit"
                    class="btn btn-block">
              Sélectionner
            </button>
          </div>
        </form>
      </div>

      <div class="plan-card featured">
        <h3>Pro</h3>
        <p class="muted">300 USDC / mois</p>
        <p>2 500 tournées / mois</p>
        <p>Jusqu'à 1 000 points par optimisation</p>
        <p>API B2B</p>

        <form method="POST"
              action="{url_for('create_payment')}">

          <input type="hidden"
                 name="plan"
                 value="pro">

          <label>Durée</label>

          <select name="duration_days">
            <option value="30">
              30 jours — 300 USDC
            </option>
            <option value="90">
              90 jours — 810 USDC
            </option>
          </select>

          <div style="margin-top:15px;">
            <button type="submit"
                    class="btn btn-block">
              Sélectionner Pro
            </button>
          </div>
        </form>
      </div>

    </div>
    """

    return page(
        body,
        title="Abonnements"
    )


@app.route("/create-payment", methods=["POST"])
@limiter.limit("10 per minute")
def create_payment():
    user = current_user()

    if not user:
        return redirect(url_for("login_form"))

    plan = request.form.get("plan")

    try:
        duration = int(
            request.form.get(
                "duration_days",
                30
            )
        )

        amount = calculate_price(
            plan,
            duration
        )

    except Exception:
        flash(
            "Paramètres de paiement invalides.",
            "danger"
        )
        return redirect(url_for("plans"))

    ref = generate_reference()

    user.payment_method = "solana_usdc"

    order = PaymentOrder(
        order_code=(
            "GR-"
            + secrets.token_hex(6).upper()
        ),
        reference=ref,
        user_id=user.id,
        plan=plan,
        duration_days=duration,
        amount_usdc=amount,
        status="pending",
    )

    db.session.add(order)
    db.session.commit()

    solana_uri = (
        f"solana:{SOLANA_RECEIVING_WALLET}"
        f"?amount={amount}"
        f"&spl-token={USDC_MINT}"
        f"&reference={ref}"
        f"&label=GlobalRouteAI"
    )

    body = f"""
    <div class="card"
         style="max-width:500px;margin:0 auto;text-align:center;">

      <h2>Paiement {order.order_code}</h2>

      <p>
        Montant :
        <strong>{amount} USDC</strong>
      </p>

      <div class="mono"
           style="background:#f1f5f9;padding:10px;border-radius:6px;">
        {SOLANA_RECEIVING_WALLET}
      </div>

      <p class="muted">
        Référence unique
      </p>

      <div class="mono"
           style="background:#f1f5f9;padding:10px;border-radius:6px;">
        {ref}
      </div>

      <div style="margin:20px 0;">
        <a href="{solana_uri}"
           class="btn btn-green">
          Payer avec portefeuille Solana
        </a>
      </div>

      <div id="status"
           class="alert alert-success">
        En attente de confirmation...
      </div>

      <a href="{url_for('dashboard')}"
         class="btn btn-secondary">
        Retour
      </a>
    </div>

    <script>
    async function checkPay() {{
      try {{
        const res = await fetch(
          "/api/payment-status/{order.id}"
        );

        const data = await res.json();

        document.getElementById(
          "status"
        ).textContent = data.message;

        if (data.paid) {{
          setTimeout(
            () => location.href="/dashboard",
            1200
          );
        }}
      }} catch(e) {{}}
    }}

    setInterval(checkPay, 6000);
    </script>
    """

    return page(
        body,
        title="Paiement USDC"
    )


@app.route("/api/payment-status/<int:order_id>")
@limiter.limit("20 per minute")
def payment_status(order_id):
    user = current_user()
    order = PaymentOrder.query.get_or_404(order_id)

    if not user or order.user_id != user.id:
        return jsonify({
            "paid": False,
            "message": "Accès refusé."
        }), 403

    if order.status == "paid":
        return jsonify({
            "paid": True,
            "message": "Déjà payé."
        })

    try:
        valid, sig, msg = verify_usdc_payment(
            order
        )

        if valid:
            activate_paid_order(
                order,
                sig
            )

            return jsonify({
                "paid": True,
                "message": "Paiement validé."
            })

        return jsonify({
            "paid": False,
            "message": msg
        })

    except Exception:
        return jsonify({
            "paid": False,
            "message": "Vérification blockchain indisponible."
        }), 503


@app.route("/invoice/<int:order_id>")
def download_invoice(order_id):
    user = current_user()
    order = PaymentOrder.query.get_or_404(order_id)

    if (
        not user
        or order.user_id != user.id
        or order.status != "paid"
    ):
        return "Accès refusé", 403

    buffer = io.BytesIO()

    pdf = canvas.Canvas(
        buffer,
        pagesize=letter
    )

    pdf.drawString(
        50,
        750,
        f"FACTURE / INVOICE - {APP_NAME}"
    )

    pdf.drawString(
        50,
        725,
        f"Commande : {order.order_code}"
    )

    pdf.drawString(
        50,
        700,
        f"Client : {user.company_name} ({user.email})"
    )

    pdf.drawString(
        50,
        675,
        f"Plan : {order.plan.title()} "
        f"({order.duration_days} jours)"
    )

    pdf.drawString(
        50,
        650,
        f"Montant : {order.amount_usdc} USDC"
    )

    pdf.drawString(
        50,
        625,
        f"Date : {order.paid_at}"
    )

    pdf.drawString(
        50,
        575,
        f"Transaction : {order.transaction_signature}"
    )

    pdf.showPage()
    pdf.save()

    buffer.seek(0)

    response = make_response(
        buffer.read()
    )

    response.headers["Content-Type"] = (
        "application/pdf"
    )

    response.headers["Content-Disposition"] = (
        "attachment; "
        f"filename=facture_{order.order_code}.pdf"
    )

    return response


# ============================================================
# DRIVER
# ============================================================

@app.route("/driver-login")
def driver_login():
    body = f"""
    <div class="card"
         style="max-width:400px;margin:0 auto;">

      <h2>🚚 Espace Livreur</h2>

      <form method="POST"
            action="{url_for('driver_space')}">

        <label>Code d'accès</label>

        <input type="password"
               name="access_code"
               autocomplete="off"
               required>

        <div style="margin-top:20px;">
          <button type="submit"
                  class="btn btn-block">
            Accéder
          </button>
        </div>

      </form>
    </div>
    """

    return page(
        body,
        title="Livreur"
    )


@app.route("/driver-space", methods=["GET", "POST"])
@limiter.limit("30 per minute")
def driver_space():
    code = (
        request.form.get("access_code")
        if request.method == "POST"
        else request.args.get("code")
    )

    code = normalize_text(
        code,
        120
    )

    routes = (
        DeliveryRoute.query
        .filter_by(access_code=code)
        .all()
        if code
        else []
    )

    route = None

    for candidate in routes:
        if check_access_code(
            candidate,
            code
        ):
            route = candidate
            break

    if not route:
        flash(
            "Code d'accès invalide.",
            "danger"
        )
        return redirect(
            url_for("driver_login")
        )

    try:
        stops = json.loads(
            route.stops_data or "[]"
        )
        stops = validate_stops(stops)
    except Exception:
        return "Données de tournée invalides.", 500

    stops_json = json.dumps(
        stops,
        ensure_ascii=False
    )

    try:
        stored_geometry = json.loads(
            route.road_geometry_json or "[]"
        )
    except Exception:
        stored_geometry = []

    geometry_json = json.dumps(
        stored_geometry,
        ensure_ascii=False
    )

    distance_km = (
        route.total_road_distance_m / 1000
        if route.total_road_distance_m
        else None
    )

    body = f"""
    <div class="card">

      <h2>Tournée : {route.route_name}</h2>

      <p class="muted">
        Livreur :
        <strong>{route.driver_name}</strong>
        · Entreprise :
        <strong>{route.company.company_name}</strong>
      </p>

      <div class="grid" style="margin-top:15px;">

        <div class="stat">
          <span>Distance routière</span>
          <strong>
            {f"{distance_km:.2f} km" if distance_km is not None else "Calcul..."}
          </strong>
        </div>

        <div class="stat">
          <span>Étapes</span>
          <strong>{len(stops)}</strong>
        </div>

        <div class="stat">
          <span>Moteur</span>
          <strong>{route.optimization_engine}</strong>
        </div>

      </div>

      <div style="margin-top:15px;display:flex;gap:10px;flex-wrap:wrap;">

        <button onclick="toggleTracking()"
                class="btn btn-green">
          📍 Suivi GPS
        </button>

        <a href="{url_for('driver_print', code=route.access_code)}"
           target="_blank"
           class="btn btn-secondary">
          🖨️ Imprimer
        </a>

      </div>

      <div id="map"></div>

    </div>

    <div class="card">
      <h3>Ordre optimisé</h3>
      <div id="stops-list"></div>
    </div>

    <script>
    const points = {stops_json};

    const map = L.map("map").setView(
      points.length
        ? [points[0].lat, points[0].lng]
        : [18.5385, -72.335],
      13
    );

    L.tileLayer(
      "https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png",
      {{maxZoom:19}}
    ).addTo(map);

    let list = "<ol>";

    points.forEach((p, i) => {{
      L.marker([
        p.lat,
        p.lng
      ]).addTo(map)
       .bindPopup(
         "<b>#" + (i + 1)
         + " " + escapeHtml(p.name)
         + "</b><br>"
         + escapeHtml(p.address)
       );

      list +=
        "<li style='margin-bottom:8px;'>"
        + "<strong>#"
        + (i + 1)
        + " — "
        + escapeHtml(p.name)
        + "</strong><br>"
        + "<span class='muted'>"
        + escapeHtml(p.address)
        + "</span>"
        + "</li>";
    }});

    list += "</ol>";

    document.getElementById(
      "stops-list"
    ).innerHTML = list;

    function escapeHtml(value) {{
      return String(value || "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }}

    function drawRealRoadRoute() {{
      const road = {geometry_json};

      if (!road.length) {{
        const warning = document.createElement("div");
        warning.className = "alert alert-danger";
        warning.textContent =
          "La géométrie routière n'est pas disponible. Aucune ligne droite de secours n'est affichée.";
        document.getElementById("map").before(warning);
        return;
      }}

      const polyline = L.polyline(
        road,
        {{
          color:"#2563eb",
          weight:6,
          opacity:.9
        }}
      ).addTo(map);

      map.fitBounds(
        polyline.getBounds(),
        {{padding:[30,30]}}
      );
    }}


    drawRealRoadRoute();

    let trackingInterval = null;
    let driverMarker = null;
    let trackingActive = false;

    function toggleTracking() {{
      const status =
        document.getElementById(
          "gps-status"
        );

      if (!trackingActive) {{

        if (!navigator.geolocation) {{
          alert(
            "GPS non disponible sur cet appareil."
          );
          return;
        }}

        trackingActive = true;
        updateDriverPosition();

        trackingInterval =
          setInterval(
            updateDriverPosition,
            5000
          );

      }} else {{

        trackingActive = false;

        if (trackingInterval) {{
          clearInterval(
            trackingInterval
          );
        }}

        if (driverMarker) {{
          map.removeLayer(
            driverMarker
          );
        }}
      }}
    }}

    function updateDriverPosition() {{
      navigator.geolocation.getCurrentPosition(
        position => {{

          const lat =
            position.coords.latitude;

          const lng =
            position.coords.longitude;

          if (!driverMarker) {{

            driverMarker =
              L.marker([
                lat,
                lng
              ]).addTo(map)
               .bindPopup(
                 "<b>Position du livreur</b>"
               );

          }} else {{

            driverMarker.setLatLng([
              lat,
              lng
            ]);

          }}

        }},
        error => console.warn(
          "GPS:",
          error.message
        ),
        {{
          enableHighAccuracy:true,
          timeout:10000,
          maximumAge:0
        }}
      );
    }}
    </script>
    """

    return page(
        body,
        title="Tournée Livreur",
        map_needed=True
    )


@app.route("/driver-print")
def driver_print():
    code = normalize_text(
        request.args.get("code"),
        120
    )

    routes = (
        DeliveryRoute.query
        .filter_by(access_code=code)
        .all()
    )

    route = None

    for candidate in routes:
        if check_access_code(
            candidate,
            code
        ):
            route = candidate
            break

    if not route:
        return (
            "Code d'accès invalide ou introuvable.",
            404
        )

    stops = json.loads(
        route.stops_data or "[]"
    )

    rows = ""

    for i, point in enumerate(
        stops,
        1
    ):
        rows += f"""
        <tr>
          <td>{i}</td>
          <td>
            <strong>{point.get('name')}</strong>
            <br>
            <span style="color:#555;font-size:12px;">
              {point.get('address')}
            </span>
          </td>
          <td>[ &nbsp; ]</td>
        </tr>
        """

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Fiche de route</title>
<style>
body {{
  font-family:Arial,sans-serif;
  color:#000;
  margin:20px;
}}
table {{
  width:100%;
  border-collapse:collapse;
  margin-top:15px;
}}
th,td {{
  border:1px solid #000;
  padding:10px;
}}
th {{
  background:#eee;
}}
@media print {{
  .no-print {{display:none;}}
}}
</style>
</head>
<body>

<div style="border-bottom:2px solid #000;padding-bottom:10px;">
<h2>
FICHE DE ROUTE :
{route.route_name}
</h2>

<p>
Entreprise :
<strong>{route.company.company_name}</strong>
· Livreur :
<strong>{route.driver_name}</strong>
</p>

<p>
Moteur :
<strong>{route.optimization_engine}</strong>
</p>

</div>

<div class="no-print"
     style="margin:15px 0;">
<button onclick="window.print();">
Imprimer
</button>
</div>

<table>
<thead>
<tr>
<th>#</th>
<th>Client & Adresse</th>
<th>Statut</th>
</tr>
</thead>

<tbody>
{rows}
</tbody>
</table>

<script>
window.onload = function() {{
  window.print();
}};
</script>

</body>
</html>
"""

    return html


# ============================================================
# ADMIN
# ============================================================

@app.route("/admin-panel", methods=["GET", "POST"])
def admin_panel():
    if request.method == "POST":
        if request.form.get("password") == ADMIN_SECRET_PASSWORD:
            session["is_admin"] = True
        else:
            flash("Mot de passe admin incorrect.", "danger")
    if not session.get("is_admin"):
        return page(f"""<div class="card" style="max-width:400px;margin:0 auto;"><h2>Administration Globale</h2>
        <form method="POST"><label>Mot de passe Admin</label><input type="password" name="password" required autocomplete="current-password">
        <div style="margin-top:20px"><button type="submit" class="btn btn-block">Entrer</button></div></form></div>""", title="Admin")
    users=User.query.order_by(User.created_at.desc()).all()
    active_rows="".join(f"<tr><td>{u.company_name}</td><td>{u.email}</td><td>{u.plan}</td><td>Actif</td></tr>" for u in users if u.active)
    pending_rows="".join(f"<tr><td>{u.company_name}</td><td>{u.email}</td><td>Invitation en attente</td></tr>" for u in users if not u.active)
    body=f"""
    <div class="card"><div style="display:flex;justify-content:space-between;align-items:center;gap:10px"><div><h2>Panel Administrateur</h2><p class="muted">Créez un compte entreprise avec son email, puis envoyez-lui sa clé.</p></div><a href="{url_for('admin_logout')}" class="btn btn-red">Quitter</a></div></div>
    <div class="card"><h3>🏢 Nouvelle entreprise</h3>
      <form method="POST" action="{url_for('admin_create_invitation')}">
        <label>Nom de l'entreprise</label><input type="text" name="company_name" required maxlength="150">
        <label>Email de l'entreprise</label><input type="email" name="email" required maxlength="160">
        <label>Pays (optionnel)</label><input type="text" name="country" maxlength="100">
        <div style="margin-top:15px"><button type="submit" class="btn">🔑 Générer la clé d'activation</button></div>
      </form>
    </div>
    <div class="card"><h3>⏳ Invitations en attente</h3><div class="table-responsive"><table><thead><tr><th>Entreprise</th><th>Email</th><th>Statut</th></tr></thead><tbody>{pending_rows or '<tr><td colspan="3" class="muted">Aucune invitation.</td></tr>'}</tbody></table></div></div>
    <div class="card"><h3>Entreprises actives</h3><div class="table-responsive"><table><thead><tr><th>Entreprise</th><th>Email</th><th>Plan</th><th>Statut</th></tr></thead><tbody>{active_rows or '<tr><td colspan="4" class="muted">Aucune entreprise.</td></tr>'}</tbody></table></div></div>
    """
    return page(body,title="Admin Panel")

@app.route("/admin/create-invitation", methods=["POST"])
def admin_create_invitation():
    if not session.get("is_admin"):
        return redirect(url_for("admin_panel"))

    company = normalize_text(request.form.get("company_name"), 150)
    email = normalize_text(request.form.get("email"), 160).lower()
    country = normalize_text(request.form.get("country"), 100)

    if not company or not email or "@" not in email:
        flash("Nom d'entreprise et email professionnel valides obligatoires.", "danger")
        return redirect(url_for("admin_panel"))

    try:
        user = User.query.filter_by(email=email).first()

        if user and user.active:
            flash("Un compte actif existe déjà avec cet email.", "danger")
            return redirect(url_for("admin_panel"))

        if not user:
            user = User(
                company_name=company,
                email=email,
                password_hash=generate_password_hash(secrets.token_urlsafe(32)),
                role="dispatcher",
                country=country,
                active=False,
            )
            db.session.add(user)
            db.session.flush()
        else:
            user.company_name = company
            user.country = country
            user.active = False

        AccountInvitation.query.filter_by(
            user_id=user.id,
            used_at=None,
        ).update(
            {"used_at": utcnow()},
            synchronize_session=False,
        )

        token = None
        for _ in range(5):
            candidate = "GRI-" + secrets.token_urlsafe(36)
            if not AccountInvitation.query.filter_by(token=candidate).first():
                token = candidate
                break

        if not token:
            raise RuntimeError("Impossible de générer une clé d'activation unique.")

        invitation = AccountInvitation(
            token=token,
            user_id=user.id,
            expires_at=utcnow() + timedelta(days=ACTIVATION_KEY_DAYS),
        )
        db.session.add(invitation)
        db.session.flush()

        db.session.add(AuditLog(
            action="ACCOUNT_INVITATION_CREATED",
            details=f"user={email}; invitation_id={invitation.id}"
        ))
        db.session.commit()

    except Exception as exc:
        db.session.rollback()
        app.logger.exception("Erreur Admin lors de la génération de clé")
        flash(
            "La génération a échoué. Détail serveur : " + str(exc),
            "danger"
        )
        return redirect(url_for("admin_panel"))

    activation_url = url_for("activate_account", _external=True)
    email_sent = False
    try:
        send_email(
            user.email,
            "GlobalRoute AI — Activation de votre compte",
            f"Bonjour {user.company_name},\n\nVotre compte GlobalRoute AI a été préparé.\n\nClé d'activation : {invitation.token}\nLien : {activation_url}\n\nCette clé est valable {ACTIVATION_KEY_DAYS} jours et ne peut être utilisée qu'une fois. Vous créerez votre mot de passe lors de l'activation.\n"
        )
        email_sent = True
    except Exception:
        app.logger.exception("SMTP activation email failed")

    body = f"""
    <div class="card" style="max-width:650px;margin:0 auto">
      <h2>✅ Clé d'activation générée</h2>
      <p><strong>Entreprise :</strong> {user.company_name}</p>
      <p><strong>Email :</strong> {user.email}</p>
      <label>Clé à envoyer au client</label>
      <div class="mono" style="background:#0f172a;color:white;padding:16px;border-radius:8px;font-size:16px;text-align:center">
        {invitation.token}
      </div>
      <label>Lien d'activation</label>
      <div class="mono" style="background:#f1f5f9;padding:12px;border-radius:8px">
        {activation_url}
      </div>
      <p class="muted">Valable {ACTIVATION_KEY_DAYS} jours et utilisable une seule fois. Le client crée son mot de passe.</p>
      <div class="alert alert-{'success' if email_sent else 'danger'}">{'E-mail d’activation envoyé automatiquement.' if email_sent else 'E-mail non envoyé : configurez SMTP dans Render. La clé reste disponible pour un envoi manuel.'}</div>
      <a href="{url_for('admin_panel')}" class="btn">Retour Admin</a>
    </div>
    """
    return page(body, title="Clé d'activation")


@app.route("/admin-logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("index"))


# ============================================================
# B2B API
# ============================================================

def authenticate_api_user():
    """Authentifie exclusivement les appels B2B par X-API-KEY."""
    key_val = request.headers.get(
        "X-API-KEY",
        ""
    ).strip()

    if not key_val:
        return None

    key = ApiKey.query.filter_by(
        key_string=key_val,
        revoked=False
    ).first()

    if not key:
        return None

    if key.expires_at and key.expires_at < utcnow():
        return None

    user = User.query.get(key.user_id)

    if not user or not user.active:
        return None

    return user


@app.route("/api/v1/route", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def api_v1_route():
    if request.method == "GET":
        return jsonify({
            "service": APP_NAME,
            "engine": "OSRM + OR-Tools",
            "routing": "real road network",
            "usage": (
                "POST JSON {'points': [...]}"
                " with X-API-KEY"
            ),
        })

    user = authenticate_api_user()

    if not user:
        return jsonify({
            "error": "invalid_api_key"
        }), 401

    if (
        user.subscription_expires_at
        and user.subscription_expires_at < utcnow()
    ):
        return jsonify({
            "error": "subscription_expired"
        }), 402

    if user.tours_used >= user.tour_limit:
        return jsonify({
            "error": "quota_exceeded"
        }), 402

    payload = request.get_json(
        silent=True
    ) or {}

    points = payload.get(
        "points",
        []
    )

    try:
        stops = validate_stops(
            points,
            max_points=min(
                MAX_ROUTE_POINTS,
                PLANS.get(
                    user.plan,
                    PLANS["standard"]
                ).get(
                    "point_limit",
                    MAX_ROUTE_POINTS
                )
            )
        )

        optimized, geometry, distance, engine = (
            optimize_stops_order(stops)
        )

    except ValueError as exc:
        return jsonify({
            "error": "invalid_data",
            "message": str(exc),
        }), 400

    except Exception as exc:
        return jsonify({
            "error": "routing_failed",
            "message": str(exc),
        }), 503

    user.tours_used += 1

    db.session.add(
        AuditLog(
            action="API_ROUTE_OPTIMIZED",
            details=(
                f"user={user.email}; "
                f"points={len(optimized)}; "
                f"engine={engine}"
            )
        )
    )

    safe_db_commit("API route audit commit", retries=1)

    return jsonify({
        "success": True,
        "engine": engine,
        "routing": "real_road_network",
        "points": len(optimized),
        "distance_m": round(
            distance,
            2
        ),
        "distance_km": round(
            distance / 1000,
            3
        ),
        "optimized_points": optimized,
        "road_geometry": geometry,
        "tours_used": user.tours_used,
    })


# ============================================================
# HEALTH
# ============================================================

@app.route("/health/routing")
def health_routing():
    return jsonify({
        "status": "ok",
        "routing_url": ROUTING_URL,
        "profile": OSRM_PROFILE,
        "ortools_installed": HAS_ORTOOLS,
        "max_route_points": MAX_ROUTE_POINTS,
        "matrix_max_points": int(os.getenv("OR_TOOLS_MATRIX_MAX_POINTS", "250")),
        "trip_limit": OSRM_TRIP_LIMIT,
        "straight_line_fallback": False,
        "real_road_routing": True,
        "exact_small_tsp": True,
        "activation_key_days": ACTIVATION_KEY_DAYS,
        "password_reset_email": bool(SMTP_USERNAME and SMTP_PASSWORD),
    })


@app.route("/health")
def health():
    db_status = "unknown"
    try:
        from sqlalchemy import text
        db.session.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as exc:
        db.session.rollback()
        db_status = "error"
        app.logger.warning("Health database check failed: %s", exc)

    return jsonify({
        "status": "healthy" if db_status == "ok" else "degraded",
        "service": APP_NAME,
        "routing_engine": "OSRM",
        "optimization_engine": (
            "OSRM + OR-Tools"
            if HAS_ORTOOLS
            else "OSRM Trip"
        ),
        "real_road_routing": True,
        "straight_line_fallback": False,
        "max_route_points": MAX_ROUTE_POINTS,
        "database": (
            "postgresql"
            if "postgresql" in database_url
            else "sqlite"
        ),
        "database_status": db_status,
        "db_pool_pre_ping": True,
        "db_pool_recycle_seconds": 240,
    })


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    port = int(
        os.getenv("PORT", "5000")
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
