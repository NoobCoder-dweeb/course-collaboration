import unittest
import sys
from datetime import datetime, timedelta

from app import allowed_file, create_app, parse_deadline
from models import (
    Admin,
    Assignment,
    Course,
    CourseMaterial,
    Lecturer,
    MaterialComment,
    MaterialInteraction,
    Student,
    db,
)


PASSWORD = "password123"
GREEN = "\033[92m"
RESET = "\033[0m"


def checked(message):
    print(f"{GREEN}✓ {message}{RESET}", file=sys.stderr, flush=True)


class BaseTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret",
                "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            }
        )
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        self.seed_data()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def seed_data(self):
        self.admin = Admin(name="Admin User", email="admin@example.com")
        self.admin.set_password(PASSWORD)

        self.lecturer = Lecturer(
            name="Lecturer User",
            email="lecturer@example.com",
            department="Computer Science",
        )
        self.lecturer.set_password(PASSWORD)

        self.student = Student(
            name="Student User",
            email="student@example.com",
            enrollment_year=2026,
            is_member=False,
        )
        self.student.set_password(PASSWORD)

        self.member = Student(
            name="Member User",
            email="member@example.com",
            enrollment_year=2026,
            is_member=True,
        )
        self.member.set_password(PASSWORD)

        self.course = Course(
            code="XBAU1001",
            title="Software Testing",
            description="Testing fundamentals.",
            status="approved",
            lecturer=self.lecturer,
        )
        self.open_course = Course(
            code="XBAU1002",
            title="Database Systems",
            description="SQLite and SQLAlchemy.",
            status="approved",
            lecturer=self.lecturer,
        )
        self.pending_course = Course(
            code="XBAU2001",
            title="Pending Course",
            description="A course awaiting approval.",
            status="pending",
            proposed_by=self.lecturer,
        )
        self.student.courses.append(self.course)
        self.member.courses.append(self.course)

        self.material = CourseMaterial(
            course=self.course,
            uploaded_by=self.lecturer,
            title="Week 1 Notes",
            description="Introductory material.",
            material_type="Notes",
            week_number=1,
            topic="Testing",
            discussion_enabled=True,
            is_priority=False,
        )
        self.priority_material = CourseMaterial(
            course=self.course,
            uploaded_by=self.lecturer,
            title="Member Case Study",
            description="Member-only reading.",
            material_type="Case Study",
            discussion_enabled=True,
            is_priority=True,
        )
        self.assignment = Assignment(
            course=self.course,
            title="Unit Test Exercise",
            requirements="Submit tests.",
            deadline=datetime.now() + timedelta(days=7),
        )

        db.session.add_all(
            [
                self.admin,
                self.lecturer,
                self.student,
                self.member,
                self.course,
                self.open_course,
                self.pending_course,
                self.material,
                self.priority_material,
                self.assignment,
            ]
        )
        db.session.commit()

    def login(self, email="student@example.com", password=PASSWORD):
        return self.client.post(
            "/login",
            data={"email": email, "password": password},
            follow_redirects=False,
        )


class UnitTests(BaseTestCase):
    def test_password_file_and_deadline_helpers(self):
        student = Student(name="Helper Student", email="helper@example.com")
        student.set_password("secret")

        self.assertTrue(student.check_password("secret"))
        self.assertFalse(student.check_password("wrong"))
        self.assertTrue(allowed_file("lecture_notes.PDF"))
        self.assertFalse(allowed_file("malware.exe"))
        self.assertFalse(allowed_file("no_extension"))
        self.assertEqual(parse_deadline("2026-07-21T14:30").year, 2026)
        self.assertIsNone(parse_deadline(""))
        self.assertIsNone(parse_deadline("21/07/2026 14:30"))
        checked("Unit: password hashing accepts the correct password and rejects a wrong password")
        checked("Unit: upload validation accepts allowed files and rejects unsafe file names")
        checked("Unit: deadline parser accepts the app format and rejects invalid dates")


class IntegrationTests(BaseTestCase):
    def test_signup_creates_student_in_test_database(self):
        response = self.client.post(
            "/signup",
            data={
                "name": "New Student",
                "email": "new@student.test",
                "password": "new-password",
                "password_confirm": "new-password",
            },
            follow_redirects=False,
        )

        created = Student.query.filter_by(email="new@student.test").first()
        self.assertEqual(response.status_code, 302)
        self.assertIsNotNone(created)
        self.assertTrue(created.check_password("new-password"))
        self.assertFalse(created.is_member)
        checked("Integration: signup creates a non-member student in the test database")

    def test_login_sets_student_session_and_rejects_wrong_password(self):
        bad_response = self.client.post(
            "/login",
            data={"email": "student@example.com", "password": "wrong"},
        )
        self.assertEqual(bad_response.status_code, 401)
        checked("Integration: login rejects an incorrect password")

        good_response = self.login()
        self.assertEqual(good_response.status_code, 302)
        self.assertIn("/dashboard", good_response.headers["Location"])
        with self.client.session_transaction() as session:
            self.assertEqual(session["user_type"], "student")
            self.assertEqual(session["user_id"], self.student.id)
        checked("Integration: login accepts valid student credentials and stores the session")

    def test_student_can_confirm_enrollment_for_approved_course_only(self):
        self.login()

        enroll_response = self.client.post(
            "/courses/enroll",
            data={"course_ids": [str(self.open_course.id), str(self.pending_course.id)]},
        )
        self.assertEqual(enroll_response.status_code, 200)
        with self.client.session_transaction() as session:
            self.assertEqual(session["pending_enrollment"]["add"], [self.open_course.id])

        confirm_response = self.client.post("/courses/enroll/confirm")
        self.assertEqual(confirm_response.status_code, 302)

        student = db.session.get(Student, self.student.id)
        enrolled_codes = {course.code for course in student.courses}
        self.assertIn("XBAU1001", enrolled_codes)
        self.assertIn("XBAU1002", enrolled_codes)
        self.assertNotIn("XBAU2001", enrolled_codes)
        checked("Integration: enrollment confirms approved courses and ignores a pending course")


class SystemTests(BaseTestCase):
    def test_student_material_discussion_flow_records_comment_and_interaction(self):
        self.login()

        response = self.client.post(
            f"/materials/{self.material.id}",
            data={"body": "This material is clear."},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 200)
        comment = MaterialComment.query.filter_by(
            material_id=self.material.id,
            student_id=self.student.id,
        ).first()
        interaction = MaterialInteraction.query.filter_by(
            material_id=self.material.id,
            student_id=self.student.id,
        ).first()
        self.assertIsNotNone(comment)
        self.assertEqual(comment.body, "This material is clear.")
        self.assertIsNotNone(interaction)
        self.assertEqual(interaction.interaction_count, 1)
        checked("System: student material page saves a discussion comment")
        checked("System: viewing/commenting on material records a student interaction")

    def test_non_member_student_cannot_open_priority_material(self):
        self.login()

        response = self.client.get(
            f"/materials/{self.priority_material.id}",
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(f"/courses/{self.course.id}", response.headers["Location"])
        interaction = MaterialInteraction.query.filter_by(
            material_id=self.priority_material.id,
            student_id=self.student.id,
        ).first()
        self.assertIsNone(interaction)
        checked("System: non-member student is blocked from member-only priority material")


if __name__ == "__main__":
    unittest.main()
