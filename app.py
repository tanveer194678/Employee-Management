import os
import re
import sqlite3
from contextlib import closing

from flask import Flask, jsonify, redirect, render_template, request, url_for, g
from werkzeug.exceptions import HTTPException


app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY", "mevi-workshop-development-key"
)

DEPARTMENTS = {
    "Computer Science",
    "Data Science",
    "Artificial Intelligence",
    "Information Technology",
    "Business Administration",
    "Electronics",
    "Unassigned"
}
YEARS = {"1st Year", "2nd Year", "3rd Year", "4th Year"}

DATABASE = os.environ.get(
    "DATABASE_PATH",
    os.path.join(app.instance_path, "management.db")
)


class APIError(Exception):
    def __init__(self, message, status_code):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@app.errorhandler(APIError)
def handle_api_error(error):
    return jsonify({"error": error.message}), error.status_code


@app.errorhandler(HTTPException)
def handle_http_exception(error):
    if request.path.startswith("/api/"):
        return jsonify({"error": error.description}), error.code
    return error


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE, timeout=10)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    os.makedirs(os.path.dirname(os.path.abspath(DATABASE)), exist_ok=True)
    with closing(sqlite3.connect(DATABASE, timeout=10)) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        tables = {
            row["name"]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }

        legacy_students = False
        if "students" in tables:
            columns = {
                row["name"]
                for row in db.execute("PRAGMA table_info(students)").fetchall()
            }
            required_columns = {
                "id", "name", "email", "roll_number", "department",
                "year", "status"
            }
            if not required_columns.issubset(columns):
                if "students_legacy" in tables:
                    raise RuntimeError(
                        "Cannot migrate the existing students table: "
                        "students_legacy already exists."
                    )
                db.execute("ALTER TABLE students RENAME TO students_legacy")
                legacy_students = True
        elif "students_legacy" in tables:
            legacy_students = True

        db.executescript("""
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL COLLATE NOCASE UNIQUE,
                roll_number TEXT NOT NULL COLLATE NOCASE UNIQUE,
                department TEXT NOT NULL,
                year TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('Active', 'Inactive')),
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS courses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                code TEXT NOT NULL COLLATE NOCASE UNIQUE,
                instructor TEXT NOT NULL,
                credits INTEGER NOT NULL CHECK (credits BETWEEN 1 AND 10)
            );

            CREATE TABLE IF NOT EXISTS enrollments (
                student_id INTEGER NOT NULL REFERENCES students(id)
                    ON DELETE CASCADE,
                course_id INTEGER NOT NULL REFERENCES courses(id)
                    ON DELETE CASCADE,
                PRIMARY KEY (student_id, course_id)
            );
        """)

        if legacy_students:
            old_columns = {
                row["name"]
                for row in db.execute(
                    "PRAGMA table_info(students_legacy)"
                ).fetchall()
            }
            if {"id", "name", "email", "course"}.issubset(old_columns):
                legacy_rows = db.execute(
                    "SELECT id, name, email, course FROM students_legacy"
                ).fetchall()
                for row in legacy_rows:
                    student_code = "LEGACY-{}".format(row["id"])
                    db.execute(
                        """
                        INSERT OR IGNORE INTO students
                            (name, email, roll_number, department, year, status)
                        VALUES (?, ?, ?, 'Unassigned', '1st Year', 'Active')
                        """,
                        (row["name"], row["email"], student_code)
                    )
                    student = db.execute(
                        "SELECT id FROM students WHERE roll_number = ?",
                        (student_code,)
                    ).fetchone()
                    if student is None:
                        continue

                    course_name = (row["course"] or "").strip() or "Unassigned course"
                    course_code = "LEGACY-{}".format(row["id"])
                    db.execute(
                        """
                        INSERT OR IGNORE INTO courses
                            (name, code, instructor, credits)
                        VALUES (?, ?, 'Unassigned', 3)
                        """,
                        (course_name, course_code)
                    )
                    course = db.execute(
                        "SELECT id FROM courses WHERE code = ?",
                        (course_code,)
                    ).fetchone()
                    db.execute(
                        """
                        INSERT OR IGNORE INTO enrollments (student_id, course_id)
                        VALUES (?, ?)
                        """,
                        (student["id"], course["id"])
                    )
        db.commit()


