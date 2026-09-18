import json
from typing import List, Dict, Any, Optional
from db.connection import get_connection, get_cursor

def append_timeline_event(
    user_id: str,
    event_type: str,
    entity_type: str,
    entity_id: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    correlation_id: Optional[str] = None,
) -> Dict[str, Any]:
    conn = get_connection()
    cur = get_cursor(conn)
    try:
        cur.execute("""
        INSERT INTO timeline_events (user_id, event_type, entity_type, entity_id, payload, correlation_id)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING *;
        """, (user_id, event_type, entity_type, entity_id, json.dumps(payload or {}), correlation_id))
        row = cur.fetchone()
        conn.commit()
        return dict(row)
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()

def get_timeline_events(user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = get_cursor(conn)
    try:
        cur.execute("""
        SELECT * FROM timeline_events
        WHERE user_id = %s
        ORDER BY occurred_at DESC
        LIMIT %s;
        """, (user_id, limit))
        return [dict(r) for r in cur.fetchall()]
    finally:
        cur.close()
        conn.close()
