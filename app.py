import os

from flask import Flask, redirect, render_template, request, session, url_for

from models import Course, Lecturer, Student, db


MAX_CREDIT_HOURS = 16


def current_user_type() -> str | None:
    user_type = session.get("user_type")
    user_id = session.get("user_id")

    if user_id and user_type in {"student", "lecturer"}:
        return user_type

    return None


def current_student() -> Student | None:
    if current_user_type() != "student":
        return None

    return db.session.get(Student, session.get("user_id"))


def pending_enrollment() -> dict[str, list[int]]:
    pending = session.get("pending_enrollment")

    if not isinstance(pending, dict):
        return {"add": [], "drop": []}

    return {
        "add": [int(course_id) for course_id in pending.get("add", [])],
        "drop": [int(course_id) for course_id in pending.get("drop", [])],
    }


def selected_course_ids(student: Student) -> set[int]:
    current_ids = {course.id for course in student.courses}
    pending = pending_enrollment()

    return (current_ids - set(pending["drop"])) | set(pending["add"])


def set_pending_enrollment(student: Student, selected_ids: set[int]) -> None:
    current_ids = {course.id for course in student.courses}
    session["pending_enrollment"] = {
        "add": sorted(selected_ids - current_ids),
        "drop": sorted(current_ids - selected_ids),
    }
    session.modified = True


def validate_enrollment(student: Student, courses: list[Course], selected_ids: set[int]) -> list[str]:
    errors = []
    selected_courses = [course for course in courses if course.id in selected_ids]
    total_credits = sum(course.credits or 0 for course in selected_courses)
    passed_ids = {course.id for course in student.passed_courses}

    if total_credits > MAX_CREDIT_HOURS:
        errors.append(f"You can take up to {MAX_CREDIT_HOURS} credit hours. Current selection is {total_credits}.")

    for course in selected_courses:
        missing_prerequisites = [
            prerequisite.code
            for prerequisite in course.prerequisites
            if prerequisite.id not in passed_ids
        ]
        if missing_prerequisites:
            errors.append(f"{course.code} requires passing these courses before this semester: {', '.join(missing_prerequisites)}.")

    return errors


def enrollment_context(student: Student, errors: list[str] | None = None, message: str | None = None) -> dict:
    courses = Course.query.order_by(Course.code).all()
    current_ids = {course.id for course in student.courses}
    passed_ids = {course.id for course in student.passed_courses}
    selected_ids = selected_course_ids(student)
    pending = pending_enrollment()
    selected_courses = [course for course in courses if course.id in selected_ids]

    return {
        "courses": courses,
        "selected_ids": selected_ids,
        "current_ids": current_ids,
        "passed_ids": passed_ids,
        "pending_add_ids": set(pending["add"]),
        "pending_drop_ids": set(pending["drop"]),
        "total_credits": sum(course.credits or 0 for course in selected_courses),
        "max_credit_hours": MAX_CREDIT_HOURS,
        "errors": errors or [],
        "message": message,
    }


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

        session.pop("pending_enrollment", None)
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

    @app.route("/courses/enroll", methods=["GET", "POST"])
    def enroll_courses():
        student = current_student()

        if student is None:
            return redirect(url_for("login"))

        courses = Course.query.order_by(Course.code).all()

        if request.method == "GET":
            return render_template("enroll_courses.html", **enrollment_context(student))

        selected_ids = {int(course_id) for course_id in request.form.getlist("course_ids")}
        valid_course_ids = {course.id for course in courses}
        selected_ids &= valid_course_ids
        set_pending_enrollment(student, selected_ids)

        errors = validate_enrollment(student, courses, selected_ids)
        action = request.form.get("action")

        if errors:
            return render_template("enroll_courses.html", **enrollment_context(student, errors=errors)), 400

        if action == "save":
            return render_template("confirm_enrollment.html", **enrollment_context(student))

        return render_template(
            "enroll_courses.html",
            **enrollment_context(student, message="Enrollment changes are saved in your session only."),
        )

    @app.route("/courses/enroll/confirm", methods=["POST"])
    def confirm_enrollment():
        student = current_student()

        if student is None:
            return redirect(url_for("login"))

        courses = Course.query.order_by(Course.code).all()
        selected_ids = selected_course_ids(student)
        errors = validate_enrollment(student, courses, selected_ids)

        if errors:
            return render_template("enroll_courses.html", **enrollment_context(student, errors=errors)), 400

        student.courses = [course for course in courses if course.id in selected_ids]
        session.pop("pending_enrollment", None)
        db.session.commit()

        return redirect(url_for("enroll_courses"))

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
