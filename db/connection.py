import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

# Fetch the raw database URL provided by Render
RAW_DATABASE_URL = os.getenv("DATABASE_URL")

if RAW_DATABASE_URL:
    # Automatically fix the format mismatch (postgres:// vs postgresql://)
    if RAW_DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = RAW_DATABASE_URL.replace("postgres://", "postgresql://", 1)
    else:
        DATABASE_URL = RAW_DATABASE_URL
else:
    # Local fallback for offline testing on your computer
    DATABASE_URL = "dbname=postgres user=postgres password=BreakingBytes345 host=localhost port=54321"

def get_connection():
    """Returns a direct psycopg2 connection to the active database context."""
    return psycopg2.connect(DATABASE_URL)

def get_cursor(conn, dict_cursor=True):
    """Returns a cursor, defaulting to RealDictCursor for clean dictionary access."""
    if dict_cursor:
        return conn.cursor(cursor_factory=RealDictCursor)
    return conn.cursor()

def verify_and_build_tables():
    """Guarantees all database tables exist immediately upon application startup."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        # 1. Enable UUID capabilities
        cur.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto";')
        
        # 2. Create the core tables sequentially
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
        
        # 3. Seed default admin if user table is completely empty
        cur.execute("SELECT COUNT(*) FROM users;")
        if cur.fetchone()[0] == 0:
            cur.execute("""
            INSERT INTO users (name, email, phone_or_upi, weekly_budget_limit, remaining_budget)
            VALUES ('Javin', 'javin.student@gmail.com', 'javin@okaxis', 6000.0, 4230.0);
            """)
            
        conn.commit()
        print("[Database Startup] Tables verified and ready.")
    except Exception as e:
        conn.rollback()
        print(f"[Database Startup Error] Initialization failed: {e}")
    finally:
        cur.close()
        conn.close()

# Execute table initialization automatically when Streamlit loads this file
verify_and_build_tables()
