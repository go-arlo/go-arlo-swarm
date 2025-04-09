import os
import psycopg2
from psycopg2.extras import Json, DictCursor
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
import json

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

def save_token(token_data: Dict[str, Any]) -> bool:
    """Save token information to database"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                print(f"Attempting to save token: {token_data['contract_address']}")
                cur.execute("""
                    INSERT INTO tokens (contract_address, name, ticker)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (contract_address) 
                    DO UPDATE SET 
                        name = EXCLUDED.name,
                        ticker = EXCLUDED.ticker
                    RETURNING contract_address
                """, (token_data['contract_address'], token_data['name'], token_data['ticker']))
                conn.commit()
                result = cur.fetchone()
                print(f"Token save result: {result}")
                return bool(result)
    except Exception as e:
        print(f"Error saving token: {str(e)}")
        return False

def save_analysis(report_data: Dict[str, Any]) -> bool:
    """Save analysis to database"""
    try:
        print(f"Attempting to save analysis for: {report_data.get('contract_address', 'unknown')}")
        print(f"Report data keys: {list(report_data.keys())}")
        
        required_fields = ['contract_address', 'token_ticker', 'chain', 'final_score', 
                          'token_safety', 'market_position', 'social_sentiment', 'holder_analysis']
        
        missing_fields = [field for field in required_fields if field not in report_data]
        if missing_fields:
            print(f"Error: Missing required fields: {missing_fields}")
            return False
            
        if not isinstance(report_data['contract_address'], str):
            print(f"Error: contract_address must be a string, got {type(report_data['contract_address'])}")
            return False
            
        if not isinstance(report_data['token_ticker'], str):
            print(f"Error: token_ticker must be a string, got {type(report_data['token_ticker'])}")
            return False
            
        if not isinstance(report_data['final_score'], (int, float)):
            try:
                report_data['final_score'] = float(report_data['final_score']) 
                print(f"Converted final_score to float: {report_data['final_score']}")
            except (ValueError, TypeError):
                print(f"Error: final_score must be a number, got {type(report_data['final_score'])}: {report_data['final_score']}")
                return False
                
        for field in ['token_safety', 'market_position', 'social_sentiment', 'holder_analysis']:
            if not isinstance(report_data[field], dict):
                print(f"Error: {field} must be a dictionary, got {type(report_data[field])}")
                return False
                
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                try:
                    cur.execute("""
                        INSERT INTO tokens (contract_address, name, ticker)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (contract_address) DO NOTHING
                    """, (
                        report_data['contract_address'],
                        report_data['token_ticker'],
                        report_data['token_ticker']
                    ))
                except Exception as e:
                    print(f"Error inserting token: {str(e)}")
                    raise

                if 'captain_summary' not in report_data or not report_data['captain_summary']:
                    report_data['captain_summary'] = f"Captain's Log: Analysis completed for {report_data['token_ticker']}."
                elif not isinstance(report_data['captain_summary'], str):
                    print(f"Warning: captain_summary is not a string, converting from {type(report_data['captain_summary'])}")
                    report_data['captain_summary'] = str(report_data['captain_summary'])
                
                token_safety = report_data['token_safety']
                market_position = report_data['market_position']
                social_sentiment = report_data['social_sentiment']
                holder_analysis = report_data['holder_analysis']
                
                print(f"Captain summary length: {len(report_data['captain_summary'])}")
                
                try:
                    cur.execute("""
                        INSERT INTO analyses (
                            contract_address, token_ticker, chain, final_score,
                            token_safety, market_position, social_sentiment, holder_analysis,
                            captain_summary, created_at, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                        ON CONFLICT (contract_address) 
                        DO UPDATE SET 
                            token_ticker = EXCLUDED.token_ticker,
                            chain = EXCLUDED.chain,
                            final_score = EXCLUDED.final_score,
                            token_safety = EXCLUDED.token_safety,
                            market_position = EXCLUDED.market_position,
                            social_sentiment = EXCLUDED.social_sentiment,
                            holder_analysis = EXCLUDED.holder_analysis,
                            captain_summary = EXCLUDED.captain_summary,
                            updated_at = CURRENT_TIMESTAMP
                    """, (
                        report_data['contract_address'],
                        report_data['token_ticker'],
                        report_data['chain'],
                        report_data['final_score'],
                        Json(token_safety),
                        Json(market_position),
                        Json(social_sentiment),
                        Json(holder_analysis),
                        report_data['captain_summary']
                    ))
                except Exception as e:
                    print(f"Error inserting analysis: {str(e)}")
                    print(f"Final score type: {type(report_data['final_score'])}, value: {report_data['final_score']}")
                    raise

                try:
                    cur.execute("""
                        UPDATE tokens 
                        SET analysis_exists = true 
                        WHERE contract_address = %s
                    """, (report_data['contract_address'],))
                except Exception as e:
                    print(f"Error updating token analysis_exists: {str(e)}")
                    raise
                
                conn.commit()
                print(f"Analysis saved successfully for {report_data['contract_address']}")
                return True
                
    except Exception as e:
        import traceback
        print(f"Error saving analysis: {str(e)}")
        print(traceback.format_exc())
        return False

def get_analysis(contract_address: str) -> Optional[Dict[str, Any]]:
    """Retrieve analysis from database"""
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cur:
                cur.execute("""
                    SELECT * FROM analyses 
                    WHERE contract_address = %s
                """, (contract_address,))
                result = cur.fetchone()
                
                if result:
                    if result['updated_at'] and not result['updated_at'].tzinfo:
                        result['updated_at'] = result['updated_at'].replace(tzinfo=timezone.utc)
                    return dict(result)
                return None
    except Exception as e:
        print(f"Error retrieving analysis: {str(e)}")
        return None

def get_token(contract_address: str) -> Optional[Dict[str, Any]]:
    """Retrieve token from database"""
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cur:
                cur.execute("""
                    SELECT * FROM tokens 
                    WHERE contract_address = %s
                """, (contract_address,))
                result = cur.fetchone()
                
                if result:
                    return dict(result)
                return None
    except Exception as e:
        print(f"Error retrieving token: {str(e)}")
        return None

def get_all_tokens() -> List[Dict[str, Any]]:
    """Retrieve all tokens from database"""
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cur:
                cur.execute("SELECT * FROM tokens ORDER BY created_at DESC")
                return [dict(row) for row in cur.fetchall()]
    except Exception as e:
        print(f"Error retrieving tokens: {str(e)}")
        return []

def token_exists(contract_address: str) -> bool:
    """Check if token exists in database"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT EXISTS(
                        SELECT 1 FROM tokens WHERE contract_address = %s
                    )
                """, (contract_address,))
                return cur.fetchone()[0]
    except Exception as e:
        print(f"Error checking token existence: {str(e)}")
        return False

def get_all_analyses(limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
    """
    Retrieve all analyses from database with pagination
    
    Args:
        limit (int): Maximum number of records to return (default: 100)
        offset (int): Number of records to skip (default: 0)
        
    Returns:
        List[Dict[str, Any]]: List of analysis records
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cur:
                cur.execute("""
                    SELECT 
                        contract_address,
                        token_ticker,
                        chain,
                        final_score,
                        updated_at
                    FROM analyses 
                    ORDER BY final_score DESC
                    LIMIT %s OFFSET %s
                """, (limit, offset))
                
                results = []
                for row in cur.fetchall():
                    if row['updated_at'] and not row['updated_at'].tzinfo:
                        row['updated_at'] = row['updated_at'].replace(tzinfo=timezone.utc)
                    results.append(dict(row))
                return results
                
    except Exception as e:
        print(f"Error retrieving analyses: {str(e)}")
        return [] 
