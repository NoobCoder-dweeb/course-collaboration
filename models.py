from datetime import datetime

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash


db = SQLAlchemy()

student_courses = db.Table(
    "student_courses",
    db.Column("student_id", db.Integer, db.ForeignKey("student.id"), primary_key=True),
    db.Column("course_id", db.Integer, db.ForeignKey("course.id"), primary_key=True),
)

class PasswordMixin:
    password_hash = db.Column(db.String(256), nullable=False)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return bool(self.password_hash) and check_password_hash(self.password_hash, password)


class Admin(db.Model, PasswordMixin):
    __tablename__ = "admin"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    email = db.Column(db.String(256), unique=True, nullable=False)


class Lecturer(db.Model, PasswordMixin):
    __tablename__ = "lecturer"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    email = db.Column(db.String(256), unique=True, nullable=False)
    department = db.Column(db.String(128), nullable=True)

    courses = db.relationship("Course", back_populates="lecturer", foreign_keys="Course.lecturer_id", lazy="select")
    announcements = db.relationship("Announcement", back_populates="lecturer", lazy="select")
    proposals = db.relationship("Course", back_populates="proposed_by", foreign_keys="Course.proposed_by_lecturer_id", lazy="select")

    def __repr__(self) -> str:
        return f"<Lecturer {self.name} id={self.id}>"


class Course(db.Model):
    __tablename__ = "course"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(256), nullable=False)
    code = db.Column(db.String(32), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(16), nullable=False, default="approved")

    lecturer_id = db.Column(db.Integer, db.ForeignKey("lecturer.id"), nullable=True)
    proposed_by_lecturer_id = db.Column(db.Integer, db.ForeignKey("lecturer.id"), nullable=True)

    lecturer = db.relationship("Lecturer", back_populates="courses", foreign_keys=[lecturer_id], lazy="joined")
    proposed_by = db.relationship("Lecturer", back_populates="proposals", foreign_keys=[proposed_by_lecturer_id], lazy="joined")
    assignments = db.relationship("Assignment", back_populates="course", lazy="select", cascade="all, delete-orphan")
    announcements = db.relationship("Announcement", back_populates="course", lazy="select", cascade="all, delete-orphan")
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
    week_number = db.Column(db.Integer, nullable=True)
    topic = db.Column(db.String(128), nullable=True)
    discussion_enabled = db.Column(db.Boolean, nullable=False, default=False)
    file_path = db.Column(db.String(512), nullable=True)
    uploaded_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    course_id = db.Column(db.Integer, db.ForeignKey("course.id"), nullable=False)
    uploaded_by_lecturer_id = db.Column(db.Integer, db.ForeignKey("lecturer.id"), nullable=False)

    course = db.relationship("Course", back_populates="materials", lazy="joined")
    uploaded_by = db.relationship("Lecturer", lazy="joined")
    comments = db.relationship("MaterialComment", back_populates="material", lazy="select", cascade="all, delete-orphan")
    interactions = db.relationship("MaterialInteraction", back_populates="material", lazy="select", cascade="all, delete-orphan")


class MaterialComment(db.Model):
    __tablename__ = "material_comment"

    id = db.Column(db.Integer, primary_key=True)
    material_id = db.Column(db.Integer, db.ForeignKey("course_material.id"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False)
    body = db.Column(db.Text, nullable=False)
    posted_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    material = db.relationship("CourseMaterial", back_populates="comments", lazy="joined")
    student = db.relationship("Student", back_populates="material_comments", lazy="joined")


class MaterialInteraction(db.Model):
    __tablename__ = "material_interaction"
    __table_args__ = (db.UniqueConstraint("material_id", "student_id", name="uq_material_student_interaction"),)

    id = db.Column(db.Integer, primary_key=True)
    material_id = db.Column(db.Integer, db.ForeignKey("course_material.id"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False)
    first_interacted_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    last_interacted_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    interaction_count = db.Column(db.Integer, nullable=False, default=1)

    material = db.relationship("CourseMaterial", back_populates="interactions", lazy="joined")
    student = db.relationship("Student", back_populates="material_interactions", lazy="joined")


class Assignment(db.Model):
    __tablename__ = "assignment"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(256), nullable=False)
    requirements = db.Column(db.Text, nullable=False)
    deadline = db.Column(db.DateTime, nullable=False)

    course_id = db.Column(db.Integer, db.ForeignKey("course.id"), nullable=False)
    course = db.relationship("Course", back_populates="assignments", lazy="joined")
    submissions = db.relationship("AssignmentSubmission", back_populates="assignment", lazy="select", cascade="all, delete-orphan")


class AssignmentSubmission(db.Model):
    __tablename__ = "assignment_submission"
    __table_args__ = (
        db.UniqueConstraint("assignment_id", "student_id", "attempt_number", name="uq_submission_attempt"),
    )

    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey("assignment.id"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False)
    file_path = db.Column(db.String(512), nullable=False)
    submitted_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    attempt_number = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(32), nullable=False, default="submitted")
    grade = db.Column(db.Float, nullable=True)
    feedback = db.Column(db.Text, nullable=True)
    graded_at = db.Column(db.DateTime, nullable=True)
    graded_by_lecturer_id = db.Column(db.Integer, db.ForeignKey("lecturer.id"), nullable=True)

    assignment = db.relationship("Assignment", back_populates="submissions", lazy="joined")
    student = db.relationship("Student", back_populates="submissions", lazy="joined")
    graded_by = db.relationship("Lecturer", lazy="joined")


class Announcement(db.Model):
    __tablename__ = "announcement"

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey("course.id"), nullable=False)
    lecturer_id = db.Column(db.Integer, db.ForeignKey("lecturer.id"), nullable=False)
    title = db.Column(db.String(256), nullable=False)
    body = db.Column(db.Text, nullable=False)
    posted_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(db.DateTime, nullable=True)

    course = db.relationship("Course", back_populates="announcements", lazy="joined")
    lecturer = db.relationship("Lecturer", back_populates="announcements", lazy="joined")


class Student(db.Model, PasswordMixin):
    __tablename__ = "student"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    email = db.Column(db.String(256), unique=True, nullable=False)
    enrollment_year = db.Column(db.Integer, nullable=True)
    is_member = db.Column(db.Boolean, nullable=False, default=False)
    skills = db.Column(db.Text, nullable=True)
    collaboration_mode = db.Column(db.String(32), nullable=True)

    courses = db.relationship("Course", secondary=student_courses, back_populates="students", lazy="select")
    submissions = db.relationship("AssignmentSubmission", back_populates="student", lazy="select")
    material_comments = db.relationship("MaterialComment", back_populates="student", lazy="select", cascade="all, delete-orphan")
    material_interactions = db.relationship("MaterialInteraction", back_populates="student", lazy="select", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Student {self.name} id={self.id}>"
