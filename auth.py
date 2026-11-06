"""
User accounts for TrendSense.

* Passwords are never stored. Only a salted PBKDF2-SHA256 hash is saved.
* 5 wrong passwords in 5 minutes locks that username for a few minutes.
* ALL new registrations get the 'owner' role (boutique/manufacturer).
* Developer/admin role is set directly in the DB by the project team (not via UI).
* No Streamlit imports here, so this file is easy to test.
"""
import hashlib
import hmac
import os
import re
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime

ITERATIONS = 200_000
MAX_FAILS = 5
LOCK_SECONDS = 300
MIN_PASSWORD = 8
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.@-]{3,40}$")

_DB = None


def init(path):
    """Create the users database (if needed). Call once at start-up."""
    global _DB
    _DB = str(path)
    with _conn() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                name TEXT, shop TEXT,
                salt BLOB NOT NULL, pw_hash BLOB NOT NULL, iterations INTEGER NOT NULL,
                role TEXT NOT NULL DEFAULT 'owner',
                lang TEXT NOT NULL DEFAULT 'en',
                lead_weeks INTEGER NOT NULL DEFAULT 3,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS watchlist (
                user_id INTEGER NOT NULL, keyword TEXT NOT NULL, added_at TEXT,
                PRIMARY KEY (user_id, keyword)
            );
            CREATE TABLE IF NOT EXISTS attempts (username TEXT NOT NULL, ts REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS login_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT NOT NULL,
                name TEXT,
                shop TEXT,
                role TEXT,
                logged_at TEXT NOT NULL,
                client TEXT DEFAULT 'Web Browser'
            );
        """)


@contextmanager
def _conn():
    c = sqlite3.connect(_DB, timeout=10)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def _hash(password, salt, iterations=ITERATIONS):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)


def _public(row):
    return {k: row[k] for k in ("id", "username", "name", "shop", "role", "lang", "lead_weeks")}


def count_users():
    with _conn() as c:
        return c.execute("SELECT COUNT(*) FROM users").fetchone()[0]


def register(username, password, name, shop, lang="en"):
    """Returns (user, None) on success or (None, error_key). Error keys match i18n texts."""
    username, name, shop = (username or "").strip(), (name or "").strip(), (shop or "").strip()
    if not (username and password and name and shop):
        return None, "err_fields"
    if not USERNAME_RE.match(username):
        return None, "err_user"
    if len(password) < MIN_PASSWORD:
        return None, "err_pw"
    salt = os.urandom(16)
    try:
        with _conn() as c:
            role = "owner"  # All users register as owners; admin set by developers in DB
            cur = c.execute(
                "INSERT INTO users (username,name,shop,salt,pw_hash,iterations,role,lang,created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (username, name, shop, salt, _hash(password, salt), ITERATIONS, role, lang,
                 datetime.now().strftime("%Y-%m-%d %H:%M")))
            row = c.execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone()
            c.execute(
                "INSERT INTO login_logs (user_id, username, name, shop, role, logged_at, client) "
                "VALUES (?,?,?,?,?,?,?)",
                (row["id"], row["username"], row["name"], row["shop"], row["role"],
                 datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "New Account Registered")
            )
        return _public(row), None
    except sqlite3.IntegrityError:
        return None, "err_taken"


def authenticate(username, password):
    """Returns (user, None) or (None, error_key)."""
    username = (username or "").strip()
    if not username or not password:
        return None, "err_fields"
    now = time.time()
    with _conn() as c:
        c.execute("DELETE FROM attempts WHERE ts < ?", (now - 86400,))
        fails = c.execute("SELECT COUNT(*) FROM attempts WHERE username=? COLLATE NOCASE AND ts>?",
                          (username, now - LOCK_SECONDS)).fetchone()[0]
        if fails >= MAX_FAILS:
            return None, "err_locked"
        row = c.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if row is None:
            _hash(password, b"0" * 16)  # same work as a real check, so timing doesn't reveal usernames
            c.execute("INSERT INTO attempts VALUES (?,?)", (username.lower(), now))
            return None, "err_login"
        ok = hmac.compare_digest(_hash(password, row["salt"], row["iterations"]), row["pw_hash"])
        if not ok:
            c.execute("INSERT INTO attempts VALUES (?,?)", (username.lower(), now))
            return None, "err_login"
        c.execute("DELETE FROM attempts WHERE username=? COLLATE NOCASE", (username,))
        c.execute(
            "INSERT INTO login_logs (user_id, username, name, shop, role, logged_at, client) "
            "VALUES (?,?,?,?,?,?,?)",
            (row["id"], row["username"], row["name"], row["shop"], row["role"],
             datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "Web Browser Session")
        )
        return _public(row), None


def set_password(username, new_password):
    """Admin tool: reset someone's password. Returns (ok, error_key)."""
    if len(new_password or "") < MIN_PASSWORD:
        return False, "err_pw"
    salt = os.urandom(16)
    with _conn() as c:
        cur = c.execute("UPDATE users SET salt=?, pw_hash=?, iterations=? WHERE username=?",
                        (salt, _hash(new_password, salt), ITERATIONS, username))
        c.execute("DELETE FROM attempts WHERE username=? COLLATE NOCASE", (username,))
        return cur.rowcount == 1, None


def update_pref(user_id, lang=None, lead_weeks=None):
    with _conn() as c:
        if lang is not None:
            c.execute("UPDATE users SET lang=? WHERE id=?", (lang, user_id))
        if lead_weeks is not None:
            c.execute("UPDATE users SET lead_weeks=? WHERE id=?", (int(lead_weeks), user_id))


def get_watchlist(user_id):
    with _conn() as c:
        return [r["keyword"] for r in
                c.execute("SELECT keyword FROM watchlist WHERE user_id=? ORDER BY added_at, keyword", (user_id,))]


def set_watchlist(user_id, keywords):
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    with _conn() as c:
        c.execute("DELETE FROM watchlist WHERE user_id=?", (user_id,))
        c.executemany("INSERT OR IGNORE INTO watchlist VALUES (?,?,?)",
                      [(user_id, k, stamp) for k in keywords])


def list_users():
    with _conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT username, name, shop, role, lang, created_at FROM users ORDER BY id")]


def get_login_logs(limit=50):
    """Retrieve audit history of user sign-ins for the admin console."""
    with _conn() as c:
        try:
            return [dict(r) for r in c.execute(
                "SELECT username, name, shop, role, logged_at, client FROM login_logs ORDER BY id DESC LIMIT ?",
                (limit,))]
        except Exception:
            return []
