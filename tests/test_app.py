import os
import sqlite3
import tempfile
import unittest


test_directory = tempfile.TemporaryDirectory()
os.environ["DATABASE_PATH"] = os.path.join(test_directory.name, "test.db")

import app as application


class ManagementAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        application.app.config["TESTING"] = True
        cls.client = application.app.test_client()

    @classmethod
    def tearDownClass(cls):
        test_directory.cleanup()

    def setUp(self):
        db = sqlite3.connect(application.DATABASE)
        try:
            db.execute("DELETE FROM enrollments")
            db.execute("DELETE FROM students")
            db.execute("DELETE FROM courses")
            db.commit()
        finally:
            db.close()

    def create_student(self, **overrides):
        student = {
            "name": "Ada Lovelace",
            "email": "ada@example.com",
            "rollNumber": "STU-1001",
            "department": "Computer Science",
            "year": "2nd Year",
            "status": "Active"
        }
        student.update(overrides)
        return self.client.post("/api/students", json=student)

    def create_course(self, **overrides):
        course = {
            "name": "Algorithms",
            "code": "CS201",
            "instructor": "Grace Hopper",
            "credits": 3
        }
        course.update(overrides)
        return self.client.post("/api/courses", json=course)

    def test_dashboard_and_assets_are_served(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"/static/style.css", response.data)
        self.assertIn(b"/static/app.js", response.data)
        script = self.client.get("/static/app.js")
        self.assertEqual(script.status_code, 200)
        script.close()
        styles = self.client.get("/static/style.css")
        self.assertEqual(styles.status_code, 200)
        styles.close()

    def test_student_course_and_enrollment_flow(self):
        student_response = self.create_student()
        course_response = self.create_course()
        self.assertEqual(student_response.status_code, 201)
        self.assertEqual(course_response.status_code, 201)

        student_id = student_response.json["id"]
        course_id = course_response.json["id"]
        enrollment = self.client.post(
            "/api/enrollments",
            json={"studentId": student_id, "courseId": course_id}
        )
        self.assertEqual(enrollment.status_code, 201)
        self.assertEqual(
            self.client.post(
                "/api/enrollments",
                json={"studentId": student_id, "courseId": course_id}
            ).status_code,
            409
        )

        student = self.client.get("/api/students").json[0]
        self.assertEqual(student["courseIds"], [course_id])
        self.assertEqual(
            self.client.delete(
                f"/api/enrollments/{student_id}/{course_id}"
            ).status_code,
            204
        )
        self.assertEqual(self.client.get("/api/students").json[0]["courseIds"], [])
        self.client.post(
            "/api/enrollments",
            json={"studentId": student_id, "courseId": course_id}
        )
        self.assertEqual(
            self.client.delete(f"/api/courses/{course_id}").status_code,
            204
        )
        self.assertEqual(self.client.get("/api/students").json[0]["courseIds"], [])

    def test_updates_duplicates_and_validation(self):
        response = self.create_student()
        student_id = response.json["id"]

        updated = self.client.put(
            f"/api/students/{student_id}",
            json={
                "name": "Ada Byron",
                "email": "ADA@example.com",
                "rollNumber": "STU-1001",
                "department": "Data Science",
                "year": "3rd Year",
                "status": "Inactive"
            }
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(
            self.client.get("/api/students").json[0]["name"],
            "Ada Byron"
        )
        self.assertEqual(
            self.create_student(email="not-an-email").status_code,
            400
        )
        self.assertEqual(
            self.create_student(
                name="   ",
                email="blank@example.com",
                rollNumber="STU-1009"
            ).status_code,
            400
        )
        duplicate_roll = self.create_student(
            email="another@example.com",
            rollNumber="stu-1001"
        )
        self.assertEqual(duplicate_roll.status_code, 409)
        self.assertEqual(duplicate_roll.json["error"], "Student ID already exists.")
        duplicate_email = self.create_student(
            email="ADA@example.com",
            rollNumber="STU-1002"
        )
        self.assertEqual(duplicate_email.json["error"], "Email already registered.")
        self.assertEqual(self.client.delete(f"/api/students/{student_id}").status_code, 204)

    def test_course_updates_duplicates_and_missing_resources(self):
        response = self.create_course()
        course_id = response.json["id"]

        self.assertEqual(
            self.client.put(
                f"/api/courses/{course_id}",
                json={
                    "name": "Advanced Algorithms",
                    "code": "cs202",
                    "instructor": "Grace Hopper",
                    "credits": 4
                }
            ).status_code,
            200
        )
        self.assertEqual(self.create_course(code="CS202").status_code, 409)
        self.assertEqual(
            self.client.post(
                "/api/courses",
                json={
                    "name": "Invalid Course",
                    "code": "BAD",
                    "instructor": "Instructor",
                    "credits": 11
                }
            ).status_code,
            400
        )
        self.assertEqual(
            self.client.post(
                "/api/courses",
                json={
                    "name": "Bool Credits",
                    "code": "BOOL1",
                    "instructor": "Instructor",
                    "credits": True
                }
            ).status_code,
            400
        )
        self.assertEqual(self.client.delete("/api/courses/9999").status_code, 404)
        self.assertEqual(self.client.delete("/api/students/9999").status_code, 404)

    def test_enrollment_validation_and_api_json_errors(self):
        student_id = self.create_student().json["id"]
        course_id = self.create_course().json["id"]

        for bad_payload in [
            {"studentId": True, "courseId": course_id},
            {"studentId": student_id, "courseId": 1.5},
            {"studentId": 0, "courseId": course_id},
            {"studentId": "abc", "courseId": course_id},
        ]:
            resp = self.client.post("/api/enrollments", json=bad_payload)
            self.assertEqual(resp.status_code, 400)
            self.assertIn("error", resp.json)

        missing = self.client.post(
            "/api/enrollments",
            json={"studentId": 9999, "courseId": course_id}
        )
        self.assertEqual(missing.status_code, 404)

        not_found_api = self.client.get("/api/does-not-exist")
        self.assertEqual(not_found_api.status_code, 404)
        self.assertIn("error", not_found_api.json)

        wrong_method = self.client.patch("/api/students")
        self.assertEqual(wrong_method.status_code, 405)
        self.assertIn("error", wrong_method.json)

    def test_existing_database_is_migrated(self):
        legacy_database = os.path.join(test_directory.name, "legacy.db")
        connection = sqlite3.connect(legacy_database)
        try:
            connection.execute("""
                CREATE TABLE students (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE,
                    course TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            connection.execute(
                "INSERT INTO students (id, name, email, course) VALUES (?, ?, ?, ?)",
                (7, "Legacy Student", "legacy@example.com", "Legacy Course")
            )
            connection.execute(
                "INSERT INTO students (id, name, email, course) VALUES (?, ?, ?, ?)",
                (8, "Null Course Student", "nullcourse@example.com", None)
            )
            connection.commit()
        finally:
            connection.close()

        original_database = application.DATABASE
        try:
            application.DATABASE = legacy_database
            application.init_db()
            connection = sqlite3.connect(legacy_database)
            try:
                students = connection.execute(
                    "SELECT name, roll_number FROM students ORDER BY id"
                ).fetchall()
                courses = connection.execute(
                    "SELECT name FROM courses ORDER BY id"
                ).fetchall()
            finally:
                connection.close()
            self.assertEqual(
                students,
                [
                    ("Legacy Student", "LEGACY-7"),
                    ("Null Course Student", "LEGACY-8"),
                ]
            )
            self.assertEqual(
                courses,
                [("Legacy Course",), ("Unassigned course",)]
            )
        finally:
            application.DATABASE = original_database
            application.init_db()

    def test_health_and_legacy_students_route(self):
        self.assertEqual(self.client.get("/health").json["status"], "healthy")
        response = self.client.get("/students")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/#students")


if __name__ == "__main__":
    unittest.main()
