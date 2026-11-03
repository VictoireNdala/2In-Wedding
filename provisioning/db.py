"""Couche données — schéma SQLite (events, guests, cards) + requêtes.

Base séparée de la bibliothèque phonétique (voir phonetics.py / phonetics.db),
qui est un actif transversal indépendant des événements.
"""
import sqlite3
from datetime import datetime, timezone

from config import APP_DB_PATH, ensure_data_dirs

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    event_type TEXT NOT NULL,
    event_date TEXT,
    message_template TEXT NOT NULL DEFAULT 'Bienvenue {civilite} {nom} au mariage de {event_name}',
    status TEXT NOT NULL DEFAULT 'draft'  -- draft, active, archived
);

CREATE TABLE IF NOT EXISTS guests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL REFERENCES events(id),
    full_name TEXT NOT NULL,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    civility TEXT,
    card_uid TEXT,
    audio_file_path TEXT,
    arrival_status TEXT NOT NULL DEFAULT 'not_arrived',  -- not_arrived, arrived
    arrived_at TEXT
);

CREATE TABLE IF NOT EXISTS cards (
    uid TEXT PRIMARY KEY,
    current_guest_id INTEGER REFERENCES guests(id),
    status TEXT NOT NULL DEFAULT 'unassigned'  -- unassigned, assigned
);

CREATE INDEX IF NOT EXISTS idx_guests_event ON guests(event_id);
CREATE INDEX IF NOT EXISTS idx_guests_card_uid ON guests(card_uid);
"""


def get_connection(db_path=APP_DB_PATH):
    ensure_data_dirs()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path=APP_DB_PATH):
    conn = get_connection(db_path)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


# --- events ---------------------------------------------------------------

def create_event(name, event_type, event_date=None, message_template=None, db_path=APP_DB_PATH):
    conn = get_connection(db_path)
    fields = {"name": name, "event_type": event_type, "event_date": event_date}
    if message_template:
        fields["message_template"] = message_template
    columns = ", ".join(fields.keys())
    placeholders = ", ".join("?" for _ in fields)
    cur = conn.execute(
        f"INSERT INTO events ({columns}) VALUES ({placeholders})",
        tuple(fields.values()),
    )
    conn.commit()
    event_id = cur.lastrowid
    conn.close()
    return event_id


def get_event(event_id, db_path=APP_DB_PATH):
    conn = get_connection(db_path)
    row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_events(db_path=APP_DB_PATH):
    conn = get_connection(db_path)
    rows = conn.execute("SELECT * FROM events ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def set_event_status(event_id, status, db_path=APP_DB_PATH):
    conn = get_connection(db_path)
    conn.execute("UPDATE events SET status = ? WHERE id = ?", (status, event_id))
    conn.commit()
    conn.close()


# --- guests ----------------------------------------------------------------

def add_guest(event_id, first_name, last_name, civility=None, db_path=APP_DB_PATH):
    full_name = f"{first_name} {last_name}".strip()
    conn = get_connection(db_path)
    cur = conn.execute(
        """INSERT INTO guests (event_id, full_name, first_name, last_name, civility)
           VALUES (?, ?, ?, ?, ?)""",
        (event_id, full_name, first_name, last_name, civility),
    )
    conn.commit()
    guest_id = cur.lastrowid
    conn.close()
    return guest_id


def get_guest(guest_id, db_path=APP_DB_PATH):
    conn = get_connection(db_path)
    row = conn.execute("SELECT * FROM guests WHERE id = ?", (guest_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_guest_by_card_uid(uid, event_id=None, db_path=APP_DB_PATH):
    conn = get_connection(db_path)
    if event_id is not None:
        row = conn.execute(
            "SELECT * FROM guests WHERE card_uid = ? AND event_id = ?", (uid, event_id)
        ).fetchone()
    else:
        row = conn.execute("SELECT * FROM guests WHERE card_uid = ?", (uid,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_guests_for_event(event_id, db_path=APP_DB_PATH):
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT * FROM guests WHERE event_id = ? ORDER BY last_name, first_name", (event_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_guest_audio_path(guest_id, audio_path, db_path=APP_DB_PATH):
    conn = get_connection(db_path)
    conn.execute("UPDATE guests SET audio_file_path = ? WHERE id = ?", (audio_path, guest_id))
    conn.commit()
    conn.close()


def set_guest_card_uid(guest_id, uid, db_path=APP_DB_PATH):
    conn = get_connection(db_path)
    conn.execute("UPDATE guests SET card_uid = ? WHERE id = ?", (uid, guest_id))
    conn.commit()
    conn.close()


def mark_guest_arrived(guest_id, db_path=APP_DB_PATH):
    conn = get_connection(db_path)
    conn.execute(
        "UPDATE guests SET arrival_status = 'arrived', arrived_at = ? WHERE id = ?",
        (datetime.now(timezone.utc).isoformat(), guest_id),
    )
    conn.commit()
    conn.close()


# --- cards -------------------------------------------------------------------

def assign_card(uid, guest_id, db_path=APP_DB_PATH):
    """Associe une carte physique (UID) à un invité. Écrase toute association précédente de cet UID."""
    conn = get_connection(db_path)
    conn.execute(
        """INSERT INTO cards (uid, current_guest_id, status) VALUES (?, ?, 'assigned')
           ON CONFLICT(uid) DO UPDATE SET current_guest_id = excluded.current_guest_id, status = 'assigned'""",
        (uid, guest_id),
    )
    conn.execute("UPDATE guests SET card_uid = ? WHERE id = ?", (uid, guest_id))
    conn.commit()
    conn.close()


def get_card(uid, db_path=APP_DB_PATH):
    conn = get_connection(db_path)
    row = conn.execute("SELECT * FROM cards WHERE uid = ?", (uid,)).fetchone()
    conn.close()
    return dict(row) if row else None


if __name__ == "__main__":
    init_db()
    print(f"Base initialisée : {APP_DB_PATH}")
