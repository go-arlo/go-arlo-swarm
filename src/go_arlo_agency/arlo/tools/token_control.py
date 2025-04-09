from agency_swarm.tools import BaseTool
from pydantic import Field
import os
import requests
from fastapi import HTTPException
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("BIRDEYE_API_KEY")
BASE_URL = "https://public-api.birdeye.so/defi/token_security"

class TokenControl(BaseTool):
    """
    Gets token safety and holder analysis data using Birdeye API.
    Provides structured safety and holder analysis output.
    """

    address: str = Field(
        ..., 
        description="The contract address to analyze"
    )
    
    chain: str = Field(
        default="solana",
        description="The blockchain network (currently only supports solana)"
    )

    def process_safety_data(self, contract_control, holder_control):
        """Process token safety data with detailed context"""
        contract_context = {
            "positive": {
                "renounced": "This significantly reduces centralization risk and potential for malicious changes.",
                "verified": "This enables public code verification and increases transparency.",
                "proxy": "This allows for secure contract upgrades while maintaining transparency."
            },
            "negative": {
                "not renounced": "This presents a risk of unauthorized contract modifications.",
                "not verified": "This lack of transparency raises security concerns.",
                "blacklist": "This indicates potential centralized control over user transactions."
            }
        }
        
        holder_context = {
            "positive": {
                "no restrictions": "This ensures users have full control over their assets.",
                "unrestricted": "This allows for normal trading without artificial limitations."
            },
            "negative": {
                "restricted": "This indicates limitations on user asset control.",
                "blacklist": "This suggests centralized control over user transactions."
            }
        }
        
        contract_detail = contract_context.get(contract_control['status'], {}).get(
            contract_control['reason'].lower().split(',')[0].strip(), 
            ""
        )
        holder_detail = holder_context.get(holder_control['status'], {}).get(
            holder_control['reason'].lower().split(',')[0].strip(), 
            ""
        )

        contract_reason = contract_control['reason'].lower().replace('contract ownership ', '')
        holder_reason = holder_control['reason'].lower().replace('token holders ', '')
        
        return {
            "assessment": "positive" if contract_control['status'] == "positive" and holder_control['status'] == "positive" else "negative",
            "summary": (f"The contract ownership has been {contract_reason}. {contract_detail} "
                       f"All token holders {holder_reason}. {holder_detail}"),
            "key_points": [
                contract_control['reason'],
                holder_control['reason']
            ]
        }

    def process_holder_data(self, percentage, concentration):
        """Process holder distribution data into analysis format"""
        detail_summary = {
            "well-balanced": "This distribution pattern suggests strong retail participation and reduced manipulation risk.",
            "moderately concentrated": "This level of concentration requires monitoring but remains within acceptable ranges.",
            "highly concentrated": "This concentration level presents significant risks of price manipulation and volatility."
        }.get(concentration, "")
        
        return {
            "assessment": "positive" if concentration == "well-balanced" else "neutral" if concentration == "moderately concentrated" else "negative",
            "summary": f"Distribution is {concentration} with {percentage}% held by top holders. {detail_summary}",
            "key_points": [f"Top holders concentration: {percentage}% ({concentration})"]
        }

    def run(self):
        """
        Executes the token control analysis using Birdeye API
        """
        try:
            response = requests.get(
                BASE_URL,
                headers={
                    "X-API-KEY": API_KEY,
                    "x-chain": self.chain
                },
                params={
                    "address": self.address
                },
                timeout=45
            )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail="Error fetching token security data"
                )
                
            data = response.json().get("data", {})
            
            if (data.get("creatorOwnerAddress") is not None or 
                data.get("ownerAddress") is not None):
                contract_control = {
                    "status": "negative",
                    "reason": "has not been renounced"
                }
            elif (data.get("mutableMetadata", True) or 
                  (data.get("metaplexOwnerUpdateAuthority") != "11111111111111111111111111111111" and 
                   data.get("metaplexOwnerUpdateAuthority") is not None)):
                contract_control = {
                    "status": "neutral",
                    "reason": "has issuance renounced but metadata remains mutable"
                }
            else:
                contract_control = {
                    "status": "positive",
                    "reason": "has been fully renounced, reducing manipulation risk"
                }

            control_issues = []
            if data.get("freezeAuthority") is not None:
                control_issues.append("freeze authority")
            if data.get("nonTransferable") is not None:
                control_issues.append("transfer restrictions")
            if data.get("freezeable") is not None:
                control_issues.append("freezable functions")
            if data.get("transferFeeEnable") is True:
                control_issues.append("transfer fees")
                
            if control_issues:
                holder_control = {
                    "status": "negative",
                    "reason": f"have {', '.join(control_issues)}"
                }
            else:
                holder_control = {
                    "status": "positive",
                    "reason": "have full control over their assets with no restrictions"
                }

            top10_holder_percent = float(data.get("top10HolderPercent", 1) or 1) * 100
            
            def get_concentration_description(percent):
                if percent < 20:
                    return "well-balanced"
                elif percent < 30:
                    return "moderately concentrated"
                else:
                    return "highly concentrated"
            
            concentration = get_concentration_description(top10_holder_percent)
            percentage = round(top10_holder_percent, 2)
            
            return {
                "success": True,
                "data": {
                    "token_safety": {
                        "assessment": (
                            "positive" if contract_control["status"] == "positive" and holder_control["status"] == "positive"
                            else "negative" if contract_control["status"] == "negative" or holder_control["status"] == "negative"
                            else "neutral"
                        ),
                        "summary": (
                            f"The contract ownership {contract_control['reason'].lower()}. " + 
                            ("This significantly reduces centralization risk and potential for malicious changes. " if contract_control["status"] == "positive"
                             else "This presents a moderate risk due to potential metadata changes. " if contract_control["status"] == "neutral"
                             else "This presents a risk of unauthorized contract modifications. ") +
                            f"All token holders {holder_control['reason'].lower()}." +
                            ("" if holder_control["status"] == "positive"
                             else " This indicates limitations on user asset control.")
                        ),
                        "key_points": [
                            f"Contract ownership {contract_control['reason']}",
                            f"Token holders {holder_control['reason']}"
                        ]
                    },
                    "holder_analysis": {
                        "assessment": "positive" if concentration == "well-balanced" else "neutral" if concentration == "moderately concentrated" else "negative",
                        "summary": f"Distribution is {concentration} with {percentage}% held by top holders. " + {
                            "well-balanced": "This distribution pattern suggests strong retail participation and reduced manipulation risk.",
                            "moderately concentrated": "This level of concentration requires monitoring but remains within acceptable ranges.",
                            "highly concentrated": "This concentration level presents significant risks of price manipulation and volatility."
                        }[concentration],
                        "key_points": [f"Top holders concentration: {percentage}% ({concentration})"],
                        "concentration": concentration
                    }
                }
            }
            
        except requests.Timeout:
            raise HTTPException(
                status_code=408,
                detail="Request timed out while fetching token security data"
            )
        except requests.RequestException as e:
            raise HTTPException(
                status_code=500,
                detail=f"Error checking token control: {str(e)}"
            ) 
