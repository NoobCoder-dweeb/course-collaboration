from datetime import datetime, timedelta
from pathlib import Path
import shutil

from app import create_app
from models import Admin, Announcement, Assignment, AssignmentSubmission, Course, CourseMaterial, Lecturer, Student, db


TEST_PASSWORD = "password123"
COURSES = [
    ("XBAU1001", "Introduction to Programming", "Programming fundamentals and problem solving."),
    ("XBAU1002", "Data Structures", "Core data structures and algorithmic thinking."),
    ("XBAU2001", "Database Systems", "Relational data modeling, SQL, and database-backed applications."),
    ("XBAU2002", "Web Application Development", "Server-rendered web applications and collaborative workflows."),
    ("XBAU3001", "Software Engineering", "Software design, testing, and team delivery practices."),
    ("XBAU3002", "Capstone Project", "A project course for integrating prior software coursework."),
]


def password_user(model, name, email, **fields):
    user = model(name=name, email=email, **fields)
    user.set_password(TEST_PASSWORD)
    db.session.add(user)
    return user


def sample_file(path: str, content: str) -> str:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return path


def main() -> None:
    app = create_app()
    with app.app_context():
        db.drop_all()
        db.create_all()
        shutil.rmtree("uploads", ignore_errors=True)

        admin = password_user(Admin, "Fixed Admin", "admin@example.com")
        lecturer = password_user(Lecturer, "Test Lecturer", "lecturer@example.com", department="Computer Science")
        lecturer_two = password_user(Lecturer, "Second Lecturer", "lecturer2@example.com", department="Information Systems")
        student = password_user(Student, "Test Student", "student@example.com", enrollment_year=2026, is_member=False)
        member = password_user(Student, "Member Student", "member@example.com", enrollment_year=2026, is_member=True)

        courses = {}
        for code, title, description in COURSES:
            course = Course(code=code, title=title, description=description, status="approved", lecturer=lecturer)
            db.session.add(course)
            courses[code] = course
        db.session.flush()

        student.courses = [courses["XBAU1002"], courses["XBAU2002"]]
        member.courses = [courses["XBAU2001"], courses["XBAU2002"]]

        material_path = sample_file("uploads/materials/week1_notes.txt", "Week 1 notes for the demo course.")
        db.session.add_all(
            [
                CourseMaterial(course=courses["XBAU1002"], uploaded_by=lecturer, title="Week 1 Notes", description="Introductory notes.", material_type="Notes", file_path=material_path),
                CourseMaterial(course=courses["XBAU2002"], uploaded_by=lecturer, title="Flask Setup", description="Starter setup checklist.", material_type="Lab", file_path=None),
            ]
        )

        now = datetime.now()
        assignment_a = Assignment(course=courses["XBAU1002"], title="Linked List Lab", requirements="Submit a zip file containing source code and a short README.", deadline=now + timedelta(days=14))
        assignment_b = Assignment(course=courses["XBAU2002"], title="Flask Routes Exercise", requirements="Submit a PDF explaining route design and screenshots.", deadline=now + timedelta(days=7))
        assignment_closed = Assignment(course=courses["XBAU2002"], title="Past HTML Exercise", requirements="This seeded assignment demonstrates closed submissions.", deadline=now - timedelta(days=1))
        db.session.add_all([assignment_a, assignment_b, assignment_closed])

        db.session.add_all(
            [
                Announcement(course=courses["XBAU1002"], lecturer=lecturer, title="Lab Groups Posted", body="Check the course page for your lab grouping."),
                Announcement(course=courses["XBAU2002"], lecturer=lecturer, title="Project Brief Available", body="The first project brief is available under materials."),
            ]
        )

        db.session.flush()
        sub1 = sample_file("uploads/submissions/student_attempt1.txt", "First non-member attempt.")
        sub2 = sample_file("uploads/submissions/student_attempt2.txt", "Second non-member attempt.")
        mem1 = sample_file("uploads/submissions/member_attempt1.txt", "Member attempt one.")
        mem2 = sample_file("uploads/submissions/member_attempt2.txt", "Member attempt two.")
        mem3 = sample_file("uploads/submissions/member_attempt3.txt", "Member attempt three.")
        db.session.add_all(
            [
                AssignmentSubmission(assignment=assignment_a, student=student, file_path=sub1, attempt_number=1),
                AssignmentSubmission(assignment=assignment_a, student=student, file_path=sub2, attempt_number=2),
                AssignmentSubmission(assignment=assignment_b, student=member, file_path=mem1, attempt_number=1),
                AssignmentSubmission(assignment=assignment_b, student=member, file_path=mem2, attempt_number=2),
                AssignmentSubmission(assignment=assignment_b, student=member, file_path=mem3, attempt_number=3),
            ]
        )

        pending = Course(
            code="XBAU3100",
            title="Human-Centered Software",
            description="A proposed elective for usability and collaborative software practice.",
            status="pending",
            proposed_by=lecturer_two,
        )
        db.session.add(pending)

        rejected = Course(
            code="XBAU3999",
            title="Legacy Systems Workshop",
            description="A rejected proposal kept hidden from students.",
            status="rejected",
            proposed_by=lecturer,
        )
        db.session.add(rejected)

        db.session.commit()

    print("Database reset and seeded.")
    print(f"Student: student@example.com / {TEST_PASSWORD}")
    print(f"Lecturer: lecturer@example.com / {TEST_PASSWORD}")
    print(f"Admin: admin@example.com / {TEST_PASSWORD}")
    print(f"Member student: member@example.com / {TEST_PASSWORD}")


if __name__ == "__main__":
    main()
