# Online Resume Builder — Cloud Deployment Project

## 1. Problem Statement
Many fresh graduates struggle to create professional resumes, which often
leads to poor job opportunities. Most either can't afford professional
resume-writing services or don't have access to design tools like Photoshop
or paid resume builders.

## 2. Proposed Solution
A **Flask web application** where users:
1. Sign up / log in to their own account.
2. Fill in their personal details, education, experience, skills, projects,
   and certifications through a simple web form.
3. Preview how their resume will look.
4. Instantly generate and download a **professionally formatted PDF resume**.

No design skills required — just a browser.

## 3. Tech Stack
| Layer            | Technology                          |
|-------------------|--------------------------------------|
| Backend           | Python 3.12, Flask 3                |
| Auth              | Flask-Login (sessions) + Flask-SQLAlchemy (SQLite) |
| PDF Generation    | xhtml2pdf (pure-Python HTML→PDF)    |
| Frontend          | HTML5, CSS3, vanilla JavaScript     |
| WSGI Server       | Gunicorn                            |
| Deployment Target | Render (free tier) / Heroku         |

**Why xhtml2pdf instead of WeasyPrint/pdfkit?** Both of those require
system-level binaries (Cairo/Pango or wkhtmltopdf) which need extra Heroku
buildpacks and are fragile to set up. xhtml2pdf is pure Python, installs via
pip alone, and works out-of-the-box on Heroku's default Python buildpack —
making deployment much simpler and more reliable.

## 4. Project Structure
```
resume-builder/
├── app.py                     # Flask application & routes
├── requirements.txt           # Python dependencies
├── Procfile                   # Heroku process definition
├── runtime.txt                # Python version pin for Heroku
├── templates/
│   ├── login.html              # Login page
│   ├── signup.html             # Sign-up page
│   ├── index.html              # Resume input form (requires login)
│   └── resume_pdf.html         # Resume layout (used for preview + PDF)
└── static/
    └── style.css                # Site styling
```

**Note on the database:** user accounts are stored in a local SQLite file
(`users.db`), created automatically on first run. On Render/Heroku's free
tiers the filesystem is *ephemeral* — it resets on every redeploy — so
accounts won't persist across deploys. That's fine for a demo/student
project. For production use, swap in a persistent database (e.g. Render's
free PostgreSQL) by setting the `DATABASE_URL` environment variable.

## 5. How It Works
1. `GET /` — renders the input form (`index.html`).
2. `POST /preview` — renders `resume_pdf.html` directly in the browser so
   the user can see the layout before downloading.
3. `POST /generate` — collects form data, renders `resume_pdf.html` to an
   HTML string, converts it to PDF bytes using `xhtml2pdf.pisa.CreatePDF`,
   and streams the file back as a downloadable attachment.

Repeating sections (Education, Experience, Projects) are submitted as
array-style fields (e.g. `education_degree[]`) added/removed dynamically
via JavaScript, then reassembled into structured lists server-side.

## 6. Run Locally
```bash
# 1. Clone / unzip the project, then move into it
cd resume-builder

# 2. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the app
python app.py
# Visit http://127.0.0.1:5000
```

## 7. Deploy to Heroku

### Prerequisites
- A free [Heroku account](https://signup.heroku.com/)
- [Heroku CLI](https://devcenter.heroku.com/articles/heroku-cli) installed
- Git installed

### Steps
```bash
# 1. Log in to Heroku
heroku login

# 2. Initialize git (skip if already a git repo)
cd resume-builder
git init
git add .
git commit -m "Initial commit: Online Resume Builder"

# 3. Create a new Heroku app (pick any unique name)
heroku create your-resume-builder-app

# 4. Deploy
git push heroku main
# If your default branch is 'master' instead of 'main', use:
# git push heroku master

# 5. Open the live app
heroku open
```

Heroku automatically detects the `requirements.txt` (Python buildpack),
reads `runtime.txt` for the Python version, and uses the `Procfile` to
start the app with Gunicorn.

### Useful Heroku commands
```bash
heroku logs --tail          # View live logs for debugging
heroku ps                   # Check running dynos
heroku config:set SECRET_KEY=your-production-secret   # Set env vars
```

### Production note
Before going live, replace the hardcoded `app.secret_key` in `app.py` with
an environment variable, e.g.:
```python
import os
app.secret_key = os.environ.get("SECRET_KEY", "dev-fallback-key")
```
and set it on Heroku with `heroku config:set SECRET_KEY=<random-value>`.

## 8. Possible Extensions
- Add multiple resume templates/themes for the user to choose from.
- Add user accounts (Flask-Login) to save and edit resumes over time.
- Store generated resumes in cloud storage (e.g. AWS S3) for later retrieval.
- Add a cover-letter generator alongside the resume builder.
- Add analytics (resume downloads count) to track usage.
