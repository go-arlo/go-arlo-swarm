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
            kwargs['report_data'] = {}
            super().__init__(**kwargs)
            return
            
        if 'report_data' in kwargs and isinstance(kwargs['report_data'], str):
            try:
                preview = kwargs['report_data'][:100] + "..." if len(kwargs['report_data']) > 100 else kwargs['report_data']
                logger.info(f"Received report_data as string, preview: {preview}")
                
                if kwargs['report_data'].startswith('"') and kwargs['report_data'].endswith('"'):
                    try:
                        unescaped = json.loads(kwargs['report_data'])
                        logger.info("Unescaped double-quoted JSON string")
                        kwargs['report_data'] = unescaped
                    except:
                        pass
                
                parsed_data = self._parse_json_with_multiple_approaches(kwargs['report_data'])
                
                if isinstance(parsed_data, dict) and 'report_data' in parsed_data:
                    logger.info("Found nested report_data structure, extracting inner data")
                    parsed_data = parsed_data['report_data']
                
                kwargs['report_data'] = parsed_data
                
            except Exception as e:
                logger.error(f"All JSON parsing methods failed: {str(e)}")
                logger.error(traceback.format_exc())
                raise ValueError(f"Failed to parse JSON: {str(e)}")
        
        super().__init__(**kwargs)
        
        if hasattr(self, 'report_data') and isinstance(self.report_data, dict):
            logger.info("Sanitizing strings in report_data")
            self._sanitize_strings(self.report_data)

    def _parse_json_with_multiple_approaches(self, json_str):
        """Try multiple approaches to parse the JSON string."""
        approaches = [
            self._standard_parse,
            self._extract_at_error_position,
            self._brute_force_extract,
            self._clean_and_parse,
            self._find_valid_json_object
        ]
        
        last_error = None
        for i, approach in enumerate(approaches):
            try:
                logger.info(f"Trying JSON parsing approach #{i+1}")
                parsed_data = approach(json_str)
                logger.info(f"Successfully parsed JSON using approach #{i+1}")
                return parsed_data
            except Exception as e:
                logger.warning(f"Approach #{i+1} failed: {str(e)}")
                last_error = e
        
        raise ValueError(f"All JSON parsing approaches failed. Last error: {str(last_error)}")
    
    def _standard_parse(self, json_str):
        """Standard JSON parsing approach."""
        return json.loads(json_str)
    
    def _extract_at_error_position(self, json_str):
        """Extract valid JSON by truncating at the error position."""
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            error_msg = str(e)
            if "Extra data" in error_msg:
                # Find the position where the valid JSON ends
                pos = int(re.search(r'char (\d+)', error_msg).group(1))
                logger.info(f"Found Extra data error, extracting JSON up to position {pos}")
                return json.loads(json_str[:pos])
            raise
    
    def _brute_force_extract(self, json_str):
        """Brute force approach: find the last valid closing brace."""
        last_brace_pos = json_str.rindex('}')
        if last_brace_pos > 0:
            truncated_json = json_str[:last_brace_pos+1]
            return json.loads(truncated_json)
        raise ValueError("Could not find valid JSON structure")
    
    def _clean_and_parse(self, json_str):
        """Clean the JSON string and try to parse it."""
        match = re.search(r'(.*}})', json_str)
        if match:
            cleaned_json = match.group(1)
            logger.info(f"Extracted JSON up to last '}}' pattern")
            return json.loads(cleaned_json)
        raise ValueError("Could not find valid JSON ending")
    
    def _find_valid_json_object(self, json_str):
        """Try to find a valid JSON object in the string."""
        match = re.search(r'({.*})', json_str)
        if match:
            potential_json = match.group(1)
            return json.loads(potential_json)
        raise ValueError("Could not find valid JSON pattern")

    @field_validator('report_data')
    def validate_report(cls, v):
        """Validate report data structure matches database schema."""
        if not isinstance(v, dict):
            logger.error("Report data must be a dictionary")
            raise ValueError("Report data must be a dictionary.")
            
        if not v:
            logger.error("Empty report_data provided")
            raise ValueError("Report data cannot be empty.")

        required_fields = [
            "final_score",
            "token_ticker",
            "contract_address",
            "chain",
            "token_safety",
            "social_sentiment",
            "holder_analysis",
            "market_position",
            "captain_summary"
        ]

        missing = [field for field in required_fields if field not in v]
        if missing:
            logger.error(f"Missing required fields: {', '.join(missing)}")
            raise ValueError(f"Missing required fields: {', '.join(missing)}")

        categories = ["token_safety", "social_sentiment", "holder_analysis", "market_position"]
        for category in categories:
            if not validate_category_structure(v.get(category, {})):
                logger.error(f"Invalid {category} structure")
                raise ValueError(f"Invalid {category} structure")

        logger.info("Report data validation successful")
        return v

    def run(self):
        """Write analysis to the database with ordered fields."""
        try:
            logger.info(f"Preparing to save analysis for {self.report_data.get('token_ticker', 'unknown token')}")
            
            report_data = dict(self.report_data)
            
            logger.info(f"Report data keys: {list(report_data.keys())}")
            logger.info(f"Token ticker: {report_data.get('token_ticker')}")
            logger.info(f"Contract address: {report_data.get('contract_address')}")
            logger.info(f"Final score: {report_data.get('final_score')}")
            
            missing_fields = []
            for field in ["token_ticker", "contract_address", "chain", "final_score", "token_safety", 
                         "social_sentiment", "holder_analysis", "market_position", "captain_summary"]:
                if field not in report_data or report_data[field] is None:
                    missing_fields.append(field)
                    
            if missing_fields:
                logger.error(f"Missing required fields in report data: {missing_fields}")
                return {
                    "status": "error",
                    "message": f"Missing required fields: {', '.join(missing_fields)}"
                }
            
            self._sanitize_strings(report_data)
            
            if "captain_summary" in report_data and isinstance(report_data["captain_summary"], str):
                if len(report_data["captain_summary"]) > 4000:
                    report_data["captain_summary"] = report_data["captain_summary"][:4000] + "... (truncated)"
                    logger.info(f"Truncated captain_summary to 4000 characters")
            
            if "timestamp" in report_data:
                report_data.pop("timestamp")
            
            ordered_data = OrderedDict([
                ("token_ticker", report_data["token_ticker"]),
                ("contract_address", report_data["contract_address"]),
                ("chain", report_data["chain"]),
                ("final_score", report_data["final_score"]),
                ("token_safety", report_data["token_safety"]),
                ("social_sentiment", report_data["social_sentiment"]),
                ("holder_analysis", report_data["holder_analysis"]),
                ("market_position", report_data["market_position"]),
                ("captain_summary", report_data["captain_summary"])
            ])

            logger.info(f"Final score type: {type(report_data['final_score'])}")
            logger.info(f"Token safety type: {type(report_data['token_safety'])}")
            
            if isinstance(ordered_data["final_score"], str):
                try:
                    ordered_data["final_score"] = float(ordered_data["final_score"])
                    logger.info(f"Converted final_score from string to float: {ordered_data['final_score']}")
                except ValueError:
                    logger.error(f"Could not convert final_score to number: {ordered_data['final_score']}")
                    return {
                        "status": "error",
                        "message": f"Invalid final_score format: {ordered_data['final_score']}"
                    }

            logger.info("Saving analysis to database")
            try:
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
            except Exception as db_error:
                logger.error(f"Database error: {str(db_error)}")
                logger.error(traceback.format_exc())
                
                import psycopg2
                if isinstance(db_error, psycopg2.Error):
                    logger.error(f"PostgreSQL error code: {db_error.pgcode}")
                    logger.error(f"PostgreSQL error message: {db_error.pgerror}")
                
                return {
                    "status": "error",
                    "message": f"Database error: {str(db_error)}"
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
                    original_len = len(value)
                    sanitized = value.replace("\u0000", "")
                    if len(sanitized) != original_len:
                        logger.info(f"Sanitized string in field '{key}': removed {original_len - len(sanitized)} null bytes")
                    data[key] = sanitized
                elif isinstance(value, (dict, list)):
                    self._sanitize_strings(value)
        elif isinstance(data, list):
            for i, item in enumerate(data):
                if isinstance(item, str):
                    original_len = len(item)
                    sanitized = item.replace("\u0000", "")
                    if len(sanitized) != original_len:
                        logger.info(f"Sanitized string in list at index {i}: removed {original_len - len(sanitized)} null bytes")
                    data[i] = sanitized
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
            # Check for duplicate summaries
            summary = report_data[category]["summary"]
            if summary in summaries:
                logger.warning(f"Duplicate summary found in {category}")
                return False
            summaries.add(summary)
            
            # Check for duplicate key points
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
