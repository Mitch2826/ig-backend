"""
app/__init__.py
The Flask application factory. create_app() builds and returns a fully
configured Flask app — this pattern (factory instead of a global `app`
object) is what lets us run different configs for dev/testing/production
and avoids circular imports between blueprints and extensions.

Call chain:
    run.py calls create_app()
    -> loads config
    -> initializes extensions (db, jwt, cors, etc.)
    -> registers blueprints
    -> returns app
"""

import os
from flask import Flask, jsonify

from config import config_by_name
from app.extensions import db, migrate, jwt, cors, mail, limiter, scheduler, init_redis


def create_app(config_name=None):
    app = Flask(__name__)

    # ── Config ───────────────────────────────────────────────────────────────
    config_name = config_name or os.environ.get("FLASK_ENV", "development")
    app.config.from_object(config_by_name[config_name])

    # ── Extensions ───────────────────────────────────────────────────────────
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    mail.init_app(app)

    # Import every model so SQLAlchemy's metadata is fully populated before
    # Alembic (flask db migrate) inspects it. Without this import, `flask db
    # migrate` sees an empty metadata and generates an empty migration even
    # though all our model files exist — they're just never loaded into
    # memory until something imports them.
    with app.app_context():
        from app import models as _models  # noqa: F401

    # CORS — only allow the frontend domain, with credentials for cookies/auth headers
    cors.init_app(app, resources={r"/api/*": {"origins": app.config["FRONTEND_URL"]}})

    # Rate limiter uses Redis as storage so limits persist across restarts.
    # storage_uri must be set on app.config BEFORE init_app() is called,
    # otherwise Limiter falls back to in-memory storage silently.
    app.config["RATELIMIT_STORAGE_URI"] = app.config["REDIS_URL"]
    limiter.init_app(app)

    # Standalone Redis client for caching + stock reservation locks.
    # Falls back to None (cache/lock skipped, DB used directly) if unreachable —
    # lets the app run locally even if Redis is briefly unavailable.
    init_redis(app.config["REDIS_URL"])

    # ── Background job scheduler (APScheduler) ───────────────────────────────
    # Guard against starting twice: Flask's debug reloader spawns a parent
    # process and a child worker process. WERKZEUG_RUN_MAIN is only set to
    # "true" inside the actual worker — so in dev we only start the scheduler
    # there. In production (gunicorn, no reloader) this env var is never set,
    # so the condition is simply skipped and the scheduler starts normally.
    is_dev_reloader_parent = (
        app.config["DEBUG"] and os.environ.get("WERKZEUG_RUN_MAIN") != "true"
    )
    if not scheduler.running and not is_dev_reloader_parent:
        scheduler.start()

    # ── Sentry error tracking (optional — only if SENTRY_DSN is set) ─────────
    if app.config.get("SENTRY_DSN"):
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration
        sentry_sdk.init(
            dsn=app.config["SENTRY_DSN"],
            integrations=[FlaskIntegration()],
            traces_sample_rate=0.1,
        )

    # ── Blueprints ───────────────────────────────────────────────────────────
    from app.blueprints.auth.routes import blp as auth_blp
    from app.blueprints.products.routes import blp as products_blp
    from app.blueprints.categories.routes import blp as categories_blp
    from app.blueprints.orders.routes import blp as orders_blp
    from app.blueprints.payments.routes import blp as payments_blp
    from app.blueprints.admin.routes import blp as admin_blp
    from app.blueprints.delivery.routes import blp as delivery_blp
    from app.blueprints.users.routes import blp as users_blp

    # flask-smorest needs an Api instance to register blueprints onto
    from flask_smorest import Api
    api = Api(app)

    api.register_blueprint(auth_blp)
    api.register_blueprint(products_blp)
    api.register_blueprint(categories_blp)
    api.register_blueprint(orders_blp)
    api.register_blueprint(payments_blp)
    api.register_blueprint(admin_blp)
    api.register_blueprint(delivery_blp)
    api.register_blueprint(users_blp)

    # ── Health check — useful for Render/uptime monitoring ───────────────────
    @app.route("/health")
    def health():
        return jsonify({"status": "ok", "service": "I&G API"})

    return app