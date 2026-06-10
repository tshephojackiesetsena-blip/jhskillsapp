import json
import os
import secrets
import string
import smtplib
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from functools import wraps

from flask import Flask, jsonify, redirect, render_template_string, request, send_from_directory, session, url_for
from werkzeug.exceptions import NotFound
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "jh_student_portal_secret_dev")
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

# Trust the reverse-proxy headers from Render/Heroku so HTTPS works correctly
# This is required for camera/microphone to work (browsers need a secure context)
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

MAX_DOCUMENT_MB = 5
ALLOWED_DOCUMENT_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "doc", "docx"}
LEARNER_DOCUMENT_TYPES = [
    {"id": "id_copy", "label": "Copy of ID", "description": "Certified or clear scan of South African ID or passport.", "required": True},
    {"id": "proof_of_address", "label": "Proof of Address", "description": "Utility bill, bank statement, or official proof not older than 3 months.", "required": True},
    {"id": "qualification", "label": "Qualifications", "description": "Latest certificate, statement of results, or academic proof.", "required": True},
    {"id": "cv", "label": "CV", "description": "Updated curriculum vitae in PDF or Word format.", "required": True},
    {"id": "funding_letter", "label": "Funding Letter", "description": "Bursary, NSFAS, or sponsor confirmation letter.", "required": False},
    {"id": "other_supporting", "label": "Other Supporting Documents", "description": "Any extra supporting files requested by the institution.", "required": False},
]
DOCUMENT_TYPE_LOOKUP = {item["id"]: item for item in LEARNER_DOCUMENT_TYPES}

DATA_DIR = os.path.join(app.root_path, "data")
LEARNER_UPLOADS_DIR = os.path.join(app.root_path, "static", "uploads", "learners")
LEARNER_DOCUMENTS_FILE = os.path.join(DATA_DIR, "learner_documents.json")
CENTRAL_UPLOADS_DIR = os.path.join(app.root_path, "static", "uploads", "documents")
CENTRAL_DOCUMENTS_FILE = os.path.join(DATA_DIR, "central_documents.json")
STUDENTS_FILE = os.path.join(DATA_DIR, "students.json")
MESSAGES_FILE = os.path.join(DATA_DIR, "messages.json")
MEET_ROOMS_FILE = os.path.join(DATA_DIR, "meet_rooms.json")
PENDING_FILE    = os.path.join(DATA_DIR, "pending_registrations.json")
VERIF_FILE      = os.path.join(DATA_DIR, "verification_tokens.json")

# ── Email config (set these environment variables on your server) ──────────
MAIL_HOST     = os.environ.get("MAIL_HOST", "smtp.gmail.com")
MAIL_PORT     = int(os.environ.get("MAIL_PORT", "587"))
MAIL_USER     = os.environ.get("MAIL_USER", "")        # e.g. noreply@jhholdings.co.za
MAIL_PASS     = os.environ.get("MAIL_PASS", "")
MAIL_FROM     = os.environ.get("MAIL_FROM", MAIL_USER)
APP_BASE_URL  = os.environ.get("APP_BASE_URL", "http://localhost:5000")

# ── SMS / OTP config (Twilio) ─────────────────────────────────────────────
TWILIO_SID    = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_TOKEN  = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM   = os.environ.get("TWILIO_FROM_NUMBER", "")  # e.g. +12345678900

JH_GROUP = {
    "name": "JH Student Services",
    "tagline": "Administration, learning support, and student success operations.",
    "companies": [
        {"id": "jh-skills", "name": "JH Skills", "focus": "Skills development and academic support.", "contact": "skills@jhholdings.co.za", "phone": "+27 12 100 2102", "status": "Active"},
        {"id": "jh-it", "name": "JH IT", "focus": "Technology support and systems enablement.", "contact": "it@jhholdings.co.za", "phone": "+27 12 100 2104", "status": "Active"},
    ],
}

LEARNING_INTERVENTIONS = [
    {"id": "INT-001", "name": "Digital Skills Cohort 2026", "programme": "Diploma in Information Technology", "participants": 120, "start_date": "2026-03-01", "end_date": "2026-11-30", "location": "Johannesburg Campus", "coordinator": "Lerato Khumalo", "expectations": "Complete all practical labs, workplace exposure, and core digital literacy tasks."},
    {"id": "INT-002", "name": "Business Administration Learnership", "programme": "Business Administration NQF 4", "participants": 85, "start_date": "2026-03-04", "end_date": "2026-10-28", "location": "Pretoria Campus", "coordinator": "Ayanda Mokoena", "expectations": "Maintain attendance, complete formative work, and participate in monthly reviews."},
]

STUDENT_TASKS = [
    {"title": "Submit network fundamentals worksheet", "module": "Network Systems", "due_date": "2026-05-28", "status": "In Progress", "comments": 4, "progress": 72},
    {"title": "Prepare presentation on cyber hygiene", "module": "Information Security", "due_date": "2026-05-30", "status": "To Do", "comments": 1, "progress": 28},
    {"title": "Complete database lab reflection", "module": "Database Systems", "due_date": "2026-06-01", "status": "Done", "comments": 2, "progress": 100},
]

STUDENT_NOTES = [
    {"title": "Math concept", "body": "Revise ratios, linear equations, and substitution before the Friday support class.", "date": "2026-05-24", "tone": "green"},
    {"title": "Biology concept", "body": "Review cell structure, organelles, and the distinction between plant and animal cells.", "date": "2026-05-22", "tone": "purple"},
]

TIMETABLE_ITEMS = [
    {"time": "08:30 AM", "lesson": "Network Systems", "teacher": "Mrs. Goodman", "location": "Lab B3", "day": "Monday"},
    {"time": "10:30 AM", "lesson": "English Communication", "teacher": "Ms. Melton", "location": "Room B2-158", "day": "Monday"},
    {"time": "12:00 PM", "lesson": "Database Systems", "teacher": "Mr. Hodge", "location": "Lab C1", "day": "Monday"},
    {"time": "02:00 PM", "lesson": "Workplace Practice", "teacher": "Mrs. Murray", "location": "Room B1-112", "day": "Monday"},
]

ANNOUNCEMENTS = [
    {"title": "Semester registration support desk opens on Monday", "category": "Registration", "date": "2026-05-24", "summary": "Students needing assistance with module selection or curriculum alignment can visit the registration desk from 08:00."},
    {"title": "Bursary and funding document review closes on 31 May", "category": "Finance", "date": "2026-05-23", "summary": "Upload outstanding sponsorship or funding letters before the monthly finance review closes."},
    {"title": "Exam timetable is now available", "category": "Academics", "date": "2026-05-22", "summary": "Students can now review final test and exam dates through the timetable and assessment sections."},
]

CAMPUS_SERVICES = [
    {"name": "Accommodation Booking", "status": "Applications Open", "detail": "Track room placement and submit housing updates."},
    {"name": "Library Resources", "status": "Available", "detail": "Reserve books, use e-journals, and renew issued material."},
    {"name": "Sports Facilities", "status": "Booking Required", "detail": "Book gym sessions, courts, and student activities."},
]

SUPPORT_SERVICES = [
    {"name": "Student Counselling", "contact": "counselling@jhstudent.co.za", "detail": "Confidential personal and academic support."},
    {"name": "Campus Healthcare", "contact": "clinic@jhstudent.co.za", "detail": "Primary healthcare, wellness, and screening services."},
    {"name": "IT Help Desk", "contact": "itsupport@jhstudent.co.za", "detail": "Portal login, LMS, Wi-Fi, and device support."},
]

ADMIN_USERS = {
    "admin@gmail.com": {"password": "1234", "name": "Matshidiso Makae", "role_label": "Super Admin", "default_route": "admin_dashboard"},
    "skills.admin@jhholdings.co.za": {"password": "1234", "name": "Lerato Khumalo", "role_label": "Sub Admin", "default_route": "admin_dashboard"},
}

STUDENT_SEED = [
    {"id": "1001", "student_number": "2026001001", "full_name": "Thabo Mokoena", "email": "thabo.mokoena@student.jh.co.za", "phone": "071 234 5678", "id_number": "9801015800088", "gender": "Male", "address": "Johannesburg", "employment": "Unemployed", "qualification": "Diploma in Information Technology", "faculty": "Faculty of Applied Sciences", "programme": "Digital Skills Cohort 2026", "coordinator": "Lerato Khumalo", "location": "Johannesburg Campus", "start_date": "2026-03-01", "status": "Active", "username": "learner.jh-1001", "password": "Learner@1001", "campus": "Johannesburg Campus", "year_level": "Year 2", "emergency_contact_name": "Nomsa Mokoena", "emergency_contact_phone": "082 456 7800", "emergency_contact_relationship": "Parent", "modules": ["Network Systems", "Database Systems", "Information Security", "English Communication"], "tuition_balance": "R18,450", "bursary_status": "Provisionally approved", "registration_status": "Registered", "lms_link": "https://canvas.instructure.com/"},
    {"id": "1002", "student_number": "2026001002", "full_name": "Ayanda Dlamini", "email": "ayanda.dlamini@student.jh.co.za", "phone": "082 445 1199", "id_number": "9905220485087", "gender": "Female", "address": "Pretoria", "employment": "Employed", "qualification": "Business Administration NQF 4", "faculty": "Faculty of Management Studies", "programme": "Business Administration Learnership", "coordinator": "Ayanda Mokoena", "location": "Pretoria Campus", "start_date": "2026-03-04", "status": "Active", "username": "learner.jh-1002", "password": "Learner@1002", "campus": "Pretoria Campus", "year_level": "Year 1", "emergency_contact_name": "Thandi Dlamini", "emergency_contact_phone": "073 555 1122", "emergency_contact_relationship": "Sister", "modules": ["Business Communication", "Office Practice", "Customer Service", "Workplace Readiness"], "tuition_balance": "R7,980", "bursary_status": "Approved", "registration_status": "Registered", "lms_link": "https://canvas.instructure.com/"},
]


# ── Storage helpers ─────────────────────────────────────────────────────────
def ensure_storage():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(LEARNER_UPLOADS_DIR, exist_ok=True)
    os.makedirs(CENTRAL_UPLOADS_DIR, exist_ok=True)
    if not os.path.exists(LEARNER_DOCUMENTS_FILE):
        with open(LEARNER_DOCUMENTS_FILE, "w") as f: json.dump({}, f)
    if not os.path.exists(CENTRAL_DOCUMENTS_FILE):
        with open(CENTRAL_DOCUMENTS_FILE, "w") as f: json.dump([], f)
    if not os.path.exists(STUDENTS_FILE):
        with open(STUDENTS_FILE, "w") as f: json.dump(STUDENT_SEED, f, indent=2)
    if not os.path.exists(MESSAGES_FILE):
        with open(MESSAGES_FILE, "w") as f: json.dump([], f)
    if not os.path.exists(MEET_ROOMS_FILE):
        with open(MEET_ROOMS_FILE, "w") as f: json.dump({}, f)
    if not os.path.exists(PENDING_FILE):
        with open(PENDING_FILE, "w") as f: json.dump([], f)
    if not os.path.exists(VERIF_FILE):
        with open(VERIF_FILE, "w") as f: json.dump({}, f)

def load_json(path, default):
    ensure_storage()
    with open(path, "r") as f: return json.load(f) if os.path.getsize(path) else default

def save_json(path, data):
    ensure_storage()
    with open(path, "w") as f: json.dump(data, f, indent=2)

def load_students(): return load_json(STUDENTS_FILE, [])
def save_students(s): save_json(STUDENTS_FILE, s)

def get_student_by_id(sid):
    for s in load_students():
        if str(s["id"]) == str(sid): return s
    return None

def get_student_by_username(username):
    username = username.strip().lower()
    for s in load_students():
        if s["username"].lower() == username: return s
    return None

def load_meet_rooms(): return load_json(MEET_ROOMS_FILE, {})
def save_meet_rooms(r): save_json(MEET_ROOMS_FILE, r)

def generate_join_code():
    """Generate a short 6-character alphanumeric join code."""
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(6))

def create_meet_room(title, creator_name):
    """Admin creates a meeting room; returns the join code and jitsi room name."""
    rooms = load_meet_rooms()
    for _ in range(20):
        code = generate_join_code()
        if code not in rooms:
            break
    jitsi_room = "jh-" + secrets.token_hex(8)
    rooms[code] = {
        "code": code,
        "title": title or "JH Meeting",
        "jitsi_room": jitsi_room,
        "creator": creator_name,
        "created_at": int(datetime.now().timestamp()),
        "active": True,
    }
    save_meet_rooms(rooms)
    return rooms[code]

def get_room_by_code(code):
    rooms = load_meet_rooms()
    return rooms.get(code.strip().upper())

# ── Pending registrations ─────────────────────────────────────────────────
def load_pending(): return load_json(PENDING_FILE, [])
def save_pending(p): save_json(PENDING_FILE, p)

# ── Verification tokens ───────────────────────────────────────────────────
def load_verif(): return load_json(VERIF_FILE, {})
def save_verif(v): save_json(VERIF_FILE, v)

def _ensure_extra_files():
    for path, default in [(PENDING_FILE, []), (VERIF_FILE, {})]:
        if not os.path.exists(path):
            with open(path, "w") as f:
                json.dump(default, f)

def create_email_token(pending_id):
    """Generate a one-time email verification link token."""
    _ensure_extra_files()
    token = secrets.token_urlsafe(32)
    store = load_verif()
    store[f"email:{pending_id}"] = {
        "token": token,
        "expires": (datetime.now() + timedelta(hours=24)).isoformat(),
        "used": False,
    }
    save_verif(store)
    return token

def create_phone_otp(pending_id):
    """Generate a 6-digit SMS OTP."""
    _ensure_extra_files()
    otp = "".join(secrets.choice(string.digits) for _ in range(6))
    store = load_verif()
    store[f"otp:{pending_id}"] = {
        "otp": otp,
        "expires": (datetime.now() + timedelta(minutes=15)).isoformat(),
        "used": False,
        "attempts": 0,
    }
    save_verif(store)
    return otp

def verify_email_token(pending_id, token):
    store = load_verif()
    key = f"email:{pending_id}"
    rec = store.get(key)
    if not rec or rec["used"]: return False
    if datetime.now() > datetime.fromisoformat(rec["expires"]): return False
    if rec["token"] != token: return False
    rec["used"] = True
    save_verif(store)
    return True

def verify_phone_otp(pending_id, otp):
    store = load_verif()
    key = f"otp:{pending_id}"
    rec = store.get(key)
    if not rec or rec["used"]: return False, "OTP already used or not found."
    if datetime.now() > datetime.fromisoformat(rec["expires"]): return False, "OTP has expired. Please resend."
    rec["attempts"] = rec.get("attempts", 0) + 1
    if rec["attempts"] > 5:
        save_verif(store)
        return False, "Too many attempts. Please resend the OTP."
    if rec["otp"] != otp:
        save_verif(store)
        return False, "Incorrect OTP. Please try again."
    rec["used"] = True
    save_verif(store)
    return True, "ok"

