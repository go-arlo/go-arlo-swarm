from agency_swarm.tools import BaseTool
from pydantic import Field, field_validator
from typing import Dict, Any, List
from ...database.db import save_analysis
from datetime import datetime
from collections import OrderedDict
import json
import logging
import re
import traceback

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("DatabaseWriter")


class DatabaseWriter(BaseTool):
    """
    Tool for writing analysis reports to PostgreSQL database.
    Expects a single report data argument in the exact format required by the schema.
    """

    report_data: Dict[str, Any] = Field(
        ...,
        description="Complete analysis report in database format, including metadata like ticker, address, and chain."
    )

    def __init__(self, **kwargs):
        """Initialize the DatabaseWriter with custom handling for JSON strings."""
        logger.info(f"DatabaseWriter initialized with kwargs keys: {list(kwargs.keys())}")
        
        if not kwargs or (len(kwargs) == 1 and 'report_data' in kwargs and not kwargs['report_data']):
            logger.error("Empty or missing report_data in DatabaseWriter initialization")
            raise ValueError("Report data cannot be empty")
            
        if 'report_data' in kwargs:
            try:
                if isinstance(kwargs['report_data'], str):
                    try:
                        kwargs['report_data'] = json.loads(kwargs['report_data'])
                    except json.JSONDecodeError:
                        match = re.search(r'({.*})', kwargs['report_data'])
                        if match:
                            kwargs['report_data'] = json.loads(match.group(1))
                        else:
                            raise ValueError("Could not parse report data JSON")
                
                if isinstance(kwargs['report_data'], dict) and 'report_data' in kwargs['report_data']:
                    kwargs['report_data'] = kwargs['report_data']['report_data']
                
                if not isinstance(kwargs['report_data'], dict):
                    raise ValueError("Report data must be a dictionary")
                
                required_fields = [
                    "final_score", "token_ticker", "contract_address", "chain",
                    "token_safety", "market_position", "social_sentiment",
                    "holder_analysis", "captain_summary"
                ]
                
                missing_fields = [field for field in required_fields if field not in kwargs['report_data']]
                if missing_fields:
                    raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")
                
                if isinstance(kwargs['report_data']['final_score'], str):
                    try:
                        kwargs['report_data']['final_score'] = float(kwargs['report_data']['final_score'])
                    except ValueError:
                        raise ValueError(f"Invalid final_score format: {kwargs['report_data']['final_score']}")
                
            except Exception as e:
                logger.error(f"Error processing report data: {str(e)}")
                logger.error(traceback.format_exc())
                raise ValueError(f"Invalid report data format: {str(e)}")
        
        super().__init__(**kwargs)
        
        if hasattr(self, 'report_data') and isinstance(self.report_data, dict):
            logger.info("Sanitizing strings in report_data")
            self._sanitize_strings(self.report_data)

    def run(self):
        """Write analysis to the database with ordered fields."""
        try:
            logger.info(f"Preparing to save analysis for {self.report_data.get('token_ticker', 'unknown token')}")
            
            report_data = dict(self.report_data)
            
            if "timestamp" in report_data:
                report_data.pop("timestamp")
            
            ordered_data = OrderedDict([
                ("token_ticker", report_data["token_ticker"]),
                ("contract_address", report_data["contract_address"]),
                ("chain", report_data["chain"]),
                ("final_score", float(report_data["final_score"])),
                ("token_safety", report_data["token_safety"]),
                ("social_sentiment", report_data["social_sentiment"]),
                ("holder_analysis", report_data["holder_analysis"]),
                ("market_position", report_data["market_position"]),
                ("captain_summary", report_data["captain_summary"])
            ])

            if len(ordered_data["captain_summary"]) > 4000:
                ordered_data["captain_summary"] = ordered_data["captain_summary"][:4000] + "... (truncated)"

            logger.info("Saving analysis to database")
            success = save_analysis(ordered_data)
            
            if success:
                logger.info(f"Successfully saved analysis for {report_data['token_ticker']}")
                return {
                    "status": "success",
                    "message": f"Analysis saved for {report_data['token_ticker']} ({report_data['contract_address']})"
                }
            else:
                logger.error("Failed to save analysis to database")
                return {
                    "status": "error",
                    "message": "Failed to save analysis to database."
                }

        except Exception as e:
            logger.error(f"Error in DatabaseWriter.run: {str(e)}")
            logger.error(traceback.format_exc())
            return {
                "status": "error",
                "message": f"Error saving to database: {str(e)}"
            }
    
    def _sanitize_strings(self, data):
        """Recursively sanitize all string values in the data structure."""
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, str):
                    data[key] = value.replace("\u0000", "")
                elif isinstance(value, (dict, list)):
                    self._sanitize_strings(value)
        elif isinstance(data, list):
            for i, item in enumerate(data):
                if isinstance(item, str):
                    data[i] = item.replace("\u0000", "")
                elif isinstance(item, (dict, list)):
                    self._sanitize_strings(item)


def validate_category_structure(category_data: Dict[str, Any]) -> bool:
    """Validate category data structure"""
    if not isinstance(category_data, dict):
        return False
        
    required_fields = ["assessment", "summary", "key_points"]
    if not all(field in category_data for field in required_fields):
        return False
        
    if category_data["assessment"] not in ["positive", "neutral", "negative"]:
        return False
        
    if not isinstance(category_data["key_points"], list):
        return False
        
    return True

def validate_unique_content(report_data):
    """Validate that each category has unique content"""
    categories = [
        "token_safety",
        "liquidity_check",
        "social_sentiment",
        "holder_analysis",
        "market_position"
    ]
    
    summaries = set()
    all_key_points = set()
    
    for category in categories:
        if category in report_data:
            summary = report_data[category]["summary"]
            if summary in summaries:
                logger.warning(f"Duplicate summary found in {category}")
                return False
            summaries.add(summary)
            
            key_points = tuple(report_data[category]["key_points"])
            if key_points in all_key_points:
                logger.warning(f"Duplicate key points found in {category}")
                return False
            all_key_points.add(key_points)
    
    return True

def write_to_database(arguments):
    """Write report to database with validation"""
    try:
        report_data = arguments.get("report_data")
        
        if not validate_unique_content(report_data):
            return {
                "success": False,
                "error": "Duplicate content found across categories"
            }
            
        success = save_analysis(report_data)
        return {
            "success": success,
            "message": "Report saved successfully" if success else "Failed to save report"
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }
