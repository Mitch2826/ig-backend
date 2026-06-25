from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_mail import Mail
from apscheduler.schedulers.background import BackgroundScheduler
import redis as redis_lib

db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()
cors = CORS()
mail = Mail()

# Rate limiter — storage backend (Redis) configured at init time in __init__.py
limiter = Limiter(key_func=get_remote_address)

# Background job scheduler — replaces Celery for our current scale (APScheduler
# runs in-process, no separate worker process needed)
scheduler = BackgroundScheduler()

# Standalone Redis client — used directly for settings cache and stock
# reservation locks (separate from the Limiter's internal Redis usage).
# Stays None if Redis is unreachable so the app can still run locally
# without Redis — caching/locking just gets skipped and falls back to the DB.
redis_client = None


def init_redis(redis_url: str):
    global redis_client
    try:
        client = redis_lib.from_url(redis_url, decode_responses=True, socket_connect_timeout=2)
        client.ping()
        redis_client = client
    except Exception:
        redis_client = None
    return redis_client