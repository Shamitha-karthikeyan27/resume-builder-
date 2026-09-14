"""
Online Resume Builder
----------------------
A Flask web app with user accounts. Users sign up / log in, then fill in
their details through a form to instantly download a professionally
formatted resume as a PDF.

PDF generation uses xhtml2pdf (pure Python, no system binaries needed),
which makes it deploy-friendly on Render/Heroku without extra buildpacks.

Auth uses Flask-Login for session management and Flask-SQLAlchemy (SQLite)
for storing user accounts, with passwords hashed via Werkzeug.
"""

import io
import os
from datetime import datetime

from flask import Flask, render_template, request, send_file, flash, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user,
    login_required, current_user,
)
from werkzeug.security import generate_password_hash, check_password_hash
from xhtml2pdf import pisa

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-fallback-key-change-in-production")

basedir = os.path.abspath(os.path.dirname(__file__))
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", f"sqlite:///{os.path.join(basedir, 'users.db')}"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

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

def render_pdf(html_content):
    """Convert an HTML string into a PDF file-like object using xhtml2pdf."""
    pdf_buffer = io.BytesIO()
    pisa_status = pisa.CreatePDF(src=html_content, dest=pdf_buffer)
    if pisa_status.err:
        return None
    pdf_buffer.seek(0)
    return pdf_buffer


def get_list_field(prefix, keys):
    """
    Collect repeated form groups (e.g. multiple education/experience entries)
    into a list of dicts. Expects form field names like 'education_degree[]'.
    """
    lists = {key: request.form.getlist(f"{prefix}_{key}[]") for key in keys}
    length = max((len(v) for v in lists.values()), default=0)
    items = []
    for i in range(length):
        entry = {}
        for key in keys:
            values = lists[key]
            entry[key] = values[i] if i < len(values) else ""
        if any(v.strip() for v in entry.values()):
            items.append(entry)
    return items


def collect_form_data(form):
    """Pull all fields (simple + repeating groups) out of the submitted form."""
    education = get_list_field("education", ["degree", "school", "year", "details"])
    experience = get_list_field("experience", ["role", "company", "duration", "details"])
    projects = get_list_field("projects", ["title", "description", "link"])
    certifications = [c.strip() for c in form.get("certifications", "").split("\n") if c.strip()]
    skills = [s.strip() for s in form.get("skills", "").split(",") if s.strip()]

    return {
        "full_name": form.get("full_name", ""),
        "email": form.get("email", ""),
        "phone": form.get("phone", ""),
        "address": form.get("address", ""),
        "linkedin": form.get("linkedin", ""),
        "github": form.get("github", ""),
        "portfolio": form.get("portfolio", ""),
        "summary": form.get("summary", ""),
        "education": education,
        "experience": experience,
        "skills": skills,
        "projects": projects,
        "certifications": certifications,
        "generated_on": datetime.now().strftime("%B %d, %Y"),
    }


# --------------------------------------------------------- Resume app routes

@app.route("/")
@login_required
def index():
    return render_template("index.html")


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

    html_content = render_template("resume_pdf.html", data=data, preview=False)
    pdf_buffer = render_pdf(html_content)

    if pdf_buffer is None:
        flash("Something went wrong while generating your PDF. Please try again.")
        return redirect(url_for("index"))

    filename = f"{data['full_name'].strip().replace(' ', '_')}_Resume.pdf"
    return send_file(
        pdf_buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


@app.errorhandler(404)
def not_found(e):
    return render_template("index.html") if current_user.is_authenticated else redirect(url_for("login"))


if __name__ == "__main__":
    app.run(debug=True)
