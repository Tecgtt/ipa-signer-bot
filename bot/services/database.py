import sqlite3
import os
import json
from typing import Optional, Dict, Any

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "bot.db")

class Database:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    p12_path TEXT,
                    p12_password TEXT,
                    mobileprovision_path TEXT,
                    cert_name TEXT,
                    cert_expiry TEXT,
                    custom_icon_path TEXT,
                    custom_bundle_id TEXT DEFAULT '',
                    custom_app_name TEXT DEFAULT '',
                    inject_dylib_path TEXT DEFAULT '',
                    is_vip INTEGER DEFAULT 0,
                    vip_expiry TEXT,
                    sign_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            conn.commit()

    def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def create_or_update_user(self, user_id: int, username: str = "", first_name: str = ""):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO users (user_id, username, first_name)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username = COALESCE(NULLIF(excluded.username, ''), users.username),
                    first_name = COALESCE(NULLIF(excluded.first_name, ''), users.first_name)
            """, (user_id, username, first_name))
            conn.commit()

    def update_user_fields(self, user_id: int, **kwargs):
        if not kwargs:
            return
        keys = list(kwargs.keys())
        values = list(kwargs.values())
        set_clause = ", ".join([f"{k} = ?" for k in keys])
        values.append(user_id)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"UPDATE users SET {set_clause} WHERE user_id = ?", values)
            conn.commit()

    def increment_sign_count(self, user_id: int):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET sign_count = sign_count + 1 WHERE user_id = ?", (user_id,))
            conn.commit()

    def clear_certificate(self, user_id: int):
        user = self.get_user(user_id)
        if user:
            for field in ['p12_path', 'mobileprovision_path']:
                path = user.get(field)
                if path and os.path.exists(path):
                    try:
                        os.remove(path)
                    except Exception:
                        pass
        self.update_user_fields(
            user_id,
            p12_path="",
            p12_password="",
            mobileprovision_path="",
            cert_name="",
            cert_expiry=""
        )

    def clear_thumbnail(self, user_id: int):
        user = self.get_user(user_id)
        if user and user.get('custom_icon_path'):
            path = user['custom_icon_path']
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass
        self.update_user_fields(user_id, custom_icon_path="")

    def get_all_users_count(self) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users")
            return cursor.fetchone()[0]

db = Database()
