"""
Database connection configuration for WinCC OA PostgreSQL historian.
"""

import psycopg2

DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 5432,
    "database": "postgres",       # change to your WinCC OA database name
    "user": "postgres",
    "password": "changeme",       # change to your actual password
}


def get_connection():
    """Return a new psycopg2 connection using DB_CONFIG.

    Raises psycopg2.OperationalError with a clear message on failure.
    """
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except psycopg2.OperationalError as e:
        print(f"[ERROR] Failed to connect to database "
              f"({DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}): {e}")
        raise
