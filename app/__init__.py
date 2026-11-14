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

    @app.errorhandler(404)
    @app.errorhandler(405)
    def api_json_errors(err):
        """Невідомі шляхи /api/* — теж JSON за контрактом помилок."""
        from flask import jsonify, request

        if request.path.startswith("/api/"):
            code = "not_found" if err.code == 404 else "bad_request"
            return jsonify(error=code, detail=err.description), err.code
        return err

    # Автопідготовка даних NASA у фоні (вимикається LSE_AUTO_PREPARE=0; у тестах вимкнена)
    from app.services import bootstrap

    bootstrap.autostart(app)

    return app
