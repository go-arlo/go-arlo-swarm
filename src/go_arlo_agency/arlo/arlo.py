from agency_swarm import Agent
from .tools.calculate_weighted_score import CalculateWeightedScore
from .tools.database_writer import DatabaseWriter
from datetime import datetime, UTC
import json
from .tools.token_control import TokenControl
from .tools.summary import Summary


class Arlo(Agent):
    def __init__(self):
        super().__init__(
            name="Arlo",
            description="Lead coordinator for Team Arlo",
            instructions="./instructions.md",
            tools=[CalculateWeightedScore, DatabaseWriter, TokenControl, Summary],
            temperature=0.5,
            max_prompt_tokens=128000,
            model="gpt-4o"
        )
        self.collected_reports = {}
        self.current_input = {}

        self.report_schema = {
            "type": "object",
            "properties": {
                "final_score": {"type": "number"},
                "token_ticker": {"type": "string"},
                "contract_address": {"type": "string"},
                "chain": {"type": "string"},
                "timestamp": {"type": "string", "format": "date-time"},
                "token_safety": {"$ref": "#/definitions/category"},
                "market_position": {"$ref": "#/definitions/category"},
                "social_sentiment": {"$ref": "#/definitions/category"},
                "holder_analysis": {"$ref": "#/definitions/category"},
                "captain_summary": {"type": "string"}
            },
            "required": [
                "final_score",
                "token_ticker",
                "contract_address",
                "chain",
                "timestamp",
                "token_safety",
                "market_position",
                "social_sentiment",
                "holder_analysis",
                "captain_summary"
            ],
            "definitions": {
                "category": {
                    "type": "object",
                    "properties": {
                        "assessment": {
                            "type": "string",
                            "enum": ["positive", "neutral", "negative"]
                        },
                        "summary": {"type": "string"},
                        "key_points": {
                            "type": "array",
                            "items": {"type": "string"}
                        }
                    },
                    "required": ["assessment", "summary", "key_points"]
                }
            }
        }

    def process_message(self, message, sender):
        """Process incoming messages with proper error handling"""
        try:
            if sender == "User":
                try:
                    message = message.strip()
                    if message.startswith('{') and message.endswith('}'):
                        input_data = json.loads(message)
                    else:
                        parts = [part.strip() for part in message.split(',')]
                        if len(parts) >= 2:
                            input_data = {
                                'ticker': parts[0],
                                'address': parts[1],
                                'chain': parts[2] if len(parts) > 2 else 'solana'
                            }
                        else:
                            return "Error: Invalid input format. Please use either JSON format or comma-separated values (ticker, address, chain)"

                    self.current_input = {
                        'ticker': input_data.get('ticker'),
                        'address': input_data.get('address'),
                        'chain': input_data.get('chain', 'solana')
                    }           
                    
                    self.request_analysis(
                        agent="Signal",
                        message=f"Please analyze the market position for the token with address {self.current_input['address']}."
                    )
                    
                    self.request_analysis(
                        agent="Trend Sage",
                        message=f"Please analyze the social sentiment for the token {self.current_input['ticker']}."
                    )

                except json.JSONDecodeError:
                    return "Error: Invalid JSON format in input message"
                
            elif sender in ["Trend Sage", "Signal"]:
                key_mapping = {
                    "Trend Sage": "trend_sage",
                    "Signal": "signal"
                }
                key = key_mapping[sender]
                self.collected_reports[key] = json.loads(message) if isinstance(message, str) else message
                print(f"Stored {sender}'s analysis.")

                self.send_message(
                    message="Acknowledged receipt of the analysis.",
                    recipient=sender
                )

                self.check_and_generate_report()

            else:
                super().process_message(message, sender)

        except Exception as e:
            print(f"Error processing message: {str(e)}")
            return f"Error processing message: {str(e)}"

    def check_and_generate_report(self):
        """Check if all required analyses are collected and generate report"""
        required_keys = ['signal', 'trend_sage']
        if all(key in self.collected_reports for key in required_keys):
            print("All analyses collected. Proceeding to generate report.")
            self.generate_final_report()
        else:
            missing_analyses = [key for key in required_keys if key not in self.collected_reports]
            print(f"Waiting for analyses from: {', '.join(missing_analyses)}")

    def generate_final_report(self):
        """Generate final report with all collected data"""
        try:
            if not self.current_input.get('address') or not self.current_input.get('ticker'):
                raise ValueError("Missing required token information (address or ticker)")
            
            control_data = self.use_tool("TokenControl", {
                "contract_address": self.current_input['address']
            })
            
            if not control_data or not isinstance(control_data, dict) or not control_data.get('data'):
                raise ValueError(f"Invalid token control data: {control_data}")
            
            control_info = control_data['data']
            
            if 'token_safety' not in control_info or 'holder_analysis' not in control_info:
                raise ValueError(f"Missing token_safety or holder_analysis in control data: {control_info}")
            
            token_safety = control_info['token_safety']
            if not isinstance(token_safety, dict) or not token_safety.get('assessment') or not token_safety.get('key_points'):
                raise ValueError(f"Token safety data missing required fields: {token_safety}")
            
            market_position = self._format_category("signal", "market")
            
            social_sentiment = self._format_category("trend_sage", "social")
            
            final_score = self.use_tool("CalculateWeightedScore", {
                "contract_status": token_safety.get('assessment', 'neutral'),
                "holder_status": control_info['holder_analysis'].get('assessment', 'neutral'),
                "concentration": control_info['holder_analysis'].get('concentration', 'moderately concentrated'),
                "market_score": self._extract_score("signal", "market_score") or 50,
                "sentiment_score": self._extract_score("trend_sage", "social_score") or 50
            })
            
            if not final_score:
                raise ValueError("Failed to calculate final score")
            
            print(f"Passing to Summary: token_safety={token_safety}, final_score={final_score}, token_ticker={self.current_input['ticker']}")
            
            summary_result = self.use_tool("Summary", {
                "token_safety": token_safety,
                "market_position": market_position,
                "social_sentiment": social_sentiment,
                "holder_analysis": control_info['holder_analysis'],
                "final_score": final_score,
                "token_ticker": self.current_input['ticker']
            })
            
            if not summary_result or not isinstance(summary_result, dict):
                raise ValueError(f"Invalid summary result: {summary_result}")
            
            captain_summary = summary_result.get('summary', f"Captain's Log: Analysis completed for {self.current_input['ticker']}.")
            
            report_data = {
                "final_score": float(final_score),
                "token_ticker": self.current_input['ticker'],
                "contract_address": self.current_input['address'],
                "chain": self.current_input.get('chain', 'solana'),
                "timestamp": datetime.now(UTC).isoformat(),
                "token_safety": control_info['token_safety'],
                "market_position": market_position,
                "social_sentiment": social_sentiment,
                "holder_analysis": control_info['holder_analysis'],
                "captain_summary": captain_summary
            }

            try:
                report_json = json.dumps(report_data)
                report_dict = json.loads(report_json)
                
                db_output = self.use_tool("DatabaseWriter", {"report_data": report_dict})
                
                if not db_output or db_output.get('status') != 'success':
                    raise ValueError(f"Failed to write report to database: {db_output}")
            except Exception as e:
                print(f"Error writing to database: {str(e)}")
                raise
            
            return {"report_data": report_data}

        except Exception as e:
            print(f"Error in generate_final_report: {str(e)}")
            raise

    def _extract_score(self, agent_key, score_key):
        report = self.collected_reports.get(agent_key)
        if not report:
            return None
        data = report.get('data')
        if not data:
            return None
        return data.get(score_key)

    def _format_category(self, agent_key, score_type):
        report = self.collected_reports.get(agent_key, {})
        if isinstance(report, str):
            try:
                report = json.loads(report)
            except json.JSONDecodeError:
                report = {}

        if not report or "data" not in report:
            return {
                "assessment": "neutral",
                "summary": f"{agent_key} analysis not available.",
                "key_points": ["No data available."]
            }

        data = report["data"]
        score = data.get(f"{score_type}_score")
        assessment = self.get_assessment(score) if score is not None else "neutral"

        return {
            "assessment": assessment,
            "summary": data.get(f"{score_type}_summary", "No summary available."),
            "key_points": data.get("key_points", ["No key points available."])
        }

    def get_assessment(self, score):
        if score >= 80:
            return "positive"
        elif score >= 65:
            return "neutral"
        else:
            return "negative"
