# College Fee Management System

A Flask + PostgreSQL college fee administration application with separate administrator and student access.

## Included
- Administrator login and student login
- Admin-managed student accounts
- Fee assignment by student and academic year
- Payment recording with balance validation
- Unique receipt numbers and downloadable PDF receipts
- Student fee summary and payment history
- Administrative reports based on recorded database rows
- CSRF protection, password hashing, role checks and secure session-cookie defaults
- Privacy Policy and Terms and Conditions pages
- Local SVG favicon
- No demo accounts, fabricated transactions, fake reviews, fake counters or payment-gateway claims

## Requirements
- Python 3.10+
- Supabase PostgreSQL project
- VS Code or another Python editor

## 1. Configure Aiven PostgreSQL
This repository is configured for the Supabase project in the Mumbai region.

Project reference: `tgoxglzjwwvigvahoxml`

In the Aiven Console, open your PostgreSQL service and copy its connection details. The production deployment uses the Aiven service host, port, database name and user configured in Vercel. Never share the database password in chat or commit it to GitHub.

## 2. Set up Python
Windows PowerShell:
```powershell
py -m venv .venv
.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

macOS/Linux:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:
- Set `SECRET_KEY` to a long random secret.
- Set `DATABASE_URL` to the PostgreSQL connection URI copied from Aiven, using the current Aiven password.
- Use the SQLAlchemy/psycopg format `postgresql+psycopg://avnadmin:URL_ENCODED_PASSWORD@YOUR_AIVEN_HOST:YOUR_AIVEN_PORT/defaultdb?sslmode=require`. Keep the host and port exactly as shown by your Aiven service.
- Keep `COOKIE_SECURE=false` only for local HTTP development.

If your database password contains special characters, URL-encode the password portion before placing it in the connection string.

## 3. Create tables and administrator
The Supabase database has the application tables provisioned. To create or synchronize the schema from the Flask models, run:
```bash
flask --app app init-db
flask --app app create-admin
```
Enter the administrator's name, email and a unique password when prompted. Admin passwords must be at least 12 characters.

## 4. Run
```bash
flask --app app run
```
Open http://127.0.0.1:5000

The first login page is `/login`. Create student accounts from Admin > Students. Give each student their login email and a temporary password through a secure channel.

## How payment recording works
This build records payments that the college has actually received through an offline or external payment process. It does not collect card/UPI credentials and does not claim to process online payments. An administrator records the payment method and optional transaction reference. The system generates a receipt from that record.

## Before public launch
This source package is not a live deployment. Do not publish it with sample `.env` values. Before launch:
1. Deploy behind HTTPS and set `COOKIE_SECURE=true`.
2. Set a strong production `SECRET_KEY` and production Aiven PostgreSQL credentials in the hosting provider's secret manager.
3. Connect a domain you own, update DNS at your registrar and verify HTTPS.
4. Replace the college identity/contact placeholders in the legal pages with approved institutional details and have the college review them.
5. Add the final institution name/logo and update the receipt heading.
6. Configure database backups, monitoring, access controls and a tested recovery process.
7. Verify the deployed favicon at `/static/favicon.svg`.

## Important
- Only authorized college personnel should create student accounts and record payments.
- Use real student data only with institutional authorization.
- The privacy and terms pages are starter templates, not legal advice or a substitute for institutional approval.
- Do not use this system as the sole financial ledger until the college has tested and approved its reconciliation process.


## Database connectivity check
After deployment, open `/health/db` on the deployed site. A successful connection returns:
```json
{"status":"ok","database":"connected"}
```
A 503 response means the configured database credentials, host, port, database, TLS settings or network access still need attention. The endpoint never exposes credentials.
