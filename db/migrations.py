import hashlib
import datetime
from db.connection import get_connection

DEFAULT_CATEGORIES = [
    ("food", "Food", "utensils"),
    ("hostel", "Hostel", "home"),
    ("travel", "Travel", "bus"),
    ("shopping", "Shopping", "shopping-bag"),
    ("entertainment", "Entertainment", "film"),
    ("education", "Education", "book"),
    ("utilities", "Utilities", "zap"),
    ("other", "Other", "tag"),
]

def hash_password(password: str) -> str:
    salt = "hostelpocket_student_salt_2026"
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()

def run_migrations():
    """Migrates schema safely adhering to SDD Section 4, 5, and 12."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("CREATE EXTENSION IF NOT EXISTS \"pgcrypto\";")

        # 1. users table evolution
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email TEXT UNIQUE,
            password_hash TEXT,
            display_name TEXT,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        );
        """)
        # Add new columns if missing from earlier prototype
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS email TEXT;")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT;")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS display_name TEXT;")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT now();")

        # Ensure Javin exists with valid credentials
        cur.execute("SELECT id FROM users WHERE LOWER(email) = 'javin.student@gmail.com' OR LOWER(name) = 'javin' LIMIT 1;")
        javin_row = cur.fetchone()
        if javin_row:
            javin_id = javin_row[0]
            cur.execute("""
            UPDATE users
            SET email = 'javin.student@gmail.com',
                password_hash = %s,
                display_name = 'Javin'
            WHERE id = %s;
            """, (hash_password("student123"), javin_id))
        else:
            cur.execute("""
            INSERT INTO users (email, password_hash, display_name)
            VALUES ('javin.student@gmail.com', %s, 'Javin')
            RETURNING id;
            """, (hash_password("student123"),))
            javin_id = cur.fetchone()[0]

        # Ensure unique constraint on email
        cur.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'users_email_key') THEN
                ALTER TABLE users ADD CONSTRAINT users_email_key UNIQUE (email);
            END IF;
        END $$;
        """)

        # 2. categories
        cur.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            icon_key TEXT,
            is_active BOOLEAN DEFAULT true
        );
        """)

        for code, name, icon in DEFAULT_CATEGORIES:
            cur.execute("""
            INSERT INTO categories (code, name, icon_key, is_active)
            VALUES (%s, %s, %s, true)
            ON CONFLICT (code) DO NOTHING;
            """, (code, name, icon))

        # 3. friends (Replaces roommates per REQ-01 / AC-01)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS friends (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            sample_upi_id TEXT,
            note TEXT,
            created_at TIMESTAMPTZ DEFAULT now(),
            archived_at TIMESTAMPTZ NULL
        );
        """)

        # Seed initial friends for Javin (Aman, Riya, Rahul, Arjun) per SDD Appendix B
        sample_friends = [
            ("Aman", "aman.sharma@okhdfcbank", "Campus study group"),
            ("Riya", "riya.patel@icici", "Hostel wing friend"),
            ("Rahul", "rahul99@paytm", "Canteen meals"),
            ("Arjun", "arjun.v@axisbank", "Project partner"),
        ]
        for f_name, f_upi, f_note in sample_friends:
            cur.execute("SELECT id FROM friends WHERE user_id = %s AND name = %s;", (javin_id, f_name))
            if not cur.fetchone():
                cur.execute("""
                INSERT INTO friends (user_id, name, sample_upi_id, note)
                VALUES (%s, %s, %s, %s);
                """, (javin_id, f_name, f_upi, f_note))

        # 4. expenses table evolution
        # Add columns needed by target SDD
        cur.execute("ALTER TABLE expenses ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES users(id) ON DELETE CASCADE;")
        cur.execute("ALTER TABLE expenses ADD COLUMN IF NOT EXISTS friend_id UUID REFERENCES friends(id) ON DELETE SET NULL;")
        cur.execute("ALTER TABLE expenses ADD COLUMN IF NOT EXISTS category_id UUID REFERENCES categories(id);")
        cur.execute("ALTER TABLE expenses ADD COLUMN IF NOT EXISTS title TEXT;")
        cur.execute("ALTER TABLE expenses ADD COLUMN IF NOT EXISTS amount NUMERIC(12,2);")
        cur.execute("ALTER TABLE expenses ADD COLUMN IF NOT EXISTS expense_date DATE;")
        cur.execute("ALTER TABLE expenses ADD COLUMN IF NOT EXISTS note TEXT;")
        cur.execute("ALTER TABLE expenses ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT now();")
        cur.execute("ALTER TABLE expenses ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ NULL;")

        # Backfill existing expenses if present
        cur.execute("""
        UPDATE expenses
        SET user_id = COALESCE(user_id, paid_by, %s),
            title = COALESCE(title, description, 'Expense'),
            amount = COALESCE(amount, total_amount::numeric, 100.00),
            expense_date = COALESCE(expense_date, created_at::date, CURRENT_DATE)
        WHERE user_id IS NULL OR title IS NULL OR amount IS NULL OR expense_date IS NULL;
        """, (javin_id,))

        # Map string category to category_id if null
        cur.execute("""
        UPDATE expenses e
        SET category_id = c.id
        FROM categories c
        WHERE e.category_id IS NULL AND LOWER(e.category) = LOWER(c.name);
        """)
        # Fallback category to 'other'
        cur.execute("""
        UPDATE expenses
        SET category_id = (SELECT id FROM categories WHERE code = 'other' LIMIT 1)
        WHERE category_id IS NULL;
        """)

        # 5. expense_items
        cur.execute("""
        CREATE TABLE IF NOT EXISTS expense_items (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            expense_id UUID NOT NULL REFERENCES expenses(id) ON DELETE CASCADE,
            item_name TEXT NOT NULL,
            quantity NUMERIC(10,2) DEFAULT 1.0 CHECK (quantity >= 0),
            unit_price NUMERIC(12,2) DEFAULT 0.0 CHECK (unit_price >= 0),
            line_total NUMERIC(12,2) NOT NULL CHECK (line_total >= 0),
            sort_order INT DEFAULT 0
        );
        """)

        # Backfill unitemized items for older expenses per Section 12 rule
        cur.execute("""
        INSERT INTO expense_items (expense_id, item_name, quantity, unit_price, line_total, sort_order)
        SELECT e.id, 'Unitemized expense', 1.0, e.amount, e.amount, 0
        FROM expenses e
        WHERE NOT EXISTS (SELECT 1 FROM expense_items ei WHERE ei.expense_id = e.id);
        """)

        # 6. expense_attachments (merged receipt + screenshot banner per REQ-03)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS expense_attachments (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            expense_id UUID NOT NULL REFERENCES expenses(id) ON DELETE CASCADE,
            file_name TEXT NOT NULL,
            mime_type TEXT,
            storage_key TEXT,
            checksum TEXT,
            created_at TIMESTAMPTZ DEFAULT now()
        );
        """)

        # 7. budgets (daily & monthly per REQ-06)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS budgets (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            period_type VARCHAR(10) NOT NULL CHECK (period_type IN ('day', 'month')),
            period_start DATE NOT NULL,
            amount NUMERIC(12,2) NOT NULL CHECK (amount >= 0),
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now(),
            CONSTRAINT uq_user_period UNIQUE (user_id, period_type, period_start)
        );
        """)

        today = datetime.date.today()
        month_start = today.replace(day=1)

        cur.execute("""
        INSERT INTO budgets (user_id, period_type, period_start, amount)
        VALUES (%s, 'day', %s, 500.00)
        ON CONFLICT (user_id, period_type, period_start) DO NOTHING;
        """, (javin_id, today))

        cur.execute("""
        INSERT INTO budgets (user_id, period_type, period_start, amount)
        VALUES (%s, 'month', %s, 10000.00)
        ON CONFLICT (user_id, period_type, period_start) DO NOTHING;
        """, (javin_id, month_start))

        # 8. timeline_events (append-only audit feed per REQ-08)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS timeline_events (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            event_type TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id UUID,
            occurred_at TIMESTAMPTZ DEFAULT now(),
            payload JSONB DEFAULT '{}'::jsonb,
            correlation_id TEXT
        );
        """)

        # 9. reminders (persisted & dismissible per REQ-07 / FR-12)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            reminder_type TEXT NOT NULL,
            due_at TIMESTAMPTZ,
            title TEXT NOT NULL,
            body TEXT,
            entity_type TEXT,
            entity_id UUID,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMPTZ DEFAULT now(),
            dismissed_at TIMESTAMPTZ NULL
        );
        """)

        # 10. ai_insights (persisted snapshots per REQ-07 / FR-11)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS ai_insights (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            generated_at TIMESTAMPTZ DEFAULT now(),
            window_start DATE,
            window_end DATE,
            insight_type TEXT,
            title TEXT NOT NULL,
            body TEXT,
            severity TEXT DEFAULT 'info',
            data JSONB DEFAULT '{}'::jsonb,
            expires_at TIMESTAMPTZ
        );
        """)

        # 11. auth_sessions
        cur.execute("""
        CREATE TABLE IF NOT EXISTS auth_sessions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            expires_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now(),
            revoked_at TIMESTAMPTZ NULL
        );
        """)

        # Indexes from SDD Section 4.2
        cur.execute("CREATE INDEX IF NOT EXISTS idx_expenses_user_date ON expenses(user_id, expense_date DESC);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_expenses_user_category_date ON expenses(user_id, category_id, expense_date DESC);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_items_expense ON expense_items(expense_id, sort_order);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_timeline_user_time ON timeline_events(user_id, occurred_at DESC);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_timeline_entity ON timeline_events(entity_type, entity_id, occurred_at DESC);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_reminders_user_due ON reminders(user_id, status, due_at);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_insights_user_generated ON ai_insights(user_id, generated_at DESC);")

        conn.commit()
        print("All SDD migrations completed cleanly and backward-compatible.")
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    run_migrations()