# ── Email sender ──────────────────────────────────────────────────────────
def send_email(to_addr, subject, html_body):
    """Send an email via SMTP. Silently logs failures if not configured."""
    if not MAIL_USER or not MAIL_PASS:
        print(f"[EMAIL - not configured] To: {to_addr}  Subject: {subject}")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = MAIL_FROM
        msg["To"]      = to_addr
        msg.attach(MIMEText(html_body, "html"))
        with smtplib.SMTP(MAIL_HOST, MAIL_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(MAIL_USER, MAIL_PASS)
            server.sendmail(MAIL_FROM, to_addr, msg.as_string())
        return True
    except Exception as e:
        print(f"[EMAIL ERROR] {e}")
        return False

def send_verification_email(to_addr, full_name, pending_id, token):
    link = f"{APP_BASE_URL}/verify-email?id={pending_id}&token={token}"
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:560px;margin:auto;background:#fff;border-radius:12px;overflow:hidden;border:1px solid #e0e0e0">
      <div style="background:linear-gradient(135deg,#8DC63F,#00A89D);padding:28px 32px">
        <h1 style="color:#fff;margin:0;font-size:22px">JH Student Portal</h1>
        <p style="color:rgba(255,255,255,.85);margin:4px 0 0;font-size:14px">Email Verification</p>
      </div>
      <div style="padding:32px">
        <p style="font-size:15px;color:#222">Hi <strong>{full_name}</strong>,</p>
        <p style="font-size:14px;color:#555">Thank you for registering. Please verify your email address to continue:</p>
        <div style="text-align:center;margin:28px 0">
          <a href="{link}" style="background:linear-gradient(135deg,#8DC63F,#00A89D);color:#fff;text-decoration:none;padding:14px 32px;border-radius:8px;font-size:15px;font-weight:700;display:inline-block">
            ✅ Verify Email Address
          </a>
        </div>
        <p style="font-size:12px;color:#999">This link expires in 24 hours. If you did not register, please ignore this email.</p>
      </div>
    </div>"""
    return send_email(to_addr, "Verify your email — JH Student Portal", html)

def send_otp_sms(phone_number, otp, full_name):
    """Send OTP via Twilio SMS. Falls back to print if not configured."""
    message_body = f"Hi {full_name.split()[0]}, your JH Portal OTP is: {otp}. Valid for 15 minutes. Do not share this code."
    if not TWILIO_SID or not TWILIO_TOKEN or not TWILIO_FROM:
        print(f"[SMS - not configured] To: {phone_number}  OTP: {otp}")
        return False
    try:
        import urllib.request, urllib.parse, base64
        url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_SID}/Messages.json"
        data = urllib.parse.urlencode({
            "From": TWILIO_FROM,
            "To": phone_number,
            "Body": message_body,
        }).encode()
        credentials = base64.b64encode(f"{TWILIO_SID}:{TWILIO_TOKEN}".encode()).decode()
        req = urllib.request.Request(url, data=data, headers={"Authorization": f"Basic {credentials}"})
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception as e:
        print(f"[SMS ERROR] {e}")
        return False

def send_approval_email(to_addr, full_name, username, password):
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:560px;margin:auto;background:#fff;border-radius:12px;overflow:hidden;border:1px solid #e0e0e0">
      <div style="background:linear-gradient(135deg,#8DC63F,#00A89D);padding:28px 32px">
        <h1 style="color:#fff;margin:0;font-size:22px">JH Student Portal</h1>
        <p style="color:rgba(255,255,255,.85);margin:4px 0 0;font-size:14px">Registration Approved 🎉</p>
      </div>
      <div style="padding:32px">
        <p style="font-size:15px;color:#222">Hi <strong>{full_name}</strong>,</p>
        <p style="font-size:14px;color:#555">Your registration has been approved by our admin team. You can now sign in to the portal:</p>
        <div style="background:#f5faf3;border:1px solid #c8e0c0;border-radius:8px;padding:16px 20px;margin:20px 0;font-size:14px">
          <div style="margin-bottom:6px"><strong>Username:</strong> <code>{username}</code></div>
          <div><strong>Password:</strong> <code>{password}</code></div>
        </div>
        <div style="text-align:center;margin:20px 0">
          <a href="{APP_BASE_URL}/" style="background:linear-gradient(135deg,#8DC63F,#00A89D);color:#fff;text-decoration:none;padding:14px 32px;border-radius:8px;font-size:15px;font-weight:700;display:inline-block">
            Sign In to Portal →
          </a>
        </div>
        <p style="font-size:12px;color:#999">We recommend changing your password after your first login.</p>
      </div>
    </div>"""
    return send_email(to_addr, "Your JH Portal account is approved — Welcome!", html)

def load_learner_document_store(): return load_json(LEARNER_DOCUMENTS_FILE, {})
def save_learner_document_store(s): save_json(LEARNER_DOCUMENTS_FILE, s)
def load_central_document_store(): return load_json(CENTRAL_DOCUMENTS_FILE, [])
def save_central_document_store(s): save_json(CENTRAL_DOCUMENTS_FILE, s)

def is_allowed_document(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_DOCUMENT_EXTENSIONS

def build_document_payload(learner_id, doc):
    d = dict(doc)
    d["view_url"] = url_for("learner_document_file", learner_id=learner_id, filename=doc["stored_name"])
    d["download_url"] = url_for("learner_document_file", learner_id=learner_id, filename=doc["stored_name"], download=1)
    return d

def get_learner_documents(learner_id):
    store = load_learner_document_store()
    return [build_document_payload(learner_id, r) for r in store.get(str(learner_id), [])]

def get_document_checklist(learner_id):
    docs = get_learner_documents(learner_id)
    cats = {d["category"] for d in docs}
    checklist = []
    for dt in LEARNER_DOCUMENT_TYPES:
        matching = [d for d in docs if d["category"] == dt["id"]]
        checklist.append({**dt, "uploaded": bool(matching), "count": len(matching), "documents": matching})
    return {
        "required_total": len([x for x in LEARNER_DOCUMENT_TYPES if x["required"]]),
        "required_uploaded": len([x for x in LEARNER_DOCUMENT_TYPES if x["required"] and x["id"] in cats]),
        "items": checklist,
    }

def current_admin():
    if not session.get("admin_logged_in"): return None
    return ADMIN_USERS.get(session.get("admin_email", "").lower())

def current_student():
    if not session.get("student_logged_in"): return None
    return get_student_by_id(session.get("student_id"))

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_admin(): return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper

def student_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_student(): return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper

def create_student_payload(form_data, current_count):
    n = 1000 + current_count + 1
    sid = str(n)
    full_name = form_data["full_name"].strip()
    first_name = full_name.split()[0].lower()
    return {
        "id": sid, "student_number": f"2026{sid}", "full_name": full_name,
        "email": form_data["email"].strip(), "phone": form_data["phone"].strip(),
        "id_number": form_data["id_number"].strip(), "gender": form_data["gender"].strip(),
        "address": form_data["address"].strip(), "employment": form_data["employment"].strip(),
        "qualification": form_data["qualification"].strip(), "faculty": form_data["faculty"].strip(),
        "programme": form_data["programme"].strip(), "coordinator": form_data["coordinator"].strip(),
        "location": form_data["location"].strip(), "start_date": form_data["start_date"].strip(),
        "status": form_data["status"].strip(), "username": f"learner.jh-{sid}",
        "password": f"Learner@{sid}", "campus": form_data["location"].strip(),
        "year_level": form_data["year_level"].strip(),
        "emergency_contact_name": form_data["emergency_contact_name"].strip(),
        "emergency_contact_phone": form_data["emergency_contact_phone"].strip(),
        "emergency_contact_relationship": form_data["emergency_contact_relationship"].strip(),
        "modules": [x.strip() for x in form_data["modules"].split(",") if x.strip()],
        "tuition_balance": form_data["tuition_balance"].strip() or "R0",
        "bursary_status": form_data["bursary_status"].strip() or "Pending",
        "registration_status": "Registered", "lms_link": "https://canvas.instructure.com/",
        "portal_email": f"{first_name}.{sid}@student.jh.co.za",
    }


# ── Shared CSS / JS (theme system) ──────────────────────────────────────────
BASE_STYLES = """
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Sans:wght@300;400;500;600&display=swap');

:root {
  --brand: #00A89D;
  --brand-2: #8DC63F;
  --brand-3: #F5C518;
  --brand-g: linear-gradient(135deg, #8DC63F 0%, #00A89D 60%, #2D6A4F 100%);
  --r: 12px;
  --r-sm: 8px;
  --trans: .22s cubic-bezier(.4,0,.2,1);
  /* JH brand colours — shared across all pages */
  --jh-green: #8DC63F;
  --jh-teal: #00A89D;
  --jh-dark: #2D6A4F;
  --jh-yellow: #F5C518;
  --jh-grad: linear-gradient(135deg, #8DC63F 0%, #00A89D 60%, #2D6A4F 100%);
  --jh-grad-soft: linear-gradient(160deg, #a8d85a22 0%, #00A89D18 100%);
}

[data-theme="light"] {
  --bg: #f0f7ee;
  --bg-2: #e4f0df;
  --surface: #FFFFFF;
  --surface-2: #f5faf3;
  --border: #c8e0c0;
  --text: #1a2e1a;
  --text-2: #3d6b3d;
  --text-3: #6b9b6b;
  --sidebar-bg: #1a2e1a;
  --sidebar-text: #a8c8a8;
  --sidebar-active: #FFFFFF;
  --sidebar-active-bg: rgba(0,168,157,.22);
  --shadow: 0 2px 16px rgba(45,106,79,.08);
  --shadow-lg: 0 8px 40px rgba(45,106,79,.15);
}

[data-theme="dark"] {
  --bg: #0d1a0d;
  --bg-2: #121f12;
  --surface: #182018;
  --surface-2: #1e2a1e;
  --border: #2a402a;
  --text: #e8f5e8;
  --text-2: #7db87d;
  --text-3: #4a7a4a;
  --sidebar-bg: #0a140a;
  --sidebar-text: #5a8a5a;
  --sidebar-active: #FFFFFF;
  --sidebar-active-bg: rgba(0,168,157,.28);
  --shadow: 0 2px 16px rgba(0,0,0,.35);
  --shadow-lg: 0 8px 40px rgba(0,0,0,.5);
}

*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{font-family:'DM Sans',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;transition:background var(--trans),color var(--trans);position:relative}
body::before{
  content:'';position:fixed;inset:0;pointer-events:none;z-index:0;
  background:
    radial-gradient(ellipse 70% 50% at 10% 5%, rgba(141,198,63,.12) 0%, transparent 55%),
    radial-gradient(ellipse 55% 45% at 90% 95%, rgba(0,168,157,.10) 0%, transparent 50%),
    radial-gradient(ellipse 40% 35% at 80% 10%, rgba(45,106,79,.08) 0%, transparent 50%);
}
.app-shell,.login-shell,.signup-shell{position:relative;z-index:1}
a{color:var(--jh-teal);text-decoration:none}
a:hover{opacity:.8}
h1,h2,h3,h4{font-family:'Syne',sans-serif;letter-spacing:-.02em}
input,select,textarea{font-family:'DM Sans',sans-serif}

/* ── Topbar logo ── */
.topbar-logo{
  display:flex;align-items:center;gap:10px;margin-right:8px;
  border-right:1px solid var(--border);padding-right:16px;
}
.topbar-logo img{height:28px;width:auto;object-fit:contain}
.topbar-logo-fallback{
  height:28px;padding:0 10px;background:var(--jh-grad);border-radius:6px;
  display:flex;align-items:center;font-family:'Syne',sans-serif;
  font-weight:800;font-size:13px;color:#fff;letter-spacing:.02em;
  box-shadow:0 2px 8px rgba(0,168,157,.25);
}

/* ── Layout ── */
.app-shell{display:flex;min-height:100vh}
.sidebar{
  width:240px;min-height:100vh;background:var(--sidebar-bg);
  display:flex;flex-direction:column;position:fixed;top:0;left:0;z-index:200;
  transition:width var(--trans),transform var(--trans);
  border-right:1px solid rgba(255,255,255,.04);
}
.sidebar.collapsed{width:64px}
.sidebar-header{
  padding:20px 16px;display:flex;align-items:center;gap:12px;
  border-bottom:1px solid rgba(255,255,255,.06);
}
.logo-btn{
  display:flex;align-items:center;gap:10px;cursor:pointer;
  background:none;border:none;padding:0;text-decoration:none;
  flex:1;min-width:0;
}
.logo-mark{
  width:36px;height:36px;border-radius:10px;background:var(--jh-grad);
  display:flex;align-items:center;justify-content:center;flex-shrink:0;
  font-family:'Syne',sans-serif;font-weight:800;font-size:16px;color:#fff;
  box-shadow:0 4px 12px rgba(0,168,157,.4);
}
.logo-text{font-family:'Syne',sans-serif;font-weight:700;font-size:13px;color:#fff;line-height:1.2;opacity:1;transition:opacity var(--trans);white-space:nowrap;overflow:hidden}
.sidebar.collapsed .logo-text{opacity:0;width:0}

.sidebar-toggle{
  background:none;border:none;cursor:pointer;color:var(--sidebar-text);
  padding:6px;border-radius:6px;transition:background var(--trans);flex-shrink:0;
}
.sidebar-toggle:hover{background:rgba(255,255,255,.08);color:#fff}
.sidebar.collapsed .sidebar-toggle svg{transform:rotate(180deg)}

.sidebar-section{padding:4px 0;flex:1;overflow-y:auto;overflow-x:hidden;scroll-behavior:smooth}
.sidebar-section::-webkit-scrollbar{width:3px}
.sidebar-section::-webkit-scrollbar-track{background:transparent}
.sidebar-section::-webkit-scrollbar-thumb{background:rgba(255,255,255,.1);border-radius:4px}
.sidebar-scroll-btn{
  width:100%;border:none;background:rgba(255,255,255,.05);color:rgba(255,255,255,.4);
  padding:3px 0;cursor:pointer;display:flex;align-items:center;justify-content:center;
  transition:background var(--trans),color var(--trans);flex-shrink:0;
}
.sidebar-scroll-btn:hover{background:rgba(255,255,255,.1);color:#fff}
.sidebar-scroll-btn svg{transition:transform .2s}
.sidebar-scroll-btn:active svg{transform:scale(.85)}
.sidebar.collapsed .sidebar-scroll-btn{opacity:0;pointer-events:none;height:0;padding:0;overflow:hidden}

.sidebar-label{
  font-size:9px;font-weight:600;text-transform:uppercase;letter-spacing:.12em;
  color:rgba(255,255,255,.25);padding:6px 16px 2px;
  white-space:nowrap;overflow:hidden;
}
.sidebar.collapsed .sidebar-label{opacity:0}

.nav-item{
  display:flex;align-items:center;gap:9px;padding:6px 12px;
  color:var(--sidebar-text);font-size:12px;font-weight:500;
  text-decoration:none;border-radius:7px;margin:1px 6px;
  transition:background var(--trans),color var(--trans);position:relative;
  white-space:nowrap;overflow:hidden;
}
.nav-item:hover{background:rgba(255,255,255,.07);color:#fff;opacity:1}
.nav-item.active{background:var(--sidebar-active-bg);color:var(--sidebar-active)}
.nav-item.active::before{content:'';position:absolute;left:0;top:20%;bottom:20%;width:3px;background:var(--jh-teal);border-radius:0 3px 3px 0}
.nav-icon{width:15px;height:15px;flex-shrink:0;opacity:.7;font-size:13px}
.nav-item.active .nav-icon,.nav-item:hover .nav-icon{opacity:1}
.nav-label{transition:opacity var(--trans);flex:1}
.sidebar.collapsed .nav-label{opacity:0;width:0;overflow:hidden}
.nav-badge{
  background:var(--jh-teal);color:#fff;font-size:10px;font-weight:700;
  padding:2px 6px;border-radius:20px;min-width:18px;text-align:center;
  transition:opacity var(--trans);
}
.sidebar.collapsed .nav-badge{opacity:0}

.sidebar-footer{padding:12px 8px;border-top:1px solid rgba(255,255,255,.06)}

/* ── Main content ── */
.main-content{
  margin-left:240px;flex:1;min-height:100vh;
  transition:margin-left var(--trans);display:flex;flex-direction:column;
}
.sidebar.collapsed ~ .main-content{margin-left:64px}

/* ── Top bar ── */
.topbar{
  height:60px;background:var(--surface);border-bottom:1px solid var(--border);
  display:flex;align-items:center;gap:16px;padding:0 24px;
  position:sticky;top:0;z-index:100;box-shadow:var(--shadow);
}
.topbar-title{font-family:'Syne',sans-serif;font-weight:700;font-size:16px;color:var(--text);flex:1}
.topbar-actions{display:flex;align-items:center;gap:10px}

.search-bar{
  display:flex;align-items:center;gap:8px;background:var(--bg-2);
  border:1px solid var(--border);border-radius:var(--r-sm);padding:6px 12px;
  transition:border-color var(--trans);
}
.search-bar:focus-within{border-color:var(--jh-teal)}
.search-bar input{background:none;border:none;outline:none;color:var(--text);font-size:13px;width:180px}
.search-bar input::placeholder{color:var(--text-3)}

/* ── Theme toggle ── */
.theme-btn{
  background:var(--bg-2);border:1px solid var(--border);border-radius:var(--r-sm);
  padding:7px 10px;cursor:pointer;color:var(--text-2);transition:all var(--trans);
  display:flex;align-items:center;gap:6px;font-size:12px;font-weight:500;
}
.theme-btn:hover{border-color:var(--jh-teal);color:var(--jh-teal)}

/* ── Avatar / user menu ── */
.user-chip{
  display:flex;align-items:center;gap:8px;padding:4px 12px 4px 4px;
  background:var(--bg-2);border:1px solid var(--border);border-radius:40px;
  cursor:pointer;transition:border-color var(--trans);
}
.user-chip:hover{border-color:var(--jh-teal)}
.user-avatar{
  width:30px;height:30px;border-radius:50%;background:var(--jh-grad);
  display:flex;align-items:center;justify-content:center;
  font-family:'Syne',sans-serif;font-weight:700;font-size:12px;color:#fff;
}
.user-name{font-size:12px;font-weight:500;color:var(--text-2)}

/* ── Page content ── */
.page{padding:28px 28px 48px;flex:1}
.page-header{margin-bottom:24px}
.page-header h1{font-size:24px;font-weight:800;color:var(--text)}
.page-header p{color:var(--text-2);font-size:14px;margin-top:4px}

/* ── Cards ── */
.card{
  background:var(--surface);border:1px solid var(--border);
  border-radius:var(--r);padding:20px;box-shadow:var(--shadow);
  transition:box-shadow var(--trans);
}
.card:hover{box-shadow:var(--shadow-lg)}
.card-title{font-family:'Syne',sans-serif;font-weight:700;font-size:15px;color:var(--text);margin-bottom:12px}

.grid-2{display:grid;grid-template-columns:1fr 1fr;gap:20px}
.grid-3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:20px}
.grid-4{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}

/* ── Stat cards ── */
.stat-card{
  background:var(--surface);border:1px solid var(--border);
  border-radius:var(--r);padding:20px;position:relative;overflow:hidden;
}
.stat-card::before{
  content:'';position:absolute;inset:0;
  background:linear-gradient(135deg,rgba(0,168,157,.06) 0%,transparent 60%);
  pointer-events:none;
}
.stat-icon{width:40px;height:40px;border-radius:10px;display:flex;align-items:center;justify-content:center;margin-bottom:12px;font-size:20px}
.stat-value{font-family:'Syne',sans-serif;font-size:28px;font-weight:800;color:var(--text);line-height:1}
.stat-label{font-size:12px;color:var(--text-2);margin-top:4px;font-weight:500}
.stat-change{font-size:11px;margin-top:8px;display:flex;align-items:center;gap:4px}
.stat-change.up{color:#22c55e}
.stat-change.neutral{color:var(--text-3)}

/* ── Progress bar ── */
.progress-bar{height:6px;background:var(--bg-2);border-radius:4px;overflow:hidden;margin-top:8px}
.progress-fill{height:100%;border-radius:4px;background:var(--jh-grad);transition:width .8s ease}

/* ── Badges ── */
.badge{
  display:inline-flex;align-items:center;gap:4px;
  font-size:11px;font-weight:600;padding:3px 10px;border-radius:20px;
}
.badge-purple{background:rgba(0,168,157,.12);color:#00897B}
.badge-teal{background:rgba(141,198,63,.12);color:#558B2F}
.badge-red{background:rgba(255,107,107,.12);color:#e05555}
.badge-green{background:rgba(34,197,94,.12);color:#16a34a}
.badge-gray{background:var(--bg-2);color:var(--text-2)}

/* ── Table ── */
.table-wrap{overflow-x:auto;border-radius:var(--r);border:1px solid var(--border)}
table{width:100%;border-collapse:collapse;font-size:13.5px}
thead tr{background:var(--surface-2);border-bottom:1px solid var(--border)}
th{padding:11px 16px;font-weight:600;font-size:11.5px;text-transform:uppercase;letter-spacing:.06em;color:var(--text-2);text-align:left;white-space:nowrap}
td{padding:12px 16px;border-bottom:1px solid var(--border);color:var(--text);vertical-align:middle}
tbody tr:last-child td{border-bottom:none}
tbody tr:hover{background:var(--surface-2)}

/* ── Buttons ── */
.btn{
  display:inline-flex;align-items:center;gap:8px;
  padding:9px 18px;border-radius:var(--r-sm);font-size:13.5px;font-weight:600;
  cursor:pointer;border:none;transition:all var(--trans);font-family:'DM Sans',sans-serif;
}
.btn-primary{background:var(--jh-grad);color:#fff;box-shadow:0 4px 14px rgba(0,168,157,.3)}
.btn-primary:hover{opacity:.88;box-shadow:0 6px 20px rgba(0,168,157,.45)}
.btn-secondary{background:var(--bg-2);color:var(--text);border:1px solid var(--border)}
.btn-secondary:hover{border-color:var(--jh-teal);color:var(--jh-teal)}
.btn-danger{background:rgba(255,107,107,.1);color:#e05555;border:1px solid rgba(255,107,107,.2)}
.btn-danger:hover{background:rgba(255,107,107,.2)}
.btn-sm{padding:6px 12px;font-size:12px}
.btn-ghost{background:none;color:var(--text-2);border:none}
.btn-ghost:hover{color:var(--jh-teal)}

/* ── Form fields ── */
.field{margin-bottom:16px}
.field label{display:block;font-size:12px;font-weight:600;color:var(--text-2);margin-bottom:6px;text-transform:uppercase;letter-spacing:.05em}
.field input,.field select,.field textarea{
  width:100%;padding:10px 14px;background:var(--bg-2);
  border:1.5px solid var(--border);border-radius:var(--r-sm);
  color:var(--text);font-size:13.5px;transition:border-color var(--trans);
  outline:none;
}
.field input:focus,.field select:focus,.field textarea:focus{border-color:var(--jh-teal);background:var(--surface)}
.field select option{background:var(--surface)}

/* ── Task cards ── */
.task-card{
  background:var(--surface);border:1px solid var(--border);
  border-radius:var(--r);padding:16px;transition:all var(--trans);
  border-left:3px solid transparent;
}
.task-card:hover{box-shadow:var(--shadow-lg);transform:translateY(-2px)}
.task-card.todo{border-left-color:#f59e0b}
.task-card.in-progress{border-left-color:var(--jh-teal)}
.task-card.done{border-left-color:#22c55e}
.task-meta{font-size:12px;color:var(--text-3);display:flex;gap:12px;margin-top:8px}

/* ── Notes ── */
.note-card{border-radius:var(--r);padding:16px;border:1px solid transparent}
.note-card.green{background:rgba(141,198,63,.07);border-color:rgba(141,198,63,.2)}
.note-card.purple{background:rgba(0,168,157,.07);border-color:rgba(0,168,157,.2)}

/* ── Announcement card ── */
.notice-card{
  background:var(--surface);border:1px solid var(--border);
  border-radius:var(--r);padding:16px;display:flex;gap:14px;align-items:flex-start;
}
.notice-dot{width:10px;height:10px;border-radius:50%;background:var(--jh-teal);flex-shrink:0;margin-top:5px}

/* ── Kanban ── */
.kanban{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;align-items:start}
.kanban-col{background:var(--surface-2);border:1px solid var(--border);border-radius:var(--r);padding:14px}
.kanban-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px}
.kanban-title{font-family:'Syne',sans-serif;font-weight:700;font-size:13px;color:var(--text)}
.kanban-count{background:var(--bg-2);color:var(--text-2);font-size:11px;font-weight:700;padding:2px 8px;border-radius:12px}

/* ── Activity feed ── */
.activity-item{display:flex;gap:12px;align-items:flex-start;padding:10px 0;border-bottom:1px solid var(--border)}
.activity-item:last-child{border-bottom:none}
.activity-icon{width:32px;height:32px;border-radius:8px;display:flex;align-items:center;justify-content:center;flex-shrink:0;font-size:15px}
.activity-content{flex:1}
.activity-text{font-size:13.5px;color:var(--text);line-height:1.4}
.activity-time{font-size:11px;color:var(--text-3);margin-top:2px}

/* ── Notification bell ── */
.notif-btn{position:relative;background:var(--bg-2);border:1px solid var(--border);border-radius:var(--r-sm);padding:7px 10px;cursor:pointer;color:var(--text-2);transition:all var(--trans)}
.notif-btn:hover{border-color:var(--jh-teal);color:var(--jh-teal)}
.notif-dot{position:absolute;top:5px;right:5px;width:8px;height:8px;border-radius:50%;background:var(--jh-yellow);border:2px solid var(--surface)}

/* ── Quick-add ── */
.quick-add{
  background:var(--jh-grad);border:none;border-radius:var(--r-sm);
  color:#fff;font-size:13.5px;font-weight:700;padding:9px 18px;
  cursor:pointer;display:flex;align-items:center;gap:8px;font-family:'DM Sans',sans-serif;
  box-shadow:0 4px 14px rgba(0,168,157,.35);transition:all var(--trans);
}
.quick-add:hover{box-shadow:0 6px 20px rgba(0,168,157,.5);transform:translateY(-1px)}

/* ── Toast ── */
.toast{
  position:fixed;bottom:24px;right:24px;z-index:9999;
  background:var(--surface);border:1px solid var(--border);
  border-radius:var(--r);padding:14px 20px;box-shadow:var(--shadow-lg);
  font-size:13.5px;color:var(--text);display:none;
  animation:slideUp .3s ease;max-width:320px;
}
.toast.show{display:flex;align-items:center;gap:10px}
.toast-icon{font-size:18px}
@keyframes slideUp{from{transform:translateY(20px);opacity:0}to{transform:translateY(0);opacity:1}}

/* ── Login page ── */
.login-shell{
  min-height:100vh;display:flex;align-items:center;justify-content:center;
  background:var(--bg);position:relative;overflow:hidden;
}
.login-shell::before{
  content:'';position:fixed;inset:0;
  background:radial-gradient(ellipse 80% 60% at 20% 10%,rgba(141,198,63,.18) 0%,transparent 60%),
             radial-gradient(ellipse 60% 50% at 80% 90%,rgba(0,168,157,.12) 0%,transparent 55%);
  pointer-events:none;z-index:0;
}
.login-box{
  width:100%;max-width:440px;position:relative;z-index:1;
  background:var(--surface);border:1px solid var(--border);
  border-radius:20px;padding:40px;box-shadow:var(--shadow-lg);
}
.login-logo{display:flex;align-items:center;gap:14px;margin-bottom:32px}
.login-logo-mark{
  width:48px;height:48px;border-radius:14px;background:var(--jh-grad);
  display:flex;align-items:center;justify-content:center;
  font-family:'Syne',sans-serif;font-weight:800;font-size:22px;color:#fff;
  box-shadow:0 6px 20px rgba(0,168,157,.4);
}
.login-logo-text{font-family:'Syne',sans-serif;font-weight:800;font-size:22px;color:var(--text)}
.login-logo-sub{font-size:12px;color:var(--text-3);font-weight:400;margin-top:2px}
.login-title{font-family:'Syne',sans-serif;font-weight:800;font-size:26px;color:var(--text);margin-bottom:6px}
.login-sub{font-size:14px;color:var(--text-2);margin-bottom:28px}
.login-error{background:rgba(255,107,107,.08);border:1px solid rgba(255,107,107,.2);border-radius:var(--r-sm);padding:11px 14px;color:#e05555;font-size:13px;margin-bottom:16px}
.login-footer{margin-top:20px;text-align:center;font-size:12px;color:var(--text-3)}
.login-theme-toggle{position:absolute;top:20px;right:20px}

/* ── Scrollbar ── */
::-webkit-scrollbar{width:5px;height:5px}
::-webkit-scrollbar-track{background:var(--bg)}
::-webkit-scrollbar-thumb{background:var(--border);border-radius:4px}
::-webkit-scrollbar-thumb:hover{background:var(--text-3)}

/* ── Responsive ── */
@media(max-width:900px){
  .grid-4{grid-template-columns:1fr 1fr}
  .grid-3{grid-template-columns:1fr 1fr}
  .kanban{grid-template-columns:1fr}
}
@media(max-width:640px){
  .grid-2,.grid-3,.grid-4{grid-template-columns:1fr}
  .main-content{margin-left:0!important}
  .sidebar{transform:translateX(-100%)}
}
"""

BASE_JS = """
// Theme management
(function(){
  const stored = localStorage.getItem('jh_theme') || 'light';
  document.documentElement.setAttribute('data-theme', stored);
})();

function toggleTheme(){
  const cur = document.documentElement.getAttribute('data-theme');
  const next = cur === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('jh_theme', next);
  const btn = document.getElementById('themeBtn');
  if(btn) btn.innerHTML = next === 'dark'
    ? '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg> Light'
    : '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg> Dark';
  updateThemeBtn();
}
function updateThemeBtn(){
  const theme = document.documentElement.getAttribute('data-theme');
  const btn = document.getElementById('themeBtn');
  if(!btn) return;
  btn.innerHTML = theme === 'dark'
    ? '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg> Light'
    : '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg> Dark';
}
document.addEventListener('DOMContentLoaded', updateThemeBtn);

// Sidebar collapse
function toggleSidebar(){
  const s = document.getElementById('sidebar');
  if(s){ s.classList.toggle('collapsed'); localStorage.setItem('jh_sb', s.classList.contains('collapsed')?'1':'0'); }
}
(function(){
  const s = document.getElementById('sidebar');
  if(s && localStorage.getItem('jh_sb') === '1') s.classList.add('collapsed');
})();

// Sidebar scroll
function sidebarScroll(delta){
  const nav = document.getElementById('sidebarNav');
  if(nav) nav.scrollBy({top: delta, behavior: 'smooth'});
}

// Toast
function showToast(msg, icon){
  let t = document.getElementById('globalToast');
  if(!t){ t = document.createElement('div'); t.id='globalToast'; t.className='toast'; document.body.appendChild(t); }
  t.innerHTML = `<span class="toast-icon">${icon||'✓'}</span>${msg}`;
  t.classList.add('show');
  setTimeout(()=>t.classList.remove('show'), 3200);
}

// Active nav
(function(){
  const links = document.querySelectorAll('.nav-item');
  const path = window.location.pathname;
  links.forEach(l => {
    const href = l.getAttribute('href');
    if(!href || href === '/' || href.includes('logout')) return;
    if(path === href || path.startsWith(href + '/')) l.classList.add('active');
  });
})();
"""


def render_shell(content, title="JH Portal", sidebar_html="", topbar_title="", active_page=""):
    _admin = current_admin()
    _student = current_student()
    if _admin:
        logout_btn = '<a href="/logout" class="btn btn-danger btn-sm" style="display:inline-flex;align-items:center;gap:6px;text-decoration:none;padding:7px 14px;font-size:12.5px"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>Log Out</a>'
    elif _student:
        logout_btn = '<a href="/student-logout" class="btn btn-danger btn-sm" style="display:inline-flex;align-items:center;gap:6px;text-decoration:none;padding:7px 14px;font-size:12.5px"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>Log Out</a>'
    else:
        logout_btn = ""
    return render_template_string(f"""<!DOCTYPE html>
<html data-theme="light" lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} — JH Student Services</title>
<style>{BASE_STYLES}</style>
<script>(function(){{const t=localStorage.getItem('jh_theme')||'light';document.documentElement.setAttribute('data-theme',t);}})();</script>
</head>
<body>
<div class="app-shell">
  {sidebar_html}
  <div class="main-content">
    <div class="topbar">
      <div class="topbar-logo">
        <img src="https://jhtraining.co.za/images/jhdevelopment.png"
             alt="JH Skills Development"
             onerror="this.style.display='none';this.nextElementSibling.style.display='flex'">
        <div class="topbar-logo-fallback" style="display:none">JH</div>
      </div>
      <span class="topbar-title">{topbar_title}</span>
      <div class="topbar-actions">
        <div class="search-bar">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
          <input type="text" placeholder="Search...">
        </div>
        <button class="notif-btn" title="Notifications">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>
          <span class="notif-dot"></span>
        </button>
        <button class="theme-btn" id="themeBtn" onclick="toggleTheme()"></button>
        {logout_btn}
      </div>
    </div>
    <div class="page">{content}</div>
  </div>
</div>
<div class="toast" id="globalToast"></div>
<script>{BASE_JS}</script>
</body>
</html>""")


def admin_sidebar(current_path=""):
    admin = current_admin()
    initials = "".join(w[0] for w in admin["name"].split()[:2]) if admin else "A"
    links = [
        ("/admin/dashboard", "🏠", "Dashboard", ""),
        ("/learners", "👥", "Learners", ""),
        ("/admin/interventions", "📚", "Programmes", ""),
        ("/documents", "📁", "Documents", ""),
        ("/clients", "🏢", "Clients", ""),
        ("/admin/activity", "📊", "Activity", ""),
        ("/admin/profile", "⚙️", "Settings", ""),
        ("/admin/messages", "💬", "Messages", ""),
        ("/admin/meet", "📹", "Meet", ""),
    ]
    nav_items = ""
    for href, icon, label, badge in links:
        active = "active" if current_path == href else ""
        b = f'<span class="nav-badge">{badge}</span>' if badge else ""
        nav_items += f'<a class="nav-item {active}" href="{href}"><span class="nav-icon">{icon}</span><span class="nav-label">{label}</span>{b}</a>\n'
    return f"""
<aside class="sidebar" id="sidebar">
  <div class="sidebar-header">
    <a href="/admin/dashboard" class="logo-btn">
      <div class="logo-mark">JH</div>
      <div class="logo-text">JH Student<br>Services</div>
    </a>
    <button class="sidebar-toggle" onclick="toggleSidebar()">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 18l-6-6 6-6"/></svg>
    </button>
  </div>
  <button class="sidebar-scroll-btn" onclick="sidebarScroll(-80)" title="Scroll up">
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="18 15 12 9 6 15"/></svg>
  </button>
  <div class="sidebar-section" id="sidebarNav">
    <div class="sidebar-label">Main Menu</div>
    {nav_items}
  </div>
  <button class="sidebar-scroll-btn" onclick="sidebarScroll(80)" title="Scroll down">
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>
  </button>
  <div class="sidebar-footer">
    <div class="nav-item" style="margin:0;border-radius:8px;background:rgba(255,255,255,.04)">
      <div class="user-avatar" style="width:30px;height:30px;font-size:11px">{initials}</div>
      <div class="nav-label" style="opacity:1">
        <div style="color:#fff;font-size:12px;font-weight:600">{admin['name'] if admin else 'Admin'}</div>
        <div style="color:rgba(255,255,255,.35);font-size:10px">{admin['role_label'] if admin else ''}</div>
      </div>
    </div>

  </div>
</aside>"""


def student_sidebar(current_path=""):
    student = current_student()
    initials = "".join(w[0] for w in student["full_name"].split()[:2]) if student else "S"
    links = [
        ("/student/dashboard", "🏠", "Dashboard", ""),
        ("/student/profile", "👤", "My Profile", ""),
        ("/student/timetable", "📅", "Schedule", ""),
        ("/student/tasks", "✅", "Tasks", str(len(STUDENT_TASKS))),
        ("/student/results", "📝", "Assessments", ""),
        ("/student/registration", "📋", "Registration", ""),
        ("/student/lms", "💻", "LMS", ""),
        ("/student/fees", "💰", "Fees", ""),
        ("/student/records", "📂", "Records", ""),
        ("/student/services", "🏫", "Services", ""),
        ("/student/support", "🤝", "Support", ""),
        ("/student/notes", "📒", "Notes", str(len(STUDENT_NOTES))),
        ("/student/announcements", "📢", "Notices", str(len(ANNOUNCEMENTS))),
        ("/student/messages", "💬", "Messages", ""),
        ("/student/meet", "📹", "Meet", ""),
    ]
    nav_items = ""
    for href, icon, label, badge in links:
        active = "active" if current_path == href else ""
        b = f'<span class="nav-badge">{badge}</span>' if badge else ""
        nav_items += f'<a class="nav-item {active}" href="{href}"><span class="nav-icon">{icon}</span><span class="nav-label">{label}</span>{b}</a>\n'
    return f"""
<aside class="sidebar" id="sidebar">
  <div class="sidebar-header">
    <a href="/student/dashboard" class="logo-btn">
      <div class="logo-mark">JH</div>
      <div class="logo-text">Learner<br>Portal</div>
    </a>
    <button class="sidebar-toggle" onclick="toggleSidebar()">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 18l-6-6 6-6"/></svg>
    </button>
  </div>
  <button class="sidebar-scroll-btn" onclick="sidebarScroll(-80)" title="Scroll up">
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="18 15 12 9 6 15"/></svg>
  </button>
  <div class="sidebar-section" id="sidebarNav">
    <div class="sidebar-label">Navigation</div>
    {nav_items}
  </div>
  <button class="sidebar-scroll-btn" onclick="sidebarScroll(80)" title="Scroll down">
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>
  </button>
  <div class="sidebar-footer">
    <div class="nav-item" style="margin:0;border-radius:8px;background:rgba(255,255,255,.04)">
      <div class="user-avatar" style="width:30px;height:30px;font-size:11px">{initials}</div>
      <div class="nav-label" style="opacity:1">
        <div style="color:#fff;font-size:12px;font-weight:600">{student['full_name'] if student else 'Learner'}</div>
        <div style="color:rgba(255,255,255,.35);font-size:10px">{student['student_number'] if student else ''}</div>
      </div>
    </div>

  </div>
</aside>"""


# ── Login (unified) ──────────────────────────────────────────────────────────
@app.route("/", methods=["GET", "POST"])
def login():
    if current_admin(): return redirect(url_for("admin_dashboard"))
    if current_student(): return redirect(url_for("student_dashboard"))

    error = None
    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "").strip()
        email_lower = identifier.lower()

        # Check admin
        admin = ADMIN_USERS.get(email_lower)
        if admin and admin["password"] == password:
            session.clear()
            session["admin_logged_in"] = True
            session["admin_email"] = email_lower
            return redirect(url_for("admin_dashboard"))

        # Check student
        student = get_student_by_username(identifier)
        if student and student["password"] == password:
            if student.get("status") not in ("Active", "Inactive"):
                error = "Your account is pending admin approval. You will receive an email once approved."
            else:
                session.clear()
                session["student_logged_in"] = True
                session["student_id"] = student["id"]
                return redirect(url_for("student_dashboard"))

        error = "Invalid credentials. Please check your email/username and password."

    page = render_template_string(f"""
<!DOCTYPE html>
<html data-theme="light" lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sign In — JH Skills Development & Consultancy</title>
<style>{BASE_STYLES}

body {{
  min-height: 100vh;
  background: var(--bg);
  display: flex;
  align-items: stretch;
}}

.login-shell {{
  display: flex;
  width: 100%;
  min-height: 100vh;
}}

/* Left panel — brand hero */
.login-hero {{
  flex: 1;
  background: var(--jh-grad);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 48px;
  position: relative;
  overflow: hidden;
}}

.login-hero::before {{
  content: '';
  position: absolute;
  inset: 0;
  background: url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%23ffffff' fill-opacity='0.04'%3E%3Ccircle cx='30' cy='30' r='20'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E");
  pointer-events: none;
}}

.hero-blob {{
  position: absolute;
  border-radius: 50%;
  filter: blur(60px);
  pointer-events: none;
}}

.hero-logo-wrap {{
  position: relative;
  z-index: 1;
  text-align: center;
  margin-bottom: 40px;
}}

.hero-logo-img {{
  width: 180px;
  height: auto;
  filter: drop-shadow(0 8px 24px rgba(0,0,0,0.25));
  margin-bottom: 20px;
}}

.hero-title {{
  font-family: 'Syne', sans-serif;
  font-weight: 800;
  font-size: 28px;
  color: #fff;
  line-height: 1.2;
  text-shadow: 0 2px 12px rgba(0,0,0,0.15);
  margin-bottom: 8px;
}}

.hero-sub {{
  font-size: 14px;
  color: rgba(255,255,255,0.82);
  font-weight: 400;
  line-height: 1.5;
}}

.hero-pills {{
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: 100%;
  max-width: 320px;
  margin-top: 40px;
}}

.hero-pill {{
  background: rgba(255,255,255,0.14);
  border: 1px solid rgba(255,255,255,0.22);
  border-radius: 40px;
  padding: 12px 20px;
  display: flex;
  align-items: center;
  gap: 12px;
  color: #fff;
  font-size: 13.5px;
  backdrop-filter: blur(8px);
}}

.hero-pill-icon {{
  font-size: 20px;
  flex-shrink: 0;
}}

/* Right panel — form */
.login-form-panel {{
  width: 480px;
  flex-shrink: 0;
  background: var(--surface);
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 60px 48px;
  position: relative;
}}

.login-theme-toggle {{
  position: absolute;
  top: 24px;
  right: 24px;
}}

.login-form-header {{
  margin-bottom: 32px;
}}

.login-form-badge {{
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: linear-gradient(90deg, #8DC63F22, #00A89D22);
  border: 1px solid #8DC63F55;
  border-radius: 20px;
  padding: 4px 12px;
  font-size: 11px;
  font-weight: 600;
  color: var(--jh-dark);
  letter-spacing: .04em;
  text-transform: uppercase;
  margin-bottom: 14px;
}}

[data-theme="dark"] .login-form-badge {{
  color: var(--jh-green);
}}

.login-title {{
  font-family: 'Syne', sans-serif;
  font-weight: 800;
  font-size: 28px;
  color: var(--text);
  line-height: 1.15;
  margin-bottom: 6px;
}}

.login-sub {{
  font-size: 14px;
  color: var(--text-2);
}}

.login-error {{
  background: rgba(255,107,107,.08);
  border: 1px solid rgba(255,107,107,.2);
  border-radius: var(--r-sm);
  padding: 11px 14px;
  color: #e05555;
  font-size: 13px;
  margin-bottom: 16px;
}}

/* Fields */
.field {{
  margin-bottom: 18px;
}}

.field label {{
  display: block;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text-2);
  margin-bottom: 6px;
  letter-spacing: .02em;
}}

.field input {{
  width: 100%;
  background: var(--bg-2);
  border: 1.5px solid var(--border);
  border-radius: var(--r-sm);
  padding: 11px 14px;
  color: var(--text);
  font-size: 14px;
  outline: none;
  transition: border-color .2s, box-shadow .2s;
}}

.field input:focus {{
  border-color: var(--jh-teal);
  box-shadow: 0 0 0 3px rgba(0,168,157,0.12);
}}

/* Buttons */
.btn-jh-primary {{
  width: 100%;
  background: var(--jh-grad);
  border: none;
  border-radius: var(--r-sm);
  padding: 13px 20px;
  color: #fff;
  font-size: 15px;
  font-weight: 700;
  font-family: 'Syne', sans-serif;
  cursor: pointer;
  letter-spacing: .02em;
  transition: opacity .2s, transform .15s, box-shadow .2s;
  box-shadow: 0 4px 18px rgba(0,168,157,0.28);
  margin-top: 4px;
}}

.btn-jh-primary:hover {{
  opacity: 0.92;
  transform: translateY(-1px);
  box-shadow: 0 6px 24px rgba(0,168,157,0.38);
}}

.btn-jh-secondary {{
  width: 100%;
  background: transparent;
  border: 2px solid var(--jh-green);
  border-radius: var(--r-sm);
  padding: 11px 20px;
  color: var(--jh-dark);
  font-size: 14px;
  font-weight: 700;
  font-family: 'Syne', sans-serif;
  cursor: pointer;
  letter-spacing: .02em;
  transition: background .2s, color .2s, transform .15s;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  text-decoration: none;
}}

[data-theme="dark"] .btn-jh-secondary {{
  color: var(--jh-green);
}}

.btn-jh-secondary:hover {{
  background: var(--jh-green);
  color: #fff;
  opacity: 1;
  transform: translateY(-1px);
}}

.login-divider {{
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 22px 0;
  color: var(--text-3);
  font-size: 12px;
}}

.login-divider::before,
.login-divider::after {{
  content: '';
  flex: 1;
  height: 1px;
  background: var(--border);
}}

.login-footer-note {{
  margin-top: 24px;
  text-align: center;
  font-size: 12px;
  color: var(--text-3);
  line-height: 1.6;
}}

@media (max-width: 820px) {{
  .login-hero {{ display: none; }}
  .login-form-panel {{ width: 100%; padding: 48px 32px; }}
}}
</style>
<script>(function(){{const t=localStorage.getItem('jh_theme')||'light';document.documentElement.setAttribute('data-theme',t);}})();</script>
</head>
<body>
<div class="login-shell">

  <!-- Left: Brand Hero -->
  <div class="login-hero">
    <div class="hero-blob" style="width:320px;height:320px;background:rgba(255,255,255,.08);top:-80px;left:-80px"></div>
    <div class="hero-blob" style="width:240px;height:240px;background:rgba(0,0,0,.1);bottom:-60px;right:-60px"></div>

    <div class="hero-logo-wrap">
      <img class="hero-logo-img"
           src="https://jhtraining.co.za/images/jhdevelopment.png"
           alt="JH Skills Development and Consultancy"
           onerror="this.style.display='none';this.nextElementSibling.style.display='flex'">
      <div style="display:none;width:100px;height:100px;background:rgba(255,255,255,.2);border-radius:20px;margin:0 auto 20px;align-items:center;justify-content:center;font-family:'Syne',sans-serif;font-weight:800;font-size:32px;color:#fff">JH</div>
      <div class="hero-title">JH Skills Development<br>& Consultancy</div>
      <div class="hero-sub">Empowering learners through quality<br>skills development programmes</div>
    </div>

    <div class="hero-pills">
      <div class="hero-pill">
        <span class="hero-pill-icon">🎓</span>
        <span>Access your learner portal and course materials</span>
      </div>
      <div class="hero-pill">
        <span class="hero-pill-icon">📋</span>
        <span>Track your progress, tasks and assessments</span>
      </div>
      <div class="hero-pill">
        <span class="hero-pill-icon">📂</span>
        <span>Upload and manage your documents securely</span>
      </div>
    </div>
  </div>

  <!-- Right: Form Panel -->
  <div class="login-form-panel">
    <button class="theme-btn login-theme-toggle" id="themeBtn" onclick="toggleTheme()"></button>

    <div class="login-form-header">
      <div class="login-form-badge">🌿 Student & Admin Portal</div>
      <h2 class="login-title">Welcome back</h2>
      <p class="login-sub">Sign in to access your portal</p>
    </div>

    {'<div class="login-error">⚠️ ' + error + '</div>' if error else ''}

    <form method="POST">
      <div class="field">
        <label>Email or Username</label>
        <input name="identifier" type="text" placeholder="Enter your email or username" required autofocus>
      </div>
      <div class="field">
        <label>Password</label>
        <input name="password" type="password" placeholder="Enter your password" required>
      </div>
      <button class="btn-jh-primary" type="submit">Sign In →</button>
    </form>

    <div class="login-divider">or</div>

    <a href="/student/signup" class="btn-jh-secondary">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><line x1="19" y1="8" x2="19" y2="14"/><line x1="22" y1="11" x2="16" y2="11"/></svg>
      Register as a Student
    </a>

    <div class="login-footer-note">
      By signing in you agree to the JH Skills Development<br>terms of use and privacy policy.
    </div>
  </div>

</div>
<script>{BASE_JS}</script>
</body>
</html>
""")
    return page


@app.after_request
def no_cache_for_protected(response):
    if request.path.startswith('/student/') or request.path.startswith('/admin/'):
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, private'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response

@app.route("/logout", methods=["GET", "POST"])
def logout():
    session.pop("admin_logged_in", None)
    session.pop("admin_email", None)
    session.clear()
    return redirect(url_for("login"))

@app.route("/student-logout", methods=["GET", "POST"])
def student_logout():
    session.pop("student_logged_in", None)
    session.pop("student_id", None)
    session.clear()
    response = redirect(url_for("login"))
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


# ── Student self-registration ─────────────────────────────────────────────────
@app.route("/student/signup", methods=["GET", "POST"])
def student_signup():
    if current_student(): return redirect(url_for("student_dashboard"))
    if current_admin(): return redirect(url_for("admin_dashboard"))

    error = None
    success = None
    pending_id = None

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email     = request.form.get("email", "").strip()
        phone     = request.form.get("phone", "").strip()
        id_number = request.form.get("id_number", "").strip()
        gender    = request.form.get("gender", "").strip()
        address   = request.form.get("address", "").strip()
        programme = request.form.get("programme", "").strip()
        password  = request.form.get("password", "").strip()
        confirm_password = request.form.get("confirm_password", "").strip()

        if not all([full_name, email, phone, id_number, gender, address, programme, password]):
            error = "Please fill in all required fields."
        elif password != confirm_password:
            error = "Passwords do not match."
        elif len(password) < 6:
            error = "Password must be at least 6 characters."
        else:
            students = load_students()
            pending  = load_pending()
            existing_students = [s for s in students if s.get("email","").lower() == email.lower() or s.get("id_number","") == id_number]
            existing_pending  = [p for p in pending  if p.get("email","").lower() == email.lower() or p.get("id_number","") == id_number]
            if existing_students or existing_pending:
                error = "An account with this email or ID number already exists."
            else:
                pid = secrets.token_hex(12)
                record = {
                    "id": pid, "full_name": full_name, "email": email, "phone": phone,
                    "id_number": id_number, "gender": gender, "address": address,
                    "programme": programme, "password": password,
                    "submitted_at": datetime.now().isoformat(),
                    "email_verified": False, "phone_verified": False,
                }
                pending.append(record)
                save_pending(pending)

                email_token = create_email_token(pid)
                otp         = create_phone_otp(pid)
                send_verification_email(email, full_name, pid, email_token)
                send_otp_sms(phone, otp, full_name)

                pending_id = pid
                success = "submitted"

    PROGRAMMES = [
        "Diploma in Information Technology",
        "Business Administration NQF 4",
        "National Certificate: IT: Systems Development NQF 5",
        "Further Education and Training Certificate: Business Administration NQF 4",
        "National Certificate: New Venture Creation NQF 2",
        "Skills Programme: Project Management",
        "Learnerships: Generic Management NQF 5",
        "Other / Not Listed",
    ]

    if success == "submitted":
        # Show verification UI
        page = render_template_string(f"""
<!DOCTYPE html>
<html data-theme="light" lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Verify Your Details — JH Portal</title>
<style>{BASE_STYLES}
body{{background:var(--bg);min-height:100vh}}
.vbox{{max-width:480px;margin:60px auto;padding:20px}}
.vcard{{background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:36px;box-shadow:0 4px 32px rgba(0,0,0,.07)}}
.vstep{{display:flex;align-items:center;gap:10px;margin-bottom:24px;font-size:13.5px;color:var(--text-2)}}
.vstep-num{{width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:12px;flex-shrink:0}}
.vstep-num.done{{background:rgba(34,197,94,.15);color:#16a34a}}
.vstep-num.active{{background:var(--jh-teal);color:#fff}}
.vstep-num.wait{{background:var(--bg-2);color:var(--text-3)}}
.otp-inputs{{display:flex;gap:8px;justify-content:center;margin:18px 0}}
.otp-inputs input{{width:44px;height:52px;border-radius:10px;border:1.5px solid var(--border);background:var(--bg-2);color:var(--text);font-size:22px;font-weight:700;text-align:center;font-family:'Syne',sans-serif;outline:none}}
.otp-inputs input:focus{{border-color:var(--jh-teal);box-shadow:0 0 0 3px rgba(0,168,157,.12)}}
.vbtn{{width:100%;background:var(--jh-grad);border:none;border-radius:8px;padding:13px;color:#fff;font-size:15px;font-weight:700;font-family:'Syne',sans-serif;cursor:pointer;margin-top:8px;transition:opacity .2s}}
.vbtn:hover{{opacity:.9}}
.vmsg{{font-size:13px;margin-top:12px;min-height:20px;text-align:center}}
.vmsg.err{{color:#e05555}}.vmsg.ok{{color:#16a34a}}
</style>
<script>(function(){{const t=localStorage.getItem('jh_theme')||'light';document.documentElement.setAttribute('data-theme',t);}})();</script>
</head>
<body>
<div class="vbox">
  <div style="text-align:center;margin-bottom:28px">
    <img src="https://jhtraining.co.za/images/jhdevelopment.png" style="height:56px" onerror="this.style.display='none'">
    <h1 style="font-family:'Syne',sans-serif;font-size:22px;margin:12px 0 4px">Almost there!</h1>
    <p style="color:var(--text-2);font-size:14px">Verify your email and mobile number to complete registration</p>
  </div>

  <div class="vcard" id="emailCard">
    <div class="vstep"><div class="vstep-num active" id="step1num">1</div><div><strong>Verify your email</strong><br><span style="font-size:12px;color:var(--text-3)">Check your inbox for a verification link</span></div></div>
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:8px;padding:14px 16px;font-size:13.5px;text-align:center;margin-bottom:16px">
      📧 We sent a link to <strong>your email</strong>.<br>Click it to verify, then come back here.
    </div>
    <div id="emailWait" style="text-align:center;color:var(--text-3);font-size:13px">Waiting for email verification…</div>
    <button class="vbtn" style="background:var(--bg-2);color:var(--text-2);border:1px solid var(--border);margin-top:14px" onclick="checkEmailStatus()">
      ✅ I've verified my email
    </button>
    <div style="text-align:center;margin-top:10px">
      <a href="#" onclick="resendEmail()" style="font-size:12px;color:var(--jh-teal)">Resend verification email</a>
    </div>
    <div class="vmsg" id="emailMsg"></div>
  </div>

  <div class="vcard" id="otpCard" style="display:none;margin-top:20px">
    <div class="vstep"><div class="vstep-num active" id="step2num">2</div><div><strong>Verify your mobile number</strong><br><span style="font-size:12px;color:var(--text-3)">Enter the 6-digit OTP sent to your phone</span></div></div>
    <div class="otp-inputs" id="otpInputs">
      <input type="text" maxlength="1" oninput="otpNext(this,0)" onkeydown="otpBack(event,0)">
      <input type="text" maxlength="1" oninput="otpNext(this,1)" onkeydown="otpBack(event,1)">
      <input type="text" maxlength="1" oninput="otpNext(this,2)" onkeydown="otpBack(event,2)">
      <input type="text" maxlength="1" oninput="otpNext(this,3)" onkeydown="otpBack(event,3)">
      <input type="text" maxlength="1" oninput="otpNext(this,4)" onkeydown="otpBack(event,4)">
      <input type="text" maxlength="1" oninput="otpNext(this,5)" onkeydown="otpBack(event,5)">
    </div>
    <button class="vbtn" onclick="submitOtp()">Verify OTP →</button>
    <div style="text-align:center;margin-top:10px">
      <a href="#" onclick="resendOtp()" style="font-size:12px;color:var(--jh-teal)">Resend OTP</a>
    </div>
    <div class="vmsg" id="otpMsg"></div>
  </div>

  <div id="doneCard" style="display:none;margin-top:20px">
    <div class="vcard" style="text-align:center">
      <div style="font-size:56px;margin-bottom:12px">🎉</div>
      <h2 style="font-family:'Syne',sans-serif;font-size:20px;margin-bottom:8px">Verification Complete!</h2>
      <p style="color:var(--text-2);font-size:14px;line-height:1.6">Your registration is now awaiting admin approval.<br>You'll receive an email with your login details once approved.</p>
      <a href="/" style="display:inline-block;margin-top:20px;background:var(--jh-grad);color:#fff;text-decoration:none;padding:12px 28px;border-radius:8px;font-weight:700;font-family:'Syne',sans-serif">← Back to Sign In</a>
    </div>
  </div>
</div>
<script>
const PENDING_ID = '{pending_id}';
const otpEls = Array.from(document.querySelectorAll('#otpInputs input'));

function otpNext(el, idx) {{
  el.value = el.value.replace(/\\D/g,'');
  if (el.value && idx < 5) otpEls[idx+1].focus();
}}
function otpBack(e, idx) {{
  if (e.key === 'Backspace' && !otpEls[idx].value && idx > 0) otpEls[idx-1].focus();
}}

async function checkEmailStatus() {{
  const res = await fetch('/api/verify/email-status', {{
    method:'POST', headers:{{'Content-Type':'application/json'}},
    body: JSON.stringify({{id: PENDING_ID}})
  }});
  const d = await res.json();
  const msg = document.getElementById('emailMsg');
  if (d.verified) {{
    msg.className = 'vmsg ok'; msg.textContent = '✅ Email verified!';
    document.getElementById('step1num').className = 'vstep-num done';
    document.getElementById('step1num').textContent = '✓';
    setTimeout(() => {{
      document.getElementById('otpCard').style.display = 'block';
      otpEls[0].focus();
    }}, 600);
  }} else {{
    msg.className = 'vmsg err'; msg.textContent = 'Not verified yet — please click the link in your email.';
  }}
}}

async function resendEmail() {{
  const res = await fetch('/api/verify/resend-email', {{
    method:'POST', headers:{{'Content-Type':'application/json'}},
    body: JSON.stringify({{id: PENDING_ID}})
  }});
  const d = await res.json();
  const msg = document.getElementById('emailMsg');
  msg.className = 'vmsg ok'; msg.textContent = d.message || 'Resent!';
}}

async function submitOtp() {{
  const otp = otpEls.map(e => e.value).join('');
  if (otp.length !== 6) {{ document.getElementById('otpMsg').className='vmsg err'; document.getElementById('otpMsg').textContent='Enter all 6 digits.'; return; }}
  const res = await fetch('/api/verify/otp', {{
    method:'POST', headers:{{'Content-Type':'application/json'}},
    body: JSON.stringify({{id: PENDING_ID, otp}})
  }});
  const d = await res.json();
  const msg = document.getElementById('otpMsg');
  if (d.ok) {{
    msg.className='vmsg ok'; msg.textContent='✅ Phone verified!';
    setTimeout(() => {{
      document.getElementById('emailCard').style.display='none';
      document.getElementById('otpCard').style.display='none';
      document.getElementById('doneCard').style.display='block';
    }}, 800);
  }} else {{
    msg.className='vmsg err'; msg.textContent = d.error || 'Invalid OTP.';
    otpEls.forEach(e => e.value=''); otpEls[0].focus();
  }}
}}

async function resendOtp() {{
  const res = await fetch('/api/verify/resend-otp', {{
    method:'POST', headers:{{'Content-Type':'application/json'}},
    body: JSON.stringify({{id: PENDING_ID}})
  }});
  const d = await res.json();
  const msg = document.getElementById('otpMsg');
  msg.className='vmsg ok'; msg.textContent = d.message || 'OTP resent!';
}}
</script>
</body>
</html>
""")
        return page

    page = render_template_string(f"""
<!DOCTYPE html>
<html data-theme="light" lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Student Registration — JH Skills Development & Consultancy</title>
<style>{BASE_STYLES}

body {{ background: var(--bg); min-height: 100vh; }}

.signup-shell {{
  min-height: 100vh;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding: 48px 20px;
}}

.signup-box {{
  width: 100%;
  max-width: 600px;
}}

.signup-header {{
  text-align: center;
  margin-bottom: 32px;
}}

.signup-logo {{
  width: 100px;
  height: auto;
  margin-bottom: 16px;
}}

.signup-title {{
  font-family: 'Syne', sans-serif;
  font-weight: 800;
  font-size: 26px;
  color: var(--text);
  margin-bottom: 6px;
}}

.signup-sub {{
  font-size: 14px;
  color: var(--text-2);
}}

.signup-card {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 36px;
  box-shadow: 0 4px 32px rgba(0,0,0,.07);
}}

.field {{ margin-bottom: 18px; }}

.field label {{
  display: block;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text-2);
  margin-bottom: 6px;
}}

.field input, .field select {{
  width: 100%;
  background: var(--bg-2);
  border: 1.5px solid var(--border);
  border-radius: 8px;
  padding: 11px 14px;
  color: var(--text);
  font-size: 14px;
  font-family: 'DM Sans', sans-serif;
  outline: none;
  transition: border-color .2s, box-shadow .2s;
}}

.field input:focus, .field select:focus {{
  border-color: var(--jh-teal);
  box-shadow: 0 0 0 3px rgba(0,168,157,0.12);
}}

.field-row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}

.signup-error {{
  background: rgba(255,107,107,.08);
  border: 1px solid rgba(255,107,107,.2);
  border-radius: 8px;
  padding: 12px 14px;
  color: #e05555;
  font-size: 13px;
  margin-bottom: 20px;
}}

.section-divider {{
  font-family: 'Syne', sans-serif;
  font-weight: 700;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: .1em;
  color: var(--text-3);
  margin: 24px 0 16px;
  display: flex;
  align-items: center;
  gap: 10px;
}}

.section-divider::after {{
  content: '';
  flex: 1;
  height: 1px;
  background: var(--border);
}}

.btn-jh-primary {{
  width: 100%;
  background: var(--jh-grad);
  border: none;
  border-radius: 8px;
  padding: 13px 20px;
  color: #fff;
  font-size: 15px;
  font-weight: 700;
  font-family: 'Syne', sans-serif;
  cursor: pointer;
  box-shadow: 0 4px 18px rgba(0,168,157,0.28);
  transition: opacity .2s, transform .15s;
  margin-top: 8px;
}}

.btn-jh-primary:hover {{ opacity: .92; transform: translateY(-1px); }}

.back-link {{
  text-align: center;
  margin-top: 20px;
  font-size: 13px;
  color: var(--text-3);
}}

.back-link a {{ color: var(--jh-teal); font-weight: 600; }}

@media (max-width: 560px) {{
  .field-row {{ grid-template-columns: 1fr; }}
  .signup-card {{ padding: 24px 20px; }}
}}
</style>
<script>(function(){{const t=localStorage.getItem('jh_theme')||'light';document.documentElement.setAttribute('data-theme',t);}})();</script>
</head>
<body>
<div class="signup-shell">
  <div class="signup-box">
    <div class="signup-header">
      <img class="signup-logo"
           src="https://jhtraining.co.za/images/jhdevelopment.png"
           alt="JH Skills Development"
           onerror="this.style.display='none'">
      <h1 class="signup-title">Student Registration</h1>
      <p class="signup-sub">Create your learner account to access the JH portal</p>
    </div>

    <div class="signup-card">
      {'<div class="signup-error">⚠️ ' + error + '</div>' if error else ''}

      <form method="POST">

      <div class="section-divider">Personal Information</div>
      <div class="field"><label>Full Name *</label><input name="full_name" type="text" placeholder="e.g. Thabo Mokoena" required></div>
      <div class="field-row">
        <div class="field"><label>Email Address *</label><input name="email" type="email" placeholder="your@email.com" required></div>
        <div class="field"><label>Phone Number *</label><input name="phone" type="tel" placeholder="e.g. +27 71 234 5678" required></div>
      </div>
      <div class="field-row">
        <div class="field"><label>ID Number *</label><input name="id_number" type="text" placeholder="13-digit SA ID number" required></div>
        <div class="field"><label>Gender *</label><select name="gender" required><option value="">Select gender</option><option>Male</option><option>Female</option><option>Non-binary</option><option>Prefer not to say</option></select></div>
      </div>
      <div class="field"><label>Residential Address *</label><input name="address" type="text" placeholder="e.g. Johannesburg, Gauteng" required></div>

      <div class="section-divider">Programme Selection</div>
      <div class="field"><label>Programme / Course *</label><select name="programme" required><option value="">Select a programme</option>{"".join(f"<option>{p}</option>" for p in PROGRAMMES)}</select></div>

      <div class="section-divider">Set Your Password</div>
      <div class="field-row">
        <div class="field"><label>Password *</label><input name="password" type="password" placeholder="Min. 6 characters" required></div>
        <div class="field"><label>Confirm Password *</label><input name="confirm_password" type="password" placeholder="Repeat password" required></div>
      </div>

      <button class="btn-jh-primary" type="submit">Submit Registration →</button>
      </form>

      <div class="back-link"><a href="/">← Already have an account? Sign in</a></div>
    </div>
  </div>
</div>
<script>{BASE_JS}</script>
</body>
</html>
""")
    return page


# ── Email-link verification ───────────────────────────────────────────────────
@app.route("/verify-email")
def verify_email():
    pid   = request.args.get("id", "")
    token = request.args.get("token", "")
    ok    = verify_email_token(pid, token)
    if ok:
        pending = load_pending()
        for p in pending:
            if p["id"] == pid:
                p["email_verified"] = True
                break
        save_pending(pending)
        msg = "✅ Email verified successfully! Go back to the registration page and click <strong>'I've verified my email'</strong> to continue."
        colour = "#2D6A4F"
    else:
        msg = "⚠️ This verification link is invalid or has already been used."
        colour = "#e05555"
    return render_template_string(f"""<!DOCTYPE html><html data-theme="light" lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Email Verification — JH Portal</title><style>{BASE_STYLES}</style></head><body style="display:flex;align-items:center;justify-content:center;min-height:100vh;background:var(--bg)"><div style="max-width:460px;background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:40px;text-align:center;box-shadow:0 4px 32px rgba(0,0,0,.07)"><img src="https://jhtraining.co.za/images/jhdevelopment.png" style="height:56px;margin-bottom:20px" onerror="this.style.display='none'"><p style="font-size:15px;color:{colour};line-height:1.7">{msg}</p><a href="/" style="display:inline-block;margin-top:24px;color:var(--jh-teal);font-weight:600;font-size:14px">← Back to Portal</a></div></body></html>""")


# ── Verification API endpoints ────────────────────────────────────────────────
@app.route("/api/verify/email-status", methods=["POST"])
def api_verify_email_status():
    data = request.get_json(force=True) or {}
    pid  = data.get("id", "")
    pending = load_pending()
    for p in pending:
        if p["id"] == pid:
            return jsonify({"verified": p.get("email_verified", False)})
    return jsonify({"verified": False})

@app.route("/api/verify/resend-email", methods=["POST"])
def api_resend_email():
    data = request.get_json(force=True) or {}
    pid  = data.get("id", "")
    pending = load_pending()
    rec = next((p for p in pending if p["id"] == pid), None)
    if not rec:
        return jsonify({"ok": False, "message": "Registration not found."})
    token = create_email_token(pid)
    send_verification_email(rec["email"], rec["full_name"], pid, token)
    return jsonify({"ok": True, "message": "Verification email resent. Check your inbox."})

@app.route("/api/verify/otp", methods=["POST"])
def api_verify_otp():
    data = request.get_json(force=True) or {}
    pid  = data.get("id", "")
    otp  = data.get("otp", "").strip()
    # Must also have email verified first
    pending = load_pending()
    rec = next((p for p in pending if p["id"] == pid), None)
    if not rec:
        return jsonify({"ok": False, "error": "Registration not found."})
    if not rec.get("email_verified"):
        return jsonify({"ok": False, "error": "Please verify your email first."})
    ok, msg = verify_phone_otp(pid, otp)
    if ok:
        rec["phone_verified"] = True
        rec["status"] = "Pending Admin"
        save_pending(pending)
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": msg})

@app.route("/api/verify/resend-otp", methods=["POST"])
def api_resend_otp():
    data = request.get_json(force=True) or {}
    pid  = data.get("id", "")
    pending = load_pending()
    rec = next((p for p in pending if p["id"] == pid), None)
    if not rec:
        return jsonify({"ok": False, "message": "Registration not found."})
    otp = create_phone_otp(pid)
    send_otp_sms(rec["phone"], otp, rec["full_name"])
    return jsonify({"ok": True, "message": "OTP resent to your phone."})


# ── Admin: approve learner ────────────────────────────────────────────────────
@app.route("/api/admin/approve-learner", methods=["POST"])
@admin_required
def api_approve_learner():
    data = request.get_json(force=True) or {}
    pid  = data.get("id", "")
    pending = load_pending()
    rec = next((p for p in pending if p["id"] == pid), None)
    if not rec:
        return jsonify({"ok": False, "error": "Pending registration not found."})

    students = load_students()
    n   = 1000 + len(students) + 1
    sid = str(n)
    first_name = rec["full_name"].split()[0].lower()
    username   = f"learner.jh-{sid}"
    password   = rec["password"]

    new_student = {
        "id": sid, "student_number": f"2026{sid}", "full_name": rec["full_name"],
        "email": rec["email"], "phone": rec["phone"], "id_number": rec["id_number"],
        "gender": rec["gender"], "address": rec["address"], "employment": "Unemployed",
        "qualification": rec["programme"], "faculty": "Pending Assignment",
        "programme": rec["programme"], "coordinator": "Pending Assignment",
        "location": "Pending Assignment", "start_date": datetime.now().strftime("%Y-%m-%d"),
        "status": "Active", "username": username, "password": password,
        "campus": "Pending Assignment", "year_level": "Year 1",
        "emergency_contact_name": "", "emergency_contact_phone": "",
        "emergency_contact_relationship": "",
        "modules": [], "tuition_balance": "R0",
        "bursary_status": "Pending", "registration_status": "Registered",
        "lms_link": "https://canvas.instructure.com/",
        "portal_email": f"{first_name}.{sid}@student.jh.co.za",
    }
    students.insert(0, new_student)
    save_students(students)

    # Remove from pending
    pending = [p for p in pending if p["id"] != pid]
    save_pending(pending)

    # Notify learner
    send_approval_email(rec["email"], rec["full_name"], username, password)

    return jsonify({"ok": True, "student": new_student})

@app.route("/api/admin/reject-learner", methods=["POST"])
@admin_required
def api_reject_learner():
    data = request.get_json(force=True) or {}
    pid  = data.get("id", "")
    pending = load_pending()
    pending = [p for p in pending if p["id"] != pid]
    save_pending(pending)
    return jsonify({"ok": True})


# ── Admin routes ──────────────────────────────────────────────────────────────
@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    students = load_students()
    active_count = len([s for s in students if s.get("status") == "Active"])
    content = f"""
<div class="page-header">
  <h1>Admin Dashboard</h1>
  <p>Overview of all student services operations — {datetime.now().strftime('%A, %d %B %Y')}</p>
</div>
<div class="grid-4" style="margin-bottom:24px">
  <div class="stat-card">
    <div class="stat-icon" style="background:rgba(0,168,157,.12)">👥</div>
    <div class="stat-value">{len(students)}</div>
    <div class="stat-label">Total Learners</div>
    <div class="stat-change up">↑ Recently registered</div>
  </div>
  <div class="stat-card">
    <div class="stat-icon" style="background:rgba(0,210,200,.12)">✅</div>
    <div class="stat-value">{active_count}</div>
    <div class="stat-label">Active Students</div>
    <div class="stat-change neutral">Currently enrolled</div>
  </div>
  <div class="stat-card">
    <div class="stat-icon" style="background:rgba(34,197,94,.12)">📚</div>
    <div class="stat-value">{len(LEARNING_INTERVENTIONS)}</div>
    <div class="stat-label">Programmes</div>
    <div class="stat-change neutral">Running now</div>
  </div>
  <div class="stat-card">
    <div class="stat-icon" style="background:rgba(255,107,107,.12)">📢</div>
    <div class="stat-value">{len(ANNOUNCEMENTS)}</div>
    <div class="stat-label">Announcements</div>
    <div class="stat-change neutral">This week</div>
  </div>
</div>
<div class="grid-2">
  <div class="card">
    <div class="card-title">Recent Learners</div>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Name</th><th>Programme</th><th>Status</th></tr></thead>
        <tbody>
          {''.join(f'<tr><td><a href="/learners/{s["id"]}">{s["full_name"]}</a></td><td>{s.get("programme","—")[:30]}</td><td><span class="badge badge-green">{s.get("status","—")}</span></td></tr>' for s in students[:5])}
        </tbody>
      </table>
    </div>
    <a href="/learners" class="btn btn-secondary btn-sm" style="margin-top:14px">View All Learners →</a>
  </div>
  <div class="card">
    <div class="card-title">Recent Notices</div>
    {''.join(f'<div class="notice-card" style="margin-bottom:10px"><div class="notice-dot"></div><div><div style="font-weight:600;font-size:13.5px;color:var(--text)">{a["title"]}</div><div style="font-size:12px;color:var(--text-3);margin-top:2px">{a["category"]} · {a["date"]}</div></div></div>' for a in ANNOUNCEMENTS)}
  </div>
</div>
<div style="margin-top:20px" class="grid-2">
  <div class="card">
    <div class="card-title">Active Programmes</div>
    {''.join(f'<div style="padding:12px 0;border-bottom:1px solid var(--border)"><div style="font-weight:600;font-size:13.5px">{i["name"]}</div><div style="font-size:12px;color:var(--text-3);margin-top:2px">{i["participants"]} participants · {i["location"]}</div><div class="progress-bar" style="margin-top:8px"><div class="progress-fill" style="width:65%"></div></div></div>' for i in LEARNING_INTERVENTIONS)}
  </div>
  <div class="card">
    <div class="card-title">Quick Actions</div>
    <div style="display:flex;flex-direction:column;gap:10px">
      <a href="/learners" class="btn btn-primary">➕ Register New Learner</a>
      <a href="/documents" class="btn btn-secondary">📁 Manage Documents</a>
      <a href="/clients" class="btn btn-secondary">🏢 View Clients</a>
      <a href="/admin/profile" class="btn btn-secondary">⚙️ Admin Settings</a>
    </div>
  </div>
</div>
"""
    return render_shell(content, "Dashboard", admin_sidebar("/admin/dashboard"), "Admin Dashboard")


@app.route("/learners")
@admin_required
def learners():
    students = load_students()
    pending  = [p for p in load_pending() if p.get("status") == "Pending Admin"]
    rows = "".join(f'''
    <tr>
      <td><a href="/learners/{s['id']}" style="font-weight:600">{s['full_name']}</a></td>
      <td style="color:var(--text-2)">{s.get('student_number','')}</td>
      <td>{s.get('programme','')[:35]}</td>
      <td>{s.get('campus','')}</td>
      <td><span class="badge badge-{'green' if s.get('status')=='Active' else 'gray'}">{s.get('status','')}</span></td>
      <td><a href="/learners/{s['id']}" class="btn btn-secondary btn-sm">View</a></td>
    </tr>''' for s in students)

    pending_badge = f'<span style="background:#e05555;color:#fff;border-radius:20px;font-size:11px;font-weight:700;padding:2px 8px;margin-left:8px">{len(pending)}</span>' if pending else ''
    pending_rows  = "".join(f'''
    <tr id="pr-{p['id']}">
      <td style="font-weight:600">{p['full_name']}</td>
      <td style="color:var(--text-2)">{p.get('email','')}</td>
      <td>{p.get('phone','')}</td>
      <td>{p.get('programme','')[:35]}</td>
      <td style="color:var(--text-3);font-size:12px">{p.get('submitted_at','')[:10]}</td>
      <td>
        <div style="display:flex;gap:6px">
          <button onclick="approveLearner('{p['id']}')"
            style="background:linear-gradient(135deg,#8DC63F,#00A89D);color:#fff;border:none;border-radius:6px;padding:6px 14px;font-size:12px;font-weight:700;cursor:pointer;font-family:'Syne',sans-serif;white-space:nowrap">
            ✅ Approve
          </button>
          <button onclick="rejectLearner('{p['id']}')"
            style="background:none;border:1px solid #dc3535;color:#dc3535;border-radius:6px;padding:6px 10px;font-size:12px;cursor:pointer">
            ✕
          </button>
        </div>
      </td>
    </tr>''' for p in pending)

    pending_section = f"""
<div class="card" style="margin-bottom:24px;border:1.5px solid rgba(229,115,115,.35);background:rgba(229,115,115,.04)">
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px">
    <div class="card-title" style="margin:0;color:#c0392b">🔔 Pending Approvals{pending_badge}</div>
    <span style="font-size:12px;color:var(--text-3)">{len(pending)} learner{'s' if len(pending)!=1 else ''} awaiting review</span>
  </div>
  <div class="table-wrap">
    <table id="pendingTable">
      <thead><tr><th>Full Name</th><th>Email</th><th>Phone</th><th>Programme</th><th>Submitted</th><th></th></tr></thead>
      <tbody>{pending_rows}</tbody>
    </table>
  </div>
</div>""" if pending else ""

    content = f"""
<div class="page-header" style="display:flex;align-items:center;justify-content:space-between">
  <div><h1>Learner Register</h1><p>{len(students)} registered students{(' · ' + str(len(pending)) + ' pending approval') if pending else ''}</p></div>
  <button class="quick-add" onclick="document.getElementById('regModal').style.display='flex'">➕ Register Learner</button>
</div>

{pending_section}

<div class="card" style="margin-bottom:20px">
  <div style="display:flex;gap:10px;align-items:center">
    <div class="search-bar" style="flex:1">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
      <input id="searchInput" type="text" placeholder="Search learners..." oninput="filterTable(this.value)" style="width:100%">
    </div>
    <select class="btn btn-secondary" style="padding:9px 12px;cursor:pointer" onchange="filterStatus(this.value)">
      <option value="">All Status</option>
      <option>Active</option>
      <option>Inactive</option>
    </select>
  </div>
</div>
<div class="table-wrap">
  <table id="learnersTable">
    <thead><tr><th>Full Name</th><th>Student No.</th><th>Programme</th><th>Campus</th><th>Status</th><th></th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>

<!-- Registration Modal -->
<div id="regModal" style="display:none;position:fixed;inset:0;z-index:500;background:rgba(0,0,0,.55);align-items:center;justify-content:center;padding:20px">
  <div style="background:var(--surface);border:1px solid var(--border);border-radius:16px;width:100%;max-width:680px;max-height:90vh;overflow-y:auto;padding:32px;position:relative">
    <button onclick="document.getElementById('regModal').style.display='none'" style="position:absolute;top:16px;right:16px;background:none;border:none;cursor:pointer;font-size:20px;color:var(--text-2)">✕</button>
    <h2 style="font-family:'Syne',sans-serif;font-size:20px;margin-bottom:20px">Register New Learner</h2>
    <div id="regMsg" style="display:none;margin-bottom:12px"></div>
    <div class="grid-2">
      <div class="field"><label>Full Name *</label><input name="full_name" placeholder="e.g. Thabo Mokoena"></div>
      <div class="field"><label>Email *</label><input name="email" type="email" placeholder="email@student.jh.co.za"></div>
      <div class="field"><label>Phone *</label><input name="phone" placeholder="+27 71 234 5678"></div>
      <div class="field"><label>ID Number *</label><input name="id_number" placeholder="13-digit SA ID"></div>
      <div class="field"><label>Gender *</label>
        <select name="gender"><option>Male</option><option>Female</option><option>Other</option></select>
      </div>
      <div class="field"><label>Employment *</label>
        <select name="employment"><option>Unemployed</option><option>Employed</option><option>Self-employed</option></select>
      </div>
      <div class="field"><label>Address *</label><input name="address" placeholder="City / Area"></div>
      <div class="field"><label>Year Level *</label>
        <select name="year_level"><option>Year 1</option><option>Year 2</option><option>Year 3</option></select>
      </div>
    </div>
    <div class="field"><label>Qualification *</label><input name="qualification" placeholder="e.g. Diploma in IT"></div>
    <div class="grid-2">
      <div class="field"><label>Faculty *</label><input name="faculty" placeholder="e.g. Faculty of Sciences"></div>
      <div class="field"><label>Programme *</label><input name="programme" placeholder="e.g. Digital Skills 2026"></div>
      <div class="field"><label>Coordinator *</label><input name="coordinator" placeholder="Coordinator name"></div>
      <div class="field"><label>Location *</label><input name="location" placeholder="e.g. Johannesburg Campus"></div>
    </div>
    <div class="grid-2">
      <div class="field"><label>Start Date *</label><input name="start_date" type="date"></div>
      <div class="field"><label>Status</label>
        <select name="status"><option>Active</option><option>Inactive</option></select>
      </div>
      <div class="field"><label>Tuition Balance</label><input name="tuition_balance" placeholder="e.g. R15,000"></div>
      <div class="field"><label>Bursary Status</label>
        <select name="bursary_status"><option>Pending</option><option>Approved</option><option>Rejected</option></select>
      </div>
    </div>
    <div class="field"><label>Modules (comma-separated) *</label><input name="modules" placeholder="e.g. Network Systems, Database Systems"></div>
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px">
      <div class="field"><label>Emergency Contact Name *</label><input name="emergency_contact_name" placeholder="Full name"></div>
      <div class="field"><label>Emergency Phone *</label><input name="emergency_contact_phone" placeholder="+27 82 000 0000"></div>
      <div class="field"><label>Relationship *</label><input name="emergency_contact_relationship" placeholder="e.g. Parent"></div>
    </div>
    <button class="btn btn-primary" onclick="registerStudent()" style="width:100%;justify-content:center;padding:12px;margin-top:8px">Register Learner</button>
  </div>
</div>
<script>
function filterTable(q) {{
  q = q.toLowerCase();
  document.querySelectorAll('#learnersTable tbody tr').forEach(r => {{
    r.style.display = r.textContent.toLowerCase().includes(q) ? '' : 'none';
  }});
}}
function filterStatus(s) {{
  document.querySelectorAll('#learnersTable tbody tr').forEach(r => {{
    r.style.display = (!s || r.textContent.includes(s)) ? '' : 'none';
  }});
}}
async function registerStudent() {{
  const modal = document.getElementById('regModal');
  const data = new FormData();
  modal.querySelectorAll('[name]').forEach(el => data.append(el.name, el.value));
  const res = await fetch('/api/admin/students', {{method:'POST', body:data}});
  const json = await res.json();
  const msg = document.getElementById('regMsg');
  msg.style.display = 'block';
  if(json.ok) {{
    msg.style.cssText = 'display:block;background:rgba(34,197,94,.1);border:1px solid rgba(34,197,94,.2);border-radius:8px;padding:10px 14px;color:#16a34a;font-size:13px';
    msg.textContent = '✓ ' + json.message + ' — Username: ' + json.student.username + ' | Password: ' + json.student.password;
    setTimeout(() => location.reload(), 2000);
  }} else {{
    msg.style.cssText = 'display:block;background:rgba(255,107,107,.08);border:1px solid rgba(255,107,107,.2);border-radius:8px;padding:10px 14px;color:#e05555;font-size:13px';
    msg.textContent = '⚠️ ' + json.message;
  }}
}}

async function approveLearner(id) {{
  const btn = document.querySelector(`#pr-${{id}} button`);
  if (btn) {{ btn.textContent = 'Approving…'; btn.disabled = true; }}
  const res = await fetch('/api/admin/approve-learner', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{id}})
  }});
  const json = await res.json();
  if (json.ok) {{
    const row = document.getElementById(`pr-${{id}}`);
    if (row) {{
      row.style.background = 'rgba(34,197,94,.08)';
      row.cells[5].innerHTML = '<span style="color:#16a34a;font-size:13px;font-weight:600">✅ Approved</span>';
      setTimeout(() => {{ row.remove(); checkEmptyPending(); }}, 1800);
    }}
  }} else {{
    alert(json.error || 'Approval failed.');
    if (btn) {{ btn.textContent = '✅ Approve'; btn.disabled = false; }}
  }}
}}

async function rejectLearner(id) {{
  if (!confirm('Remove this registration?')) return;
  const res = await fetch('/api/admin/reject-learner', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{id}})
  }});
  const json = await res.json();
  if (json.ok) {{
    const row = document.getElementById(`pr-${{id}}`);
    if (row) {{ row.remove(); checkEmptyPending(); }}
  }}
}}

function checkEmptyPending() {{
  const tbody = document.querySelector('#pendingTable tbody');
  if (tbody && tbody.rows.length === 0) {{
    const card = tbody.closest('.card');
    if (card) card.remove();
  }}
}}
</script>
"""
    return render_shell(content, "Learners", admin_sidebar("/learners"), "Learner Register")


@app.route("/learners/<student_id>")
@admin_required
def learner_profile(student_id):
    student = get_student_by_id(student_id)
    if not student: raise NotFound()
    docs = get_learner_documents(student_id)
    checklist = get_document_checklist(student_id)
    progress = int(checklist["required_uploaded"] / max(checklist["required_total"], 1) * 100)
    content = f"""
<div class="page-header" style="display:flex;align-items:center;gap:12px">
  <a href="/learners" class="btn btn-secondary btn-sm">← Back</a>
  <div><h1>{student['full_name']}</h1><p>Student #{student['student_number']} · {student.get('programme','')}</p></div>
  <span class="badge badge-green" style="margin-left:auto">{student.get('status','')}</span>
</div>
<div class="grid-2" style="margin-bottom:20px">
  <div class="card">
    <div class="card-title">Personal Information</div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px 20px;font-size:13.5px">
      <div><span style="color:var(--text-3)">Email</span><div>{student.get('email','')}</div></div>
      <div><span style="color:var(--text-3)">Phone</span><div>{student.get('phone','')}</div></div>
      <div><span style="color:var(--text-3)">Gender</span><div>{student.get('gender','')}</div></div>
      <div><span style="color:var(--text-3)">ID Number</span><div>{student.get('id_number','')}</div></div>
      <div><span style="color:var(--text-3)">Address</span><div>{student.get('address','')}</div></div>
      <div><span style="color:var(--text-3)">Employment</span><div>{student.get('employment','')}</div></div>
    </div>
  </div>
  <div class="card">
    <div class="card-title">Academic Information</div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px 20px;font-size:13.5px">
      <div><span style="color:var(--text-3)">Campus</span><div>{student.get('campus','')}</div></div>
      <div><span style="color:var(--text-3)">Year</span><div>{student.get('year_level','')}</div></div>
      <div><span style="color:var(--text-3)">Tuition</span><div>{student.get('tuition_balance','')}</div></div>
      <div><span style="color:var(--text-3)">Bursary</span><div>{student.get('bursary_status','')}</div></div>
      <div><span style="color:var(--text-3)">Username</span><div><code style="background:var(--bg-2);padding:2px 6px;border-radius:4px">{student.get('username','')}</code></div></div>
      <div><span style="color:var(--text-3)">Password</span><div><code style="background:var(--bg-2);padding:2px 6px;border-radius:4px">{student.get('password','')}</code></div></div>
    </div>
  </div>
</div>
<div class="card" style="margin-bottom:20px">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
    <div class="card-title">Document Checklist ({checklist['required_uploaded']}/{checklist['required_total']} required)</div>
    <span class="badge badge-{'green' if progress==100 else 'purple'}">{progress}% complete</span>
  </div>
  <div class="progress-bar" style="margin-bottom:16px"><div class="progress-fill" style="width:{progress}%"></div></div>
  <div class="grid-2">
    {''.join(f'''<div style="padding:10px;background:var(--bg-2);border-radius:8px;border:1px solid var(--border)">
      <div style="display:flex;align-items:center;gap:8px">
        <span>{'✅' if item['uploaded'] else '⬜'}</span>
        <div><div style="font-weight:600;font-size:13px">{item['label']}</div>
        <div style="font-size:11px;color:var(--text-3)">{'Required' if item['required'] else 'Optional'} · {item['count']} file(s)</div></div>
      </div></div>''' for item in checklist['items'])}
  </div>
  <div style="margin-top:16px">
    <div class="card-title">Upload Document</div>
    <div style="display:flex;gap:10px;flex-wrap:wrap">
      <select id="docCat" class="btn btn-secondary" style="padding:9px 12px">
        {''.join(f'<option value="{dt["id"]}">{dt["label"]}</option>' for dt in LEARNER_DOCUMENT_TYPES)}
      </select>
      <input type="file" id="docFile" style="flex:1;padding:8px;border:1px solid var(--border);border-radius:8px;background:var(--bg-2);color:var(--text);font-size:13px">
      <button class="btn btn-primary" onclick="uploadDoc('{student_id}')">Upload</button>
    </div>
    <div id="uploadMsg" style="margin-top:8px;font-size:13px"></div>
  </div>
</div>
{''.join(f'''<div class="notice-card" style="margin-bottom:8px"><div class="notice-dot"></div>
  <div><div style="font-weight:600;font-size:13px">{d['category_label']}</div>
  <div style="font-size:12px;color:var(--text-3)">{d['original_name']} · {d['uploaded_at']}</div>
  <div style="display:flex;gap:8px;margin-top:6px">
    <a href="{d['view_url']}" target="_blank" class="btn btn-secondary btn-sm">View</a>
    <a href="{d['download_url']}" class="btn btn-secondary btn-sm">Download</a>
  </div></div></div>''' for d in docs) if docs else '<div class="card" style="text-align:center;color:var(--text-3)">No documents uploaded yet</div>'}
<script>
async function uploadDoc(lid){{
  const cat=document.getElementById('docCat').value;
  const file=document.getElementById('docFile').files[0];
  if(!file){{document.getElementById('uploadMsg').innerHTML='<span style="color:#e05555">Please select a file.</span>';return;}}
  const fd=new FormData();fd.append('document_category',cat);fd.append('document_file',file);
  const res=await fetch(`/learners/${{lid}}/documents/upload`,{{method:'POST',body:fd}});
  const j=await res.json();
  document.getElementById('uploadMsg').innerHTML=j.ok?'<span style="color:#16a34a">✓ '+j.message+'</span>':'<span style="color:#e05555">⚠️ '+j.message+'</span>';
  if(j.ok)setTimeout(()=>location.reload(),1200);
}}
</script>
"""
    return render_shell(content, student["full_name"], admin_sidebar("/learners"), student["full_name"])


@app.route("/admin/interventions")
@admin_required
def admin_interventions():
    content = f"""
<div class="page-header"><h1>Programmes & Interventions</h1><p>All active learning programmes</p></div>
<div class="grid-2">
  {''.join(f'''<div class="card">
    <div style="display:flex;justify-content:space-between;align-items:flex-start">
      <span class="badge badge-purple">{i['id']}</span>
      <span class="badge badge-green">Active</span>
    </div>
    <h3 style="margin:12px 0 8px;font-family:'Syne',sans-serif">{i['name']}</h3>
    <p style="color:var(--text-2);font-size:13.5px">{i['programme']}</p>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:14px;font-size:13px">
      <div><span style="color:var(--text-3)">Participants</span><div style="font-weight:600">{i['participants']}</div></div>
      <div><span style="color:var(--text-3)">Location</span><div>{i['location']}</div></div>
      <div><span style="color:var(--text-3)">Start</span><div>{i['start_date']}</div></div>
      <div><span style="color:var(--text-3)">End</span><div>{i['end_date']}</div></div>
    </div>
    <div style="margin-top:12px;padding:10px;background:var(--bg-2);border-radius:8px;font-size:12.5px;color:var(--text-2)">{i['expectations']}</div>
  </div>''' for i in LEARNING_INTERVENTIONS)}
</div>
"""
    return render_shell(content, "Programmes", admin_sidebar("/admin/interventions"), "Programmes")


@app.route("/documents")
@admin_required
def documents():
    docs = load_central_document_store()
    content = f"""
<div class="page-header" style="display:flex;justify-content:space-between;align-items:center">
  <div><h1>Document Repository</h1><p>{len(docs)} documents stored</p></div>
  <button class="quick-add" onclick="document.getElementById('uploadBox').style.display='block'">➕ Upload Document</button>
</div>
<div id="uploadBox" class="card" style="display:none;margin-bottom:20px">
  <div class="card-title">Upload New Document</div>
  <div style="display:flex;gap:10px;flex-wrap:wrap">
    <input id="docName" placeholder="Document name" style="flex:1;padding:9px 14px;border:1.5px solid var(--border);border-radius:8px;background:var(--bg-2);color:var(--text);font-size:13px;outline:none">
    <input type="file" id="docFile2" style="flex:1;padding:8px;border:1px solid var(--border);border-radius:8px;background:var(--bg-2);color:var(--text)">
    <button class="btn btn-primary" onclick="uploadCentral()">Upload</button>
  </div>
  <div id="uploadMsg2" style="margin-top:8px;font-size:13px"></div>
</div>
<div class="table-wrap">
  <table>
    <thead><tr><th>Document Name</th><th>ID</th><th>Updated</th><th>Status</th><th></th></tr></thead>
    <tbody>
      {''.join(f'''<tr>
        <td style="font-weight:600">{d['name']}</td>
        <td style="color:var(--text-3);font-size:12px">{d['id']}</td>
        <td style="color:var(--text-2)">{d['updated']}</td>
        <td><span class="badge badge-green">{d['status']}</span></td>
        <td><a href="/static/uploads/documents/{d['stored_name']}" target="_blank" class="btn btn-secondary btn-sm">View</a></td>
      </tr>''' for d in docs) if docs else '<tr><td colspan="5" style="text-align:center;color:var(--text-3);padding:32px">No documents uploaded yet</td></tr>'}
    </tbody>
  </table>
</div>
<script>
async function uploadCentral(){{
  const name=document.getElementById('docName').value.trim();
  const file=document.getElementById('docFile2').files[0];
  if(!name||!file){{document.getElementById('uploadMsg2').innerHTML='<span style="color:#e05555">Please complete all fields.</span>';return;}}
  const fd=new FormData();fd.append('name',name);fd.append('document_file',file);
  const res=await fetch('/documents/upload',{{method:'POST',body:fd}});
  const j=await res.json();
  if(j.ok)location.reload();
  else document.getElementById('uploadMsg2').innerHTML='<span style="color:#e05555">'+j.message+'</span>';
}}
</script>
"""
    return render_shell(content, "Documents", admin_sidebar("/documents"), "Documents")


@app.route("/clients")
@admin_required
def clients():
    content = f"""
<div class="page-header"><h1>Client Companies</h1><p>{JH_GROUP['tagline']}</p></div>
<div class="grid-2">
  {''.join(f'''<div class="card" style="cursor:pointer" onclick="location.href='/clients/{c['id']}'">
    <div style="display:flex;justify-content:space-between;align-items:flex-start">
      <div class="logo-mark" style="font-size:12px;width:40px;height:40px">{c['name'][:2].upper()}</div>
      <span class="badge badge-green">{c['status']}</span>
    </div>
    <h3 style="margin:12px 0 6px;font-family:'Syne',sans-serif">{c['name']}</h3>
    <p style="color:var(--text-2);font-size:13.5px">{c['focus']}</p>
    <div style="margin-top:12px;font-size:12.5px;color:var(--text-3)">{c['contact']} · {c['phone']}</div>
  </div>''' for c in JH_GROUP['companies'])}
</div>
"""
    return render_shell(content, "Clients", admin_sidebar("/clients"), "Clients")


@app.route("/clients/<company_id>")
@admin_required
def company_profile(company_id):
    company = next((c for c in JH_GROUP["companies"] if c["id"] == company_id), None)
    if not company: raise NotFound()
    content = f"""
<div class="page-header" style="display:flex;align-items:center;gap:12px">
  <a href="/clients" class="btn btn-secondary btn-sm">← Back</a>
  <div><h1>{company['name']}</h1><p>{company['focus']}</p></div>
</div>
<div class="grid-2">
  <div class="card">
    <div class="card-title">Contact Details</div>
    <p style="font-size:13.5px;color:var(--text-2)">📧 {company['contact']}</p>
    <p style="font-size:13.5px;color:var(--text-2);margin-top:8px">📞 {company['phone']}</p>
  </div>
  <div class="card">
    <div class="card-title">Status</div>
    <span class="badge badge-green" style="font-size:14px;padding:6px 16px">{company['status']}</span>
  </div>
</div>
"""
    return render_shell(content, company["name"], admin_sidebar("/clients"), company["name"])


@app.route("/admin/activity")
@admin_required
def admin_activity():
    content = """
<div class="page-header"><h1>Activity Feed</h1><p>Recent system events and actions</p></div>
<div class="card">
  <div class="activity-item"><div class="activity-icon" style="background:rgba(0,168,157,.1)">👥</div><div class="activity-content"><div class="activity-text"><strong>Thabo Mokoena</strong> registered — Diploma in IT</div><div class="activity-time">2 hours ago</div></div></div>
  <div class="activity-item"><div class="activity-icon" style="background:rgba(0,210,200,.1)">📁</div><div class="activity-content"><div class="activity-text"><strong>Ayanda Dlamini</strong> uploaded ID document</div><div class="activity-time">4 hours ago</div></div></div>
  <div class="activity-item"><div class="activity-icon" style="background:rgba(34,197,94,.1)">📢</div><div class="activity-content"><div class="activity-text">New announcement: <strong>Exam timetable released</strong></div><div class="activity-time">Yesterday at 14:30</div></div></div>
  <div class="activity-item"><div class="activity-icon" style="background:rgba(255,107,107,.1)">⚙️</div><div class="activity-content"><div class="activity-text"><strong>Admin</strong> updated learner status</div><div class="activity-time">2 days ago</div></div></div>
</div>
"""
    return render_shell(content, "Activity", admin_sidebar("/admin/activity"), "Activity Feed")


@app.route("/admin/profile")
@admin_required
def admin_profile():
    admin = current_admin()
    content = f"""
<div class="page-header"><h1>Admin Settings</h1></div>
<div class="grid-2">
  <div class="card">
    <div class="card-title">Profile</div>
    <div style="display:flex;align-items:center;gap:16px;margin-bottom:16px">
      <div class="user-avatar" style="width:64px;height:64px;font-size:22px;border-radius:16px">{admin['name'][0]}</div>
      <div><div style="font-family:'Syne',sans-serif;font-weight:700;font-size:18px">{admin['name']}</div>
      <div class="badge badge-purple">{admin['role_label']}</div></div>
    </div>
    <div class="field"><label>Email</label><input value="{session.get('admin_email','')}" readonly style="opacity:.7"></div>
    <div class="field"><label>Company Scope</label><input value="JH Student Services" readonly style="opacity:.7"></div>
  </div>
  <div class="card">
    <div class="card-title">Theme Preference</div>
    <p style="color:var(--text-2);font-size:13.5px;margin-bottom:16px">Toggle between light and dark mode using the button in the top bar, or click below.</p>
    <button class="btn btn-secondary" onclick="toggleTheme()">🌙 Toggle Dark / Light Mode</button>
    
  </div>
</div>
"""
    return render_shell(content, "Settings", admin_sidebar("/admin/profile"), "Settings")


# ── API ────────────────────────────────────────────────────────────────────────
@app.route("/api/admin/students", methods=["GET", "POST"])
@admin_required
def admin_students_api():
    students = load_students()
    if request.method == "GET": return jsonify({"students": students})
    payload = {k: request.form.get(k, "") for k in ["full_name","email","phone","id_number","gender","address","employment","qualification","faculty","programme","coordinator","location","start_date","status","year_level","emergency_contact_name","emergency_contact_phone","emergency_contact_relationship","modules","tuition_balance","bursary_status"]}
    if any(not v.strip() for k, v in payload.items() if k not in {"tuition_balance","bursary_status"}):
        return jsonify({"ok": False, "message": "Please complete all required fields."}), 400
    if any(s["email"].lower() == payload["email"].strip().lower() for s in students):
        return jsonify({"ok": False, "message": "A student with that email already exists."}), 400
    new_student = create_student_payload(payload, len(students))
    students.insert(0, new_student)
    save_students(students)
    return jsonify({"ok": True, "message": "Student registered successfully.", "student": new_student, "students": students})


# ── Student routes ────────────────────────────────────────────────────────────
@app.route("/student/dashboard")
@student_required
def student_dashboard():
    student = current_student()
    done = len([t for t in STUDENT_TASKS if t["status"] == "Done"])
    content = f"""
<div class="page-header">
  <h1>Welcome back, {student['full_name'].split()[0]} 👋</h1>
  <p>{student['programme']} · {student['campus']} · {datetime.now().strftime('%A, %d %B %Y')}</p>
</div>
<div class="grid-4" style="margin-bottom:24px">
  <div class="stat-card"><div class="stat-icon" style="background:rgba(0,168,157,.12)">📚</div><div class="stat-value">{len(student.get('modules',[]))}</div><div class="stat-label">Modules</div></div>
  <div class="stat-card"><div class="stat-icon" style="background:rgba(0,210,200,.12)">✅</div><div class="stat-value">{done}/{len(STUDENT_TASKS)}</div><div class="stat-label">Tasks Done</div></div>
  <div class="stat-card"><div class="stat-icon" style="background:rgba(255,107,107,.12)">📢</div><div class="stat-value">{len(ANNOUNCEMENTS)}</div><div class="stat-label">Notices</div></div>
  <div class="stat-card"><div class="stat-icon" style="background:rgba(34,197,94,.12)">💰</div><div class="stat-value" style="font-size:20px">{student.get('tuition_balance','—')}</div><div class="stat-label">Tuition Balance</div></div>
</div>
<div class="grid-2">
  <div>
    <div class="card" style="margin-bottom:20px">
      <div class="card-title">Today's Schedule</div>
      {''.join(f'''<div style="display:flex;gap:12px;align-items:center;padding:10px 0;border-bottom:1px solid var(--border)">
        <div style="font-family:'Syne',sans-serif;font-size:12px;color:var(--jh-teal);min-width:72px">{t['time']}</div>
        <div><div style="font-weight:600;font-size:13.5px">{t['lesson']}</div>
        <div style="font-size:12px;color:var(--text-3)">{t['teacher']} · {t['location']}</div></div></div>''' for t in TIMETABLE_ITEMS)}
    </div>
    <div class="card">
      <div class="card-title">My Notes</div>
      {''.join(f'<div class="note-card {n["tone"]}" style="margin-bottom:10px"><div style="font-weight:600;font-size:13px">{n["title"]}</div><div style="font-size:13px;color:var(--text-2);margin-top:4px">{n["body"]}</div><div style="font-size:11px;color:var(--text-3);margin-top:6px">{n["date"]}</div></div>' for n in STUDENT_NOTES)}
      <a href="/student/notes" class="btn btn-secondary btn-sm" style="margin-top:8px">View All Notes</a>
    </div>
  </div>
  <div>
    <div class="card" style="margin-bottom:20px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
        <div class="card-title" style="margin:0">My Tasks</div>
        <a href="/student/tasks" style="font-size:12px;color:var(--jh-teal)">View All</a>
      </div>
      {''.join(f'''<div class="task-card {'todo' if t['status']=='To Do' else 'in-progress' if t['status']=='In Progress' else 'done'}" style="margin-bottom:10px">
        <div style="display:flex;justify-content:space-between;align-items:flex-start">
          <div style="font-weight:600;font-size:13.5px">{t['title']}</div>
          <span class="badge {'badge-teal' if t['status']=='Done' else 'badge-purple' if t['status']=='In Progress' else 'badge-gray'}">{t['status']}</span>
        </div>
        <div class="task-meta"><span>📦 {t['module']}</span><span>📅 {t['due_date']}</span></div>
        <div class="progress-bar"><div class="progress-fill" style="width:{t['progress']}%"></div></div>
      </div>''' for t in STUDENT_TASKS)}
    </div>
    <div class="card">
      <div class="card-title">Announcements</div>
      {''.join(f'<div class="notice-card" style="margin-bottom:10px"><div class="notice-dot"></div><div><div style="font-weight:600;font-size:13px">{a["title"]}</div><div style="font-size:12px;color:var(--text-3)">{a["category"]} · {a["date"]}</div></div></div>' for a in ANNOUNCEMENTS[:2])}
      <a href="/student/announcements" class="btn btn-secondary btn-sm" style="margin-top:8px">View All</a>
    </div>
  </div>
</div>
"""
    return render_shell(content, "Dashboard", student_sidebar("/student/dashboard"), f"Welcome, {student['full_name'].split()[0]}")


@app.route("/student/profile", methods=["GET","POST"])
@student_required
def student_profile():
    student = current_student()
    if request.method == "POST":
        students = load_students()
        for item in students:
            if str(item["id"]) == str(student["id"]):
                for field in ["phone","address","email","emergency_contact_name","emergency_contact_phone","emergency_contact_relationship"]:
                    item[field] = request.form.get(field, item[field]).strip()
                break
        save_students(students)
        return redirect(url_for("student_profile"))
    student = get_student_by_id(student["id"])
    checklist = get_document_checklist(student["id"])
    progress = int(checklist["required_uploaded"] / max(checklist["required_total"],1) * 100)
    content = f"""
<div class="page-header" style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px">
  <div>
    <h1>My Profile</h1>
    <p>Manage your personal information</p>
  </div>

</div>
<div class="grid-2">
  <div class="card">
    <div style="display:flex;align-items:center;gap:16px;margin-bottom:20px">
      <div class="user-avatar" style="width:56px;height:56px;font-size:20px;border-radius:14px">{''.join(w[0] for w in student['full_name'].split()[:2])}</div>
      <div><div style="font-family:'Syne',sans-serif;font-weight:700;font-size:18px">{student['full_name']}</div>
      <div style="color:var(--text-2);font-size:13px">{student['student_number']}</div></div>
    </div>
    <form method="POST">
    <div class="field"><label>Phone</label><input name="phone" value="{student.get('phone','')}"></div>
    <div class="field"><label>Address</label><input name="address" value="{student.get('address','')}"></div>
    <div class="field"><label>Email</label><input name="email" value="{student.get('email','')}"></div>
    <div class="field"><label>Emergency Contact Name</label><input name="emergency_contact_name" value="{student.get('emergency_contact_name','')}"></div>
    <div class="field"><label>Emergency Contact Phone</label><input name="emergency_contact_phone" value="{student.get('emergency_contact_phone','')}"></div>
    <div class="field"><label>Relationship</label><input name="emergency_contact_relationship" value="{student.get('emergency_contact_relationship','')}"></div>
    <button class="btn btn-primary" type="submit">Save Changes</button>
    </form>
  </div>
  <div>
    <div class="card" style="margin-bottom:16px">
      <div class="card-title">Academic Details</div>
      <div style="display:grid;gap:8px;font-size:13.5px">
        <div style="display:flex;justify-content:space-between"><span style="color:var(--text-3)">Programme</span><span>{student.get('programme','')}</span></div>
        <div style="display:flex;justify-content:space-between"><span style="color:var(--text-3)">Campus</span><span>{student.get('campus','')}</span></div>
        <div style="display:flex;justify-content:space-between"><span style="color:var(--text-3)">Year Level</span><span>{student.get('year_level','')}</span></div>
        <div style="display:flex;justify-content:space-between"><span style="color:var(--text-3)">Bursary</span><span>{student.get('bursary_status','')}</span></div>
      </div>
    </div>
    <div class="card">
      <div style="display:flex;justify-content:space-between;margin-bottom:10px">
        <div class="card-title" style="margin:0">Documents</div>
        <span class="badge badge-{'green' if progress==100 else 'purple'}">{progress}%</span>
      </div>
      <div class="progress-bar"><div class="progress-fill" style="width:{progress}%"></div></div>
      <div style="margin-top:12px;display:flex;flex-direction:column;gap:6px">
        {''.join(f'''<div style="display:flex;justify-content:space-between;font-size:13px">
          <span>{'✅' if item['uploaded'] else '⬜'} {item['label']}</span>
          <span style="color:var(--text-3)">{item['count']} file(s)</span>
        </div>''' for item in checklist['items'])}
      </div>
      <div style="margin-top:14px">
        <div class="card-title" style="font-size:12px">Upload</div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:6px">
          <select id="sCat" style="flex:1;padding:8px;border:1.5px solid var(--border);border-radius:8px;background:var(--bg-2);color:var(--text);font-size:13px">
            {''.join(f'<option value="{dt["id"]}">{dt["label"]}</option>' for dt in LEARNER_DOCUMENT_TYPES)}
          </select>
          <input type="file" id="sFile" style="flex:1;padding:7px;border:1px solid var(--border);border-radius:8px;background:var(--bg-2);color:var(--text)">
          <button class="btn btn-primary btn-sm" onclick="sUpload('{student['id']}')">Upload</button>
        </div>
        <div id="sMsg" style="font-size:12px;margin-top:6px"></div>
      </div>
    </div>
  </div>
</div>
<script>
async function sUpload(lid){{
  const cat=document.getElementById('sCat').value;
  const file=document.getElementById('sFile').files[0];
  if(!file){{document.getElementById('sMsg').innerHTML='<span style="color:#e05555">Select a file.</span>';return;}}
  const fd=new FormData();fd.append('document_category',cat);fd.append('document_file',file);
  const res=await fetch('/student/documents/upload',{{method:'POST',body:fd}});
  const j=await res.json();
  document.getElementById('sMsg').innerHTML=j.ok?'<span style="color:#16a34a">✓ '+j.message+'</span>':'<span style="color:#e05555">'+j.message+'</span>';
  if(j.ok)setTimeout(()=>location.reload(),1200);
}}
</script>
"""
    return render_shell(content, "Profile", student_sidebar("/student/profile"), "My Profile")


@app.route("/student/tasks")
@student_required
def student_tasks():
    todo = [t for t in STUDENT_TASKS if t["status"] == "To Do"]
    inprog = [t for t in STUDENT_TASKS if t["status"] == "In Progress"]
    done = [t for t in STUDENT_TASKS if t["status"] == "Done"]
    def task_card(t):
        cls = "todo" if t["status"]=="To Do" else "in-progress" if t["status"]=="In Progress" else "done"
        badge = "badge-gray" if t["status"]=="To Do" else "badge-purple" if t["status"]=="In Progress" else "badge-teal"
        return f'''<div class="task-card {cls}" style="margin-bottom:10px">
          <div style="font-weight:600;font-size:13.5px">{t['title']}</div>
          <span class="badge {badge}" style="margin-top:6px">{t['status']}</span>
          <div class="task-meta"><span>📦 {t['module']}</span><span>📅 {t['due_date']}</span><span>💬 {t['comments']}</span></div>
          <div class="progress-bar"><div class="progress-fill" style="width:{t['progress']}%"></div></div>
          <div style="font-size:11px;color:var(--text-3);margin-top:4px">{t['progress']}% complete</div>
        </div>'''
    content = f"""
<div class="page-header"><h1>My Tasks</h1><p>Kanban view of all assignments</p></div>
<div class="kanban">
  <div class="kanban-col">
    <div class="kanban-header"><div class="kanban-title">🕐 To Do</div><div class="kanban-count">{len(todo)}</div></div>
    {''.join(task_card(t) for t in todo) or '<div style="color:var(--text-3);font-size:13px;text-align:center;padding:20px">All done!</div>'}
  </div>
  <div class="kanban-col">
    <div class="kanban-header"><div class="kanban-title">⚡ In Progress</div><div class="kanban-count">{len(inprog)}</div></div>
    {''.join(task_card(t) for t in inprog)}
  </div>
  <div class="kanban-col">
    <div class="kanban-header"><div class="kanban-title">✅ Done</div><div class="kanban-count">{len(done)}</div></div>
    {''.join(task_card(t) for t in done)}
  </div>
</div>
"""
    return render_shell(content, "Tasks", student_sidebar("/student/tasks"), "My Tasks")


@app.route("/student/timetable")
@student_required
def student_timetable():
    content = f"""
<div class="page-header"><h1>My Schedule</h1><p>Weekly timetable</p></div>
<div class="card">
  <div class="table-wrap">
    <table>
      <thead><tr><th>Time</th><th>Lesson</th><th>Teacher</th><th>Location</th><th>Day</th></tr></thead>
      <tbody>
        {''.join(f'''<tr>
          <td style="font-weight:600;color:var(--jh-teal)">{t['time']}</td>
          <td>{t['lesson']}</td>
          <td style="color:var(--text-2)">{t['teacher']}</td>
          <td style="color:var(--text-2)">{t['location']}</td>
          <td><span class="badge badge-purple">{t['day']}</span></td>
        </tr>''' for t in TIMETABLE_ITEMS)}
      </tbody>
    </table>
  </div>
</div>
"""
    return render_shell(content, "Schedule", student_sidebar("/student/timetable"), "My Schedule")


@app.route("/student/results")
@student_required
def student_results():
    results = [
        {"title": "Network Systems Test 1", "type": "Test", "score": "78%", "status": "Released"},
        {"title": "Database Systems Practical", "type": "Assignment", "score": "84%", "status": "Released"},
        {"title": "Information Security Exam", "type": "Final Exam", "score": "Pending", "status": "Awaiting Release"},
    ]
    content = f"""
<div class="page-header"><h1>Assessments & Results</h1></div>
<div class="table-wrap">
  <table>
    <thead><tr><th>Assessment</th><th>Type</th><th>Score</th><th>Status</th></tr></thead>
    <tbody>
      {''.join(f'''<tr>
        <td style="font-weight:600">{r['title']}</td>
        <td><span class="badge badge-gray">{r['type']}</span></td>
        <td style="font-weight:700;color:{'var(--jh-teal)' if r['score']!='Pending' else 'var(--text-3)'}">{r['score']}</td>
        <td><span class="badge {'badge-green' if r['status']=='Released' else 'badge-gray'}">{r['status']}</span></td>
      </tr>''' for r in results)}
    </tbody>
  </table>
</div>
"""
    return render_shell(content, "Assessments", student_sidebar("/student/results"), "Assessments")


@app.route("/student/announcements")
@student_required
def student_announcements():
    content = f"""
<div class="page-header"><h1>Announcements</h1><p>{len(ANNOUNCEMENTS)} notices</p></div>
<div style="display:flex;flex-direction:column;gap:12px">
  {''.join(f'''<div class="card" style="border-left:3px solid var(--jh-teal)">
    <div style="display:flex;justify-content:space-between;align-items:flex-start">
      <div>
        <div style="font-weight:700;font-size:15px;font-family:'Syne',sans-serif">{a['title']}</div>
        <div style="color:var(--text-2);font-size:13.5px;margin-top:6px">{a['summary']}</div>
      </div>
      <div style="text-align:right;flex-shrink:0;margin-left:16px">
        <span class="badge badge-purple">{a['category']}</span>
        <div style="font-size:11px;color:var(--text-3);margin-top:6px">{a['date']}</div>
      </div>
    </div>
  </div>''' for a in ANNOUNCEMENTS)}
</div>
"""
    return render_shell(content, "Announcements", student_sidebar("/student/announcements"), "Announcements")


@app.route("/student/registration")
@student_required
def student_registration():
    student = current_student()
    content = f"""
<div class="page-header"><h1>Registration</h1></div>
<div class="grid-2">
  <div class="card">
    <div class="card-title">Enrolled Programme</div>
    <div style="font-family:'Syne',sans-serif;font-size:18px;font-weight:700;margin-bottom:8px">{student.get('programme','')}</div>
    <div style="font-size:13.5px;color:var(--text-2)">Start: {student.get('start_date','')} · Campus: {student.get('campus','')}</div>
    <span class="badge badge-green" style="margin-top:10px">Registered</span>
  </div>
  <div class="card">
    <div class="card-title">Modules</div>
    {''.join(f'<div style="padding:8px 0;border-bottom:1px solid var(--border);font-size:13.5px">📚 {m}</div>' for m in student.get('modules',[]))}
  </div>
</div>
<div style="margin-top:20px"><div class="card-title" style="margin-bottom:14px;font-family:\'Syne\',sans-serif;font-size:16px;font-weight:700">Available Programmes</div>
<div class="grid-2">
  {''.join(f'''<div class="card">
    <span class="badge badge-gray">{i['id']}</span>
    <h3 style="margin:10px 0 6px;font-family:'Syne',sans-serif">{i['name']}</h3>
    <p style="font-size:13.5px;color:var(--text-2)">{i['programme']}</p>
    <div style="font-size:12px;color:var(--text-3);margin-top:8px">{i['participants']} participants · {i['location']}</div>
  </div>''' for i in LEARNING_INTERVENTIONS)}
</div></div>
"""
    return render_shell(content, "Registration", student_sidebar("/student/registration"), "Registration")


@app.route("/student/lms")
@student_required
def student_lms():
    student = current_student()
    content = f"""
<div class="page-header"><h1>Learning Management</h1></div>
<div class="card" style="margin-bottom:20px;text-align:center;padding:36px">
  <div style="font-size:40px;margin-bottom:12px">💻</div>
  <h2 style="font-family:'Syne',sans-serif">Canvas LMS</h2>
  <p style="color:var(--text-2);margin:8px 0 20px">Access your course materials, submissions, and discussions on Canvas</p>
  <a href="{student.get('lms_link','#')}" target="_blank" class="btn btn-primary" style="font-size:15px;padding:12px 28px">Open Canvas →</a>
</div>
<div class="card-title" style="margin-bottom:12px;font-family:'Syne',sans-serif;font-size:16px;font-weight:700">Recent Tasks</div>
{''.join(f'''<div class="task-card {'done' if t['status']=='Done' else 'in-progress' if t['status']=='In Progress' else 'todo'}" style="margin-bottom:10px">
  <div style="display:flex;justify-content:space-between"><div style="font-weight:600">{t['title']}</div><span class="badge {'badge-teal' if t['status']=='Done' else 'badge-purple' if t['status']=='In Progress' else 'badge-gray'}">{t['status']}</span></div>
  <div class="task-meta"><span>{t['module']}</span><span>Due {t['due_date']}</span></div>
</div>''' for t in STUDENT_TASKS)}
"""
    return render_shell(content, "LMS", student_sidebar("/student/lms"), "LMS")


@app.route("/student/fees")
@student_required
def student_fees():
    student = current_student()
    content = f"""
<div class="page-header"><h1>Fees & Finance</h1></div>
<div class="grid-2">
  <div class="stat-card">
    <div class="stat-icon" style="background:rgba(255,107,107,.12)">💰</div>
    <div class="stat-value" style="font-size:24px">{student.get('tuition_balance','—')}</div>
    <div class="stat-label">Outstanding Balance</div>
  </div>
  <div class="stat-card">
    <div class="stat-icon" style="background:rgba(34,197,94,.12)">🎓</div>
    <div class="stat-value" style="font-size:20px">{student.get('bursary_status','—')}</div>
    <div class="stat-label">Bursary Status</div>
  </div>
</div>
<div class="card" style="margin-top:20px">
  <div class="card-title">Payment Information</div>
  <p style="color:var(--text-2);font-size:13.5px">For payment queries, contact the finance office at <a href="mailto:finance@jhstudent.co.za">finance@jhstudent.co.za</a></p>
</div>
"""
    return render_shell(content, "Fees", student_sidebar("/student/fees"), "Fees")


@app.route("/student/records")
@student_required
def student_records():
    student = current_student()
    docs = get_learner_documents(student["id"])
    content = f"""
<div class="page-header"><h1>My Records</h1></div>
<div class="card" style="margin-bottom:20px">
  <div class="card-title">Uploaded Documents ({len(docs)})</div>
  {''.join(f'''<div style="display:flex;justify-content:space-between;align-items:center;padding:10px 0;border-bottom:1px solid var(--border)">
    <div><div style="font-weight:600;font-size:13.5px">{d['category_label']}</div>
    <div style="font-size:12px;color:var(--text-3)">{d['original_name']} · {d['uploaded_at']}</div></div>
    <div style="display:flex;gap:8px">
      <a href="{d['view_url']}" target="_blank" class="btn btn-secondary btn-sm">View</a>
      <a href="{d['download_url']}" class="btn btn-secondary btn-sm">⬇</a>
    </div>
  </div>''' for d in docs) if docs else '<p style="color:var(--text-3);font-size:13.5px">No documents uploaded yet.</p>'}
</div>
"""
    return render_shell(content, "Records", student_sidebar("/student/records"), "Records")


@app.route("/student/services")
@student_required
def student_services():
    content = f"""
<div class="page-header"><h1>Campus Services</h1></div>
<div class="grid-3">
  {''.join(f'''<div class="card">
    <div style="font-size:28px;margin-bottom:10px">🏫</div>
    <div style="font-weight:700;font-family:'Syne',sans-serif;margin-bottom:6px">{s['name']}</div>
    <p style="color:var(--text-2);font-size:13.5px">{s['detail']}</p>
    <span class="badge badge-green" style="margin-top:10px">{s['status']}</span>
  </div>''' for s in CAMPUS_SERVICES)}
</div>
"""
    return render_shell(content, "Services", student_sidebar("/student/services"), "Services")


@app.route("/student/support")
@student_required
def student_support():
    content = f"""
<div class="page-header"><h1>Student Support</h1></div>
<div class="grid-3">
  {''.join(f'''<div class="card">
    <div style="font-size:28px;margin-bottom:10px">🤝</div>
    <div style="font-weight:700;font-family:'Syne',sans-serif;margin-bottom:6px">{s['name']}</div>
    <p style="color:var(--text-2);font-size:13.5px">{s['detail']}</p>
    <a href="mailto:{s['contact']}" class="btn btn-secondary btn-sm" style="margin-top:10px">📧 Contact</a>
  </div>''' for s in SUPPORT_SERVICES)}
</div>
"""
    return render_shell(content, "Support", student_sidebar("/student/support"), "Support")


@app.route("/student/notes")
@student_required
def student_notes():
    content = f"""
<div class="page-header"><h1>My Notes</h1></div>
<div class="grid-2">
  {''.join(f'''<div class="note-card {n['tone']}">
    <div style="font-weight:700;font-family:'Syne',sans-serif;margin-bottom:8px">{n['title']}</div>
    <p style="font-size:13.5px;color:var(--text-2)">{n['body']}</p>
    <div style="font-size:11px;color:var(--text-3);margin-top:10px">{n['date']}</div>
  </div>''' for n in STUDENT_NOTES)}
</div>
"""
    return render_shell(content, "Notes", student_sidebar("/student/notes"), "Notes")


# ── Document upload routes ─────────────────────────────────────────────────────
@app.route("/student/documents/upload", methods=["POST"])
@student_required
def student_document_upload():
    return upload_document_for_learner(current_student()["id"])

@app.route("/learners/<learner_id>/documents/upload", methods=["POST"])
@admin_required
def upload_learner_document(learner_id):
    return upload_document_for_learner(learner_id)

def upload_document_for_learner(learner_id):
    cat = request.form.get("document_category", "").strip()
    file = request.files.get("document_file")
    if cat not in DOCUMENT_TYPE_LOOKUP:
        return jsonify({"ok": False, "message": "Please select a valid document type."}), 400
    if not file or not file.filename:
        return jsonify({"ok": False, "message": "Please choose a file to upload."}), 400
    if not is_allowed_document(file.filename):
        return jsonify({"ok": False, "message": "Invalid file type. Allowed: " + ", ".join(sorted(ALLOWED_DOCUMENT_EXTENSIONS)).upper()}), 400
    folder = os.path.join(LEARNER_UPLOADS_DIR, str(learner_id))
    os.makedirs(folder, exist_ok=True)
    orig = secure_filename(file.filename)
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    stored = f"{cat}_{ts}_{orig}"
    file.save(os.path.join(folder, stored))
    store = load_learner_document_store()
    store.setdefault(str(learner_id), []).insert(0, {"id": f"{learner_id}-{ts}", "category": cat, "category_label": DOCUMENT_TYPE_LOOKUP[cat]["label"], "original_name": orig, "stored_name": stored, "uploaded_at": datetime.now().strftime("%Y-%m-%d %H:%M")})
    save_learner_document_store(store)
    return jsonify({"ok": True, "message": f"{DOCUMENT_TYPE_LOOKUP[cat]['label']} uploaded successfully.", "documents": get_learner_documents(learner_id), "checklist": get_document_checklist(learner_id)})

@app.route("/learners/<learner_id>/documents/files/<filename>")
def learner_document_file(learner_id, filename):
    if not current_admin() and not current_student(): return redirect(url_for("login"))
    as_attachment = request.args.get("download") == "1"
    return send_from_directory(os.path.join(LEARNER_UPLOADS_DIR, str(learner_id)), filename, as_attachment=as_attachment)

@app.route("/documents/upload", methods=["POST"])
@admin_required
def upload_central_document():
    name = request.form.get("name", "").strip()
    file = request.files.get("document_file")
    if not name or not file or not file.filename:
        return jsonify({"ok": False, "message": "Please complete name and select a file."}), 400
    if not is_allowed_document(file.filename):
        return jsonify({"ok": False, "message": "Invalid file type."}), 400
    orig = secure_filename(file.filename)
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    stored = f"{ts}_{orig}"
    file.save(os.path.join(CENTRAL_UPLOADS_DIR, stored))
    docs = load_central_document_store()
    docs.insert(0, {"id": f"DOC-{ts}", "name": name, "stored_name": stored, "updated": datetime.now().strftime("%Y-%m-%d %H:%M"), "status": "Current"})
    save_central_document_store(docs)
    return jsonify({"ok": True, "documents": docs})

@app.errorhandler(413)
def file_too_large(_):
    return jsonify({"ok": False, "message": f"File too large. Max {MAX_DOCUMENT_MB} MB."}), 413






# ══════════════════════════════════════════════════════════════════════════════
# MESSAGING SYSTEM
# ══════════════════════════════════════════════════════════════════════════════

def load_messages(): return load_json(MESSAGES_FILE, [])
def save_messages(m): save_json(MESSAGES_FILE, m)
def load_meet_rooms(): return load_json(MEET_ROOMS_FILE, {})
def save_meet_rooms(r): save_json(MEET_ROOMS_FILE, r)

def get_caller_identity():
    admin = current_admin()
    if admin:
        return {"id": f"admin::{session.get('admin_email')}", "name": admin["name"], "role": "admin"}
    student = current_student()
    if student:
        return {"id": f"student::{student['id']}", "name": student["full_name"], "role": "student"}
    return None

def get_all_contacts(caller):
    contacts = []
    if caller["role"] == "admin":
        for s in load_students():
            contacts.append({"id": f"student::{s['id']}", "name": s["full_name"], "sub": s.get("student_number",""), "role": "student"})
        for email, a in ADMIN_USERS.items():
            cid = f"admin::{email}"
            if cid != caller["id"]:
                contacts.append({"id": cid, "name": a["name"], "sub": a["role_label"], "role": "admin"})
    else:
        for email, a in ADMIN_USERS.items():
            contacts.append({"id": f"admin::{email}", "name": a["name"], "sub": a["role_label"], "role": "admin"})
    return contacts

def get_thread_key(id_a, id_b):
    ids = sorted([id_a, id_b])
    return f"{ids[0]}||{ids[1]}"

def get_thread_messages(caller_id, other_id):
    key = get_thread_key(caller_id, other_id)
    all_msgs = load_messages()
    return [m for m in all_msgs if m.get("thread") == key]

def get_unread_count(caller_id):
    all_msgs = load_messages()
    return sum(1 for m in all_msgs if m.get("to_id") == caller_id and not m.get("read"))

MSG_PAGE_CSS = """
.msg-layout{display:flex;height:calc(100vh - 60px - 56px);overflow:hidden;gap:0;margin:-28px -28px -48px;border-top:1px solid var(--border)}
.msg-contacts{width:300px;flex-shrink:0;border-right:1px solid var(--border);background:var(--surface);display:flex;flex-direction:column;overflow:hidden}
.msg-contacts-header{padding:16px;border-bottom:1px solid var(--border);font-family:'Syne',sans-serif;font-weight:700;font-size:14px;display:flex;align-items:center;gap:8px}
.msg-search{padding:10px 14px;border-bottom:1px solid var(--border)}
.msg-search input{width:100%;background:var(--bg-2);border:1px solid var(--border);border-radius:8px;padding:8px 12px;font-size:13px;color:var(--text);outline:none}
.msg-search input:focus{border-color:var(--jh-teal)}
.msg-contact-list{flex:1;overflow-y:auto}
.msg-contact-item{display:flex;align-items:center;gap:10px;padding:12px 14px;cursor:pointer;border-bottom:1px solid var(--border);transition:background .15s;position:relative}
.msg-contact-item:hover{background:var(--surface-2)}
.msg-contact-item.active{background:rgba(0,168,157,.1);border-left:3px solid var(--jh-teal)}
.msg-contact-avatar{width:38px;height:38px;border-radius:50%;background:var(--jh-grad);display:flex;align-items:center;justify-content:center;font-family:'Syne',sans-serif;font-weight:700;font-size:13px;color:#fff;flex-shrink:0}
.msg-contact-info{flex:1;min-width:0}
.msg-contact-name{font-size:13.5px;font-weight:600;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.msg-contact-sub{font-size:11px;color:var(--text-3);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.msg-contact-preview{font-size:11.5px;color:var(--text-2);margin-top:1px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.unread-badge{background:var(--jh-teal);color:#fff;font-size:10px;font-weight:700;padding:2px 6px;border-radius:20px;min-width:18px;text-align:center}

.msg-chat{flex:1;display:flex;flex-direction:column;overflow:hidden;background:var(--bg)}
.msg-chat-header{padding:14px 18px;border-bottom:1px solid var(--border);background:var(--surface);display:flex;align-items:center;gap:12px}
.msg-chat-title{font-family:'Syne',sans-serif;font-weight:700;font-size:15px;color:var(--text);flex:1}
.msg-chat-sub{font-size:12px;color:var(--text-3)}
.msg-meet-btn{background:var(--jh-grad);color:#fff;border:none;border-radius:8px;padding:7px 14px;font-size:12.5px;font-weight:600;cursor:pointer;display:flex;align-items:center;gap:6px;transition:opacity .2s}
.msg-meet-btn:hover{opacity:.85}

.msg-body{flex:1;overflow-y:auto;padding:20px 18px;display:flex;flex-direction:column;gap:10px}
.msg-body::-webkit-scrollbar{width:4px}
.msg-body::-webkit-scrollbar-thumb{background:var(--border);border-radius:4px}

.msg-bubble-row{display:flex;align-items:flex-end;gap:8px}
.msg-bubble-row.mine{flex-direction:row-reverse}
.msg-bubble-avatar{width:28px;height:28px;border-radius:50%;background:var(--jh-grad);display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:700;color:#fff;flex-shrink:0}
.msg-bubble{max-width:65%;padding:10px 14px;border-radius:16px;font-size:13.5px;line-height:1.5;word-break:break-word}
.msg-bubble.theirs{background:var(--surface);border:1px solid var(--border);color:var(--text);border-bottom-left-radius:4px}
.msg-bubble.mine{background:var(--jh-grad);color:#fff;border-bottom-right-radius:4px}
.msg-meta{font-size:10px;color:var(--text-3);margin-top:3px;text-align:right}
.msg-bubble.theirs + .msg-meta{text-align:left}

.msg-footer{padding:12px 18px;border-top:1px solid var(--border);background:var(--surface);display:flex;gap:10px;align-items:flex-end}
.msg-input{flex:1;background:var(--bg-2);border:1.5px solid var(--border);border-radius:12px;padding:10px 14px;font-size:13.5px;color:var(--text);outline:none;resize:none;font-family:'DM Sans',sans-serif;line-height:1.4;max-height:120px;overflow-y:auto;transition:border-color .2s}
.msg-input:focus{border-color:var(--jh-teal)}
.msg-send-btn{background:var(--jh-grad);color:#fff;border:none;border-radius:10px;width:40px;height:40px;cursor:pointer;display:flex;align-items:center;justify-content:center;flex-shrink:0;transition:opacity .2s}
.msg-send-btn:hover{opacity:.85}
.msg-send-btn:disabled{opacity:.4;cursor:not-allowed}

.msg-empty{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;color:var(--text-3);gap:10px}
.msg-empty-icon{font-size:48px;opacity:.4}
.msg-date-divider{text-align:center;font-size:11px;color:var(--text-3);padding:4px 0;display:flex;align-items:center;gap:8px}
.msg-date-divider::before,.msg-date-divider::after{content:'';flex:1;height:1px;background:var(--border)}
"""

def _messages_page(sidebar_fn, sidebar_path, base_route):
    caller = get_caller_identity()
    contacts = get_all_contacts(caller)
    all_msgs = load_messages()

    # Build contact list with last message preview and unread count
    contact_items_html = ""
    for c in contacts:
        key = get_thread_key(caller["id"], c["id"])
        thread = [m for m in all_msgs if m.get("thread") == key]
        last = thread[-1] if thread else None
        unread = sum(1 for m in thread if m.get("to_id") == caller["id"] and not m.get("read"))
        preview = (last["body"][:40] + "…") if last and len(last.get("body","")) > 40 else (last["body"] if last else "No messages yet")
        initials = "".join(w[0].upper() for w in c["name"].split()[:2])
        badge = f'<span class="unread-badge">{unread}</span>' if unread else ""
        role_icon = "👤" if c["role"] == "student" else "⚙️"
        safe_name = c["name"].replace("'", "&#39;")
        safe_id = c["id"].replace(":", "_").replace(".", "_")
        contact_items_html += f"""
<div class="msg-contact-item" onclick="openThread('{c['id']}', '{safe_name}', '{c['sub']}')" id="contact-{safe_id}">
  <div class="msg-contact-avatar">{initials}</div>
  <div class="msg-contact-info">
    <div class="msg-contact-name">{role_icon} {c['name']}</div>
    <div class="msg-contact-sub">{c['sub']}</div>
    <div class="msg-contact-preview" id="preview-{safe_id}">{preview}</div>
  </div>
  {badge}
</div>"""

    content = f"""
<style>{MSG_PAGE_CSS}</style>
<div class="msg-layout">
  <div class="msg-contacts">
    <div class="msg-contacts-header">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
      Messages
    </div>
    <div class="msg-search"><input type="text" placeholder="Search contacts…" oninput="filterContacts(this.value)"></div>
    <div class="msg-contact-list" id="contactList">{contact_items_html}</div>
  </div>

  <div class="msg-chat" id="chatPanel">
    <div class="msg-empty" id="chatEmpty">
      <div class="msg-empty-icon">💬</div>
      <div style="font-size:15px;font-weight:600;color:var(--text-2)">Select a conversation</div>
      <div style="font-size:13px">Choose a contact from the left to start messaging</div>
    </div>

    <div id="chatActive" style="display:none;flex:1;flex-direction:column;overflow:hidden">
      <div class="msg-chat-header">
        <div class="msg-contact-avatar" id="chatAvatar" style="width:36px;height:36px;font-size:12px"></div>
        <div style="flex:1">
          <div class="msg-chat-title" id="chatName">–</div>
          <div class="msg-chat-sub" id="chatSub">–</div>
        </div>
        <button class="msg-meet-btn" onclick="startMeetFromChat()">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2" ry="2"/></svg>
          Start Meet
        </button>
      </div>
      <div class="msg-body" id="msgBody"></div>
      <div class="msg-footer">
        <textarea class="msg-input" id="msgInput" placeholder="Type a message…" rows="1"
          onkeydown="if(event.key==='Enter'&&!event.shiftKey){{event.preventDefault();sendMsg()}}"
          oninput="this.style.height='auto';this.style.height=this.scrollHeight+'px'"></textarea>
        <button class="msg-send-btn" id="sendBtn" onclick="sendMsg()">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
        </button>
      </div>
    </div>
  </div>
</div>

<script>
const MY_ID = '{caller["id"]}';
const MY_NAME = '{caller["name"]}';
let activeContactId = null;
let activeContactName = null;
let pollTimer = null;

function filterContacts(q) {{
  document.querySelectorAll('.msg-contact-item').forEach(el => {{
    const name = el.querySelector('.msg-contact-name').textContent.toLowerCase();
    el.style.display = name.includes(q.toLowerCase()) ? '' : 'none';
  }});
}}

function openThread(contactId, contactName, contactSub) {{
  activeContactId = contactId;
  activeContactName = contactName;
  document.getElementById('chatEmpty').style.display = 'none';
  const ca = document.getElementById('chatActive');
  ca.style.display = 'flex';
  ca.style.flexDirection = 'column';
  document.getElementById('chatName').textContent = contactName;
  document.getElementById('chatSub').textContent = contactSub;
  const initials = contactName.split(' ').slice(0,2).map(w=>w[0]?.toUpperCase()||'').join('');
  document.getElementById('chatAvatar').textContent = initials;
  document.querySelectorAll('.msg-contact-item').forEach(el => el.classList.remove('active'));
  const cid = contactId.replace(/:/g,'_').replace(/\\./g,'_');
  const el = document.getElementById('contact-'+cid);
  if(el) el.classList.add('active');
  loadMessages(true);
  clearInterval(pollTimer);
  pollTimer = setInterval(() => loadMessages(false), 3000);
  document.getElementById('msgInput').focus();
}}

async function loadMessages(scroll) {{
  if(!activeContactId) return;
  const res = await fetch('/api/messages/thread?with='+encodeURIComponent(activeContactId));
  const data = await res.json();
  if(!data.ok) return;
  renderMessages(data.messages, scroll);
  // Mark read
  await fetch('/api/messages/read', {{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{from_id:activeContactId}})}});
}}

function renderMessages(msgs, scroll) {{
  const body = document.getElementById('msgBody');
  body.innerHTML = '';
  let lastDate = '';
  msgs.forEach(m => {{
    const d = new Date(m.ts * 1000);
    const dateStr = d.toLocaleDateString('en-ZA', {{weekday:'short',month:'short',day:'numeric'}});
    if(dateStr !== lastDate) {{
      lastDate = dateStr;
      const div = document.createElement('div');
      div.className = 'msg-date-divider';
      div.textContent = dateStr;
      body.appendChild(div);
    }}
    const mine = m.from_id === MY_ID;
    const initials = m.from_name.split(' ').slice(0,2).map(w=>w[0]?.toUpperCase()||'').join('');
    const row = document.createElement('div');
    row.className = 'msg-bubble-row' + (mine ? ' mine' : '');
    const time = d.toLocaleTimeString('en-ZA', {{hour:'2-digit',minute:'2-digit'}});
    row.innerHTML = `
      <div class="msg-bubble-avatar">${{initials}}</div>
      <div>
        <div class="msg-bubble ${{mine?'mine':'theirs'}}">${{escHtml(m.body)}}</div>
        <div class="msg-meta">${{time}}</div>
      </div>`;
    body.appendChild(row);
  }});
  if(scroll) body.scrollTop = body.scrollHeight;
}}

function escHtml(s) {{
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\\n/g,'<br>');
}}

async function sendMsg() {{
  const inp = document.getElementById('msgInput');
  const body = inp.value.trim();
  if(!body || !activeContactId) return;
  inp.value = '';
  inp.style.height = 'auto';
  document.getElementById('sendBtn').disabled = true;
  const res = await fetch('/api/messages/send', {{
    method: 'POST',
    headers: {{'Content-Type':'application/json'}},
    body: JSON.stringify({{to_id: activeContactId, body}})
  }});
  const data = await res.json();
  document.getElementById('sendBtn').disabled = false;
  if(data.ok) {{
    loadMessages(true);
    // Update preview
    const cid = activeContactId.replace(/:/g,'_').replace(/\\./g,'_');
    const prev = document.getElementById('preview-'+cid);
    if(prev) prev.textContent = body.length > 40 ? body.substring(0,40)+'…' : body;
  }}
}}

function startMeetFromChat() {{
  if(!activeContactId) return;
  const roomId = 'meet-' + Date.now();
  window.open('{base_route.replace("/messages", "/meet")}?room='+roomId+'&invite='+encodeURIComponent(activeContactId)+'&name='+encodeURIComponent(activeContactName), '_blank');
}}
</script>
"""
    return render_shell(content, "Messages", sidebar_fn(sidebar_path), "Messages")


@app.route("/student/messages")
@student_required
def student_messages():
    return _messages_page(student_sidebar, "/student/messages", "/student/messages")

@app.route("/admin/messages")
@admin_required
def admin_messages():
    return _messages_page(admin_sidebar, "/admin/messages", "/admin/messages")


# ── Messaging API ────────────────────────────────────────────────────────────

@app.route("/api/messages/thread")
def api_messages_thread():
    caller = get_caller_identity()
    if not caller: return jsonify({"ok": False}), 401
    other_id = request.args.get("with", "")
    if not other_id: return jsonify({"ok": False, "error": "Missing param"}), 400
    msgs = get_thread_messages(caller["id"], other_id)
    return jsonify({"ok": True, "messages": msgs})

@app.route("/api/messages/send", methods=["POST"])
def api_messages_send():
    caller = get_caller_identity()
    if not caller: return jsonify({"ok": False}), 401
    data = request.get_json(force=True) or {}
    to_id = data.get("to_id", "").strip()
    body = data.get("body", "").strip()
    if not to_id or not body: return jsonify({"ok": False, "error": "Missing fields"}), 400
    all_msgs = load_messages()
    msg = {
        "id": f"msg-{int(datetime.now().timestamp()*1000)}",
        "thread": get_thread_key(caller["id"], to_id),
        "from_id": caller["id"],
        "from_name": caller["name"],
        "to_id": to_id,
        "body": body,
        "ts": int(datetime.now().timestamp()),
        "read": False
    }
    all_msgs.append(msg)
    save_messages(all_msgs)
    return jsonify({"ok": True, "msg": msg})

@app.route("/api/messages/read", methods=["POST"])
def api_messages_read():
    caller = get_caller_identity()
    if not caller: return jsonify({"ok": False}), 401
    data = request.get_json(force=True) or {}
    from_id = data.get("from_id", "")
    all_msgs = load_messages()
    changed = False
    for m in all_msgs:
        if m.get("to_id") == caller["id"] and m.get("from_id") == from_id and not m.get("read"):
            m["read"] = True
            changed = True
    if changed: save_messages(all_msgs)
    return jsonify({"ok": True})

@app.route("/api/messages/unread")
def api_messages_unread():
    caller = get_caller_identity()
    if not caller: return jsonify({"ok": False}), 401
    count = get_unread_count(caller["id"])
    return jsonify({"ok": True, "count": count})


# ══════════════════════════════════════════════════════════════════════════════
# MEET ROOM API  (code-based access)
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/meet/create", methods=["POST"])
@admin_required
def api_meet_create():
    caller = get_caller_identity()
    data = request.get_json(force=True) or {}
    title = data.get("title", "").strip()
    room = create_meet_room(title, caller["name"] if caller else "Admin")
    return jsonify({"ok": True, "room": room})

@app.route("/api/meet/join", methods=["POST"])
def api_meet_join():
    caller = get_caller_identity()
    if not caller:
        return jsonify({"ok": False, "error": "Not logged in"}), 401
    data = request.get_json(force=True) or {}
    code = data.get("code", "").strip().upper()
    if not code:
        return jsonify({"ok": False, "error": "No code provided"}), 400
    room = get_room_by_code(code)
    if not room:
        return jsonify({"ok": False, "error": "Invalid code"}), 404
    if not room.get("active"):
        return jsonify({"ok": False, "error": "This meeting has ended"}), 410
    return jsonify({"ok": True, "room": room})

@app.route("/api/meet/end", methods=["POST"])
@admin_required
def api_meet_end():
    data = request.get_json(force=True) or {}
    code = data.get("code", "").strip().upper()
    rooms = load_meet_rooms()
    if code in rooms:
        rooms[code]["active"] = False
        save_meet_rooms(rooms)
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "Room not found"}), 404

