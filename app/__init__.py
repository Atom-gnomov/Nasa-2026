"""Lunar Site Explorer — вебзастосунок для порівняння місць і дат посадки на Місяці."""

from flask import Flask

from app.config import Config


def create_app(config_object: type[Config] = Config) -> Flask:
    """Фабрика застосунку Flask."""
    app = Flask(__name__)
    app.config.from_object(config_object)

    from app.routes.api import bp as api_bp
    from app.routes.pages import bp as pages_bp

    app.register_blueprint(pages_bp)
    app.register_blueprint(api_bp, url_prefix="/api")
    return app
