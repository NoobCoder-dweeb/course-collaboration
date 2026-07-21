import os
from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import Flask, abort, flash, redirect, render_template, request, send_from_directory, session, url_for
from sqlalchemy import func, inspect, or_, text
from werkzeug.utils import secure_filename

from models import (
    Admin, Announcement, Assignment, AssignmentSubmission, Course, CourseMaterial,
    Lecturer, MaterialComment, MaterialInteraction, Student, db,
)


ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "txt", "png", "jpg", "jpeg", "zip"}


def current_user_type() -> str | None:
    user_type = session.get("user_type")
    user_id = session.get("user_id")
    return user_type if user_id and user_type in {"student", "lecturer", "admin"} else None


def current_user():
    user_type = current_user_type()
    model = {"student": Student, "lecturer": Lecturer, "admin": Admin}.get(user_type)
    return db.session.get(model, session.get("user_id")) if model else None


def current_student() -> Student | None:
    user = current_user()
    return user if current_user_type() == "student" else None


def current_lecturer() -> Lecturer | None:
    user = current_user()
    return user if current_user_type() == "lecturer" else None


def login_required(role: str | None = None):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user_type = current_user_type()
            if user_type is None:
                flash("Please log in to continue.", "error")
                return redirect(url_for("login"))
            if role and user_type != role:
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator


def approved_courses_query():
    return Course.query.filter_by(status="approved")


def pending_enrollment() -> dict[str, list[int]]:
    pending = session.get("pending_enrollment")
    if not isinstance(pending, dict):
        return {"add": []}
    return {"add": [int(course_id) for course_id in pending.get("add", [])]}


def selected_course_ids(student: Student) -> set[int]:
    current_ids = {course.id for course in student.courses}
    return current_ids | set(pending_enrollment()["add"])


def set_pending_enrollment(student: Student, selected_ids: set[int]) -> None:
    current_ids = {course.id for course in student.courses}
    session["pending_enrollment"] = {"add": sorted(selected_ids - current_ids)}
    session.modified = True


def enrollment_context(student: Student, courses: list[Course], errors: list[str] | None = None) -> dict:
    current_ids = {course.id for course in student.courses}
    selected_ids = selected_course_ids(student)
    pending_add_ids = set(pending_enrollment()["add"])

    return {
        "courses": courses,
        "selected_ids": selected_ids,
        "current_ids": current_ids,
        "pending_add_ids": pending_add_ids,
        "errors": errors or [],
    }


def lecturer_course(course_id: int) -> Course:
    lecturer = current_lecturer()
    course = db.session.get(Course, course_id) or abort(404)
    if not lecturer or course.lecturer_id != lecturer.id:
        abort(403)
    return course


def enrolled_course(course_id: int) -> Course:
    student = current_student()
    course = db.session.get(Course, course_id) or abort(404)
    if not student or course not in student.courses:
        abort(403)
    return course


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def save_upload(file, subfolder: str) -> str | None:
    if not file or not file.filename:
        return None
    if not allowed_file(file.filename):
        return ""
    filename = f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{secure_filename(file.filename)}"
    upload_dir = Path("uploads") / subfolder
    upload_dir.mkdir(parents=True, exist_ok=True)
    file.save(upload_dir / filename)
    return str(upload_dir / filename).replace("\\", "/")