@app.route("/api/meet/rooms")
@admin_required
def api_meet_rooms():
    rooms = load_meet_rooms()
    active = [r for r in rooms.values() if r.get("active")]
    active.sort(key=lambda r: r.get("created_at", 0), reverse=True)
    return jsonify({"ok": True, "rooms": active})

# ══════════════════════════════════════════════════════════════════════════════
# VIDEO MEET (Jitsi Meet — camera & mic work on any HTTPS connection)
# ══════════════════════════════════════════════════════════════════════════════

MEET_PAGE_CSS = """
.meet-shell{min-height:100vh;background:#0a0a0a;display:flex;flex-direction:column;font-family:'DM Sans',sans-serif;color:#fff;margin:-28px -28px -48px}
.meet-topbar{height:56px;background:#111;border-bottom:1px solid #222;display:flex;align-items:center;padding:0 20px;gap:14px;flex-shrink:0}
.meet-topbar-title{font-family:'Syne',sans-serif;font-weight:700;font-size:15px;color:#fff;flex:1}

.meet-lobby{flex:1;display:flex;align-items:center;justify-content:center;padding:40px}
.meet-lobby-card{background:#111;border:1px solid #222;border-radius:16px;padding:36px;max-width:460px;width:100%;text-align:center}
.meet-room-input{width:100%;background:#1a1a1a;border:1px solid #333;border-radius:8px;padding:11px 14px;color:#fff;font-size:13.5px;outline:none;font-family:'DM Sans',sans-serif;text-align:center;margin-bottom:12px;box-sizing:border-box}
.meet-room-input:focus{border-color:#00A89D}
.meet-join-btn{width:100%;background:linear-gradient(135deg,#8DC63F,#00A89D);color:#fff;border:none;border-radius:10px;padding:13px;font-size:14px;font-weight:700;cursor:pointer;font-family:'Syne',sans-serif;transition:opacity .2s;margin-bottom:8px}
.meet-join-btn:hover{opacity:.88}
.meet-hint{font-size:11px;color:#555;margin-top:8px;line-height:1.5}

.meet-active{flex:1;display:none;flex-direction:column}
.meet-active.shown{display:flex}
.meet-active-bar{height:48px;background:#111;border-bottom:1px solid #222;display:flex;align-items:center;padding:0 16px;gap:12px;flex-shrink:0}
.meet-room-badge{font-size:12px;color:#888;background:#1a1a1a;border:1px solid #333;border-radius:6px;padding:3px 10px;cursor:pointer;transition:background .2s}
.meet-room-badge:hover{background:#222;color:#00A89D}
.meet-frame-wrap{flex:1;position:relative;overflow:hidden}
.meet-frame-wrap iframe{position:absolute;inset:0;width:100%;height:100%;border:none}
"""

