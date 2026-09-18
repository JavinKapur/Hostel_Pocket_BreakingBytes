import datetime
from typing import List, Dict, Any, Optional
from db.connection import get_connection, get_cursor

def get_active_reminders(user_id: str) -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = get_cursor(conn)
    try:
        cur.execute("""
        SELECT * FROM reminders
        WHERE user_id = %s AND status = 'active'
        ORDER BY created_at DESC;
        """, (user_id,))
        return [dict(r) for r in cur.fetchall()]
    finally:
        cur.close()
        conn.close()

def dismiss_reminder(user_id: str, reminder_id: str) -> bool:
    conn = get_connection()
    cur = get_cursor(conn)
    try:
        cur.execute("""
        UPDATE reminders
        SET status = 'dismissed', dismissed_at = NOW()
        WHERE id = %s AND user_id = %s;
        """, (reminder_id, user_id))
        affected = cur.rowcount
        conn.commit()
        return affected > 0
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()

def evaluate_and_sync_reminders(user_id: str, budget_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Evaluates SDD Section 8.2 reminder rules:
    - BUDGET_MISSING
    - BUDGET_80
    - BUDGET_EXCEEDED
    """
    conn = get_connection()
    cur = get_cursor(conn)
    try:
        # Check active reminders types already present today
        cur.execute("""
        SELECT reminder_type FROM reminders
        WHERE user_id = %s AND status = 'active';
        """, (user_id,))
        existing_types = {r["reminder_type"] for r in cur.fetchall()}

        now = datetime.datetime.now()

        # Rule 1: BUDGET_MISSING
        if (budget_data.get("daily_budget") is None or budget_data.get("monthly_budget") is None) and "BUDGET_MISSING" not in existing_types:
            cur.execute("""
            INSERT INTO reminders (user_id, reminder_type, title, body, status)
            VALUES (%s, 'BUDGET_MISSING', 'Set your student budget', 'No active daily or monthly budget found for this period. Set one to stay on track.', 'active');
            """, (user_id,))

        # Rule 2: BUDGET_EXCEEDED
        monthly_pct = budget_data.get("monthly_pct", 0.0)
        if monthly_pct > 100 and "BUDGET_EXCEEDED" not in existing_types:
            cur.execute("""
            INSERT INTO reminders (user_id, reminder_type, title, body, status)
            VALUES (%s, 'BUDGET_EXCEEDED', 'Monthly budget limit reached', 'You have spent 100%% of your monthly budget. Minimize discretionary spending.', 'active');
            """, (user_id,))
        # Rule 3: BUDGET_80
        elif monthly_pct >= 80 and monthly_pct <= 100 and "BUDGET_80" not in existing_types:
            cur.execute("""
            INSERT INTO reminders (user_id, reminder_type, title, body, status)
            VALUES (%s, 'BUDGET_80', 'Monthly budget threshold (80%%)', 'You have reached 80%% of your monthly budget. Review upcoming expenses.', 'active');
            """, (user_id,))

        conn.commit()
        return get_active_reminders(user_id)
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()
