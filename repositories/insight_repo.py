import json
import datetime
from typing import List, Dict, Any, Optional
from db.connection import get_connection, get_cursor

def get_latest_insight(user_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cur = get_cursor(conn)
    try:
        cur.execute("""
        SELECT * FROM ai_insights
        WHERE user_id = %s
        ORDER BY generated_at DESC
        LIMIT 1;
        """, (user_id,))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        cur.close()
        conn.close()

def save_insight(
    user_id: str,
    title: str,
    body: str,
    insight_type: str = "spending_pattern",
    severity: str = "info",
    data: Optional[Dict[str, Any]] = None,
    window_start: Optional[datetime.date] = None,
    window_end: Optional[datetime.date] = None,
) -> Dict[str, Any]:
    conn = get_connection()
    cur = get_cursor(conn)
    try:
        cur.execute("""
        INSERT INTO ai_insights (user_id, window_start, window_end, insight_type, title, body, severity, data)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *;
        """, (
            user_id,
            window_start,
            window_end,
            insight_type,
            title,
            body,
            severity,
            json.dumps(data or {}),
        ))
        row = cur.fetchone()
        conn.commit()
        return dict(row)
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()