def _admin_meet_page(sidebar_fn, sidebar_path, base_route):
    caller = get_caller_identity()
    user_name = caller["name"].replace("'", "\\'") if caller else "Admin"
    back_url = base_route.replace("/meet", "/messages")
    content = f"""
<style>
:root{{--jh-grad:linear-gradient(135deg,#8DC63F 0%,#00A89D 60%,#2D6A4F 100%)}}
{MEET_PAGE_CSS}
.meet-code-badge{{
  display:inline-block;font-size:32px;font-weight:800;letter-spacing:.18em;
  font-family:'Syne',sans-serif;color:#fff;background:#1a1a1a;
  border:2px solid #00A89D;border-radius:12px;padding:14px 28px;
  text-align:center;cursor:pointer;transition:background .2s;user-select:all;
}}
.meet-code-badge:hover{{background:#222}}
.meet-code-hint{{font-size:11.5px;color:#555;margin-top:10px;line-height:1.6}}
.meet-create-form{{display:flex;gap:8px;margin-bottom:16px;width:100%}}
.meet-create-form input{{flex:1;background:#1a1a1a;border:1px solid #333;border-radius:8px;
  padding:10px 14px;color:#fff;font-size:13px;outline:none;font-family:'DM Sans',sans-serif}}
.meet-create-form input:focus{{border-color:#00A89D}}
.meet-create-btn{{background:var(--jh-grad);color:#fff;border:none;border-radius:8px;
  padding:10px 20px;font-size:13px;font-weight:700;cursor:pointer;white-space:nowrap;
  font-family:'Syne',sans-serif;transition:opacity .2s}}
.meet-create-btn:hover{{opacity:.85}}
.meet-active-rooms{{margin-top:16px;width:100%;text-align:left}}
.meet-room-row{{background:#1a1a1a;border:1px solid #2a2a2a;border-radius:8px;
  padding:10px 14px;margin-bottom:8px;display:flex;align-items:center;gap:10px}}
.meet-room-row-code{{font-family:'Syne',sans-serif;font-weight:800;font-size:18px;
  letter-spacing:.12em;color:#00A89D;min-width:70px}}
.meet-room-row-title{{flex:1;font-size:13px;color:#ccc}}
.meet-room-row-btn{{background:none;border:1px solid #333;border-radius:6px;
  color:#888;font-size:11px;padding:4px 10px;cursor:pointer;transition:all .2s}}
.meet-room-row-btn:hover{{border-color:#00A89D;color:#00A89D}}
.meet-room-row-end{{background:none;border:1px solid #333;border-radius:6px;
  color:#888;font-size:11px;padding:4px 10px;cursor:pointer;transition:all .2s}}
.meet-room-row-end:hover{{border-color:#dc3535;color:#dc3535}}
</style>
<div class="meet-shell" id="meetShell">

  <div class="meet-topbar">
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#00A89D" stroke-width="2"><polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2"/></svg>
    <span class="meet-topbar-title">JH Meet — Admin</span>
    <a href="{back_url}" style="font-size:12px;color:#666;text-decoration:none;padding:4px 10px;background:#1a1a1a;border:1px solid #333;border-radius:6px;transition:color .2s" onmouseover="this.style.color='#00A89D'" onmouseout="this.style.color='#666'">← Back</a>
  </div>

  <!-- Lobby -->
  <div class="meet-lobby" id="lobbyPanel">
    <div class="meet-lobby-card" style="max-width:520px">
      <div style="font-size:48px;margin-bottom:16px">📹</div>
      <h2 style="font-family:'Syne',sans-serif;font-size:22px;font-weight:800;margin-bottom:8px">Start a Meeting</h2>
      <p style="color:#888;font-size:13px;margin-bottom:24px">Create a meeting and share the join code with students.</p>

      <div class="meet-create-form">
        <input id="meetingTitle" type="text" placeholder="Meeting title (optional)">
        <button class="meet-create-btn" onclick="createMeeting()">🎥 Create</button>
      </div>

      <!-- Code display -->
      <div id="codeArea" style="display:none;margin-bottom:20px">
        <p style="color:#aaa;font-size:12px;margin-bottom:8px">Share this code with students:</p>
        <div class="meet-code-badge" id="codeBadge" onclick="copyCode()" title="Click to copy">------</div>
        <div class="meet-code-hint">Click the code to copy it &nbsp;·&nbsp; Students enter it on their Meet page</div>
        <button onclick="joinAsAdmin()" style="margin-top:16px;background:var(--jh-grad);color:#fff;border:none;border-radius:10px;padding:12px 28px;font-size:14px;font-weight:700;cursor:pointer;font-family:'Syne',sans-serif;transition:opacity .2s">
          Enter Meeting →
        </button>
      </div>

      <!-- Active rooms -->
      <div class="meet-active-rooms" id="activeRooms"></div>

      <!-- Rejoin last meeting banner -->
      <div id="rejoinBanner" style="display:none;margin-top:16px;background:#1a1a1a;border:1px solid #2a2a2a;border-radius:10px;padding:14px 18px;width:100%;box-sizing:border-box">
        <div style="font-size:11px;color:#666;text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px">Last meeting</div>
        <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
          <span id="rejoinTitle" style="flex:1;font-size:13.5px;color:#ccc;min-width:80px"></span>
          <span id="rejoinCode" style="font-family:'Syne',sans-serif;font-weight:800;font-size:16px;letter-spacing:.12em;color:#00A89D"></span>
          <button onclick="doRejoin()"
            style="background:linear-gradient(135deg,#8DC63F,#00A89D);color:#fff;border:none;border-radius:7px;padding:7px 16px;font-size:12px;font-weight:700;cursor:pointer;font-family:'Syne',sans-serif;white-space:nowrap">
            ↩ Rejoin
          </button>
        </div>
      </div>
    </div>
  </div>

  <!-- Active meeting -->
  <div class="meet-active" id="meetingPanel">
    <div class="meet-active-bar">
      <span id="roomBadge" class="meet-room-badge" onclick="copyRoom()" title="Click to copy">Room: –</span>
      <span id="codeLabel" style="font-size:12px;color:#666;margin-left:4px"></span>
      <span style="flex:1"></span>
      <button onclick="endMeeting()" style="background:#dc3535;color:#fff;border:none;border-radius:8px;padding:6px 16px;font-size:13px;font-weight:600;cursor:pointer;font-family:'DM Sans',sans-serif;margin-right:8px">End Meeting</button>
      <button onclick="leaveMeet()" style="background:#333;color:#fff;border:none;border-radius:8px;padding:6px 16px;font-size:13px;font-weight:600;cursor:pointer;font-family:'DM Sans',sans-serif">Leave</button>
    </div>
    <div class="meet-frame-wrap">
      <iframe id="jitsiFrame" allow="camera; microphone; display-capture; fullscreen; autoplay" allowfullscreen></iframe>
    </div>
  </div>

</div>

<script>
const MY_NAME_MEET = '{user_name}';
const BACK_URL = '{back_url}';
let currentRoom = null;
let currentCode = null;

async function createMeeting() {{
  const title = document.getElementById('meetingTitle').value.trim();
  const res = await fetch('/api/meet/create', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{title}})
  }});
  const data = await res.json();
  if (!data.ok) {{ alert('Could not create meeting.'); return; }}
  currentCode = data.room.code;
  currentRoom = data.room.jitsi_room;
  document.getElementById('codeBadge').textContent = currentCode;
  document.getElementById('codeArea').style.display = 'block';
  loadActiveRooms();
}}

function copyCode() {{
  const code = document.getElementById('codeBadge').textContent;
  navigator.clipboard.writeText(code).then(() => {{
    const b = document.getElementById('codeBadge');
    const orig = b.textContent;
    b.textContent = 'Copied ✓';
    setTimeout(() => b.textContent = orig, 1800);
  }});
}}

function joinAsAdmin() {{
  if (!currentRoom) return;
  document.getElementById('roomBadge').textContent = 'Room: ' + currentRoom;
  document.getElementById('codeLabel').textContent = '· Code: ' + currentCode;
  document.getElementById('lobbyPanel').style.display = 'none';
  const panel = document.getElementById('meetingPanel');
  panel.classList.add('shown');
  const jitsiUrl = 'https://meet.jit.si/' + encodeURIComponent(currentRoom)
    + '#userInfo.displayName="' + encodeURIComponent(MY_NAME_MEET) + '"'
    + '&config.prejoinPageEnabled=false'
    + '&config.startWithAudioMuted=false'
    + '&config.startWithVideoMuted=false'
    + '&interfaceConfig.SHOW_JITSI_WATERMARK=false'
    + '&interfaceConfig.SHOW_BRAND_WATERMARK=false';
  document.getElementById('jitsiFrame').src = jitsiUrl;
}}

async function endMeeting() {{
  if (currentCode && confirm('End this meeting for everyone?')) {{
    await fetch('/api/meet/end', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{code: currentCode}})
    }});
    leaveMeet();
  }}
}}

function leaveMeet() {{
  // Capture last room before clearing
  const lastRoom = currentCode ? {{ code: currentCode, jitsiRoom: currentRoom, title: document.getElementById('roomBadge').textContent.replace('Room: ', '') }} : null;
  document.getElementById('jitsiFrame').src = '';
  document.getElementById('meetingPanel').classList.remove('shown');
  document.getElementById('lobbyPanel').style.display = 'flex';
  currentRoom = null; currentCode = null;
  document.getElementById('codeArea').style.display = 'none';
  document.getElementById('meetingTitle').value = '';
  if (lastRoom) {{
    document.getElementById('rejoinTitle').textContent = lastRoom.title;
    document.getElementById('rejoinCode').textContent = lastRoom.code;
    document.getElementById('rejoinBanner').style.display = 'block';
    // Store for doRejoin
    window._adminLastRoom = lastRoom;
  }}
  loadActiveRooms();
}}

function doRejoin() {{
  const r = window._adminLastRoom;
  if (!r) return;
  currentCode = r.code;
  currentRoom = r.jitsiRoom;
  joinAsAdmin();
}}

function copyRoom() {{
  if (!currentRoom) return;
  navigator.clipboard.writeText(currentRoom);
}}

async function loadActiveRooms() {{
  const res = await fetch('/api/meet/rooms');
  const data = await res.json();
  const el = document.getElementById('activeRooms');
  if (!data.ok || !data.rooms.length) {{ el.innerHTML = ''; return; }}
  el.innerHTML = '<p style="color:#555;font-size:11px;margin-bottom:8px;text-transform:uppercase;letter-spacing:.08em">Active Meetings</p>'
    + data.rooms.map(r => `
      <div class="meet-room-row">
        <span class="meet-room-row-code">${{r.code}}</span>
        <span class="meet-room-row-title">${{r.title}}</span>
        <button class="meet-room-row-btn" onclick="rejoinRoom('${{r.code}}','${{r.jitsi_room}}')">Rejoin</button>
        <button class="meet-room-row-end" onclick="endRoomByCode('${{r.code}}')">End</button>
      </div>`).join('');
}}

function rejoinRoom(code, jitsiRoom) {{
  currentCode = code; currentRoom = jitsiRoom;
  joinAsAdmin();
}}

async function endRoomByCode(code) {{
  if (!confirm('End this meeting?')) return;
  await fetch('/api/meet/end', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{code}})
  }});
  loadActiveRooms();
}}

loadActiveRooms();
</script>
"""
    return render_shell(content, "JH Meet", sidebar_fn(sidebar_path), "JH Meet")


