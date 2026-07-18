# Course Collaboration

A Flask/Jinja2 course collaboration platform for XBAU2114N. It supports student enrolment, assignment submission, lecturer course management, materials, announcements, course proposals, admin accounts, membership management, approvals, and reports.

## Requirements

- Python 3.13 or newer
- Git

The commands below are written for Windows PowerShell.

## 1. Clone the Project

```powershell
git clone https://github.com/NoobCoder-dweeb/course-collaboration.git
cd course-collaboration
```

## 2. Create a Virtual Environment


```powershell
python -m venv venv
```

## 3. Install Dependencies

```powershell
pip install --upgrade pip
pip install -r requirements.txt
```

## 4. Initialize or Reset the Database

Run the seed script:

```powershell
py seed.py
```

This command does all of the following:

- Deletes the existing SQLite tables.
- Creates fresh tables.
- Deletes and recreates demo upload files under `uploads/`.
- Adds sample students, lecturers, admin, courses, materials, assignments, submissions, announcements, and proposals.

Use the same command whenever you want to reset the app back to the demo data.

The SQLite database is created at:

```text
instance/course_collaboration.sqlite
```

## 5. Start the App

```powershell
flask run
```

Open the local URL shown by Flask, usually:

```text
http://127.0.0.1:5000
```

## Demo Accounts

All seeded accounts use the same password:

```text
password123
```

| Role | Email |
| --- | --- |
| Admin | admin@example.com |
| Lecturer | lecturer@example.com |
| Second lecturer | lecturer2@example.com |
| Student | student@example.com |
| Member student | member@example.com |


## Fresh Setup Checklist for Teammates

1. Clone the repo.
2. Create `venv`.
3. Install `requirements.txt`.
4. Run `seed.py`.
5. Start Flask.
6. Log in with one of the demo accounts.
