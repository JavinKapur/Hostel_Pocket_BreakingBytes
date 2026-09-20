import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

# Fetch the variable from Render
DATABASE_URL = os.getenv("DATABASE_URL")

def get_connection():
    """Returns a direct psycopg2 connection to PostgreSQL."""
    if DATABASE_URL:
        cleaned_url = DATABASE_URL
        # Render uses 'postgres://', but psycopg2 needs 'postgresql://'
        if cleaned_url.startswith("postgres://"):
            cleaned_url = cleaned_url.replace("postgres://", "postgresql://", 1)
            
        return psycopg2.connect(cleaned_url)
    else:
        # Local fallback string when running on your computer
        local_dsn = "dbname=postgres user=postgres password=BreakingBytes345 host=localhost port=54321"
        return psycopg2.connect(local_dsn)

def get_cursor(conn, dict_cursor=True):
    """Returns a cursor, defaulting to RealDictCursor for clean dictionary access."""
    if dict_cursor:
        return conn.cursor(cursor_factory=RealDictCursor)
    return conn.cursor()