def parse_deadline(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M")
    except ValueError:
        return None


def record_material_interaction(material: CourseMaterial, student: Student) -> None:
    interaction = MaterialInteraction.query.filter_by(material_id=material.id, student_id=student.id).first()
    if interaction:
        interaction.last_interacted_at = datetime.now()
        interaction.interaction_count += 1
    else:
        db.session.add(MaterialInteraction(material=material, student=student))


def material_form_fields(material: CourseMaterial) -> None:
    week_value = request.form.get("week_number", "").strip()
    material.week_number = int(week_value) if week_value.isdigit() and 1 <= int(week_value) <= 52 else None
    material.topic = request.form.get("topic", "").strip() or None
    material.discussion_enabled = request.form.get("discussion_enabled") == "1"


def ensure_schema_upgrades() -> None:
    """Add columns introduced after the initial SQLite prototype without erasing data."""
    inspector = inspect(db.engine)
    upgrades = {
        "student": {
            "skills": "ALTER TABLE student ADD COLUMN skills TEXT",
            "collaboration_mode": "ALTER TABLE student ADD COLUMN collaboration_mode VARCHAR(32)",
        },
        "course_material": {
            "week_number": "ALTER TABLE course_material ADD COLUMN week_number INTEGER",
            "topic": "ALTER TABLE course_material ADD COLUMN topic VARCHAR(128)",
            "discussion_enabled": "ALTER TABLE course_material ADD COLUMN discussion_enabled BOOLEAN NOT NULL DEFAULT 0",
        },
        "assignment_submission": {
            "grade": "ALTER TABLE assignment_submission ADD COLUMN grade FLOAT",
            "feedback": "ALTER TABLE assignment_submission ADD COLUMN feedback TEXT",
            "graded_at": "ALTER TABLE assignment_submission ADD COLUMN graded_at DATETIME",
            "graded_by_lecturer_id": "ALTER TABLE assignment_submission ADD COLUMN graded_by_lecturer_id INTEGER REFERENCES lecturer(id)",
        },
    }
    for table_name, columns in upgrades.items():
        existing = {column["name"] for column in inspector.get_columns(table_name)}
        for column_name, statement in columns.items():
            if column_name not in existing:
                db.session.execute(text(statement))
    db.session.commit()


def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key")
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///course_collaboration.sqlite"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["UPLOAD_FOLDER"] = os.path.abspath("uploads")
    if config:
        app.config.update(config)

    db.init_app(app)

    @app.context_processor
    def inject_user():
        return {"current_user": current_user(), "current_user_type": current_user_type()}

    @app.route("/")
    def index():
        return redirect(url_for("dashboard" if current_user_type() else "login"))

    @app.route("/signup", methods=["GET", "POST"])
    def signup():
        if request.method == "GET":
            return render_template("signup.html")

        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("password_confirm", "")

        if not name or not email or not password:
            return render_template("signup.html", error="Name, email, and password are required."), 400
        if password != confirm:
            return render_template("signup.html", error="Password confirmation does not match."), 400
        if Student.query.filter_by(email=email).first() or Lecturer.query.filter_by(email=email).first() or Admin.query.filter_by(email=email).first():
            return render_template("signup.html", error="That email is already registered."), 400

        student = Student(name=name, email=email, is_member=False, enrollment_year=datetime.now().year)
        student.set_password(password)
        db.session.add(student)
        db.session.commit()
        flash("Student account created. Please log in.", "success")
        return redirect(url_for("login"))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "GET":
            return render_template("login.html")

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        candidates = [
            ("student", Student.query.filter_by(email=email).first()),
            ("lecturer", Lecturer.query.filter_by(email=email).first()),
            ("admin", Admin.query.filter_by(email=email).first()),
        ]

        for user_type, user in candidates:
            if user and user.check_password(password):
                session.clear()
                session["user_id"] = user.id
                session["user_type"] = user_type
                return redirect(url_for("dashboard"))

        return render_template("login.html", error="Invalid email or password."), 401

    @app.route("/dashboard")
    @login_required()
    def dashboard():
        user_type = current_user_type()
        if user_type == "student":
            student = current_student()
            course_ids = [course.id for course in student.courses]
            announcements = Announcement.query.filter(Announcement.course_id.in_(course_ids)).order_by(Announcement.posted_at.desc()).limit(5).all() if course_ids else []
            assignments = Assignment.query.filter(Assignment.course_id.in_(course_ids), Assignment.deadline >= datetime.now()).order_by(Assignment.deadline).limit(5).all() if course_ids else []
            return render_template("student_dashboard.html", student=student, announcements=announcements, assignments=assignments)
        if user_type == "lecturer":
            lecturer = current_lecturer()
            return render_template("lecturer_dashboard.html", lecturer=lecturer, courses=lecturer.courses)
        return redirect(url_for("admin_dashboard"))

    @app.route("/student/profile", methods=["GET", "POST"])
    @login_required("student")
    def student_profile():
        student = current_student()
        if request.method == "POST":
            student.skills = request.form.get("skills", "").strip() or None
            mode = request.form.get("collaboration_mode", "").strip()
            allowed_modes = {"Online", "In person", "Hybrid", "Flexible"}
            student.collaboration_mode = mode if mode in allowed_modes else None
            db.session.commit()
            flash("Your collaboration profile was updated.", "success")
            return redirect(url_for("student_profile"))
        return render_template("student_profile.html", student=student)

    @app.route("/courses")
    @login_required()
    def courses():
        if current_user_type() == "student":
            return render_template("student_courses.html", courses=current_student().courses)
        if current_user_type() == "lecturer":
            return render_template("lecturer_dashboard.html", lecturer=current_lecturer(), courses=current_lecturer().courses)
        return redirect(url_for("admin_dashboard"))

    @app.route("/courses/catalogue")
    @login_required("student")
    def course_catalogue():
        student = current_student()
        query = request.args.get("q", "").strip()
        courses_query = approved_courses_query()
        if query:
            like = f"%{query}%"
            courses_query = courses_query.filter(or_(Course.code.ilike(like), Course.title.ilike(like)))
        courses = courses_query.order_by(Course.code).all()
        return render_template("course_catalogue.html", q=query, **enrollment_context(student, courses))

    @app.route("/courses/enroll", methods=["GET", "POST"])
    @login_required("student")
    def enroll_courses():
        student = current_student()
        courses = approved_courses_query().order_by(Course.code).all()

        if request.method == "GET":
            return render_template("enroll_courses.html", **enrollment_context(student, courses))

        selected_ids = {int(course_id) for course_id in request.form.getlist("course_ids")}
        current_ids = {course.id for course in student.courses}
        valid_ids = {course.id for course in courses}
        selected_ids = (selected_ids & valid_ids) | current_ids
        set_pending_enrollment(student, selected_ids)
        return render_template("confirm_enrollment.html", **enrollment_context(student, courses))

    @app.route("/courses/enroll/confirm", methods=["POST"])
    @login_required("student")
    def confirm_enrollment():
        student = current_student()
        courses = approved_courses_query().order_by(Course.code).all()
        selected_ids = selected_course_ids(student)

        current_ids = {course.id for course in student.courses}
        student.courses = list({course.id: course for course in student.courses + [course for course in courses if course.id in selected_ids - current_ids]}.values())
        session.pop("pending_enrollment", None)
        db.session.commit()
        flash("Enrollment confirmed.", "success")
        return redirect(url_for("courses"))

    @app.route("/courses/<int:course_id>")
    @login_required("student")
    def course_detail(course_id):
        course = enrolled_course(course_id)
        materials = CourseMaterial.query.filter_by(course_id=course.id).order_by(CourseMaterial.week_number.is_(None), CourseMaterial.week_number, CourseMaterial.topic, CourseMaterial.uploaded_at).all()
        assignments = Assignment.query.filter_by(course_id=course.id).order_by(Assignment.deadline).all()
        announcements = Announcement.query.filter_by(course_id=course.id).order_by(Announcement.posted_at.desc()).all()
        return render_template("course_detail.html", course=course, materials=materials, assignments=assignments, announcements=announcements)

    @app.route("/student/courses/<int:course_id>/materials")
    @login_required("student")
    def student_course_materials(course_id):
        return redirect(url_for("course_detail", course_id=course_id))

    @app.route("/student/courses/<int:course_id>/assignments")
    @login_required("student")
    def student_course_assignments(course_id):
        return redirect(url_for("course_detail", course_id=course_id))

    @app.route("/student/assignments/<int:assignment_id>/submit", methods=["GET", "POST"])
    @login_required("student")
    def submit_assignment(assignment_id):
        student = current_student()
        assignment = db.session.get(Assignment, assignment_id) or abort(404)
        if assignment.course not in student.courses:
            abort(403)
        submissions = AssignmentSubmission.query.filter_by(assignment_id=assignment.id, student_id=student.id).order_by(AssignmentSubmission.attempt_number).all()
        after_deadline = datetime.now() > assignment.deadline
        remaining_attempts = None if student.is_member else max(0, 2 - len(submissions))

        if request.method == "POST":
            if after_deadline:
                flash("This assignment deadline has passed.", "error")
                return redirect(url_for("submit_assignment", assignment_id=assignment.id))
            if not student.is_member and len(submissions) >= 2:
                flash("Non-member students can submit at most two attempts for each assignment.", "error")
                return redirect(url_for("submit_assignment", assignment_id=assignment.id))
            saved_path = save_upload(request.files.get("submission_file"), "submissions")
            if saved_path is None:
                flash("Please choose a file to submit.", "error")
                return redirect(url_for("submit_assignment", assignment_id=assignment.id))
            if saved_path == "":
                flash("Invalid file type.", "error")
                return redirect(url_for("submit_assignment", assignment_id=assignment.id))
            submission = AssignmentSubmission(
                assignment=assignment,
                student=student,
                file_path=saved_path,
                attempt_number=len(submissions) + 1,
                status="submitted",
            )
            db.session.add(submission)
            db.session.commit()
            flash("Submission saved.", "success")
            return redirect(url_for("submit_assignment", assignment_id=assignment.id))

        return render_template("assignment_submit.html", assignment=assignment, submissions=submissions, after_deadline=after_deadline, remaining_attempts=remaining_attempts)

    @app.route("/student/assignments/<int:assignment_id>/submissions")
    @login_required("student")
    def student_submissions(assignment_id):
        return redirect(url_for("submit_assignment", assignment_id=assignment_id))

    @app.route("/lecturer/courses/<int:course_id>")
    @login_required("lecturer")
    def lecturer_course_detail(course_id):
        course = lecturer_course(course_id)
        return render_template("lecturer_course_detail.html", course=course)

    @app.route("/lecturer/courses/<int:course_id>/materials", methods=["GET", "POST"])
    @login_required("lecturer")
    def lecturer_materials(course_id):
        course = lecturer_course(course_id)
        if request.method == "POST":
            title = request.form.get("title", "").strip()
            if not title:
                flash("Material title is required.", "error")
            else:
                saved_path = save_upload(request.files.get("material_file"), "materials")
                if saved_path == "":
                    flash("Invalid file type.", "error")
                else:
                    material = CourseMaterial(
                        course=course,
                        title=title,
                        description=request.form.get("description", "").strip(),
                        material_type=request.form.get("material_type", "").strip(),
                        file_path=saved_path,
                        uploaded_by=current_lecturer(),
                    )
                    material_form_fields(material)
                    db.session.add(material)
                    db.session.commit()
                    flash("Material saved.", "success")
                    return redirect(url_for("lecturer_materials", course_id=course.id))
        materials = CourseMaterial.query.filter_by(course_id=course.id).order_by(CourseMaterial.week_number.is_(None), CourseMaterial.week_number, CourseMaterial.topic, CourseMaterial.uploaded_at).all()
        return render_template("lecturer_materials.html", course=course, materials=materials)

    @app.route("/lecturer/materials/<int:material_id>/edit", methods=["GET", "POST"])
    @login_required("lecturer")
    def edit_material(material_id):
        material = db.session.get(CourseMaterial, material_id) or abort(404)
        lecturer_course(material.course_id)
        if request.method == "POST":
            title = request.form.get("title", "").strip()
            if not title:
                flash("Material title is required.", "error")
            else:
                material.title = title
                material.description = request.form.get("description", "").strip()
                material.material_type = request.form.get("material_type", "").strip()
                material_form_fields(material)
                saved_path = save_upload(request.files.get("material_file"), "materials")
                if saved_path == "":
                    flash("Invalid file type.", "error")
                else:
                    if saved_path:
                        material.file_path = saved_path
                    db.session.commit()
                    flash("Material updated.", "success")
                    return redirect(url_for("lecturer_materials", course_id=material.course_id))
        return render_template("material_form.html", material=material, course=material.course)

    @app.route("/lecturer/materials/<int:material_id>/delete", methods=["POST"])
    @login_required("lecturer")
    def delete_material(material_id):
        material = db.session.get(CourseMaterial, material_id) or abort(404)
        course_id = material.course_id
        lecturer_course(course_id)
        db.session.delete(material)
        db.session.commit()
        flash("Material deleted.", "success")
        return redirect(url_for("lecturer_materials", course_id=course_id))

    @app.route("/lecturer/courses/<int:course_id>/assignments", methods=["GET", "POST"])
    @login_required("lecturer")
    def lecturer_assignments(course_id):
        course = lecturer_course(course_id)
        if request.method == "POST":
            title = request.form.get("title", "").strip()
            requirements = request.form.get("requirements", "").strip()
            deadline = parse_deadline(request.form.get("deadline", ""))
            if not title or not requirements or not deadline:
                flash("Title, requirements, and deadline are required.", "error")
            else:
                db.session.add(Assignment(course=course, title=title, requirements=requirements, deadline=deadline))
                db.session.commit()
                flash("Assignment saved.", "success")
                return redirect(url_for("lecturer_assignments", course_id=course.id))
        assignments = Assignment.query.filter_by(course_id=course.id).order_by(Assignment.deadline).all()
        return render_template("lecturer_assignments.html", course=course, assignments=assignments)

    @app.route("/lecturer/assignments/<int:assignment_id>/edit", methods=["GET", "POST"])
    @login_required("lecturer")
    def edit_assignment(assignment_id):
        assignment = db.session.get(Assignment, assignment_id) or abort(404)
        lecturer_course(assignment.course_id)
        if request.method == "POST":
            title = request.form.get("title", "").strip()
            requirements = request.form.get("requirements", "").strip()
            deadline = parse_deadline(request.form.get("deadline", ""))
            if not title or not requirements or not deadline:
                flash("Title, requirements, and deadline are required.", "error")
            else:
                assignment.title = title
                assignment.requirements = requirements
                assignment.deadline = deadline
                db.session.commit()
                flash("Assignment updated.", "success")
                return redirect(url_for("lecturer_assignments", course_id=assignment.course_id))
        return render_template("assignment_form.html", assignment=assignment, course=assignment.course)

    @app.route("/lecturer/assignments/<int:assignment_id>/delete", methods=["POST"])
    @login_required("lecturer")
    def delete_assignment(assignment_id):
        assignment = db.session.get(Assignment, assignment_id) or abort(404)
        course_id = assignment.course_id
        lecturer_course(course_id)
        db.session.delete(assignment)
        db.session.commit()
        flash("Assignment deleted.", "success")
        return redirect(url_for("lecturer_assignments", course_id=course_id))

    @app.route("/lecturer/assignments/<int:assignment_id>/submissions", methods=["GET", "POST"])
    @login_required("lecturer")
    def lecturer_submissions(assignment_id):
        assignment = db.session.get(Assignment, assignment_id) or abort(404)
        lecturer_course(assignment.course_id)
        if request.method == "POST":
            submission = db.session.get(AssignmentSubmission, request.form.get("submission_id", type=int)) or abort(404)
            if submission.assignment_id != assignment.id:
                abort(403)
            grade_value = request.form.get("grade", "").strip()
            try:
                grade = float(grade_value)
            except ValueError:
                grade = -1
            if not 0 <= grade <= 100:
                flash("Grade must be a number from 0 to 100.", "error")
            else:
                submission.grade = grade
                submission.feedback = request.form.get("feedback", "").strip() or None
                submission.graded_at = datetime.now()
                submission.graded_by = current_lecturer()
                submission.status = "graded"
                db.session.commit()
                flash(f"Grade saved for {submission.student.name}.", "success")
            return redirect(url_for("lecturer_submissions", assignment_id=assignment.id))
        submissions = AssignmentSubmission.query.filter_by(assignment_id=assignment.id).order_by(AssignmentSubmission.student_id, AssignmentSubmission.attempt_number).all()
        return render_template("lecturer_submissions.html", assignment=assignment, submissions=submissions)

    @app.route("/lecturer/courses/<int:course_id>/announcements", methods=["GET", "POST"])
    @login_required("lecturer")
    def lecturer_announcements(course_id):
        course = lecturer_course(course_id)
        if request.method == "POST":
            title = request.form.get("title", "").strip()
            body = request.form.get("body", "").strip()
            if not title or not body:
                flash("Announcement title and message are required.", "error")
            else:
                db.session.add(Announcement(course=course, lecturer=current_lecturer(), title=title, body=body))
                db.session.commit()
                flash("Announcement posted.", "success")
                return redirect(url_for("lecturer_announcements", course_id=course.id))
        announcements = Announcement.query.filter_by(course_id=course.id).order_by(Announcement.posted_at.desc()).all()
        return render_template("lecturer_announcements.html", course=course, announcements=announcements)

    @app.route("/lecturer/announcements/<int:announcement_id>/edit", methods=["GET", "POST"])
    @login_required("lecturer")
    def edit_announcement(announcement_id):
        announcement = db.session.get(Announcement, announcement_id) or abort(404)
        lecturer_course(announcement.course_id)
        if request.method == "POST":
            title = request.form.get("title", "").strip()
            body = request.form.get("body", "").strip()
            if not title or not body:
                flash("Announcement title and message are required.", "error")
            else:
                announcement.title = title
                announcement.body = body
                announcement.updated_at = datetime.now()
                db.session.commit()
                flash("Announcement updated.", "success")
                return redirect(url_for("lecturer_announcements", course_id=announcement.course_id))
        return render_template("announcement_form.html", announcement=announcement, course=announcement.course)

    @app.route("/lecturer/announcements/<int:announcement_id>/delete", methods=["POST"])
    @login_required("lecturer")
    def delete_announcement(announcement_id):
        announcement = db.session.get(Announcement, announcement_id) or abort(404)
        course_id = announcement.course_id
        lecturer_course(course_id)
        db.session.delete(announcement)
        db.session.commit()
        flash("Announcement deleted.", "success")
        return redirect(url_for("lecturer_announcements", course_id=course_id))

    @app.route("/materials/<int:material_id>", methods=["GET", "POST"])
    @login_required()
    def material_detail(material_id):
        material = db.session.get(CourseMaterial, material_id) or abort(404)
        if current_user_type() == "student":
            student = current_student()
            if material.course not in student.courses:
                abort(403)
            record_material_interaction(material, student)
            if request.method == "POST":
                if not material.discussion_enabled:
                    abort(403)
                body = request.form.get("body", "").strip()
                if not body:
                    flash("Comment cannot be empty.", "error")
                elif len(body) > 2000:
                    flash("Comment must be 2,000 characters or fewer.", "error")
                else:
                    db.session.add(MaterialComment(material=material, student=student, body=body))
                    flash("Your comment was posted.", "success")
            db.session.commit()
        elif current_user_type() == "lecturer":
            lecturer_course(material.course_id)
            if request.method == "POST":
                abort(403)
        comments = MaterialComment.query.filter_by(material_id=material.id).order_by(MaterialComment.posted_at).all()
        return render_template("material_detail.html", material=material, comments=comments)

    @app.route("/lecturer/materials/<int:material_id>/interactions")
    @login_required("lecturer")
    def material_interactions(material_id):
        material = db.session.get(CourseMaterial, material_id) or abort(404)
        lecturer_course(material.course_id)
        interactions = MaterialInteraction.query.filter_by(material_id=material.id).order_by(MaterialInteraction.last_interacted_at.desc()).all()
        interacted_ids = {interaction.student_id for interaction in interactions}
        not_interacted = [student for student in material.course.students if student.id not in interacted_ids]
        return render_template(
            "material_interactions.html", material=material, interactions=interactions,
            not_interacted=sorted(not_interacted, key=lambda student: student.name.lower()),
        )

    @app.route("/lecturer/course-proposals", methods=["GET", "POST"])
    @login_required("lecturer")
    def course_proposals():
        lecturer = current_lecturer()
        if request.method == "POST":
            code = request.form.get("code", "").strip().upper()
            title = request.form.get("title", "").strip()
            if not code or not title:
                flash("Course code and title are required.", "error")
            elif Course.query.filter_by(code=code).first():
                flash("A course with that code already exists.", "error")
            else:
                proposal = Course(
                    code=code,
                    title=title,
                    description=request.form.get("description", "").strip(),
                    status="pending",
                    proposed_by=lecturer,
                )
                db.session.add(proposal)
                db.session.commit()
                flash("Course proposal submitted.", "success")
                return redirect(url_for("course_proposals"))
        proposals = Course.query.filter_by(proposed_by_lecturer_id=lecturer.id).order_by(Course.id.desc()).all()
        return render_template("course_proposals.html", proposals=proposals)

    @app.route("/lecturer/course-proposals/<int:course_id>/edit", methods=["GET", "POST"])
    @login_required("lecturer")
    def edit_course_proposal(course_id):
        proposal = db.session.get(Course, course_id) or abort(404)
        if proposal.proposed_by_lecturer_id != current_lecturer().id or proposal.status != "pending":
            abort(403)
        if request.method == "POST":
            title = request.form.get("title", "").strip()
            if not title:
                flash("Title is required.", "error")
            else:
                proposal.title = title
                proposal.description = request.form.get("description", "").strip()
                db.session.commit()
                flash("Course proposal updated.", "success")
                return redirect(url_for("course_proposals"))
        return render_template("course_proposal_form.html", proposal=proposal)

    @app.route("/admin/dashboard")
    @login_required("admin")
    def admin_dashboard():
        return render_template("admin_dashboard.html", student_count=Student.query.count(), lecturer_count=Lecturer.query.count(), pending_count=Course.query.filter_by(status="pending").count())

    @app.route("/admin/lecturers", methods=["GET", "POST"])
    @login_required("admin")
    def admin_lecturers():
        if request.method == "POST":
            if request.form.get("action") == "delete":
                selected_ids = [int(lecturer_id) for lecturer_id in request.form.getlist("lecturer_ids") if lecturer_id.isdigit()]
                if not selected_ids:
                    flash("Select at least one lecturer to delete.", "error")
                    return redirect(url_for("admin_lecturers", q=request.form.get("q", "")))

                lecturers = Lecturer.query.filter(Lecturer.id.in_(selected_ids)).all()
                if not lecturers:
                    flash("No matching lecturers were found.", "error")
                    return redirect(url_for("admin_lecturers", q=request.form.get("q", "")))

                CourseMaterial.query.filter(CourseMaterial.uploaded_by_lecturer_id.in_(selected_ids)).delete(synchronize_session=False)
                Announcement.query.filter(Announcement.lecturer_id.in_(selected_ids)).delete(synchronize_session=False)
                Course.query.filter(Course.lecturer_id.in_(selected_ids)).update({Course.lecturer_id: None}, synchronize_session=False)
                Course.query.filter(Course.proposed_by_lecturer_id.in_(selected_ids)).update({Course.proposed_by_lecturer_id: None}, synchronize_session=False)
                for lecturer in lecturers:
                    db.session.delete(lecturer)
                db.session.commit()
                flash(f"Deleted {len(lecturers)} lecturer account(s).", "success")
                return redirect(url_for("admin_lecturers", q=request.form.get("q", "")))

            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            if not name or not email or not password:
                flash("Name, email, and password are required.", "error")
            elif Student.query.filter_by(email=email).first() or Lecturer.query.filter_by(email=email).first() or Admin.query.filter_by(email=email).first():
                flash("That email is already registered.", "error")
            else:
                lecturer = Lecturer(name=name, email=email, department=request.form.get("department", "").strip())
                lecturer.set_password(password)
                db.session.add(lecturer)
                db.session.commit()
                flash("Lecturer account created.", "success")
                return redirect(url_for("admin_lecturers"))
        query = request.args.get("q", "").strip()
        lecturers_query = Lecturer.query
        if query:
            like = f"%{query}%"
            lecturers_query = lecturers_query.filter(Lecturer.name.ilike(like))
        delete_mode = request.args.get("delete") == "1"
        return render_template("admin_lecturers.html", lecturers=lecturers_query.order_by(Lecturer.name).all(), q=query, delete_mode=delete_mode)

    @app.route("/admin/students/<int:student_id>/membership", methods=["POST"])
    @login_required("admin")
    def update_membership(student_id):
        student = db.session.get(Student, student_id) or abort(404)
        student.is_member = request.form.get("is_member") == "1"
        db.session.commit()
        flash(f"{student.name}'s membership status was updated.", "success")
        return redirect(url_for("admin_students", q=request.form.get("q", "")))

    @app.route("/admin/students", methods=["GET", "POST"])
    @login_required("admin")
    def admin_students():
        if request.method == "POST":
            selected_ids = [int(student_id) for student_id in request.form.getlist("student_ids") if student_id.isdigit()]
            if not selected_ids:
                flash("Select at least one student to delete.", "error")
                return redirect(url_for("admin_students", q=request.form.get("q", "")))

            students = Student.query.filter(Student.id.in_(selected_ids)).all()
            if not students:
                flash("No matching students were found.", "error")
                return redirect(url_for("admin_students", q=request.form.get("q", "")))

            AssignmentSubmission.query.filter(AssignmentSubmission.student_id.in_(selected_ids)).delete(synchronize_session=False)
            for student in students:
                student.courses.clear()
                db.session.delete(student)
            db.session.commit()
            flash(f"Deleted {len(students)} student account(s).", "success")
            return redirect(url_for("admin_students", q=request.form.get("q", "")))

        query = request.args.get("q", "").strip()
        students_query = Student.query
        if query:
            like = f"%{query}%"
            students_query = students_query.filter(Student.name.ilike(like))
        delete_mode = request.args.get("delete") == "1"
        return render_template("admin_students.html", students=students_query.order_by(Student.name).all(), q=query, delete_mode=delete_mode)

    @app.route("/admin/reports")
    @login_required("admin")
    def admin_reports():
        enrollment = db.session.query(Course, func.count(Student.id)).outerjoin(Course.students).filter(Course.status == "approved").group_by(Course.id).order_by(Course.code).all()
        submission_counts = db.session.query(Assignment, func.count(AssignmentSubmission.id)).outerjoin(Assignment.submissions).group_by(Assignment.id).order_by(Assignment.deadline).all()
        participation = []
        for course in approved_courses_query().order_by(Course.code).all():
            participation.append((course, len(course.students), len(course.materials), len(course.announcements)))
        return render_template("admin_reports.html", enrollment=enrollment, submission_counts=submission_counts, participation=participation)

    @app.route("/admin/course-approvals", methods=["GET", "POST"])
    @login_required("admin")
    def course_approvals():
        if request.method == "POST":
            proposal = db.session.get(Course, int(request.form.get("course_id"))) or abort(404)
            action = request.form.get("action")
            if proposal.status != "pending":
                flash("Only pending proposals can be reviewed.", "error")
            elif action == "approve":
                proposal.status = "approved"
                proposal.lecturer_id = proposal.proposed_by_lecturer_id
                db.session.commit()
                flash("Course proposal approved.", "success")
            elif action == "reject":
                proposal.status = "rejected"
                db.session.commit()
                flash("Course proposal rejected.", "success")
            return redirect(url_for("course_approvals"))
        proposals = Course.query.filter(Course.status.in_(["pending", "rejected"])).order_by(Course.id.desc()).all()
        return render_template("course_approvals.html", proposals=proposals)

    @app.route("/files/<path:stored_path>")
    @login_required()
    def download_file(stored_path):
        stored_path = stored_path.replace("\\", "/")
        material = CourseMaterial.query.filter_by(file_path=stored_path).first()
        submission = AssignmentSubmission.query.filter_by(file_path=stored_path).first()
        if material:
            if current_user_type() == "student" and material.course not in current_student().courses:
                abort(403)
            if current_user_type() == "lecturer" and material.course.lecturer_id != current_lecturer().id:
                abort(403)
            if current_user_type() not in {"student", "lecturer", "admin"}:
                abort(403)
            if current_user_type() == "student":
                record_material_interaction(material, current_student())
                db.session.commit()
        elif submission:
            if current_user_type() == "student" and submission.student_id != current_student().id:
                abort(403)
            if current_user_type() == "lecturer" and submission.assignment.course.lecturer_id != current_lecturer().id:
                abort(403)
            if current_user_type() not in {"student", "lecturer", "admin"}:
                abort(403)
        else:
            abort(404)
        return send_from_directory(os.getcwd(), stored_path, as_attachment=True)

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    with app.app_context():
        db.create_all()
        ensure_schema_upgrades()

    return app


def main() -> None:
    app = create_app()
    with app.app_context():
        db.create_all()
    print("Flask app initialized and database tables created.")


if __name__ == "__main__":
    main()
