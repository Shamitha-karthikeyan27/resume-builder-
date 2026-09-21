"""Online Resume Builder - accounts, PDF import, templates and PDF export."""

import io
import os
import re
from datetime import datetime

from flask import Flask, render_template, request, send_file, flash, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from xhtml2pdf import pisa
from pypdf import PdfReader

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-fallback-key-change-in-production")
basedir = os.path.abspath(os.path.dirname(__file__))
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", f"sqlite:///{os.path.join(basedir, 'users.db')}")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Please log in to access the Resume Builder."


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


with app.app_context():
    db.create_all()


# ---------------------------------------------------------------- Auth routes
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        if not username or not email or not password:
            flash("All fields are required.")
            return redirect(url_for("signup"))
        if password != confirm:
            flash("Passwords do not match.")
            return redirect(url_for("signup"))
        if len(password) < 6:
            flash("Password must be at least 6 characters.")
            return redirect(url_for("signup"))
        if User.query.filter_by(username=username).first():
            flash("That username is already taken.")
            return redirect(url_for("signup"))
        if User.query.filter_by(email=email).first():
            flash("An account with that email already exists.")
            return redirect(url_for("signup"))
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        login_user(user)
        flash("Account created successfully. Welcome!")
        return redirect(url_for("index"))
    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()
        if user is None or not user.check_password(password):
            flash("Invalid username or password.")
            return redirect(url_for("login"))
        login_user(user)
        return redirect(url_for("index"))
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.")
    return redirect(url_for("login"))


# ------------------------------------------------------------ PDF generation
def make_pdf_safe(value):
    """Replace punctuation that can break built-in ReportLab fonts."""
    if not isinstance(value, str):
        return value
    replacements = {
        "\u2013": "-", "\u2014": "-", "\u2212": "-",
        "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
        "\u2022": "-", "\u00a0": " ", "\u2192": "->", "\u2190": "<-",
        "\u2026": "...", "\u2605": "*", "\u25c6": "*",
    }
    for old, new in replacements.items():
        value = value.replace(old, new)
    return value