def request_json():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise APIError("Request body must be a JSON object.", 400)
    return payload


def required_text(payload, field):
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        labels = {"rollNumber": "Student ID"}
        label = labels.get(field, field.replace("_", " ").title())
        raise APIError("{} is required.".format(label), 400)
    return value.strip()


def parse_positive_int(value, message):
    """Parse a strictly positive integer from an int or digit-only string."""
    if isinstance(value, bool):
        raise APIError(message, 400)
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str) and re.fullmatch(r"\d+", value.strip()):
        parsed = int(value.strip())
    else:
        raise APIError(message, 400)

    if parsed < 1:
        raise APIError(message, 400)
    return parsed


def validate_student(payload):
    student = {
        "name": required_text(payload, "name"),
        "email": required_text(payload, "email").lower(),
        "roll_number": required_text(payload, "rollNumber"),
        "department": required_text(payload, "department"),
        "year": required_text(payload, "year"),
        "status": required_text(payload, "status")
    }

    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", student["email"]):
        raise APIError("Please enter a valid email address.", 400)
    if student["department"] not in DEPARTMENTS:
        raise APIError("Please select a valid department.", 400)
    if student["year"] not in YEARS:
        raise APIError("Please select a valid year.", 400)
    if student["status"] not in ("Active", "Inactive"):
        raise APIError("Status must be Active or Inactive.", 400)

    return student


def validate_course(payload):
    course = {
        "name": required_text(payload, "name"),
        "code": required_text(payload, "code").upper(),
        "instructor": required_text(payload, "instructor")
    }
    credits = payload.get("credits")
    if isinstance(credits, bool) or not (
        isinstance(credits, int)
        or isinstance(credits, str) and re.fullmatch(r"\d+", credits.strip())
    ):
        raise APIError("Credits must be a whole number from 1 to 10.", 400)
    credits = int(credits)
    if not 1 <= credits <= 10:
        raise APIError("Credits must be a whole number from 1 to 10.", 400)
    course["credits"] = credits
    return course


def duplicate_error(error, fields):
    message = str(error).lower()
    if "students.email" in message:
        return APIError("Email already registered.", 409)
    if "students.roll_number" in message:
        return APIError("Student ID already exists.", 409)
    if "courses.code" in message:
        return APIError("Course code already exists.", 409)
    return APIError("A record with the same {} already exists.".format(fields), 409)


@app.route("/")
def dashboard():
    return render_template("index.html")


@app.route("/students")
def students_page():
    return redirect(url_for("dashboard", _anchor="students"))


@app.route("/api/students", methods=["GET"])
def list_students():
    db = get_db()
    records = db.execute(
        """
        SELECT id, name, email, roll_number, department, year, status
        FROM students
        ORDER BY id DESC
        """
    ).fetchall()
    enrollments = db.execute(
        "SELECT student_id, course_id FROM enrollments ORDER BY course_id ASC"
    ).fetchall()
    course_ids = {}
    for enrollment in enrollments:
        course_ids.setdefault(enrollment["student_id"], []).append(
            enrollment["course_id"]
        )

    return jsonify([
        {
            "id": record["id"],
            "name": record["name"],
            "email": record["email"],
            "rollNumber": record["roll_number"],
            "department": record["department"],
            "year": record["year"],
            "status": record["status"],
            "courseIds": course_ids.get(record["id"], [])
        }
        for record in records
    ])


@app.route("/api/students", methods=["POST"])
def create_student():
    student = validate_student(request_json())
    db = get_db()
    try:
        cursor = db.execute(
            """
            INSERT INTO students (name, email, roll_number, department, year, status)
            VALUES (:name, :email, :roll_number, :department, :year, :status)
            """,
            student
        )
        db.commit()
    except sqlite3.IntegrityError as error:
        db.rollback()
        raise duplicate_error(error, "email or student ID")
    return jsonify({"id": cursor.lastrowid}), 201


