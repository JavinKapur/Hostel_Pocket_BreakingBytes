import datetime
from typing import Optional, Dict, Any
from db.connection import get_connection, get_cursor

def get_budget(user_id: str, period_type: str, period_start: datetime.date) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cur = get_cursor(conn)
    try:
        cur.execute("""
        SELECT * FROM budgets
        WHERE user_id = %s AND period_type = %s AND period_start = %s
        LIMIT 1;
        """, (user_id, period_type, period_start))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        cur.close()
        conn.close()

def set_budget(user_id: str, period_type: str, period_start: datetime.date, amount: float) -> Dict[str, Any]:
    conn = get_connection()
    cur = get_cursor(conn)
    try:
        cur.execute("""
        INSERT INTO budgets (user_id, period_type, period_start, amount, updated_at)
        VALUES (%s, %s, %s, %s, NOW())
        ON CONFLICT (user_id, period_type, period_start)
        DO UPDATE SET amount = EXCLUDED.amount, updated_at = NOW()
        RETURNING *;
        """, (user_id, period_type, period_start, amount))
        row = cur.fetchone()
        conn.commit()
        return dict(row)
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()

def get_budget_utilization(user_id: str, ref_date: Optional[datetime.date] = None) -> Dict[str, Any]:
    """
    Aggregates daily and monthly spent vs budget for the given date.
    Per SDD Section 7.2:
      daily_spent = SUM(expenses.amount WHERE expense_date = today)
      monthly_spent = SUM(expenses.amount WHERE month(expense_date) = current_month)
    """
    if not ref_date:
        ref_date = datetime.date.today()
    month_start = ref_date.replace(day=1)
    if ref_date.month == 12:
        next_month = datetime.date(ref_date.year + 1, 1, 1)
    else:
        next_month = datetime.date(ref_date.year, ref_date.month + 1, 1)

    conn = get_connection()
    cur = get_cursor(conn)
    try:
        # 1. Daily spent
        cur.execute("""
        SELECT COALESCE(SUM(amount), 0) as spent
        FROM expenses
        WHERE user_id = %s AND expense_date = %s AND deleted_at IS NULL;
        """, (user_id, ref_date))
        daily_spent = float(cur.fetchone()["spent"])

        # 2. Monthly spent
        cur.execute("""
        SELECT COALESCE(SUM(amount), 0) as spent
        FROM expenses
        WHERE user_id = %s AND expense_date >= %s AND expense_date < %s AND deleted_at IS NULL;
        """, (user_id, month_start, next_month))
        monthly_spent = float(cur.fetchone()["spent"])

        # 3. Daily budget
        cur.execute("""
        SELECT amount FROM budgets
        WHERE user_id = %s AND period_type = 'day' AND period_start = %s
        LIMIT 1;
        """, (user_id, ref_date))
        d_row = cur.fetchone()
        daily_budget = float(d_row["amount"]) if d_row else None

        # 4. Monthly budget
        cur.execute("""
        SELECT amount FROM budgets
        WHERE user_id = %s AND period_type = 'month' AND period_start = %s
        LIMIT 1;
        """, (user_id, month_start))
        m_row = cur.fetchone()
        monthly_budget = float(m_row["amount"]) if m_row else None

        daily_remaining = (daily_budget - daily_spent) if daily_budget is not None else 0.0
        daily_pct = (daily_spent / daily_budget * 100) if (daily_budget and daily_budget > 0) else 0.0

        monthly_remaining = (monthly_budget - monthly_spent) if monthly_budget is not None else 0.0
        monthly_pct = (monthly_spent / monthly_budget * 100) if (monthly_budget and monthly_budget > 0) else 0.0

        return {
            "ref_date": ref_date,
            "month_start": month_start,
            "daily_budget": daily_budget,
            "daily_spent": daily_spent,
            "daily_remaining": daily_remaining,
            "daily_pct": daily_pct,
            "monthly_budget": monthly_budget,
            "monthly_spent": monthly_spent,
            "monthly_remaining": monthly_remaining,
            "monthly_pct": monthly_pct,
        }
    finally:
        cur.close()
        conn.close()
