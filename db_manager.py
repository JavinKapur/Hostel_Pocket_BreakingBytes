import os
import uuid
import datetime
from typing import Dict, List, Any, Optional, Tuple
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

# Fetch the environment variable string from Render
RAW_DATABASE_URL = os.getenv("DATABASE_URL")

if RAW_DATABASE_URL:
    if RAW_DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = RAW_DATABASE_URL.replace("postgres://", "postgresql://", 1)
    else:
        DATABASE_URL = RAW_DATABASE_URL
else:
    # Local fallback string when running offline on your machine
    DATABASE_URL = "dbname=postgres user=postgres password=BreakingBytes345 host=localhost port=54321"

# Seed room members with realistic Indian UPI handles and placeholder emails
DEFAULT_MEMBERS = [
    {"name": "Javin", "email": "javin.student@gmail.com", "phone_or_upi": "javin@okaxis", "weekly_budget": 6000.0, "remaining": 4230.0, "streak": 7, "xp": 480},
    {"name": "Rahul", "email": "rahul.student@gmail.com", "phone_or_upi": "rahul.sharma@okhdfcbank", "weekly_budget": 5000.0, "remaining": 3800.0, "streak": 5, "xp": 350},
    {"name": "Arjun", "email": "arjun.student@gmail.com", "phone_or_upi": "arjun.verma@icici", "weekly_budget": 5000.0, "remaining": 3400.0, "streak": 6, "xp": 410},
    {"name": "Karan", "email": "karan.student@gmail.com", "phone_or_upi": "karan98@paytm", "weekly_budget": 5000.0, "remaining": 2900.0, "streak": 3, "xp": 220},
]


def get_connection():
    return psycopg2.connect(DATABASE_URL)


def init_db():
    """Initializes tables, ensures constraints, and seeds default room data if empty."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        # Enable the UUID extension in the cloud database first
        cur.execute("CREATE EXTENSION IF NOT EXISTS \"pgcrypto\";")

        # Create tables if not exist
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL,
            email TEXT,
            phone_or_upi TEXT,
            total_xp INTEGER DEFAULT 0,
            current_streak INTEGER DEFAULT 0,
            weekly_budget_limit DOUBLE PRECISION DEFAULT 1000.0,
            remaining_budget DOUBLE PRECISION DEFAULT 1000.0
        );
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL,
            created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now()
        );
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            group_id UUID,
            paid_by UUID,
            total_amount DOUBLE PRECISION NOT NULL,
            description TEXT,
            category TEXT,
            image_url TEXT,
            created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now()
        );
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS splits (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            expense_id UUID,
            owed_by UUID,
            amount DOUBLE PRECISION NOT NULL,
            is_paid BOOLEAN DEFAULT false
        );
        """)

        # Ensure unique group (Fixed tuple indexing)
        cur.execute("SELECT id FROM groups WHERE name = %s LIMIT 1;", ("Room 304",))
        group_row = cur.fetchone()
        if not group_row:
            cur.execute("INSERT INTO groups (name) VALUES (%s) RETURNING id;", ("Room 304",))
            group_id = cur.fetchone()[0]
        else:
            group_id = group_row[0]

        # Seed or update users
        for member in DEFAULT_MEMBERS:
            cur.execute("SELECT id FROM users WHERE name = %s LIMIT 1;", (member["name"],))
            existing = cur.fetchone()
            if not existing:
                cur.execute(
                    """
                    INSERT INTO users (name, email, phone_or_upi, total_xp, current_streak, weekly_budget_limit, remaining_budget)
                    VALUES (%s, %s, %s, %s, %s, %s, %s);
                    """,
                    (
                        member["name"],
                        member["email"],
                        member["phone_or_upi"],
                        member["xp"],
                        member["streak"],
                        member["weekly_budget"],
                        member["remaining"],
                    ),
                )
            else:
                # Update UPI ID and email if missing (Fixed tuple indexing via existing[0])
                cur.execute(
                    """
                    UPDATE users 
                    SET phone_or_upi = COALESCE(phone_or_upi, %s),
                        email = COALESCE(email, %s)
                    WHERE id = %s;
                    """, 
                    (member["phone_or_upi"], member["email"], existing[0])
                )

        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()


