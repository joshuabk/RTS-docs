# RTS Register — Machine Return-to-Service Reporting

A Django web app for radiation oncology departments to create, store, and export
reports documenting a machine's return to clinical service after an outage.

## What it captures
Each report records:
- **Machine & department** — which machine was down and where it lives
- **Outage start / work completed** — the timeline
- **What was worked on** — fault and repair description, plus who performed the work
- **Physics evaluation** — status (not required / performed / pending), the evaluation
  performed, and the responsible medical physicist
- **Return-to-service approval** — approver name/role (approval date is stamped
  automatically)
- **Vendor documentation link** — URL to the vendor's service report

Reports are **saved in the database** and can be **exported to a print-ready PDF**
(one report per file, suitable for a QA binder or document-management system).

## Quick start
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo        # demo departments/machines/report + admin user
python manage.py runserver
```
Open http://127.0.0.1:8000/ and sign in.

Demo credentials from `seed_demo`: **admin / changeme123** (change immediately).
To create your own admin instead: `python manage.py createsuperuser`.

## Managing clinics and machines (selection options)
Use the in-app **Clinics & machines** page (top nav) to add the clinics and machines
that appear as options when creating a report:
- Add a clinic (name, optional short code, location).
- Add a machine and assign it to exactly one clinic. A machine belongs to one clinic only.

When creating or editing a report, pick the **clinic** first; the **machine** dropdown then
shows only that clinic's machines (loaded via `/api/machines/`). Full bulk management and
user accounts are also available in the Django admin at `/admin/`.

## Project layout
- `config/` — project settings and root URLs
- `reports/` — models, forms, views, admin, PDF export (`reports/pdf.py`),
  templates, and the stylesheet (`reports/static/reports/app.css`)
- `reports/management/commands/seed_demo.py` — demo data

## Production notes
This ships with development defaults. Before deploying: set `DEBUG = False`,
move `SECRET_KEY` to an environment variable, set `ALLOWED_HOSTS`, serve over
HTTPS, run `collectstatic`, and consider Postgres instead of SQLite. Because
these reports support clinical QA, ensure your deployment meets your
institution's record-retention, access-control, and audit requirements.
