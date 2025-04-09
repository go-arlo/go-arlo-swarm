import os
import psycopg2
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

def init_db():
    """Initialize database with schema"""
    conn = None
    try:
        print(f"Connecting to database...")
        conn = psycopg2.connect(
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
        
        schema_path = Path(__file__).parent / 'schema.sql'
        with open(schema_path, 'r') as f:
            schema = f.read()
            
        print(f"Executing schema...")
        with conn.cursor() as cur:
            cur.execute(schema)
        conn.commit()
        print("Database initialized successfully")
        
    except Exception as e:
        print(f"Error initializing database: {str(e)}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    init_db()
