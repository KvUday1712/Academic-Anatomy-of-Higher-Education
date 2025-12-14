import os
from datetime import datetime, timedelta, date
from flask_cors import cross_origin    # ensure this import exists near top with your other imports

from flask import Flask, request, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import (
    JWTManager, create_access_token,
    jwt_required, get_jwt_identity
)
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# -----------------------------------------------------------------------------
# Paths / App setup
# -----------------------------------------------------------------------------

# BASE_DIR -> .../SAPT/backend
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# FRONTEND_FOLDER -> .../SAPT/frontend
FRONTEND_FOLDER = os.path.join(BASE_DIR, "..", "frontend")

app = Flask(__name__)

# TODO: change this to your MySQL credentials
# Example: "mysql+pymysql://user:password@localhost/student_tracker"
app.config["SQLALCHEMY_DATABASE_URI"] = "mysql+pymysql://root:Password%4012@127.0.0.1:3306/student_tracker"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

app.config["JWT_SECRET_KEY"] = "super-secret-key-change-me"  # change in production

# uploads folder stays inside backend/
app.config["UPLOAD_FOLDER"] = os.path.join(BASE_DIR, "uploads")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

db = SQLAlchemy(app)
jwt = JWTManager(app)
CORS(app)


# -----------------------------------------------------------------------------
# Models
# -----------------------------------------------------------------------------

class Course(db.Model):
    __tablename__ = "courses"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    code = db.Column(db.String(50), unique=True, nullable=True)

    staff = db.relationship("User", back_populates="course", lazy=True)
    students = db.relationship("Student", back_populates="course", lazy=True)


class User(db.Model):
    """
    Generic user model:
      - role: "admin" | "staff" | "student"
      - staff: course_id is used to link staff to a Course
    """
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    username = db.Column(db.String(120), unique=True, nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # admin/staff/student

    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=True)
    course = db.relationship("Course", back_populates="staff")

    student = db.relationship("Student", back_populates="user", uselist=False)

    def set_password(self, raw):
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw):
        return check_password_hash(self.password_hash, raw)


class Student(db.Model):
    __tablename__ = "students"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=True)

    user = db.relationship("User", back_populates="student")
    course = db.relationship("Course", back_populates="students")

    attendance_records = db.relationship("AttendanceRecord", back_populates="student", lazy=True)
    results = db.relationship("Result", back_populates="student", lazy=True)


class AttendanceRecord(db.Model):
    __tablename__ = "attendance_records"
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    status = db.Column(db.String(20), nullable=False)  # "present"/"absent"

    student = db.relationship("Student", back_populates="attendance_records")
    course = db.relationship("Course")


class Result(db.Model):
    __tablename__ = "results"
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    subject_name = db.Column(db.String(255), nullable=False)
    ia1 = db.Column(db.Integer, nullable=False)
    ia2 = db.Column(db.Integer, nullable=False)
    ia3 = db.Column(db.Integer, nullable=False)
    attendance = db.Column(db.Integer, nullable=False)  # percentage

    student = db.relationship("Student", back_populates="results")


class Subject(db.Model):
    __tablename__ = "subjects"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    course_name = db.Column(db.String(255), nullable=True)
    staff_name = db.Column(db.String(255), nullable=True)
    session_name = db.Column(db.String(255), nullable=True)


class LeaveRequest(db.Model):
    __tablename__ = "leave_requests"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    reason = db.Column(db.Text, nullable=False)
    from_date = db.Column(db.Date, nullable=False)
    to_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), default="pending")  # pending/approved/rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    student = db.relationship("Student")


