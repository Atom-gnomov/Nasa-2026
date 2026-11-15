"""Lunar Site Explorer — вебзастосунок для порівняння місць і дат посадки на Місяці."""

import hashlib
from pathlib import Path

from flask import Flask

from app.config import Config


def create_app(config_object: type[Config] = Config) -> Flask:
    """Фабрика застосунку Flask."""
    app = Flask(__name__)
    app.config.from_object(config_object)

    from app.routes.api import bp as api_bp
    from app.routes.pages import bp as pages_bp

    app.register_blueprint(pages_bp)

    # Хеш вмісту в URL статичних файлів (?v=…): браузер бере їх із кешу, а після зміни файлу завантажує заново.
    hashes: dict[tuple[str, int, int], str] = {}

    @app.url_defaults
    def add_static_hash(endpoint, values):
        # JS-модулі без хешу: їх імпортують одне в одного за звичайним URL, а різні URL створили б два екземпляри модуля
        if endpoint != "static" or "v" in values or not values.get("filename") or values["filename"].endswith(".js"):
            return
        path = Path(app.static_folder or "") / values["filename"]
        try:
            st = path.stat()
        except OSError:
            return
        key = (str(path), st.st_mtime_ns, st.st_size)
        if key not in hashes:
            hashes[key] = hashlib.md5(path.read_bytes(), usedforsecurity=False).hexdigest()[:10]
        values["v"] = hashes[key]
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
