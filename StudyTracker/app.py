import os
from flask import Flask
from extensions import db, login_manager, bcrypt


def create_app() -> Flask:
    app = Flask(__name__)

    _configure_app(app)

    db.init_app(app)
    login_manager.init_app(app)
    bcrypt.init_app(app)

    login_manager.login_view = "main.login"
    login_manager.login_message_category = "info"
    login_manager.login_message = "Пожалуйста, войдите, чтобы получить доступ к этой странице."

    @app.template_filter('datetime_ru')
    def datetime_ru_filter(value, format='%d.%m.%Y %H:%M'):
        return value.strftime(format) if value else ""

    from routes import main as main_blueprint
    app.register_blueprint(main_blueprint)

    import models

    with app.app_context():
        db.create_all()
        _ensure_upload_dir(app)

    return app


def _configure_app(app: Flask) -> None:
    app.config["SECRET_KEY"] = os.environ.get(
        "SECRET_KEY", "dev-secret-key-CHANGE-IN-PRODUCTION-42xQ!"
    )
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
        "DATABASE_URL", "sqlite:///study_tracker.db"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
    app.config["UPLOAD_FOLDER"] = os.path.join(app.root_path, "static", "uploads")
    app.config["ALLOWED_EXTENSIONS"] = {"png", "jpg", "jpeg", "gif", "pdf"}


def _ensure_upload_dir(app: Flask) -> None:
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)


if __name__ == "__main__":
    create_app().run(debug=True)