let students = [];
let courses = [];
let messageTimer;

function escapeHTML(value) {
    return String(value ?? "").replace(/[&<>"']/g, character => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
    })[character]);
}

async function api(path, options = {}) {
    const response = await fetch(path, {
        ...options,
        headers: {
            ...(options.body ? { "Content-Type": "application/json" } : {}),
            ...options.headers
        }
    });
    const isJson = response.headers.get("content-type")?.includes("application/json");
    const result = isJson ? await response.json() : null;

    if (!response.ok) {
        throw new Error(result?.error || `Request failed (${response.status}).`);
    }

    return result;
}

function hideMessage() {
    window.clearTimeout(messageTimer);
    const element = document.getElementById("appMessage");
    element.hidden = true;
}

function showMessage(message, isError = false) {
    const element = document.getElementById("appMessage");
    const textElement = document.getElementById("appMessageText");
    textElement.textContent = message;
    element.classList.toggle("error", isError);
    element.hidden = false;
    window.clearTimeout(messageTimer);
    messageTimer = window.setTimeout(() => {
        element.hidden = true;
    }, 5000);
}

document.getElementById("appMessageClose").addEventListener("click", hideMessage);

async function loadData() {
    const [studentData, courseData] = await Promise.all([
        api("/api/students"),
        api("/api/courses")
    ]);
    students = studentData;
    courses = courseData;
    renderAll();
}

function getStudentCourses(student) {
    return (student.courseIds || [])
        .map(id => courses.find(course => course.id === id))
        .filter(Boolean);
}

function updateDashboard() {
    document.getElementById("totalStudents").textContent = students.length;
    document.getElementById("totalCourses").textContent = courses.length;
    document.getElementById("totalEnrollments").textContent = students.reduce(
        (total, student) => total + (student.courseIds?.length || 0),
        0
    );
    document.getElementById("activeStudents").textContent = students.filter(
        student => student.status === "Active"
    ).length;
}

const studentForm = document.getElementById("studentForm");
const studentSubmitButton = document.getElementById("studentSubmit");

studentForm.addEventListener("submit", async event => {
    event.preventDefault();

    const id = document.getElementById("studentId").value;
    const student = {
        name: document.getElementById("studentName").value.trim(),
        email: document.getElementById("studentEmail").value.trim().toLowerCase(),
        rollNumber: document.getElementById("rollNumber").value.trim(),
        department: document.getElementById("studentDepartment").value,
        year: document.getElementById("studentYear").value,
        status: document.getElementById("studentStatus").value
    };

    if (!student.name || !student.email || !student.rollNumber || !student.department || !student.year) {
        showMessage("Please fill in all required student fields.", true);
        return;
    }

    studentSubmitButton.disabled = true;
    try {
        await api(id ? `/api/students/${id}` : "/api/students", {
            method: id ? "PUT" : "POST",
            body: JSON.stringify(student)
        });
        resetStudentForm();
        await loadData();
        showMessage(id ? "Student updated." : "Student added.");
    } catch (error) {
        showMessage(error.message, true);
    } finally {
        studentSubmitButton.disabled = false;
    }
});

function resetStudentForm() {
    studentForm.reset();
    document.getElementById("studentId").value = "";
    studentSubmitButton.textContent = "+ Add Student";
    document.getElementById("cancelEdit").hidden = true;
}

function editStudent(id) {
    const student = students.find(item => item.id === id);
    if (!student) return;

    document.getElementById("studentId").value = student.id;
    document.getElementById("studentName").value = student.name;
    document.getElementById("studentEmail").value = student.email;
    document.getElementById("rollNumber").value = student.rollNumber;
    document.getElementById("studentDepartment").value = student.department;
    document.getElementById("studentYear").value = student.year;
    document.getElementById("studentStatus").value = student.status;
    studentSubmitButton.textContent = "Save Changes";
    document.getElementById("cancelEdit").hidden = false;
    studentForm.scrollIntoView({ behavior: "smooth", block: "center" });
    document.getElementById("studentName").focus({ preventScroll: true });
}

async function deleteStudent(id) {
    const student = students.find(item => item.id === id);
    if (!student || !confirm(`Delete student ${student.name}?`)) return;

    try {
        await api(`/api/students/${id}`, { method: "DELETE" });
        if (document.getElementById("studentId").value === String(id)) {
            resetStudentForm();
        }
        await loadData();
        showMessage("Student deleted.");
    } catch (error) {
        showMessage(error.message, true);
    }
}

