from app import create_app
from models import Course, Lecturer, Student, db


TEST_PASSWORD = "password123"
COURSES = [
    {
        "code": "XBAU1001",
        "title": "Introduction to Programming",
        "description": "Programming fundamentals and problem solving.",
        "credits": 4,
        "prerequisites": [],
    },
    {
        "code": "XBAU1002",
        "title": "Data Structures",
        "description": "Core data structures and algorithmic thinking.",
        "credits": 4,
        "prerequisites": ["XBAU1001"],
    },
    {
        "code": "XBAU2001",
        "title": "Database Systems",
        "description": "Relational data modeling, SQL, and database-backed applications.",
        "credits": 4,
        "prerequisites": ["XBAU1002"],
    },
    {
        "code": "XBAU2002",
        "title": "Web Application Development",
        "description": "Server-rendered web applications and collaborative workflows.",
        "credits": 4,
        "prerequisites": ["XBAU1001"],
    },
    {
        "code": "XBAU3001",
        "title": "Software Engineering",
        "description": "Software design, testing, and team delivery practices.",
        "credits": 4,
        "prerequisites": ["XBAU2001", "XBAU2002"],
    },
    {
        "code": "XBAU3002",
        "title": "Capstone Project",
        "description": "A project course for integrating prior software coursework.",
        "credits": 4,
        "prerequisites": ["XBAU3001"],
    },
]


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


def upsert_courses() -> dict[str, Course]:
    courses = {}

    for course_data in COURSES:
        course = Course.query.filter_by(code=course_data["code"]).first()

        if course is None:
            course = Course(code=course_data["code"], title=course_data["title"])
            db.session.add(course)

        course.title = course_data["title"]
        course.description = course_data["description"]
        course.credits = course_data["credits"]
        courses[course.code] = course

    db.session.flush()

    for course_data in COURSES:
        course = courses[course_data["code"]]
        course.prerequisites = [
            courses[prerequisite_code]
            for prerequisite_code in course_data["prerequisites"]
        ]

    return courses


def main() -> None:
    app = create_app()

    with app.app_context():
        db.create_all()
        courses = upsert_courses()
        student = upsert_student()
        upsert_lecturer()

        current_codes = {course.code for course in student.courses}
        if not student.courses or current_codes == {"XBAU1001"}:
            student.courses = []
            student.courses.append(courses["XBAU1002"])

        student.passed_courses = [courses["XBAU1001"]]

        db.session.commit()

    print("Seeded test users:")
    print(f"Student: student@example.com / {TEST_PASSWORD}")
    print(f"Lecturer: lecturer@example.com / {TEST_PASSWORD}")
    print("Seeded courses with prerequisites.")
    print("Test student passed XBAU1001 last semester.")


if __name__ == "__main__":
    main()
