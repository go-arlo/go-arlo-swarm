import os
import sys
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def get_db_connection():
    """Create database connection from environment variables"""
    try:
        return psycopg2.connect(
            host=os.getenv('PGHOST'),
            port=os.getenv('PGPORT'),
            user=os.getenv('PGUSER'),
            password=os.getenv('PGPASSWORD'),
            dbname=os.getenv('PGDATABASE'),
            keepalives=1,
            keepalives_idle=30,
            keepalives_interval=10,
            keepalives_count=5,
            connect_timeout=10
        )
    except psycopg2.Error as e:
        print(f"Database connection error: {e}")
        raise

def run_migrations():
    """Run all database migrations"""
    conn = None
    try:
        print("Starting database migrations...")
        print(f"Connecting to database at {os.getenv('PGHOST')}:{os.getenv('PGPORT')}...")
        
        conn = get_db_connection()
        
        with conn.cursor() as cur:
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'analyses'
                )
            """)
            table_exists = cur.fetchone()[0]
            
            if not table_exists:
                print("Analyses table does not exist. Please run the initial schema setup first.")
                return False
            
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'analyses' AND column_name = 'captain_summary'
            """)
            has_captain_summary = bool(cur.fetchone())
            
            if not has_captain_summary:
                print("Adding captain_summary column to analyses table...")
                cur.execute("""
                    ALTER TABLE analyses
                    ADD COLUMN captain_summary TEXT
                """)
                conn.commit()
                print("captain_summary column added successfully")
            else:
                print("captain_summary column already exists")
            
        print("All migrations completed successfully")
        return True
    except Exception as e:
        print(f"Error running migrations: {str(e)}")
        return False
    finally:
        if conn:
            conn.close()

def main():
    """Main function to run migrations from command line"""
    print(f"Database host: {os.getenv('PGHOST')}")
    print(f"Database port: {os.getenv('PGPORT')}")
    print(f"Database name: {os.getenv('PGDATABASE')}")
    print(f"Database user: {os.getenv('PGUSER')}")
    
    success = run_migrations()
    
    if success:
        print("Migrations completed successfully")
        sys.exit(0)
    else:
        print("Migrations failed")
        sys.exit(1)

if __name__ == "__main__":
    main() 
