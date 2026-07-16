import os

from flask import Flask, redirect, render_template, request, session, url_for

from models import Lecturer, Student, db


def current_user_type() -> str | None:
    user_type = session.get("user_type")
    user_id = session.get("user_id")

    if user_id and user_type in {"student", "lecturer"}:
        return user_type

    return None


def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key")
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///course_collaboration.sqlite"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    if config:
        app.config.update(config)

    db.init_app(app)

    @app.route("/")
    def index():
        if current_user_type():
            return redirect(url_for("dashboard"))

        return redirect(url_for("login"))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "GET":
            return render_template("login.html")

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        student = Student.query.filter_by(email=email).first()
        lecturer = Lecturer.query.filter_by(email=email).first()

        user = None
        user_type = None

        if student and student.check_password(password):
            user = student
            user_type = "student"
        elif lecturer and lecturer.check_password(password):
            user = lecturer
            user_type = "lecturer"

        if user is None:
            return render_template("login.html", error="Invalid email or password."), 401

        session["user_id"] = user.id
        session["user_type"] = user_type
        return redirect(url_for("dashboard"))

    @app.route("/dashboard")
    def dashboard():
        user_type = current_user_type()

        if user_type is None:
            return redirect(url_for("login"))

        if user_type == "student":
            return render_template("student_dashboard.html")

        return render_template("lecturer_dashboard.html")

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    return app


def main() -> None:
    app = create_app()
    with app.app_context():
        db.create_all()

    print("Flask app initialized and database tables created.")


if __name__ == "__main__":
    main()
