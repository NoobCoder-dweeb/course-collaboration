from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

# Shared SQLAlchemy instance for the Flask app.
db = SQLAlchemy()

student_courses = db.Table(
    "student_courses",
    db.Column("student_id", db.Integer, db.ForeignKey("student.id"), primary_key=True),
    db.Column("course_id", db.Integer, db.ForeignKey("course.id"), primary_key=True),
)


class Lecturer(db.Model):
    __tablename__ = "lecturer"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    email = db.Column(db.String(256), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    department = db.Column(db.String(128), nullable=True)

    courses = db.relationship("Course", back_populates="lecturer", lazy="select")

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        if not self.password_hash:
            return False

        return check_password_hash(self.password_hash, password)

    def __repr__(self) -> str:
        return f"<Lecturer {self.name} id={self.id}>"


class Course(db.Model):
    __tablename__ = "course"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(256), nullable=False)
    code = db.Column(db.String(32), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    credits = db.Column(db.Integer, nullable=True)

    lecturer_id = db.Column(db.Integer, db.ForeignKey("lecturer.id"), nullable=True)
    lecturer = db.relationship("Lecturer", back_populates="courses", lazy="joined")

    assignments = db.relationship("Assignment", back_populates="course", lazy="select", cascade="all, delete-orphan")
    materials = db.relationship("CourseMaterial", back_populates="course", lazy="select", cascade="all, delete-orphan")
    students = db.relationship("Student", secondary=student_courses, back_populates="courses", lazy="select")

    def __repr__(self) -> str:
        return f"<Course {self.code} title={self.title}>"


class CourseMaterial(db.Model):
    __tablename__ = "course_material"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(256), nullable=False)
    description = db.Column(db.Text, nullable=True)
    material_type = db.Column(db.String(64), nullable=True)
    file_url = db.Column(db.String(512), nullable=True)
    uploaded_at = db.Column(db.DateTime, nullable=True)

    course_id = db.Column(db.Integer, db.ForeignKey("course.id"), nullable=False)
    course = db.relationship("Course", back_populates="materials", lazy="joined")

    def __repr__(self) -> str:
        return f"<CourseMaterial {self.title} id={self.id}>"


class Assignment(db.Model):
    __tablename__ = "assignment"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(256), nullable=False)
    description = db.Column(db.Text, nullable=True)
    due_date = db.Column(db.DateTime, nullable=True)
    max_score = db.Column(db.Integer, nullable=True)

    course_id = db.Column(db.Integer, db.ForeignKey("course.id"), nullable=False)
    course = db.relationship("Course", back_populates="assignments", lazy="joined")

    def __repr__(self) -> str:
        return f"<Assignment {self.title} id={self.id}>"


class Student(db.Model):
    __tablename__ = "student"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    email = db.Column(db.String(256), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    enrollment_year = db.Column(db.Integer, nullable=True)

    courses = db.relationship("Course", secondary=student_courses, back_populates="students", lazy="select")

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        if not self.password_hash:
            return False

        return check_password_hash(self.password_hash, password)

    def __repr__(self) -> str:
        return f"<Student {self.name} id={self.id}>"