document.getElementById("cancelEdit").addEventListener("click", resetStudentForm);
document.getElementById("studentSearch").addEventListener("input", renderStudents);
document.getElementById("studentStatusFilter").addEventListener("change", renderStudents);

function renderStudents() {
    const table = document.getElementById("studentTable");
    const query = document.getElementById("studentSearch").value.trim().toLowerCase();
    const statusFilter = document.getElementById("studentStatusFilter").value;

    const filteredStudents = students.filter(student => {
        if (statusFilter && student.status !== statusFilter) {
            return false;
        }
        if (!query) {
            return true;
        }
        return [
            student.name,
            student.email,
            student.rollNumber,
            student.department,
            student.year
        ].some(value => value.toLowerCase().includes(query));
    });

    if (filteredStudents.length === 0) {
        table.innerHTML = `
            <tr>
                <td colspan="7" class="empty-state">No students found.</td>
            </tr>
        `;
        return;
    }

    table.innerHTML = filteredStudents.map(student => {
        const studentCourses = getStudentCourses(student);
        const coursesMarkup = studentCourses.length === 0
            ? `<span class="muted-text">None</span>`
            : `<div class="course-pills">${studentCourses.map(course => `
                <span class="course-pill" title="${escapeHTML(course.name)}">${escapeHTML(course.code)}</span>
            `).join("")}</div>`;

        return `
            <tr>
                <td>
                    <strong>${escapeHTML(student.name)}</strong><br>
                    <small class="muted-text">${escapeHTML(student.email)}</small>
                </td>
                <td>${escapeHTML(student.rollNumber)}</td>
                <td>${escapeHTML(student.department)}</td>
                <td>${escapeHTML(student.year)}</td>
                <td>
                    <span class="badge ${student.status === "Active" ? "active" : "inactive"}">
                        ${escapeHTML(student.status)}
                    </span>
                </td>
                <td>${coursesMarkup}</td>
                <td>
                    <button type="button" class="secondary-btn" data-action="edit-student" data-id="${student.id}">Edit</button>
                    <button type="button" class="secondary-btn" data-action="delete-student" data-id="${student.id}">Delete</button>
                </td>
            </tr>
        `;
    }).join("");
}

document.getElementById("studentTable").addEventListener("click", event => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    const id = Number(button.dataset.id);
    if (button.dataset.action === "edit-student") {
        editStudent(id);
    } else if (button.dataset.action === "delete-student") {
        deleteStudent(id);
    }
});

const courseForm = document.getElementById("courseForm");
const courseSubmitButton = document.getElementById("courseSubmit");

courseForm.addEventListener("submit", async event => {
    event.preventDefault();

    const id = document.getElementById("courseId").value;
    const course = {
        name: document.getElementById("courseName").value.trim(),
        code: document.getElementById("courseCode").value.trim().toUpperCase(),
        instructor: document.getElementById("courseInstructor").value.trim(),
        credits: Number(document.getElementById("courseCredits").value)
    };

    if (!course.name || !course.code || !course.instructor) {
        showMessage("Please fill in all required course fields.", true);
        return;
    }

    if (!Number.isInteger(course.credits) || course.credits < 1 || course.credits > 10) {
        showMessage("Credits must be a whole number from 1 to 10.", true);
        return;
    }

    courseSubmitButton.disabled = true;
    try {
        await api(id ? `/api/courses/${id}` : "/api/courses", {
            method: id ? "PUT" : "POST",
            body: JSON.stringify(course)
        });
        resetCourseForm();
        await loadData();
        showMessage(id ? "Course updated." : "Course added.");
    } catch (error) {
        showMessage(error.message, true);
    } finally {
        courseSubmitButton.disabled = false;
    }
});

function resetCourseForm() {
    courseForm.reset();
    document.getElementById("courseId").value = "";
    document.getElementById("courseCredits").value = 3;
    courseSubmitButton.textContent = "+ Add Course";
    document.getElementById("cancelCourseEdit").hidden = true;
}

function editCourse(id) {
    const course = courses.find(item => item.id === id);
    if (!course) return;

    document.getElementById("courseId").value = course.id;
    document.getElementById("courseName").value = course.name;
    document.getElementById("courseCode").value = course.code;
    document.getElementById("courseInstructor").value = course.instructor;
    document.getElementById("courseCredits").value = course.credits;
    courseSubmitButton.textContent = "Save Changes";
    document.getElementById("cancelCourseEdit").hidden = false;
    courseForm.scrollIntoView({ behavior: "smooth", block: "center" });
    document.getElementById("courseName").focus({ preventScroll: true });
}

