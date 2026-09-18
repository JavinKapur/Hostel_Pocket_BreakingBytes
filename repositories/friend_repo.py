from typing import List, Dict, Any, Optional
from db.connection import get_connection, get_cursor

def get_friends(user_id: str, include_archived: bool = False) -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = get_cursor(conn)
    try:
        query = "SELECT * FROM friends WHERE user_id = %s"
        if not include_archived:
            query += " AND archived_at IS NULL"
        query += " ORDER BY name ASC;"
        cur.execute(query, (user_id,))
        return [dict(r) for r in cur.fetchall()]
    finally:
        cur.close()
        conn.close()

def get_friend_by_id(user_id: str, friend_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cur = get_cursor(conn)
    try:
        cur.execute("SELECT * FROM friends WHERE id = %s AND user_id = %s LIMIT 1;", (friend_id, user_id))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        cur.close()
        conn.close()

def create_friend(user_id: str, name: str, sample_upi_id: str = "", note: str = "") -> Dict[str, Any]:
    conn = get_connection()
    cur = get_cursor(conn)
    try:
        cur.execute("""
        INSERT INTO friends (user_id, name, sample_upi_id, note)
        VALUES (%s, %s, %s, %s)
        RETURNING *;
        """, (user_id, name.strip(), sample_upi_id.strip() if sample_upi_id else None, note.strip() if note else None))
        row = cur.fetchone()
        conn.commit()
        return dict(row)
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()

def update_friend(user_id: str, friend_id: str, name: str, sample_upi_id: str = "", note: str = "") -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cur = get_cursor(conn)
    try:
        cur.execute("""
        UPDATE friends
        SET name = %s, sample_upi_id = %s, note = %s
        WHERE id = %s AND user_id = %s
        RETURNING *;
        """, (name.strip(), sample_upi_id.strip() if sample_upi_id else None, note.strip() if note else None, friend_id, user_id))
        row = cur.fetchone()
        conn.commit()
        return dict(row) if row else None
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()

def archive_friend(user_id: str, friend_id: str) -> bool:
    conn = get_connection()
    cur = get_cursor(conn)
    try:
        cur.execute("""
        UPDATE friends
        SET archived_at = NOW()
        WHERE id = %s AND user_id = %s AND archived_at IS NULL;
        """, (friend_id, user_id))
        affected = cur.rowcount
        conn.commit()
        return affected > 0
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()
