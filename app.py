from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime, timedelta
from functools import wraps
from typing import Optional

from flask import Flask, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, "zoomies.db")

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-before-production")
app.config["DATABASE"] = DATABASE

GROOMERS = ["Terri", "Emily", "Taylor", "Amanda", "Midge"]
BOOKING_SLOTS = [("08:00", "10:00"), ("10:00", "12:00"), ("13:00", "15:00"), ("15:00", "17:00")]
CUSTOMER_SERVICES = {
    "Full-Service Bath": 65.00,
    "Full-Service Groom": 95.00,
}


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_: Optional[BaseException]) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            name TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin','employee','customer'))
        );

        CREATE TABLE IF NOT EXISTS dogs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            breed TEXT,
            birthdate TEXT,
            medical_notes TEXT,
            behavior_notes TEXT,
            coat_goals TEXT,
            vaccination_expiry TEXT,
            FOREIGN KEY(owner_user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dog_id INTEGER NOT NULL,
            customer_user_id INTEGER NOT NULL,
            groomer TEXT NOT NULL,
            service TEXT NOT NULL,
            appointment_date TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            notes TEXT,
            status TEXT NOT NULL DEFAULT 'Confirmed',
            created_at TEXT NOT NULL,
            FOREIGN KEY(dog_id) REFERENCES dogs(id) ON DELETE CASCADE,
            FOREIGN KEY(customer_user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS availability_blocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            groomer TEXT NOT NULL,
            block_date TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            block_type TEXT NOT NULL,
            note TEXT,
            created_by INTEGER,
            FOREIGN KEY(created_by) REFERENCES users(id)
        );

        CREATE INDEX IF NOT EXISTS idx_appt_lookup
        ON appointments(groomer, appointment_date, start_time, end_time);

        CREATE INDEX IF NOT EXISTS idx_block_lookup
        ON availability_blocks(groomer, block_date, start_time, end_time);
        """
    )
    db.commit()


def seed_db() -> None:
    db = get_db()
    if db.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"] == 0:
        users = [
            ("admin@zoomies.local", generate_password_hash("Zoomies123!"), "Terri Admin", "admin"),
            ("staff@zoomies.local", generate_password_hash("Zoomies123!"), "Front Desk", "employee"),
            ("customer@zoomies.local", generate_password_hash("Zoomies123!"), "Mary Johnson", "customer"),
        ]
        db.executemany("INSERT INTO users(email,password_hash,name,role) VALUES(?,?,?,?)", users)
        customer = db.execute("SELECT id FROM users WHERE email='customer@zoomies.local'").fetchone()
        db.execute(
            """INSERT INTO dogs(owner_user_id,name,breed,birthdate,medical_notes,behavior_notes,coat_goals,vaccination_expiry)
               VALUES(?,?,?,?,?,?,?,?)""",
            (customer["id"], "Buddy", "Doodle", "2021-04-15", "", "Can be nervous around dryers",
             "Teddy bear style, 1/2 inch body", "2027-05-01"),
        )
        db.commit()


@app.before_request
def ensure_database() -> None:
    init_db()
    seed_db()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def roles_required(*roles):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if session.get("role") not in roles:
                flash("You do not have permission to view that page.", "error")
                return redirect(url_for("home"))
            return view(*args, **kwargs)
        return wrapped
    return decorator


def observed_date(d: date) -> date:
    if d.weekday() == 5:
        return d - timedelta(days=1)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


def nth_weekday(year: int, month: int, weekday: int, occurrence: int) -> date:
    d = date(year, month, 1)
    return d + timedelta(days=(weekday - d.weekday()) % 7 + (occurrence - 1) * 7)


def last_weekday(year: int, month: int, weekday: int) -> date:
    next_month = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
    d = next_month - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - weekday) % 7)


def federal_holidays(year: int) -> list[dict]:
    fixed = [
        ("New Year's Day", date(year, 1, 1)),
        ("Juneteenth National Independence Day", date(year, 6, 19)),
        ("Independence Day", date(year, 7, 4)),
        ("Veterans Day", date(year, 11, 11)),
        ("Christmas Day", date(year, 12, 25)),
    ]
    floating = [
        ("Martin Luther King Jr. Day", nth_weekday(year, 1, 0, 3)),
        ("Washington's Birthday", nth_weekday(year, 2, 0, 3)),
        ("Memorial Day", last_weekday(year, 5, 0)),
        ("Labor Day", nth_weekday(year, 9, 0, 1)),
        ("Columbus Day / Indigenous Peoples' Day", nth_weekday(year, 10, 0, 2)),
        ("Thanksgiving Day", nth_weekday(year, 11, 3, 4)),
    ]
    rows = [{"name": name, "date": d, "observed": observed_date(d)} for name, d in fixed]
    rows += [{"name": name, "date": d, "observed": d} for name, d in floating]
    return sorted(rows, key=lambda x: x["observed"])


def holiday_name(date_text: str) -> Optional[str]:
    d = date.fromisoformat(date_text)
    for holiday in federal_holidays(d.year):
        if d in (holiday["date"], holiday["observed"]):
            return holiday["name"]
    return None


def overlaps(start_a: str, end_a: str, start_b: str, end_b: str) -> bool:
    return start_a < end_b and start_b < end_a


def slot_unavailable(groomer: str, date_text: str, start_time: str, end_time: str) -> Optional[str]:
    holiday = holiday_name(date_text)
    if holiday:
        return holiday

    db = get_db()
    appt = db.execute(
        """SELECT id FROM appointments
           WHERE groomer=? AND appointment_date=? AND status!='Cancelled'
           AND start_time < ? AND ? < end_time
           LIMIT 1""",
        (groomer, date_text, end_time, start_time),
    ).fetchone()
    if appt:
        return "Already booked"

    block = db.execute(
        """SELECT block_type, note FROM availability_blocks
           WHERE (groomer=? OR groomer='All Groomers') AND block_date=?
           AND start_time < ? AND ? < end_time
           LIMIT 1""",
        (groomer, date_text, end_time, start_time),
    ).fetchone()
    if block:
        return block["note"] or block["block_type"]

    return None


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = get_db().execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if not user or not check_password_hash(user["password_hash"], password):
            flash("Incorrect email or password.", "error")
        else:
            session.clear()
            session.update(user_id=user["id"], name=user["name"], role=user["role"])
            return redirect(url_for("home"))
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def home():
    role = session["role"]
    if role == "customer":
        return redirect(url_for("customer_home"))
    return redirect(url_for("employee_dashboard"))


@app.route("/employee")
@roles_required("admin", "employee")
def employee_dashboard():
    db = get_db()
    today = date.today().isoformat()
    appointments = db.execute(
        """SELECT a.*, d.name AS dog_name, u.name AS customer_name
           FROM appointments a
           JOIN dogs d ON d.id=a.dog_id
           JOIN users u ON u.id=a.customer_user_id
           WHERE a.appointment_date=?
           ORDER BY a.start_time, a.groomer""",
        (today,),
    ).fetchall()
    return render_template("employee.html", appointments=appointments, today=today)


@app.route("/calendar")
@roles_required("admin", "employee")
def calendar_view():
    selected_date = request.args.get("date") or date.today().isoformat()
    db = get_db()
    appointments = db.execute(
        """SELECT a.*, d.name AS dog_name
           FROM appointments a JOIN dogs d ON d.id=a.dog_id
           WHERE a.appointment_date=? AND a.status!='Cancelled'""",
        (selected_date,),
    ).fetchall()
    blocks = db.execute(
        "SELECT * FROM availability_blocks WHERE block_date=?",
        (selected_date,),
    ).fetchall()
    holiday = holiday_name(selected_date)
    return render_template(
        "calendar.html",
        selected_date=selected_date,
        groomers=GROOMERS,
        slots=BOOKING_SLOTS,
        appointments=appointments,
        blocks=blocks,
        holiday=holiday,
    )


@app.route("/availability", methods=["GET", "POST"])
@roles_required("admin", "employee")
def availability():
    db = get_db()
    if request.method == "POST":
        groomer = request.form["groomer"]
        block_date = request.form["block_date"]
        start_time = request.form["start_time"]
        end_time = request.form["end_time"]
        block_type = request.form["block_type"]
        note = request.form.get("note", "").strip()
        if start_time >= end_time:
            flash("End time must be later than start time.", "error")
        else:
            db.execute(
                """INSERT INTO availability_blocks
                   (groomer,block_date,start_time,end_time,block_type,note,created_by)
                   VALUES(?,?,?,?,?,?,?)""",
                (groomer, block_date, start_time, end_time, block_type, note, session["user_id"]),
            )
            db.commit()
            flash("Schedule block saved.", "success")
            return redirect(url_for("availability"))

    blocks = db.execute(
        "SELECT * FROM availability_blocks ORDER BY block_date DESC, start_time"
    ).fetchall()
    holidays = federal_holidays(date.today().year)
    return render_template(
        "availability.html",
        groomers=GROOMERS,
        blocks=blocks,
        holidays=holidays,
        today=date.today().isoformat(),
    )


@app.post("/availability/<int:block_id>/delete")
@roles_required("admin", "employee")
def delete_availability(block_id: int):
    db = get_db()
    db.execute("DELETE FROM availability_blocks WHERE id=?", (block_id,))
    db.commit()
    flash("Schedule block removed.", "success")
    return redirect(url_for("availability"))


@app.route("/customer")
@roles_required("customer")
def customer_home():
    db = get_db()
    dogs = db.execute("SELECT * FROM dogs WHERE owner_user_id=?", (session["user_id"],)).fetchall()
    appointments = db.execute(
        """SELECT a.*, d.name AS dog_name FROM appointments a
           JOIN dogs d ON d.id=a.dog_id
           WHERE a.customer_user_id=? AND a.status!='Cancelled'
           ORDER BY a.appointment_date, a.start_time""",
        (session["user_id"],),
    ).fetchall()
    return render_template("customer.html", dogs=dogs, appointments=appointments)


@app.route("/book", methods=["GET", "POST"])
@roles_required("customer")
def book():
    db = get_db()
    dogs = db.execute("SELECT * FROM dogs WHERE owner_user_id=?", (session["user_id"],)).fetchall()
    selected_date = request.values.get("appointment_date") or (date.today() + timedelta(days=1)).isoformat()
    selected_groomer = request.values.get("groomer") or GROOMERS[0]

    if request.method == "POST" and request.form.get("action") == "confirm":
        dog_id = int(request.form["dog_id"])
        service = request.form["service"]
        groomer = request.form["groomer"]
        start_time = request.form["start_time"]
        end_time = dict(BOOKING_SLOTS)[start_time]
        notes = request.form.get("notes", "").strip()

        owns_dog = db.execute(
            "SELECT id FROM dogs WHERE id=? AND owner_user_id=?",
            (dog_id, session["user_id"]),
        ).fetchone()
        if not owns_dog:
            flash("That dog is not attached to your account.", "error")
        elif service not in CUSTOMER_SERVICES:
            flash("Invalid service.", "error")
        else:
            reason = slot_unavailable(groomer, selected_date, start_time, end_time)
            if reason:
                flash(f"That time is unavailable: {reason}.", "error")
            else:
                db.execute(
                    """INSERT INTO appointments
                       (dog_id,customer_user_id,groomer,service,appointment_date,start_time,end_time,notes,status,created_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (
                        dog_id, session["user_id"], groomer, service, selected_date,
                        start_time, end_time, notes, "Confirmed", datetime.now().isoformat(timespec="seconds"),
                    ),
                )
                db.commit()
                flash("Your grooming appointment is confirmed.", "success")
                return redirect(url_for("customer_home"))

    availability_map = {}
    for start_time, end_time in BOOKING_SLOTS:
        availability_map[start_time] = slot_unavailable(selected_groomer, selected_date, start_time, end_time)

    return render_template(
        "book.html",
        dogs=dogs,
        groomers=GROOMERS,
        services=CUSTOMER_SERVICES,
        slots=BOOKING_SLOTS,
        selected_date=selected_date,
        selected_groomer=selected_groomer,
        availability_map=availability_map,
        holiday=holiday_name(selected_date),
    )


@app.post("/appointment/<int:appointment_id>/cancel")
@login_required
def cancel_appointment(appointment_id: int):
    db = get_db()
    appt = db.execute("SELECT * FROM appointments WHERE id=?", (appointment_id,)).fetchone()
    if not appt:
        flash("Appointment not found.", "error")
    elif session["role"] == "customer" and appt["customer_user_id"] != session["user_id"]:
        flash("You cannot cancel that appointment.", "error")
    else:
        db.execute("UPDATE appointments SET status='Cancelled' WHERE id=?", (appointment_id,))
        db.commit()
        flash("Appointment cancelled.", "success")
    return redirect(url_for("home"))


@app.route("/kiosk")
def kiosk():
    return render_template("kiosk.html")


@app.get("/health")
def health():
    return {"status": "ok", "app": "Zoomies OS"}, 200


if __name__ == "__main__":
    with app.app_context():
        init_db()
        seed_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=True)