async function deleteCourse(id) {
    const course = courses.find(item => item.id === id);
    if (!course || !confirm(`Delete course "${course.name}"?`)) return;

    try {
        await api(`/api/courses/${id}`, { method: "DELETE" });
        if (document.getElementById("courseId").value === String(id)) {
            resetCourseForm();
        }
        await loadData();
        showMessage("Course deleted.");
    } catch (error) {
        showMessage(error.message, true);
    }
}

document.getElementById("cancelCourseEdit").addEventListener(
    "click",
    resetCourseForm
);

function renderCourses() {
    const grid = document.getElementById("courseGrid");
    if (courses.length === 0) {
        grid.innerHTML = `
            <div class="empty-state">
                No courses added yet. Create your first course above.
            </div>
        `;
        return;
    }

    grid.innerHTML = courses.map(course => `
        <div class="course-card">
            <div class="course-code">${escapeHTML(course.code)}</div>
            <h3>${escapeHTML(course.name)}</h3>
            <p>Instructor: ${escapeHTML(course.instructor)}</p>
            <p>Credits: ${escapeHTML(course.credits)}</p>
            <p>Enrolled Students: ${students.filter(student =>
                (student.courseIds || []).includes(course.id)
            ).length}</p>
            <div class="course-actions">
                <button type="button" class="secondary-btn" data-action="edit-course" data-id="${course.id}">Edit</button>
                <button type="button" class="secondary-btn" data-action="delete-course" data-id="${course.id}">Delete</button>
            </div>
        </div>
    `).join("");
}

document.getElementById("courseGrid").addEventListener("click", event => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    const id = Number(button.dataset.id);
    if (button.dataset.action === "edit-course") {
        editCourse(id);
    } else if (button.dataset.action === "delete-course") {
        deleteCourse(id);
    }
});

const enrollmentForm = document.getElementById("enrollmentForm");
const enrollSubmitButton = document.getElementById("enrollSubmit");
const enrollStudentSelect = document.getElementById("enrollStudent");
const enrollCourseSelect = document.getElementById("enrollCourse");

enrollmentForm.addEventListener("submit", async event => {
    event.preventDefault();
    const studentId = Number(enrollStudentSelect.value);
    const courseId = Number(enrollCourseSelect.value);

    if (!Number.isInteger(studentId) || studentId < 1 || !Number.isInteger(courseId) || courseId < 1) {
        showMessage("Select a valid student and course.", true);
        return;
    }

    enrollSubmitButton.disabled = true;
    try {
        await api("/api/enrollments", {
            method: "POST",
            body: JSON.stringify({ studentId, courseId })
        });
        enrollmentForm.reset();
        await loadData();
        showMessage("Student enrolled in the course.");
    } catch (error) {
        showMessage(error.message, true);
    } finally {
        renderEnrollmentOptions();
    }
});

async function removeEnrollment(studentId, courseId) {
    const student = students.find(item => item.id === studentId);
    const course = courses.find(item => item.id === courseId);
    if (!student || !course) return;
    if (!confirm(`Remove ${student.name} from ${course.name}?`)) return;

    try {
        await api(`/api/enrollments/${studentId}/${courseId}`, {
            method: "DELETE"
        });
        await loadData();
        showMessage("Enrollment removed.");
    } catch (error) {
        showMessage(error.message, true);
    }
}

function renderCourseSelectOptions() {
    const selectedStudentId = Number(enrollStudentSelect.value);
    const selectedStudent = students.find(item => item.id === selectedStudentId);
    const enrolledIds = new Set(selectedStudent?.courseIds || []);
    const previousCourse = enrollCourseSelect.value;

    const availableCount = courses.filter(course => !enrolledIds.has(course.id)).length;
    const placeholder = courses.length === 0
        ? "No courses available"
        : (selectedStudent && availableCount === 0
            ? "Student is enrolled in all courses"
            : "Choose a course");

    enrollCourseSelect.innerHTML = `
        <option value="">${placeholder}</option>
        ${courses.map(course => {
            const alreadyEnrolled = enrolledIds.has(course.id);
            return `
                <option value="${course.id}" ${alreadyEnrolled ? "disabled" : ""}>
                    ${escapeHTML(course.name)} (${escapeHTML(course.code)})${alreadyEnrolled ? " - Enrolled" : ""}
                </option>
            `;
        }).join("")}
    `;

    const hasSelectableCourse = courses.length > 0 && (!selectedStudent || availableCount > 0);
    enrollCourseSelect.disabled = !hasSelectableCourse;
    enrollSubmitButton.disabled = students.length === 0 || !hasSelectableCourse;

    if (
        hasSelectableCourse &&
        courses.some(course => String(course.id) === previousCourse && !enrolledIds.has(course.id))
    ) {
        enrollCourseSelect.value = previousCourse;
    } else {
        enrollCourseSelect.value = "";
    }
}