@app.route("/api/students/<int:student_id>", methods=["PUT"])
def update_student(student_id):
    student = validate_student(request_json())
    db = get_db()
    try:
        cursor = db.execute(
            """
            UPDATE students
            SET name = :name, email = :email, roll_number = :roll_number,
                department = :department, year = :year, status = :status
            WHERE id = :id
            """,
            dict(student, id=student_id)
        )
        if cursor.rowcount == 0:
            db.rollback()
            raise APIError("Student not found.", 404)
        db.commit()
    except sqlite3.IntegrityError as error:
        db.rollback()
        raise duplicate_error(error, "email or student ID")
    return jsonify({"id": student_id})


@app.route("/api/students/<int:student_id>", methods=["DELETE"])
def delete_student(student_id):
    db = get_db()
    cursor = db.execute("DELETE FROM students WHERE id = ?", (student_id,))
    if cursor.rowcount == 0:
        raise APIError("Student not found.", 404)
    db.commit()
    return "", 204


@app.route("/api/courses", methods=["GET"])
def list_courses():
    courses = get_db().execute(
        "SELECT id, name, code, instructor, credits FROM courses ORDER BY id DESC"
    ).fetchall()
    return jsonify([dict(course) for course in courses])


@app.route("/api/courses", methods=["POST"])
def create_course():
    course = validate_course(request_json())
    db = get_db()
    try:
        cursor = db.execute(
            """
            INSERT INTO courses (name, code, instructor, credits)
            VALUES (:name, :code, :instructor, :credits)
            """,
            course
        )
        db.commit()
    except sqlite3.IntegrityError as error:
        db.rollback()
        raise duplicate_error(error, "course code")
    return jsonify({"id": cursor.lastrowid}), 201


@app.route("/api/courses/<int:course_id>", methods=["PUT"])
def update_course(course_id):
    course = validate_course(request_json())
    db = get_db()
    try:
        cursor = db.execute(
            """
            UPDATE courses
            SET name = :name, code = :code, instructor = :instructor,
                credits = :credits
            WHERE id = :id
            """,
            dict(course, id=course_id)
        )
        if cursor.rowcount == 0:
            db.rollback()
            raise APIError("Course not found.", 404)
        db.commit()
    except sqlite3.IntegrityError as error:
        db.rollback()
        raise duplicate_error(error, "course code")
    return jsonify({"id": course_id})


@app.route("/api/courses/<int:course_id>", methods=["DELETE"])
def delete_course(course_id):
    db = get_db()
    cursor = db.execute("DELETE FROM courses WHERE id = ?", (course_id,))
    if cursor.rowcount == 0:
        raise APIError("Course not found.", 404)
    db.commit()
    return "", 204


@app.route("/api/enrollments", methods=["POST"])
def create_enrollment():
    payload = request_json()
    student_id = parse_positive_int(
        payload.get("studentId"), "Select a valid student and course."
    )
    course_id = parse_positive_int(
        payload.get("courseId"), "Select a valid student and course."
    )

    db = get_db()
    student = db.execute(
        "SELECT id FROM students WHERE id = ?", (student_id,)
    ).fetchone()
    course = db.execute(
        "SELECT id FROM courses WHERE id = ?", (course_id,)
    ).fetchone()
    if student is None or course is None:
        raise APIError("Student or course not found.", 404)

    try:
        db.execute(
            "INSERT INTO enrollments (student_id, course_id) VALUES (?, ?)",
            (student_id, course_id)
        )
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        raise APIError("This student is already enrolled in this course.", 409)
    return "", 201


@app.route(
    "/api/enrollments/<int:student_id>/<int:course_id>",
    methods=["DELETE"]
)
def delete_enrollment(student_id, course_id):
    db = get_db()
    cursor = db.execute(
        "DELETE FROM enrollments WHERE student_id = ? AND course_id = ?",
        (student_id, course_id)
    )
    if cursor.rowcount == 0:
        raise APIError("Enrollment not found.", 404)
    db.commit()
    return "", 204


@app.route("/health")
def health():
    try:
        get_db().execute("SELECT 1").fetchone()
    except sqlite3.Error as error:
        return jsonify({
            "status": "unhealthy",
            "application": "MEVI Management Portal",
            "error": str(error)
        }), 503
    return jsonify({
        "status": "healthy",
        "application": "MEVI Management Portal"
    })


init_db()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5001"))
    app.run(host="0.0.0.0", port=port, debug=False)