def sanitize_for_pdf(value):
    if isinstance(value, dict):
        return {key: sanitize_for_pdf(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_for_pdf(item) for item in value]
    return make_pdf_safe(value)


def render_pdf(html_content):
    """Render HTML to a PDF buffer and only fail when no PDF was produced."""
    pdf_buffer = io.BytesIO()
    try:
        pisa_status = pisa.CreatePDF(src=html_content, dest=pdf_buffer, encoding="UTF-8")
        pdf_bytes = pdf_buffer.getvalue()

        # xhtml2pdf can report non-fatal CSS warnings in ``err`` even when it
        # successfully produced a usable PDF. Do not throw away a valid PDF
        # just because the renderer reported warnings.
        if not pdf_bytes:
            app.logger.error(
                "xhtml2pdf produced an empty PDF. status=%s log=%s",
                getattr(pisa_status, "err", "unknown"),
                getattr(pisa_status, "log", "unknown"),
            )
            return None

        if getattr(pisa_status, "err", 0):
            app.logger.warning(
                "xhtml2pdf completed with warnings/errors, but a PDF was produced: %s",
                getattr(pisa_status, "log", "unknown"),
            )

        pdf_buffer.seek(0)
        return pdf_buffer
    except Exception:
        app.logger.exception("PDF generation crashed")
        return None


def get_list_field(prefix, keys):
    lists = {key: request.form.getlist(f"{prefix}_{key}[]") for key in keys}
    length = max((len(v) for v in lists.values()), default=0)
    items = []
    for i in range(length):
        entry = {key: (lists[key][i] if i < len(lists[key]) else "") for key in keys}
        if any(v.strip() for v in entry.values()):
            items.append(entry)
    return items


def collect_form_data(form):
    education = get_list_field("education", ["degree", "school", "year", "details"])
    experience = get_list_field("experience", ["role", "company", "duration", "details"])
    projects = get_list_field("projects", ["title", "description", "link"])
    certifications = [c.strip() for c in form.get("certifications", "").split("\n") if c.strip()]
    skills = [s.strip() for s in form.get("skills", "").split(",") if s.strip()]
    return {
        "full_name": form.get("full_name", ""), "email": form.get("email", ""),
        "phone": form.get("phone", ""), "address": form.get("address", ""),
        "linkedin": form.get("linkedin", ""), "github": form.get("github", ""),
        "portfolio": form.get("portfolio", ""), "summary": form.get("summary", ""),
        "education": education, "experience": experience, "skills": skills,
        "projects": projects, "certifications": certifications,
        "template": form.get("template", "modern"),
        "generated_on": datetime.now().strftime("%B %d, %Y"),
    }


# -------------------------------------------------------- PDF import helpers
SECTION_ALIASES = {
    "summary": {"summary", "professional summary", "profile", "objective", "career objective", "about me"},
    "education": {"education", "academic background", "academic qualifications"},
    "experience": {"experience", "work experience", "professional experience", "employment", "internships", "internship"},
    "projects": {"projects", "academic projects", "personal projects", "project experience"},
    "skills": {"skills", "technical skills", "core skills", "key skills", "technologies"},
    "certifications": {"certifications", "certificates", "licenses & certifications"},
}


def clean_line(value):
    return re.sub(r"\s+", " ", value).strip(" •|-–—\t")


def normalize_heading(line):
    return re.sub(r"[^a-z& ]", "", line.lower()).strip()


def sectionize(text):
    sections = {key: [] for key in SECTION_ALIASES}
    current = None
    for raw in text.splitlines():
        line = clean_line(raw)
        if not line:
            continue
        normalized = normalize_heading(line)
        found = next((key for key, aliases in SECTION_ALIASES.items() if normalized in aliases), None)
        if found:
            current = found
        elif current:
            sections[current].append(line)
    return sections


def parse_resume_pdf(file_storage):
    """Extract text from a PDF and use conservative regex/heading heuristics to prefill fields."""
    reader = PdfReader(file_storage.stream)
    text = "\n".join((page.extract_text() or "") for page in reader.pages)
    text = re.sub(r"\r", "\n", text)
    lines = [clean_line(x) for x in text.splitlines() if clean_line(x)]
    sections = sectionize(text)

    email = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", text, re.I)
    phone = re.search(r"(?:\+?\d[\d\s().-]{8,}\d)", text)
    linkedin = re.search(r"(?:https?://)?(?:www\.)?linkedin\.com/in/[\w./-]+", text, re.I)
    github = re.search(r"(?:https?://)?(?:www\.)?github\.com/[\w./-]+", text, re.I)
    urls = re.findall(r"https?://[^\s)]+|(?:www\.)[^\s)]+", text, re.I)

    # First non-contact-looking line is generally the candidate's name.
    name = ""
    for line in lines[:8]:
        if (len(line.split()) <= 5 and not re.search(r"@|linkedin|github|resume|curriculum|phone|email", line, re.I)
                and not re.search(r"\d{3,}", line)):
            name = line
            break

    summary = " ".join(sections["summary"][:5])
    skills = []
    for line in sections["skills"]:
        parts = re.split(r"[,|•;]", line)
        skills.extend(clean_line(p) for p in parts if clean_line(p))
    skills = list(dict.fromkeys(skills))[:30]

    education = []
    for line in sections["education"]:
        if len(line) < 3:
            continue
        year = ""
        year_match = re.search(r"(?:19|20)\d{2}\s*(?:-|–|—|to)\s*(?:(?:19|20)\d{2}|present|current)?", line, re.I)
        if year_match:
            year = year_match.group(0)
        chunks = [clean_line(x) for x in re.split(r"\s*[|•]\s*", line) if clean_line(x)]
        education.append({"degree": chunks[0] if chunks else line, "school": chunks[1] if len(chunks) > 1 else "", "year": year, "details": ""})
    education = education[:5]

    experience = []
    for line in sections["experience"]:
        if len(line) < 3:
            continue
        parts = [clean_line(x) for x in re.split(r"\s*[|•]\s*", line) if clean_line(x)]
        duration_match = re.search(r"(?:19|20)\d{2}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)", line, re.I)
        duration = duration_match.group(0) if duration_match else ""
        experience.append({"role": parts[0] if parts else line, "company": parts[1] if len(parts) > 1 else "", "duration": duration, "details": ""})
    experience = experience[:6]

    projects = []
    for line in sections["projects"]:
        parts = [clean_line(x) for x in re.split(r"\s*[|•]\s*", line) if clean_line(x)]
        projects.append({"title": parts[0] if parts else line, "description": " ".join(parts[1:]), "link": ""})
    projects = projects[:8]

    certifications = sections["certifications"][:10]
    portfolio = ""
    for u in urls:
        low = u.lower()
        if "linkedin.com" not in low and "github.com" not in low:
            portfolio = u
            break

    return {
        "full_name": name, "email": email.group(0) if email else "",
        "phone": phone.group(0).strip() if phone else "",
        "address": "", "linkedin": linkedin.group(0) if linkedin else "",
        "github": github.group(0) if github else "", "portfolio": portfolio,
        "summary": summary, "education": education, "experience": experience,
        "skills": skills, "projects": projects, "certifications": certifications,
    }


@app.route("/extract-resume", methods=["POST"])
@login_required
def extract_resume():
    upload = request.files.get("resume_pdf")
    if not upload or not upload.filename:
        flash("Please choose a PDF resume to import.")
        return redirect(url_for("index"))
    if not upload.filename.lower().endswith(".pdf"):
        flash("Only PDF files are supported for automatic import.")
        return redirect(url_for("index"))
    try:
        data = parse_resume_pdf(upload)
        session["imported_resume"] = data
        flash("Resume imported. Review the extracted fields and edit anything that needs correction.")
    except Exception as exc:
        app.logger.exception("Resume extraction failed: %s", exc)
        flash("I couldn't read that PDF. Try a text-based PDF rather than a scanned image PDF.")
    return redirect(url_for("index"))


# --------------------------------------------------------- Resume app routes
@app.route("/")
@login_required
def index():
    imported = session.pop("imported_resume", None)
    return render_template("index.html", imported=imported)


@app.route("/preview", methods=["POST"])
@login_required
def preview():
    data = collect_form_data(request.form)
    return render_template("resume_pdf.html", data=data, preview=True)


@app.route("/generate", methods=["POST"])
@login_required
def generate():
    data = collect_form_data(request.form)
    if not data["full_name"].strip():
        flash("Full name is required to generate a resume.")
        return redirect(url_for("index"))
    pdf_data = sanitize_for_pdf(data)
    html_content = render_template("resume_pdf.html", data=pdf_data, preview=False)
    pdf_buffer = render_pdf(html_content)
    if pdf_buffer is None:
        # Return an actual error response instead of redirecting to the editor.
        # The frontend can show the message without making it look like the
        # download silently navigated away from the page.
        return (
            "PDF generation failed on the server. Please try again. Check the Render logs for the exact renderer error.",
            500,
            {"Content-Type": "text/plain; charset=utf-8"},
        )
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", data["full_name"].strip()).strip("._") or "Resume"
    filename = f"{safe_name}_Resume.pdf"
    response = send_file(
        pdf_buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
        max_age=0,
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@app.errorhandler(404)
def not_found(e):
    return render_template("index.html", imported=None) if current_user.is_authenticated else redirect(url_for("login"))


if __name__ == "__main__":
    app.run(debug=True)