function renderEnrollmentOptions() {
    const selectedStudent = enrollStudentSelect.value;

    enrollStudentSelect.innerHTML = `
        <option value="">${students.length === 0 ? "No students available" : "Choose a student"}</option>
        ${students.map(student => `
            <option value="${student.id}">
                ${escapeHTML(student.name)} (${escapeHTML(student.rollNumber)})
            </option>
        `).join("")}
    `;
    enrollStudentSelect.disabled = students.length === 0;

    if (students.some(student => String(student.id) === selectedStudent)) {
        enrollStudentSelect.value = selectedStudent;
    }

    renderCourseSelectOptions();
}

enrollStudentSelect.addEventListener("change", renderCourseSelectOptions);

function renderEnrollments() {
    const table = document.getElementById("enrollmentTable");
    const enrolledStudents = students.filter(
        student => (student.courseIds || []).length > 0
    );

    if (enrolledStudents.length === 0) {
        table.innerHTML = `
            <tr>
                <td colspan="3" class="empty-state">No enrollments yet.</td>
            </tr>
        `;
        return;
    }

    table.innerHTML = enrolledStudents.map(student => `
        <tr>
            <td><strong>${escapeHTML(student.name)}</strong></td>
            <td>${escapeHTML(student.rollNumber)}</td>
            <td>
                ${getStudentCourses(student).map(course => `
                    <div class="enrollment-row">
                        <span>
                            ${escapeHTML(course.name)}
                            <small class="muted-text">(${escapeHTML(course.code)})</small>
                        </span>
                        <button type="button" class="secondary-btn"
                            data-action="remove-enrollment"
                            data-student-id="${student.id}"
                            data-course-id="${course.id}">
                            Remove
                        </button>
                    </div>
                `).join("")}
            </td>
        </tr>
    `).join("");
}

document.getElementById("enrollmentTable").addEventListener("click", event => {
    const button = event.target.closest("button[data-action='remove-enrollment']");
    if (!button) return;
    removeEnrollment(
        Number(button.dataset.studentId),
        Number(button.dataset.courseId)
    );
});

function renderAll() {
    updateDashboard();
    renderStudents();
    renderCourses();
    renderEnrollmentOptions();
    renderEnrollments();
}

function setActiveNav(hash) {
    const targetHash = hash || "#dashboard";
    const navLinks = Array.from(document.querySelectorAll(".nav"));
    const matchingLink = navLinks.find(link => link.getAttribute("href") === targetHash) || navLinks[0];
    navLinks.forEach(nav => {
        nav.classList.toggle("active", nav === matchingLink);
    });
}

function syncNavOnScroll() {
    const sections = ["#dashboard", "#students", "#courses", "#enrollments"]
        .map(id => document.querySelector(id))
        .filter(Boolean);
    const offset = window.scrollY + 140;
    let current = "#dashboard";
    for (const section of sections) {
        if (section.offsetTop <= offset) {
            current = `#${section.id}`;
        }
    }
    setActiveNav(current);
}

document.querySelectorAll(".nav").forEach(link => {
    link.addEventListener("click", () => {
        setActiveNav(link.getAttribute("href"));
    });
});

window.addEventListener("hashchange", () => setActiveNav(window.location.hash));
window.addEventListener("scroll", syncNavOnScroll, { passive: true });
setActiveNav(window.location.hash);

window.editStudent = editStudent;
window.deleteStudent = deleteStudent;
window.editCourse = editCourse;
window.deleteCourse = deleteCourse;
window.removeEnrollment = removeEnrollment;

loadData().catch(error => {
    console.error("Could not load management data:", error);
    showMessage(`Could not load data: ${error.message}`, true);
});
