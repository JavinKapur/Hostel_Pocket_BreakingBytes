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
