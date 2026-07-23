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