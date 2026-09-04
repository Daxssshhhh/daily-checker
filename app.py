from flask import Flask, render_template, request, redirect, url_for, jsonify
import sqlite3
from datetime import date, datetime, timedelta

app = Flask(__name__)

DATABASE = "daily_checker.db"


# ---------------- DATABASE ----------------

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS habits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS daily_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            habit_id INTEGER NOT NULL,
            log_date TEXT NOT NULL,
            completed INTEGER NOT NULL DEFAULT 0,

            FOREIGN KEY(habit_id)
            REFERENCES habits(id),

            UNIQUE(habit_id, log_date)
        );

        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            note_date TEXT NOT NULL UNIQUE,
            content TEXT NOT NULL DEFAULT ''
        );
    """)

    conn.commit()
    conn.close()


# ---------------- DASHBOARD ----------------

@app.route("/")
def dashboard():

    conn = get_db()

    today = date.today().isoformat()

    habits = conn.execute("""
        SELECT
            h.id,
            h.name,
            COALESCE(dl.completed, 0) AS completed
        FROM habits h

        LEFT JOIN daily_logs dl
        ON h.id = dl.habit_id
        AND dl.log_date = ?

        ORDER BY h.id
    """, (today,)).fetchall()

    completed = sum(h["completed"] for h in habits)
    total = len(habits)

    percentage = 0

    if total > 0:
        percentage = round((completed / total) * 100)

    conn.close()

    return render_template(
        "dashboard.html",
        habits=habits,
        completed=completed,
        total=total,
        percentage=percentage,
        today=today
    )


# ---------------- ADD HABIT ----------------

@app.post("/add-habit")
def add_habit():

    name = request.form.get("name", "").strip()

    if name:

        conn = get_db()

        conn.execute("""
            INSERT INTO habits(name, created_at)
            VALUES (?, ?)
        """, (
            name,
            datetime.now().isoformat()
        ))

        conn.commit()
        conn.close()

    return redirect(url_for("dashboard"))


# ---------------- TOGGLE HABIT ----------------

@app.post("/toggle/<int:habit_id>")
def toggle_habit(habit_id):

    log_date = request.form.get(
        "log_date",
        date.today().isoformat()
    )

    conn = get_db()

    existing = conn.execute("""
        SELECT completed
        FROM daily_logs

        WHERE habit_id = ?
        AND log_date = ?
    """, (
        habit_id,
        log_date
    )).fetchone()

    if existing:

        new_value = 0 if existing["completed"] else 1

        conn.execute("""
            UPDATE daily_logs

            SET completed = ?

            WHERE habit_id = ?
            AND log_date = ?
        """, (
            new_value,
            habit_id,
            log_date
        ))

    else:

        conn.execute("""
            INSERT INTO daily_logs
            (habit_id, log_date, completed)

            VALUES (?, ?, 1)
        """, (
            habit_id,
            log_date
        ))

    conn.commit()
    conn.close()

    return redirect(
        request.referrer or
        url_for("dashboard")
    )


# ---------------- DELETE HABIT ----------------

@app.post("/delete-habit/<int:habit_id>")
def delete_habit(habit_id):

    conn = get_db()

    conn.execute("""
        DELETE FROM daily_logs
        WHERE habit_id = ?
    """, (habit_id,))

    conn.execute("""
        DELETE FROM habits
        WHERE id = ?
    """, (habit_id,))

    conn.commit()
    conn.close()

    return redirect(url_for("dashboard"))


# ---------------- HISTORY ----------------

@app.route("/history")
def history():

    selected_date = request.args.get(
        "date",
        date.today().isoformat()
    )

    conn = get_db()

    habits = conn.execute("""
        SELECT
            h.id,
            h.name,
            COALESCE(dl.completed, 0) AS completed

        FROM habits h

        LEFT JOIN daily_logs dl

        ON h.id = dl.habit_id
        AND dl.log_date = ?

        ORDER BY h.id
    """, (
        selected_date,
    )).fetchall()

    note = conn.execute("""
        SELECT content
        FROM notes

        WHERE note_date = ?
    """, (
        selected_date,
    )).fetchone()

    conn.close()

    note_content = ""

    if note:
        note_content = note["content"]

    return render_template(
        "history.html",
        habits=habits,
        selected_date=selected_date,
        note=note_content
    )


# ---------------- SAVE NOTE ----------------

@app.post("/save-note")
def save_note():

    note_date = request.form["note_date"]

    content = request.form.get(
        "content",
        ""
    ).strip()

    conn = get_db()

    conn.execute("""
        INSERT INTO notes(
            note_date,
            content
        )

        VALUES (?, ?)

        ON CONFLICT(note_date)

        DO UPDATE SET
        content = excluded.content
    """, (
        note_date,
        content
    ))

    conn.commit()
    conn.close()

    return redirect(
        url_for(
            "history",
            date=note_date
        )
    )


# ---------------- ANALYTICS PAGE ----------------

@app.route("/analytics")
def analytics():

    return render_template(
        "analytics.html"
    )


# ---------------- ANALYTICS API ----------------

@app.get("/api/analytics")
def analytics_api():

    period = request.args.get(
        "period",
        "week"
    )

    today = date.today()

    # ---------- DAY ----------

    if period == "day":

        start = today
        end = today

        dates = [
            today.isoformat()
        ]

        labels = [
            today.strftime("%a")
        ]

    # ---------- WEEK ----------

    elif period == "week":

        start = today - timedelta(days=6)

        end = today

        dates = []

        labels = []

        for i in range(7):

            current = start + timedelta(days=i)

            dates.append(
                current.isoformat()
            )

            labels.append(
                current.strftime("%a")
            )

    # ---------- MONTH ----------

    elif period == "month":

        start = today.replace(day=1)

        end = today

        dates = []

        labels = []

        current = start

        while current <= end:

            dates.append(
                current.isoformat()
            )

            labels.append(
                current.strftime("%d %b")
            )

            current += timedelta(days=1)

    # ---------- 30 DAYS ----------

    else:

        start = today - timedelta(days=29)

        end = today

        dates = []

        labels = []

        for i in range(30):

            current = start + timedelta(days=i)

            dates.append(
                current.isoformat()
            )

            labels.append(
                current.strftime("%d %b")
            )

    conn = get_db()

    # Number of habits
    total_habits = conn.execute("""
        SELECT COUNT(*)
        FROM habits
    """).fetchone()[0]

    daily_completion = []

    for current_date in dates:

        completed = conn.execute("""
            SELECT COUNT(*)

            FROM daily_logs

            WHERE log_date = ?
            AND completed = 1
        """, (
            current_date,
        )).fetchone()[0]

        if total_habits > 0:

            percentage = round(
                completed /
                total_habits *
                100
            )

        else:

            percentage = 0

        daily_completion.append(
            percentage
        )

    # ---------- HABIT STATISTICS ----------

    habits = conn.execute("""
        SELECT id, name
        FROM habits

        ORDER BY id
    """).fetchall()

    habit_data = []

    for habit in habits:

        completed_days = conn.execute("""
            SELECT COUNT(*)

            FROM daily_logs

            WHERE habit_id = ?

            AND log_date
            BETWEEN ?
            AND ?

            AND completed = 1
        """, (
            habit["id"],
            start.isoformat(),
            end.isoformat()
        )).fetchone()[0]

        habit_data.append({
            "name": habit["name"],
            "completed": completed_days
        })

    conn.close()

    return jsonify({
        "labels": labels,
        "daily": daily_completion,
        "habits": habit_data
    })


# ---------------- START APPLICATION ----------------

if __name__ == "__main__":

    init_db()

    app.run(
        debug=True
    )