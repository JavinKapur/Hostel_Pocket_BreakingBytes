import hashlib
from typing import Optional, Dict, Any
from db.connection import get_connection, get_cursor

def hash_password(password: str) -> str:
    salt = "hostelpocket_student_salt_2026"
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()

def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cur = get_cursor(conn)
    try:
        cur.execute("SELECT * FROM users WHERE LOWER(email) = LOWER(%s) LIMIT 1;", (email.strip(),))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        cur.close()
        conn.close()

def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cur = get_cursor(conn)
    try:
        cur.execute("SELECT * FROM users WHERE id = %s LIMIT 1;", (user_id,))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        cur.close()
        conn.close()

def authenticate_user(email: str, password: str) -> Optional[Dict[str, Any]]:
    user = get_user_by_email(email)
    if not user:
        return None
    if user.get("password_hash") == hash_password(password):
        return user
    return None

def create_user(email: str, password: str, display_name: str) -> Dict[str, Any]:
    conn = get_connection()
    cur = get_cursor(conn)
    try:
        cur.execute("""
        INSERT INTO users (email, password_hash, display_name)
        VALUES (%s, %s, %s)
        RETURNING *;
        """, (email.strip().lower(), hash_password(password), display_name.strip()))
        row = cur.fetchone()
        conn.commit()
        return dict(row)
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()
