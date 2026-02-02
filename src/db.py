"""
PostgreSQL Database Connection Utility
Provides connection management for Railway-hosted PostgreSQL database
"""

import os
from contextlib import contextmanager
from typing import Generator
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

load_dotenv()


def get_connection_string() -> str:
    """
    Get PostgreSQL connection string from environment variables.
    """
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return database_url

    host = os.getenv("PGHOST", "localhost")
    port = os.getenv("PGPORT", "5432")
    database = os.getenv("PGDATABASE", "postgres")
    user = os.getenv("PGUSER", "postgres")
    password = os.getenv("PGPASSWORD", "")

    return f"postgresql://{user}:{password}@{host}:{port}/{database}"


def get_connection(
    cursor_factory=RealDictCursor
) -> psycopg2.extensions.connection:
    """
    Create and return a new database connection.

    Args:
        cursor_factory: Cursor factory to use (default: RealDictCursor)

    Returns:
        PostgreSQL connection object
    """
    conn_string = get_connection_string()
    return psycopg2.connect(conn_string, cursor_factory=cursor_factory)


@contextmanager
def get_db_cursor(
    commit: bool = True
) -> Generator[psycopg2.extensions.cursor, None, None]:
    """
    Context manager for database operations with automatic connection handling.

    Args:
        commit: Whether to commit the transaction on success (default: True)

    Yields:
        Database cursor (RealDictCursor)

    Example:
        with get_db_cursor() as cursor:
            cursor.execute("SELECT * FROM rejected_tokens")
            rows = cursor.fetchall()
    """
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        yield cursor
        if commit:
            conn.commit()
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()


def init_rejected_tokens_table():
    """
    Initialize the rejected_tokens table if it doesn't exist.
    """
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS rejected_tokens (
        id SERIAL PRIMARY KEY,
        token_key VARCHAR(255) UNIQUE NOT NULL,
        address VARCHAR(255) NOT NULL,
        chain VARCHAR(50) NOT NULL,
        reason VARCHAR(255) NOT NULL,
        timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        metadata JSONB DEFAULT '{}'::jsonb,
        symbol VARCHAR(50)
    );

    CREATE INDEX IF NOT EXISTS idx_rejected_tokens_chain
        ON rejected_tokens(chain);
    CREATE INDEX IF NOT EXISTS idx_rejected_tokens_timestamp
        ON rejected_tokens(timestamp);
    CREATE INDEX IF NOT EXISTS idx_rejected_tokens_reason
        ON rejected_tokens(reason);
    """

    with get_db_cursor() as cursor:
        cursor.execute(create_table_sql)
    print("✅ rejected_tokens table initialized")


def test_connection() -> bool:
    """
    Test the database connection.

    Returns:
        True if connection successful, False otherwise
    """
    try:
        with get_db_cursor(commit=False) as cursor:
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            return result is not None
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False


def query_rejected_tokens(
    chain: str = None,
    reason: str = None,
    address: str = None,
    limit: int = 50
) -> list:
    """
    Query rejected_tokens table with optional filters.

    Args:
        chain: Filter by chain (e.g., 'solana', 'ethereum')
        reason: Filter by rejection reason
        address: Filter by token address (partial match)
        limit: Maximum number of results (default: 50)

    Returns:
        List of rejected token records
    """
    query = "SELECT * FROM rejected_tokens WHERE 1=1"
    params = []

    if chain:
        query += " AND chain = %s"
        params.append(chain)
    if reason:
        query += " AND reason = %s"
        params.append(reason)
    if address:
        query += " AND address ILIKE %s"
        params.append(f"%{address}%")

    query += " ORDER BY timestamp DESC LIMIT %s"
    params.append(limit)

    with get_db_cursor(commit=False) as cursor:
        cursor.execute(query, params)
        return cursor.fetchall()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Database utility for rejected_tokens")
    parser.add_argument("command", choices=["test", "init", "query", "count"],
                        help="Command to run")
    parser.add_argument("--chain", help="Filter by chain")
    parser.add_argument("--reason", help="Filter by reason")
    parser.add_argument("--address", help="Filter by address (partial match)")
    parser.add_argument("--limit", type=int, default=50, help="Limit results (default: 50)")

    args = parser.parse_args()

    if args.command == "test":
        print("Testing database connection...")
        if test_connection():
            print("Database connection successful")
        else:
            print("Could not connect to database")

    elif args.command == "init":
        print("Initializing rejected_tokens table...")
        init_rejected_tokens_table()

    elif args.command == "query":
        rows = query_rejected_tokens(
            chain=args.chain,
            reason=args.reason,
            address=args.address,
            limit=args.limit
        )
        if not rows:
            print("No results found")
        else:
            for row in rows:
                print(f"{row['timestamp']} | {row['chain']:10} | {row['symbol'] or 'N/A':10} | "
                      f"{row['reason']:20} | {row['address'][:20]}...")

    elif args.command == "count":
        with get_db_cursor(commit=False) as cursor:
            query = "SELECT COUNT(*) as count FROM rejected_tokens WHERE 1=1"
            params = []
            if args.chain:
                query += " AND chain = %s"
                params.append(args.chain)
            if args.reason:
                query += " AND reason = %s"
                params.append(args.reason)
            if args.address:
                query += " AND address ILIKE %s"
                params.append(f"%{args.address}%")
            cursor.execute(query, params)
            result = cursor.fetchone()
            print(f"Total: {result['count']}")
