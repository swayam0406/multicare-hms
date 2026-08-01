# 🏥 Multicare Hospital Management System (HMS)

An enterprise-grade Hospital Management System built with Django, PostgreSQL, and Bootstrap 5.
Developed incrementally using Agile Scrum methodology.

## 📋 Project Status

**Current Sprint:** Sprint 1 — Environment Setup
**Version:** 0.1.0

## 🛠️ Tech Stack

- **Backend:** Python 3.12+, Django 5.2 LTS
- **Database:** PostgreSQL 16
- **Frontend:** Django Templates, Bootstrap 5, Bootstrap Icons
- **Auth:** Django Authentication + Role-Based Access Control (planned)
- **Deployment (planned):** Gunicorn + Nginx

## 📦 Modules (Planned)

- `accounts` — Users, roles, authentication
- `patients` — Patient registration and CRUD
- `doctors` — Doctor and department management
- `appointments` — Scheduling and queue management
- `medical_records` — EMR, diagnosis, prescriptions
- `billing` — Invoices, insurance, payments
- `laboratory` — Lab tests and results
- `pharmacy` — Medicine dispensing
- `inventory` — Hospital assets and supplies
- `dashboard` — Analytics and reporting
- `core` — Shared utilities and base templates

## 🚀 Local Setup

### Prerequisites

- Python 3.12 or higher
- PostgreSQL 16
- Git

### Installation

```bash
# 1. Clone the repository
git clone <repo-url>
cd multicare-hms

# 2. Create and activate virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1     # Windows PowerShell
# source venv/bin/activate      # Linux/Mac

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
copy .env.example .env
# Edit .env and fill in real database credentials

# 5. Run migrations
python manage.py migrate

# 6. Start the dev server
python manage.py runserver
```

Visit **http://127.0.0.1:8000/** to view the app.

## 🗂️ Project Structure
multicare-hms/
├── core/ # Shared app (base templates, home page)
├── multicare_hms/ # Django project settings
├── static/ # Source static files
├── staticfiles/ # Collected static files (auto)
├── media/ # User uploads
├── templates/ # Project-wide templates
├── venv/ # Virtual environment (not committed)
├── .env # Secrets (not committed)
├── .env.example # Env template
├── manage.py
├── requirements.txt
└── README.md
## 📅 Sprint Log

| Sprint | Epic | Status |
|--------|------|--------|
| Sprint 1 | Project Foundation | 🟡 In Progress |
| Sprint 2 | Authentication | ⏳ Planned |
| Sprint 3 | Patient Management | ⏳ Planned |
| Sprint 4 | Appointment Management | ⏳ Planned |
| Sprint 5 | Clinical Management | ⏳ Planned |
| Sprint 6 | Billing | ⏳ Planned |
| Sprint 7 | Lab / Pharmacy / Inventory | ⏳ Planned |
| Sprint 8 | Analytics & Deployment | ⏳ Planned |

## 📜 License

For educational and portfolio purposes.

## Running Tests

```powershell
python manage.py test
```

## Measuring Coverage

```powershell
coverage run manage.py test
coverage report
coverage html   # opens htmlcov/index.html
```

Current coverage: **~XX%** (run `coverage report` to update).