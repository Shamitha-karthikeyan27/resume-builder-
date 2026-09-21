# Online Resume Builder — Smart Resume Studio

A Flask-based resume builder with account login, automatic PDF resume import, five resume templates, live completion metrics, preview, and PDF export.

## Features

1. **PDF resume import & auto-fill** — upload an existing text-based PDF. The app extracts contact information, summary, education, experience, projects, skills and certifications using `pypdf` plus lightweight parsing heuristics. All imported values remain editable.
2. **Five templates** — Modern, ATS Classic, Minimal, Executive and Creative. The selected template is used for both preview and downloaded PDF.
3. **Featured template chooser** — template cards are shown before the form so users can select a preferred design.
4. **Live visualisation** — profile completion ring, filled-fields metric, section count, project count, read-time estimate, skill coverage bar and content-strength indicators update while the user types.
5. **Existing features retained** — signup/login, dynamic education/experience/project fields, preview and PDF generation.

## Important PDF import note
The importer works best with **text-based PDFs**. Scanned/image-only PDFs do not contain selectable text and will need OCR to be imported accurately. The extracted values should always be reviewed before generating the final resume.

## Run locally
```bash
cd resume-builder
python -m venv venv
venv\\Scripts\\activate       # Windows
pip install -r requirements.txt
python app.py
```
Open `http://127.0.0.1:5000`.

## Deployment
The existing `Procfile` and `runtime.txt` can continue to be used with Render/Heroku. Make sure the deployment installs the updated `requirements.txt` so `pypdf` is available.
