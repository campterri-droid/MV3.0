# Zoomies OS Working MVP 3.0

This is a real database-backed Flask application, not a static demo.

## Working features

- Persistent SQLite database
- Login and role separation
- Admin/staff dashboard
- Customer portal
- Customer dog records
- Customer grooming booking
- Two-hour groomer appointment blocks
- No overlapping appointments per groomer
- Permanent 12:00–1:00 PM lunch gap
- Groomer days off and partial-day unavailability
- All-groomer closures
- Automatic U.S. federal holiday blocking for staffed grooming
- Self-wash kiosk remains available on holidays
- Customer appointment cancellation
- Daily staff calendar

## Demo accounts

All seeded accounts use:

`Zoomies123!`

- Admin: `admin@zoomies.local`
- Staff: `staff@zoomies.local`
- Customer: `customer@zoomies.local`

Change these before production.

## Run on Windows

1. Install Python 3.11 or newer.
2. Open Command Prompt in this project folder.
3. Create a virtual environment:

```bat
python -m venv .venv
.venv\Scripts\activate
```

4. Install dependencies:

```bat
pip install -r requirements.txt
```

5. Run the app:

```bat
python app.py
```

6. Open Google Chrome to:

`http://127.0.0.1:5000`

The SQLite database file `zoomies.db` is created automatically.

## Deploy

This can be deployed to Render, Railway, Fly.io, or another Python host. For multi-user production use, replace SQLite with PostgreSQL and set a strong `SECRET_KEY`.

## Important production work still needed

- Secure password reset and email verification
- Real SMS/email provider
- Clover API integration
- Production PostgreSQL database
- Photo/file storage
- Backups and audit logs
- Fine-grained permissions
- CSRF protection
- Privacy policy, terms, waiver text, and production security review


## Render deployment — recommended method

This package includes `render.yaml`.

1. Make sure `app.py`, `requirements.txt`, `render.yaml`, `runtime.txt`, `templates/`, and `static/` are at the repository root.
2. In Render choose **New → Blueprint**.
3. Select the GitHub repository.
4. Render should read `render.yaml` and configure the service automatically.

If using **New → Web Service** instead:

- Runtime: Python
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn --bind 0.0.0.0:$PORT app:app`
- Health check path: `/health`

If the files are inside a subfolder, enter that exact folder in Render's **Root Directory** field.