def _student_meet_page(sidebar_fn, sidebar_path, base_route):
    caller = get_caller_identity()
    user_name = caller["name"].replace("'", "\\'") if caller else "Guest"
    back_url = base_route.replace("/meet", "/messages")
    content = f"""
<style>
:root{{--jh-grad:linear-gradient(135deg,#8DC63F 0%,#00A89D 60%,#2D6A4F 100%)}}
{MEET_PAGE_CSS}
.meet-code-input{{
  width:100%;background:#1a1a1a;border:2px solid #333;border-radius:10px;
  padding:14px;color:#fff;font-size:28px;font-weight:800;letter-spacing:.18em;
  font-family:'Syne',sans-serif;text-align:center;outline:none;
  text-transform:uppercase;margin-bottom:12px;box-sizing:border-box;
}}
.meet-code-input:focus{{border-color:#00A89D}}
.meet-code-error{{color:#dc3535;font-size:12.5px;margin-bottom:10px;min-height:18px}}
</style>
<div class="meet-shell" id="meetShell">

  <div class="meet-topbar">
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#00A89D" stroke-width="2"><polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2"/></svg>
    <span class="meet-topbar-title">JH Meet</span>
    <a href="{back_url}" style="font-size:12px;color:#666;text-decoration:none;padding:4px 10px;background:#1a1a1a;border:1px solid #333;border-radius:6px;transition:color .2s" onmouseover="this.style.color='#00A89D'" onmouseout="this.style.color='#666'">← Back</a>
  </div>

  <!-- Lobby -->
  <div class="meet-lobby" id="lobbyPanel">
    <div class="meet-lobby-card">
      <div style="font-size:48px;margin-bottom:16px">📹</div>
      <h2 style="font-family:'Syne',sans-serif;font-size:22px;font-weight:800;margin-bottom:8px">Join a Meeting</h2>
      <p style="color:#888;font-size:13.5px;margin-bottom:24px">Enter the 6-character code from your moderator.</p>

      <input id="codeInput" class="meet-code-input" type="text" maxlength="6"
        placeholder="ABC123" autocomplete="off" spellcheck="false"
        oninput="this.value=this.value.toUpperCase()"
        onkeydown="if(event.key==='Enter')joinWithCode()">

      <div class="meet-code-error" id="codeError"></div>

      <button class="meet-join-btn" onclick="joinWithCode()">
        🎥 &nbsp;Join Meeting
      </button>

      <!-- Rejoin banner — shown after leaving a meeting -->
      <div id="rejoinBanner" style="display:none;margin-top:16px;background:#1a1a1a;border:1px solid #2a2a2a;border-radius:10px;padding:14px 16px;text-align:left">
        <div style="font-size:11px;color:#666;text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px">Last meeting</div>
        <div style="display:flex;align-items:center;gap:10px">
          <span id="rejoinTitle" style="flex:1;font-size:13.5px;color:#ccc"></span>
          <span id="rejoinCode" style="font-family:'Syne',sans-serif;font-weight:800;font-size:16px;letter-spacing:.12em;color:#00A89D"></span>
          <button onclick="doRejoin()"
            style="background:linear-gradient(135deg,#8DC63F,#00A89D);color:#fff;border:none;border-radius:7px;padding:7px 16px;font-size:12px;font-weight:700;cursor:pointer;font-family:'Syne',sans-serif;white-space:nowrap">
            ↩ Rejoin
          </button>
        </div>
      </div>

      <div class="meet-hint">
        Your moderator will share the code before the meeting starts.
      </div>
    </div>
  </div>

  <!-- Active meeting -->
  <div class="meet-active" id="meetingPanel">
    <div class="meet-active-bar">
      <span id="roomBadge" class="meet-room-badge">In Meeting</span>
      <span style="flex:1"></span>
      <button onclick="leaveMeet()" style="background:#dc3535;color:#fff;border:none;border-radius:8px;padding:6px 16px;font-size:13px;font-weight:600;cursor:pointer;font-family:'DM Sans',sans-serif">Leave</button>
    </div>
    <div class="meet-frame-wrap">
      <iframe id="jitsiFrame" allow="camera; microphone; display-capture; fullscreen; autoplay" allowfullscreen></iframe>
    </div>
  </div>

</div>

<script>
const MY_NAME_MEET = '{user_name}';
let lastRoom = null;

async function joinWithCode() {{
  const code = document.getElementById('codeInput').value.trim().toUpperCase();
  document.getElementById('codeError').textContent = '';
  if (code.length !== 6) {{
    document.getElementById('codeError').textContent = 'Please enter the full 6-character code.';
    return;
  }}
  const res = await fetch('/api/meet/join', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{code}})
  }});
  const data = await res.json();
  if (!data.ok) {{
    document.getElementById('codeError').textContent = data.error || 'Invalid or expired code.';
    return;
  }}
  lastRoom = {{ code, jitsiRoom: data.room.jitsi_room, title: data.room.title }};
  launchMeeting(data.room.jitsi_room, data.room.title);
}}

function doRejoin() {{
  if (!lastRoom) return;
  launchMeeting(lastRoom.jitsiRoom, lastRoom.title);
}}

function launchMeeting(jitsiRoom, title) {{
  document.getElementById('roomBadge').textContent = title;
  document.getElementById('lobbyPanel').style.display = 'none';
  document.getElementById('meetingPanel').classList.add('shown');
  const jitsiUrl = 'https://meet.jit.si/' + encodeURIComponent(jitsiRoom)
    + '#userInfo.displayName="' + encodeURIComponent(MY_NAME_MEET) + '"'
    + '&config.prejoinPageEnabled=false'
    + '&config.startWithAudioMuted=false'
    + '&config.startWithVideoMuted=false'
    + '&interfaceConfig.SHOW_JITSI_WATERMARK=false'
    + '&interfaceConfig.SHOW_BRAND_WATERMARK=false';
  document.getElementById('jitsiFrame').src = jitsiUrl;
}}

function leaveMeet() {{
  document.getElementById('jitsiFrame').src = '';
  document.getElementById('meetingPanel').classList.remove('shown');
  document.getElementById('lobbyPanel').style.display = 'flex';
  document.getElementById('codeInput').value = '';
  if (lastRoom) {{
    document.getElementById('rejoinTitle').textContent = lastRoom.title;
    document.getElementById('rejoinCode').textContent = lastRoom.code;
    document.getElementById('rejoinBanner').style.display = 'block';
  }}
}}
</script>
"""
    return render_shell(content, "JH Meet", sidebar_fn(sidebar_path), "JH Meet")