def get_user_by_name(name: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT * FROM users WHERE LOWER(name) = LOWER(%s) LIMIT 1;", (name,))
        res = cur.fetchone()
        return dict(res) if res else None
    finally:
        cur.close()
        conn.close()


def get_all_users() -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT * FROM users ORDER BY name ASC;")
        return [dict(r) for r in cur.fetchall()]
    finally:
        cur.close()
        conn.close()


def add_expense_with_splits(
    paid_by_name: str,
    total_amount: float,
    description: str,
    category: str,
    splits: List[Dict[str, Any]],
    group_name: str = "Room 304",
    image_url: Optional[str] = None,
) -> str:
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM groups WHERE name = %s LIMIT 1;", (group_name,))
        grow = cur.fetchone()
        if not grow:
            cur.execute("INSERT INTO groups (name) VALUES (%s) RETURNING id;", (group_name,))
            group_id = cur.fetchone()[0]
        else:
            group_id = grow[0]

        cur.execute("SELECT id FROM users WHERE LOWER(name) = LOWER(%s) LIMIT 1;", (paid_by_name,))
        prow = cur.fetchone()
        if not prow:
            cur.execute("INSERT INTO users (name, phone_or_upi) VALUES (%s, %s) RETURNING id;", (paid_by_name, f"{paid_by_name.lower()}@upi"))
            payer_id = cur.fetchone()[0]
        else:
            payer_id = prow[0]

        cur.execute(
            """
            INSERT INTO expenses (group_id, paid_by, total_amount, description, category, image_url)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING id;
            """,
            (group_id, payer_id, total_amount, description, category, image_url),
        )
        expense_id = cur.fetchone()[0]

        for item in splits:
            friend_name = item["friend_name"]
            amount_owed = float(item["amount_owed"])

            cur.execute("SELECT id FROM users WHERE LOWER(name) = LOWER(%s) LIMIT 1;", (friend_name,))
            urow = cur.fetchone()
            if not urow:
                cur.execute("INSERT INTO users (name, phone_or_upi) VALUES (%s, %s) RETURNING id;", (friend_name, f"{friend_name.lower()}@upi"))
                owed_user_id = cur.fetchone()[0]
            else:
                owed_user_id = urow[0]

            cur.execute(
                """
                INSERT INTO splits (expense_id, owed_by, amount, is_paid)
                VALUES (%s, %s, %s, %s);
                """,
                (expense_id, owed_user_id, amount_owed, False),
            )

        cur.execute("UPDATE users SET remaining_budget = remaining_budget - %s WHERE id = %s;", (total_amount, payer_id))

        conn.commit()
        return str(expense_id)
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()


def get_recent_expenses(limit: int = 10) -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        query = """
        SELECT e.id, e.total_amount as amount, e.description as merchant, e.category,
               e.created_at, u.name as paid_by,
               COUNT(s.id) as split_count
        FROM expenses e
        LEFT JOIN users u ON e.paid_by = u.id
        LEFT JOIN splits s ON e.id = s.expense_id
        GROUP BY e.id, u.name
        ORDER BY e.created_at DESC
        LIMIT %s;
        """
        cur.execute(query, (limit,))
        rows = cur.fetchall()
        results = []
        for r in rows:
            created_str = r["created_at"].strftime("%b %d, %H:%M") if r["created_at"] else "Recently"
            results.append({
                "id": str(r["id"]),
                "merchant": r["merchant"] or "Expense",
                "category": r["category"] or "Other",
                "amount": float(r["amount"]),
                "date": created_str,
                "paidBy": r["paid_by"] or "Roommate",
                "status": "Pending",
                "participants": ["Rahul", "Arjun", "Karan"][:max(1, r["split_count"])],
            })
        return results
    finally:
        cur.close()
        conn.close()


def get_balances_for_user(current_user: str = "Javin") -> Dict[str, float]:
    conn = get_connection()
    cur = conn.cursor()
    balances = {"Rahul": 120.0, "Arjun": 120.0, "Karan": -80.0}
    try:
        cur.execute("SELECT id FROM users WHERE LOWER(name) = LOWER(%s);", (current_user,))
        cu_row = cur.fetchone()
        if not cu_row:
            return balances
        cu_id = cu_row[0]

        cur.execute(
            """
