import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def truncate_tables():
    """Truncate all tables in the correct order to handle foreign key constraints"""
    conn = None
    try:
        print("Connecting to database...")
        conn = psycopg2.connect(
            host=os.getenv('PGHOST'),
            port=os.getenv('PGPORT'),
            user=os.getenv('PGUSER'),
            password=os.getenv('PGPASSWORD'),
            dbname=os.getenv('PGDATABASE')
        )
        
        with conn.cursor() as cur:
            print("Truncating analyses table...")
            cur.execute("TRUNCATE TABLE analyses CASCADE;")
            
            print("Truncating tokens table...")
            cur.execute("TRUNCATE TABLE tokens CASCADE;")
            
            conn.commit()
            print("Successfully truncated all tables")
            
    except Exception as e:
        print(f"Error truncating tables: {str(e)}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    confirm = input("This will delete ALL data from the database. Are you sure? (y/N): ")
    if confirm.lower() == 'y':
        truncate_tables()
    else:
        print("Operation cancelled") 