@app.route("/student/meet")
@student_required
def student_meet():
    return _student_meet_page(student_sidebar, "/student/meet", "/student/meet")

@app.route("/admin/meet")
@admin_required
def admin_meet():
    return _admin_meet_page(admin_sidebar, "/admin/meet", "/admin/meet")



if __name__ == "__main__":
    import threading, webbrowser, sys

    use_https = "--https" in sys.argv

    if use_https:
        # Generate a self-signed cert so camera/mic work over HTTPS
        import subprocess, os
        cert_file = os.path.join(app.root_path, "cert.pem")
        key_file  = os.path.join(app.root_path, "key.pem")
        if not (os.path.exists(cert_file) and os.path.exists(key_file)):
            subprocess.run([
                "openssl", "req", "-x509", "-newkey", "rsa:2048",
                "-keyout", key_file, "-out", cert_file,
                "-days", "365", "-nodes",
                "-subj", "/CN=localhost"
            ], check=True)
        ssl_context = (cert_file, key_file)
        url = "https://localhost:5000"
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
        print(f"\n  Running with HTTPS — camera & microphone will work.")
        print(f"  Open: {url}  (accept the self-signed certificate warning)\n")
        app.run(host="0.0.0.0", port=5000, debug=False, ssl_context=ssl_context)
    else:
        url = "http://localhost:5000"
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
        print(f"\n  Running on HTTP.  Camera & microphone work on localhost.")
        print(f"  For remote access with camera/mic, restart with:  python app.py --https\n")
        app.run(host="0.0.0.0", port=5000, debug=False)
