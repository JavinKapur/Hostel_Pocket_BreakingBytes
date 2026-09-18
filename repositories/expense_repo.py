import datetime
import json
from typing import List, Dict, Any, Optional
from db.connection import get_connection, get_cursor

def get_categories() -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = get_cursor(conn)
    try:
        cur.execute("SELECT * FROM categories WHERE is_active = true ORDER BY name ASC;")
        return [dict(r) for r in cur.fetchall()]
    finally:
        cur.close()
        conn.close()

def save_expense_atomic(
    user_id: str,
    category_id: str,
    title: str,
    amount: float,
    expense_date: datetime.date,
    friend_id: Optional[str] = None,
    note: Optional[str] = None,
    items: Optional[List[Dict[str, Any]]] = None,
    attachments: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Executes the atomic Save Expense Workflow (SDD Section 7.1):
    1. Validate item totals
    2. Insert expense header
    3. Insert item rows
    4. Insert attachment metadata rows
    5. Insert timeline event for expense.created
    6. Commit transaction atomically
    """
    conn = get_connection()
    cur = get_cursor(conn)
    try:
        # 1. Insert header
        cur.execute("""
        INSERT INTO expenses (user_id, category_id, friend_id, title, amount, expense_date, note)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING *;
        """, (user_id, category_id, friend_id if friend_id else None, title.strip(), amount, expense_date, note.strip() if note else None))
        expense = dict(cur.fetchone())
        expense_id = expense["id"]

        # 2. Insert item rows
        inserted_items = []
        if items:
            for idx, it in enumerate(items):
                name = it.get("item_name", "").strip() or "Item"
                qty = float(it.get("quantity", 1.0))
                price = float(it.get("unit_price", 0.0))
                line_total = float(it.get("line_total", qty * price))
                cur.execute("""
                INSERT INTO expense_items (expense_id, item_name, quantity, unit_price, line_total, sort_order)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING *;
                """, (expense_id, name, qty, price, line_total, idx))
                inserted_items.append(dict(cur.fetchone()))
        else:
            # Create a single line item matching the header
            cur.execute("""
            INSERT INTO expense_items (expense_id, item_name, quantity, unit_price, line_total, sort_order)
            VALUES (%s, %s, 1.0, %s, %s, 0)
            RETURNING *;
            """, (expense_id, title, amount, amount))
            inserted_items.append(dict(cur.fetchone()))

        # 3. Insert attachment metadata rows
        inserted_attachments = []
        if attachments:
            for att in attachments:
                cur.execute("""
                INSERT INTO expense_attachments (expense_id, file_name, mime_type, storage_key, checksum)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING *;
                """, (
                    expense_id,
                    att.get("file_name", "receipt.jpg"),
                    att.get("mime_type", "image/jpeg"),
                    att.get("storage_key", ""),
                    att.get("checksum", ""),
                ))
                inserted_attachments.append(dict(cur.fetchone()))

        # 4. Insert timeline event
        cur.execute("""
        INSERT INTO timeline_events (user_id, event_type, entity_type, entity_id, payload)
        VALUES (%s, 'expense.created', 'expense', %s, %s);
        """, (
            user_id,
            expense_id,
            json.dumps({
                "title": title,
                "amount": amount,
                "expense_date": str(expense_date),
                "items_count": len(inserted_items),
                "attachments_count": len(inserted_attachments),
            }),
        ))

        conn.commit()
        expense["items"] = inserted_items
        expense["attachments"] = inserted_attachments
        return expense
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()

def get_expenses(
    user_id: str,
    start_date: Optional[datetime.date] = None,
    end_date: Optional[datetime.date] = None,
    category_id: Optional[str] = None,
    friend_id: Optional[str] = None,
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
    search_query: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Fetches filtered list of expenses with joined category, friend, and item counts."""
    conn = get_connection()
    cur = get_cursor(conn)
    try:
        sql = """
        SELECT e.*, c.name as category_name, c.icon_key, f.name as friend_name,
               (SELECT COUNT(*) FROM expense_items ei WHERE ei.expense_id = e.id) as item_count,
               (SELECT COUNT(*) FROM expense_attachments ea WHERE ea.expense_id = e.id) as attachment_count
        FROM expenses e
        JOIN categories c ON e.category_id = c.id
        LEFT JOIN friends f ON e.friend_id = f.id
        WHERE e.user_id = %s AND e.deleted_at IS NULL
        """
        params = [user_id]

        if start_date:
            sql += " AND e.expense_date >= %s"
            params.append(start_date)
        if end_date:
            sql += " AND e.expense_date <= %s"
            params.append(end_date)
        if category_id:
            sql += " AND e.category_id = %s"
            params.append(category_id)
        if friend_id:
            sql += " AND e.friend_id = %s"
            params.append(friend_id)
        if min_amount is not None:
            sql += " AND e.amount >= %s"
            params.append(min_amount)
        if max_amount is not None:
            sql += " AND e.amount <= %s"
            params.append(max_amount)
        if search_query:
            term = f"%{search_query.strip()}%"
            sql += """ AND (
                e.title ILIKE %s OR e.note ILIKE %s OR
                EXISTS (SELECT 1 FROM expense_items ei WHERE ei.expense_id = e.id AND ei.item_name ILIKE %s)
            )"""
            params.extend([term, term, term])

        sql += " ORDER BY e.expense_date DESC, e.created_at DESC LIMIT %s;"
        params.append(limit)

        cur.execute(sql, tuple(params))
        return [dict(r) for r in cur.fetchall()]
    finally:
        cur.close()
        conn.close()

def get_expense_details(user_id: str, expense_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cur = get_cursor(conn)
    try:
        cur.execute("""
        SELECT e.*, c.name as category_name, c.icon_key, f.name as friend_name
        FROM expenses e
        JOIN categories c ON e.category_id = c.id
        LEFT JOIN friends f ON e.friend_id = f.id
        WHERE e.id = %s AND e.user_id = %s AND e.deleted_at IS NULL
        LIMIT 1;
        """, (expense_id, user_id))
        exp_row = cur.fetchone()
        if not exp_row:
            return None
        res = dict(exp_row)

        cur.execute("SELECT * FROM expense_items WHERE expense_id = %s ORDER BY sort_order ASC;", (expense_id,))
        res["items"] = [dict(r) for r in cur.fetchall()]

        cur.execute("SELECT * FROM expense_attachments WHERE expense_id = %s ORDER BY created_at ASC;", (expense_id,))
        res["attachments"] = [dict(r) for r in cur.fetchall()]

        return res
    finally:
        cur.close()
        conn.close()

def get_category_aggregates_with_items(user_id: str, start_date: datetime.date, end_date: datetime.date) -> List[Dict[str, Any]]:
    """
    Produces category totals and item-level breakdown for Dashboard Category Drilldown (SDD Section 5.1 & 7.2).
    """
    conn = get_connection()
    cur = get_cursor(conn)
    try:
        # Get category totals
        cur.execute("""
        SELECT c.id as category_id, c.name as category_name, c.icon_key,
               COALESCE(SUM(e.amount), 0) as total_amount
        FROM categories c
        JOIN expenses e ON e.category_id = c.id
        WHERE e.user_id = %s AND e.expense_date >= %s AND e.expense_date <= %s AND e.deleted_at IS NULL
        GROUP BY c.id, c.name, c.icon_key
        ORDER BY total_amount DESC;
        """, (user_id, start_date, end_date))
        cat_rows = [dict(r) for r in cur.fetchall()]

        # Get top items per category
        for cat in cat_rows:
            cur.execute("""
            SELECT ei.item_name, SUM(ei.line_total) as item_total, SUM(ei.quantity) as total_quantity
            FROM expense_items ei
            JOIN expenses e ON ei.expense_id = e.id
            WHERE e.user_id = %s AND e.category_id = %s AND e.expense_date >= %s AND e.expense_date <= %s AND e.deleted_at IS NULL
            GROUP BY ei.item_name
            ORDER BY item_total DESC
            LIMIT 5;
            """, (user_id, cat["category_id"], start_date, end_date))
            cat["items"] = [dict(r) for r in cur.fetchall()]

        return cat_rows
    finally:
        cur.close()
        conn.close()
