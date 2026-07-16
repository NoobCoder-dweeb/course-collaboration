from app import create_app
from models import Lecturer, Student, db


TEST_PASSWORD = "password123"


def upsert_student() -> Student:
    student = Student.query.filter_by(email="student@example.com").first()

    if student is None:
        student = Student(
            name="Test Student",
            email="student@example.com",
            enrollment_year=2026,
        )
        db.session.add(student)

    student.set_password(TEST_PASSWORD)
    return student


def upsert_lecturer() -> Lecturer:
    lecturer = Lecturer.query.filter_by(email="lecturer@example.com").first()

    if lecturer is None:
        lecturer = Lecturer(
            name="Test Lecturer",
            email="lecturer@example.com",
            department="Computer Science",
        )
        db.session.add(lecturer)

    lecturer.set_password(TEST_PASSWORD)
    return lecturer


def main() -> None:
    app = create_app()

    with app.app_context():
        db.create_all()
        upsert_student()
        upsert_lecturer()
        db.session.commit()

    print("Seeded test users:")
    print(f"Student: student@example.com / {TEST_PASSWORD}")
    print(f"Lecturer: lecturer@example.com / {TEST_PASSWORD}")


if __name__ == "__main__":
    main()