class ReferenceBook(db.Model):
    __tablename__ = "reference_books"
    id = db.Column(db.Integer, primary_key=True)
    author = db.Column(db.String(255), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    pdf_url = db.Column(db.String(512), nullable=False)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# -----------------------------------------------------------------------------
# Helper functions
# -----------------------------------------------------------------------------

def course_to_str(course: Course):
    if not course:
        return ""
    return course.name or course.code or ""


def student_to_dict(student: Student):
    return {
        "id": student.id,
        "name": student.user.full_name,
        "full_name": student.user.full_name,
        "email": student.user.email,
        "course": course_to_str(student.course),
        "course_name": course_to_str(student.course),
    }


def result_to_dict(result: Result):
    return {
        "id": result.id,
        "student_id": result.student_id,
        "student_name": result.student.user.full_name if result.student and result.student.user else None,
        "subject_name": result.subject_name,
        "ia1": result.ia1,
        "ia2": result.ia2,
        "ia3": result.ia3,
        "attendance": result.attendance,
    }

def subject_to_dict(subject: "Subject"):
    return {
        "id": subject.id,
        "name": subject.name,
        "course": subject.course_name,
        "staff": subject.staff_name,
        "session": subject.session_name,
    }


def attendance_to_dict(record: AttendanceRecord):
    return {
        "id": record.id,
        "date": record.date.isoformat(),
        "course": course_to_str(record.course),
        "student_id": record.student_id,
        "student_name": record.student.user.full_name if record.student and record.student.user else None,
        "status": record.status,
    }


# -----------------------------------------------------------------------------
# Auth routes
# -----------------------------------------------------------------------------

@app.route("/api/auth/login", methods=["POST"])
def login():
    """
    Request JSON (frontend sends):
      {
        "username": "...",  # or email
        "email": "...",     # same as username
        "password": "...",
        "user_type": "admin" | "staff" | "student"
      }
    """
    data = request.get_json() or {}
    username = data.get("username") or data.get("email")
    password = data.get("password")
    user_type = data.get("user_type")

    if not username or not password:
        return jsonify({"error": "Missing credentials"}), 400

    # find user by email or username
    user = User.query.filter(
        (User.email == username) | (User.username == username)
    ).first()

    if not user or not user.check_password(password):
        # Let frontend fallback to local admin/staff/student storage
        return jsonify({"error": "Invalid credentials"}), 401

    # Optional: check that role matches requested user_type
    if user_type and user.role.lower() != user_type.lower():
        return jsonify({"error": "Role mismatch"}), 403

    identity = str(user.id)
    additional_claims = {"role": user.role}
    access_token = create_access_token(
        identity=identity,
        additional_claims=additional_claims,
        expires_delta=timedelta(hours=8),
    )

    # Build extra info for frontend convenience
    response_payload = {
        "access_token": access_token,
        "role": user.role,
        "user": {
            "id": user.id,
            "full_name": user.full_name,
            "username": user.username,
            "email": user.email,
        },
    }

    # If student, include student_id and course_name
    if user.role.lower() == "student" and user.student:
        response_payload["student_id"] = user.student.id
        response_payload["student_name"] = user.full_name
        response_payload["course_name"] = course_to_str(user.student.course)

    # If staff, include course_name
    if user.role.lower() == "staff":
        response_payload["course_name"] = course_to_str(user.course)

    return jsonify(response_payload), 200


@app.route("/api/auth/me", methods=["GET"])
@jwt_required()
def me():
    current_user_id = get_jwt_identity()
    try:
        current_user_id = int(current_user_id)
    except (TypeError, ValueError):
        # handle missing/invalid id
        return jsonify({"error": "Invalid token identity"}), 401
    user = User.query.get(current_user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    payload = {
        "id": user.id,
        "name": user.full_name,
        "full_name": user.full_name,
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "user_type": user.role,
    }

    if user.role.lower() == "student" and user.student:
        payload["student_id"] = user.student.id
        payload["student_name"] = user.full_name
        payload["course_name"] = course_to_str(user.student.course)

    if user.role.lower() == "staff":
        payload["course_name"] = course_to_str(user.course)

    return jsonify(payload), 200


# -----------------------------------------------------------------------------
# Courses
# -----------------------------------------------------------------------------

@app.route("/api/courses/", methods=["GET", "POST"])
@jwt_required(optional=True)
def courses():
    if request.method == "GET":
        courses = Course.query.order_by(Course.name.asc()).all()
        return jsonify([
            {"id": c.id, "name": c.name, "code": c.code}
            for c in courses
        ])

    # POST: create new course
    data = request.get_json() or {}
    name = data.get("name")
    code = data.get("code")

    if not name:
        return jsonify({"error": "Course name required"}), 400

    if Course.query.filter_by(name=name).first():
        return jsonify({"error": "Course already exists"}), 400

    course = Course(name=name, code=code)
    db.session.add(course)
    db.session.commit()
    return jsonify({"id": course.id, "name": course.name, "code": course.code}), 201


# -----------------------------------------------------------------------------
# Staff creation (Add Staff)
# -----------------------------------------------------------------------------

@app.route("/api/staff/", methods=["POST"])
@jwt_required(optional=True)  # you can enforce admin-only later
def add_staff():
    data = request.get_json() or {}
    name = data.get("name")
    email = data.get("email")
    course_str = data.get("course")
    password = data.get("password")

    if not all([name, email, password]):
        return jsonify({"error": "Missing required fields"}), 400

    existing = User.query.filter_by(email=email).first()
    if existing:
        return jsonify({"error": "User with this email already exists"}), 400

    course = None
    if course_str:
        course = Course.query.filter(
            (Course.name == course_str) | (Course.code == course_str)
        ).first()

    user = User(
        full_name=name,
        email=email,
        username=email,
        role="staff",
        course=course,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    return jsonify({
        "id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "course_name": course_to_str(user.course),
        "role": user.role,
    }), 201


# -----------------------------------------------------------------------------
# Students
# -----------------------------------------------------------------------------

@app.route("/api/students/", methods=["GET"])
@jwt_required(optional=True)
def list_students():
    course_filter = request.args.get("course")

    query = Student.query.join(User).outerjoin(Course)
    if course_filter:
        query = query.filter(
            (Course.name == course_filter) | (Course.code == course_filter)
        )

    students = query.all()
    return jsonify([student_to_dict(s) for s in students]), 200


# (Optional) For future: create student endpoint
@app.route("/api/students/", methods=["POST"])
@jwt_required(optional=True)
def create_student():
    data = request.get_json() or {}
    name = data.get("name")
    email = data.get("email")
    course_str = data.get("course")
    password = data.get("password") or "password123"

    if not all([name, email]):
        return jsonify({"error": "Missing fields"}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "Email already registered"}), 400

    course = None
    if course_str:
        course = Course.query.filter(
            (Course.name == course_str) | (Course.code == course_str)
        ).first()

    user = User(
        full_name=name,
        email=email,
        username=email,
        role="student",
    )
    user.set_password(password)
    db.session.add(user)
    db.session.flush()

    student = Student(user_id=user.id, course=course)
    db.session.add(student)
    db.session.commit()

    return jsonify({
        "id": student.id,
        "name": name,
        "email": email,
        "course": course_to_str(course),
    }), 201


# -----------------------------------------------------------------------------
# Attendance
# -----------------------------------------------------------------------------

@app.route("/api/attendance/", methods=["POST"])
@jwt_required(optional=True)
def submit_attendance():
    """
    Expects payload like:
    {
      "date": "YYYY-MM-DD",
      "course": "CSE",
      "records": [
        { "student_id": 1, "student_name": "Alice", "status": "present" },
        ...
      ]
    }
    """
    data = request.get_json() or {}
    date_str = data.get("date")
    course_str = data.get("course")
    records = data.get("records") or []

    if not date_str:
        return jsonify({"error": "date is required"}), 400

    try:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Invalid date format (expected YYYY-MM-DD)"}), 400

    course = None
    if course_str:
        course = Course.query.filter(
            (Course.name == course_str) | (Course.code == course_str)
        ).first()

    # Simple approach: delete existing records for that date+course then insert
    q = AttendanceRecord.query.filter_by(date=d)
    if course:
        q = q.filter(AttendanceRecord.course_id == course.id)
    existing = q.all()
    for e in existing:
        db.session.delete(e)

    for rec in records:
        sid = rec.get("student_id")
        sname = rec.get("student_name")
        status = (rec.get("status") or "").lower() or "present"

        student = None
        if sid:
            student = Student.query.get(sid)
        if not student and sname:
            student = Student.query.join(User).filter(User.full_name == sname).first()

        if not student:
            # skip unknown students
            continue

        ar = AttendanceRecord(
            date=d,
            course_id=course.id if course else None,
            student_id=student.id,
            status=status,
        )
        db.session.add(ar)

    db.session.commit()
    return jsonify({"msg": "Attendance saved"}), 201


@app.route("/api/attendance/", methods=["GET"])
@jwt_required(optional=True)
def get_attendance():
    """
    Frontend calls with ?date=YYYY-MM-DD
    (you can extend with ?course=)
    """
    date_str = request.args.get("date")
    course_str = request.args.get("course")

    if not date_str:
        return jsonify({"error": "date query parameter required"}), 400

    try:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Invalid date format (expected YYYY-MM-DD)"}), 400

    query = AttendanceRecord.query.filter_by(date=d)

    if course_str:
        course = Course.query.filter(
            (Course.name == course_str) | (Course.code == course_str)
        ).first()
        if course:
            query = query.filter(AttendanceRecord.course_id == course.id)

    records = query.all()
    return jsonify([attendance_to_dict(r) for r in records]), 200


# -----------------------------------------------------------------------------
# Leave Requests
# -----------------------------------------------------------------------------

@app.route("/api/leaves/", methods=["OPTIONS", "POST"])
@cross_origin()
@jwt_required(optional=True)
def create_leave_request():
    # For preflight
    if request.method == "OPTIONS":
        return jsonify({}), 200

    # DEBUG: print the raw request body + JSON
    raw = request.get_data(as_text=True)
    print("---- RAW REQUEST BODY ----")
    print(raw)
    try:
        data = request.get_json(silent=True) or {}
    except Exception as e:
        print("get_json error:", e)
        data = {}

    print("---- PARSED JSON ----")
    print(repr(data))

    # Defensive: if subject present, coerce to string once and for all
    if "subject" in data and data["subject"] is not None:
        try:
            data["subject"] = str(data["subject"])
        except Exception:
            data["subject"] = ""

    # now continue using `data` (instead of calling request.get_json() again)
    student_id = data.get("student_id")
    reason = data.get("reason")
    from_date_str = data.get("from_date")
    to_date_str = data.get("to_date")
    
    # Optional extras we ignore for DB (but accept without error)
    requester_name = data.get("requester_name")
    title = data.get("title")
    subject = data.get("subject")   # some other code may be sending this

    # Just to be safe: normalize subject if present
    if subject is not None and not isinstance(subject, str):
        subject = str(subject)

    # Validate required fields
    if not all([student_id, reason, from_date_str, to_date_str]):
        return jsonify({"error": "Missing fields (student_id, reason, from_date, to_date required)"}), 400

    # Ensure student_id is an integer
    try:
        student_id = int(student_id)
    except (TypeError, ValueError):
        return jsonify({"error": "student_id must be an integer"}), 400

    # Parse dates (YYYY-MM-DD)
    try:
        from_date = datetime.strptime(from_date_str, "%Y-%m-%d").date()
        to_date = datetime.strptime(to_date_str, "%Y-%m-%d").date()
    except Exception:
        return jsonify({"error": "Invalid date format (expected YYYY-MM-DD)"}), 400

    # Check student exists
    student = Student.query.get(student_id)
    if not student:
        return jsonify({"error": "Student not found"}), 404

    leave = LeaveRequest(
        student_id=student_id,
        reason=reason,
        from_date=from_date,
        to_date=to_date
    )

    try:
        db.session.add(leave)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print("Error creating leave request:", e)
        return jsonify({"error": "Could not create leave request"}), 500

    # DEBUG confirmation
    print("=== /api/leaves/ created leave id:", leave.id, "===")

    return jsonify({
        "id": leave.id,
        "student_id": leave.student_id,
        "reason": leave.reason,
        "from_date": leave.from_date.isoformat(),
        "to_date": leave.to_date.isoformat(),
        "status": leave.status,
        "created_at": leave.created_at.isoformat(),
        # echo extras (not stored) if you like:
        "requester_name": requester_name,
        "title": title,
        "subject": subject,
    }), 201


# -----------------------------------------------------------------------------
# Subjects
# -----------------------------------------------------------------------------

@app.route("/api/subjects/", methods=["GET", "POST"])
@jwt_required(optional=True)
def subjects():
    if request.method == "GET":
        subjects = Subject.query.order_by(Subject.name.asc()).all()
        return jsonify([subject_to_dict(s) for s in subjects]), 200

    # POST - create a new subject
    data = request.get_json() or {}

    name = data.get("name") or data.get("subjectName")
    course_name = data.get("course") or data.get("courseName")
    staff_name = data.get("staff") or data.get("staffName")
    session_name = data.get("session") or data.get("sessionName")

    if not name:
        return jsonify({"error": "Subject name is required"}), 400

    new_subject = Subject(
        name=name,
        course_name=course_name,
        staff_name=staff_name,
        session_name=session_name,
    )
    db.session.add(new_subject)
    db.session.commit()

    return jsonify(subject_to_dict(new_subject)), 201


@app.route("/api/subjects/<int:subject_id>", methods=["DELETE"])
@jwt_required(optional=True)
def delete_subject(subject_id):
    s = Subject.query.get(subject_id)
    if not s:
        return jsonify({"error": "Subject not found"}), 404

    db.session.delete(s)
    db.session.commit()
    return jsonify({"msg": "Deleted"}), 200



# -----------------------------------------------------------------------------
# Results
# -----------------------------------------------------------------------------

@app.route("/api/results/", methods=["POST"])
@jwt_required(optional=True)
def add_result():
    data = request.get_json() or {}
    student_id = data.get("student_id")
    student_name = data.get("student_name")
    subject_name = data.get("subject_name")
    ia1 = data.get("ia1")
    ia2 = data.get("ia2")
    ia3 = data.get("ia3")
    attendance = data.get("attendance")

    if not subject_name:
        return jsonify({"error": "subject_name is required"}), 400

    student = None
    if student_id:
        student = Student.query.get(student_id)
    if not student and student_name:
        student = Student.query.join(User).filter(User.full_name == student_name).first()

    if not student:
        return jsonify({"error": "Student not found"}), 404

    try:
        ia1 = int(ia1)
        ia2 = int(ia2)
        ia3 = int(ia3)
        attendance = int(attendance)
    except (TypeError, ValueError):
        return jsonify({"error": "Marks and attendance must be integers"}), 400

    res = Result(
        student_id=student.id,
        subject_name=subject_name,
        ia1=ia1,
        ia2=ia2,
        ia3=ia3,
        attendance=attendance,
    )
    db.session.add(res)
    db.session.commit()

    return jsonify(result_to_dict(res)), 201


@app.route("/api/results/", methods=["GET"])
@jwt_required(optional=True)
def get_results():
    student_id = request.args.get("student_id")
    student_name = request.args.get("student_name")

    query = Result.query.join(Student).join(User)

    if student_id:
        query = query.filter(Result.student_id == int(student_id))
    elif student_name:
        query = query.filter(User.full_name == student_name)

    results = query.all()
    return jsonify([result_to_dict(r) for r in results]), 200


# -----------------------------------------------------------------------------
# Reference Books
# -----------------------------------------------------------------------------

@app.route("/api/reference-books/", methods=["POST"])
@jwt_required(optional=True)
def upload_reference_book():
    """
    Expects multipart/form-data with: author, title, pdf
    """
    author = request.form.get("author")
    title = request.form.get("title")
    pdf = request.files.get("pdf")

    if not all([author, title, pdf]):
        return jsonify({"error": "author, title and pdf are required"}), 400

    filename = secure_filename(pdf.filename)
    if not filename.lower().endswith(".pdf"):
        return jsonify({"error": "Only PDF files allowed"}), 400

    save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    # Avoid overwrite by adding timestamp if needed
    if os.path.exists(save_path):
        base, ext = os.path.splitext(filename)
        filename = f"{base}_{int(datetime.utcnow().timestamp())}{ext}"
        save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)

    pdf.save(save_path)

    # URL used by frontend
    pdf_url = f"/uploads/{filename}"

    current_user_id = None
    try:
        current_user_id = get_jwt_identity()
    except Exception:
        pass

    book = ReferenceBook(
        author=author,
        title=title,
        pdf_url=pdf_url,
        uploaded_by_id=current_user_id,
    )
    db.session.add(book)
    db.session.commit()

    return jsonify({
        "id": book.id,
        "author": book.author,
        "title": book.title,
        "pdf_url": book.pdf_url,
    }), 201


@app.route("/api/reference-books/", methods=["GET"])
@jwt_required(optional=True)
def list_reference_books():
    books = ReferenceBook.query.order_by(ReferenceBook.created_at.desc()).all()
    return jsonify([
        {
            "id": b.id,
            "author": b.author,
            "title": b.title,
            "pdf_url": b.pdf_url,
        }
        for b in books
    ]), 200


@app.route("/api/reference-books/<int:book_id>", methods=["DELETE"])
@jwt_required(optional=True)
def delete_reference_book(book_id):
    book = ReferenceBook.query.get(book_id)
    if not book:
        return jsonify({"error": "Book not found"}), 404

    # Optionally check role here (admin/staff only)
    db.session.delete(book)
    db.session.commit()
    return jsonify({"msg": "Deleted"}), 200


# Serve uploaded PDFs
@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


# -----------------------------------------------------------------------------
# Frontend serving (THIS is what fixes your 404)
# -----------------------------------------------------------------------------

@app.route("/")
def index():
    """Serve the main landing page."""
    return send_from_directory(FRONTEND_FOLDER, "main.html")


@app.route("/<path:path>")
def serve_frontend(path):
    """
    Serve any other file (HTML/CSS/JS/images) from the frontend folder,
    WITHOUT touching /api/... or /uploads/... routes (they are defined above).
    """
    
    file_path = os.path.join(FRONTEND_FOLDER, path)
    if os.path.isfile(file_path):
        return send_from_directory(FRONTEND_FOLDER, path)
    return jsonify({"error": "Not Found"}), 404


# -----------------------------------------------------------------------------
# CLI helper to create tables (run once)
# -----------------------------------------------------------------------------

@app.cli.command("init-db")
def init_db():
    """Initialize database tables."""
    db.create_all()
    print("Database tables created.")


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    # For dev only
    app.run(debug=True)
