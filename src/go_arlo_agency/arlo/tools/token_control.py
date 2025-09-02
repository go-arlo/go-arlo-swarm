from agency_swarm.tools import BaseTool
from pydantic import Field
import os
import requests
from fastapi import HTTPException
from dotenv import load_dotenv

load_dotenv()

BIRDEYE_API_KEY = os.getenv("BIRDEYE_API_KEY")
MORALIS_API_KEY = os.getenv("MORALIS_API_KEY")
BIRDEYE_BASE_URL = "https://public-api.birdeye.so/defi/token_security"
MORALIS_BASE_URL = "https://deep-index.moralis.io/api/v2.2/erc20"

class TokenControl(BaseTool):
    """
    Gets token safety and holder analysis data using Birdeye API for safety and Moralis API for Base chain holder distribution.
    Supports both Solana and Base chains with automatic detection.
    Provides structured safety and holder analysis output.
    """

    address: str = Field(
        ..., 
        description="The contract address to analyze"
    )
    
    chain: str = Field(
        default="auto",
        description="The blockchain network (auto-detect, solana, or base)"
    )

    def _detect_chain(self, address: str) -> str:
        """Auto-detect chain based on address format"""
        if address.startswith("0x"):
            return "base"
        else:
            return "solana"

    def _get_base_holders_from_moralis(self, address: str) -> float:
        """Get actual holder distribution data from Moralis API for Base tokens"""
        if not MORALIS_API_KEY:
            raise Exception("MORALIS_API_KEY is required for accurate Base token holder analysis")
        
        url = f"{MORALIS_BASE_URL}/{address}/owners"
        headers = {
            "X-API-KEY": MORALIS_API_KEY,
            "Accept": "application/json"
        }
        params = {
            "chain": "base",
            "order": "DESC",
            "limit": 100
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=30)
        
        if response.status_code != 200:
            raise Exception(f"Moralis API error {response.status_code}: {response.text}")
        
        data = response.json()
        holders = data.get("result", [])
        
        if not holders:
            raise Exception("No holder data returned from Moralis API")
        
        top_10_holders = holders[:10]
        total_top_10_percentage = sum(
            float(holder.get("percentage_relative_to_total_supply", 0)) 
            for holder in top_10_holders
        )
        
        print(f"🔍 Moralis Holder Analysis:")
        print(f"  Total holders returned: {len(holders)}")
        print(f"  Top 10 holder concentration: {total_top_10_percentage:.2f}%")
        
        print(f"  Top 5 holders:")
        for i, holder in enumerate(top_10_holders[:5], 1):
            percentage = float(holder.get("percentage_relative_to_total_supply", 0))
            address_short = holder.get("owner_address", "")[:10] + "..."
            print(f"    {i}. {address_short} - {percentage:.2f}%")
        
        return total_top_10_percentage

    def _analyze_solana_token(self, data: dict) -> dict:
        """Analyze Solana token using existing logic"""
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
        
        return contract_control, holder_control, top10_holder_percent

    def _analyze_base_token(self, data: dict) -> dict:
        """Analyze Base token using Birdeye for safety and Moralis for holder distribution"""
        owner_address = data.get("ownerAddress", "")
        owner_percentage = float(data.get("ownerPercentage", "0"))
        can_take_back_ownership = data.get("canTakeBackOwnership", "0") == "1"
        is_mintable = data.get("isMintable", "0") == "1"
        
        if owner_address and owner_address != "" and owner_percentage > 0:
            contract_control = {
                "status": "negative", 
                "reason": "has not been renounced"
            }
        elif can_take_back_ownership or is_mintable:
            contract_control = {
                "status": "neutral",
                "reason": "has partial renouncement but retains some control functions"
            }
        else:
            contract_control = {
                "status": "positive",
                "reason": "has been fully renounced, reducing manipulation risk"
            }

        control_issues = []
        
        if data.get("cannotBuy", "0") == "1":
            control_issues.append("buying restrictions")
        if data.get("cannotSellAll", "0") == "1":
            control_issues.append("selling restrictions")
        if data.get("transferPausable", "0") == "1":
            control_issues.append("pausable transfers")
        if data.get("isBlacklisted", "0") == "1":
            control_issues.append("blacklist functionality")
        
        buy_tax = float(data.get("buyTax", "0"))
        sell_tax = float(data.get("sellTax", "0"))
        transfer_tax = float(data.get("transferTax", "0"))
        
        if buy_tax > 0:
            control_issues.append(f"buy tax ({buy_tax}%)")
        if sell_tax > 0:
            control_issues.append(f"sell tax ({sell_tax}%)")
        if transfer_tax > 0:
            control_issues.append(f"transfer tax ({transfer_tax}%)")
            
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

        top10_holder_percent = self._get_base_holders_from_moralis(self.address)
        
        return contract_control, holder_control, top10_holder_percent

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
            "summary": (f"The contract ownership {contract_reason}. {contract_detail} "
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
        Executes the token control analysis using Birdeye API for safety and Moralis API for Base holder distribution
        """
        try:
            if self.chain == "auto":
                detected_chain = self._detect_chain(self.address)
                print(f"Auto-detected chain: {detected_chain} for address: {self.address}")
            else:
                detected_chain = self.chain
            
            if not BIRDEYE_API_KEY:
                raise HTTPException(
                    status_code=400,
                    detail="BIRDEYE_API_KEY is required for token safety analysis"
                )
            
            if detected_chain == "base" and not MORALIS_API_KEY:
                raise HTTPException(
                    status_code=400,
                    detail="MORALIS_API_KEY is required for accurate Base token holder analysis"
                )
            
            response = requests.get(
                BIRDEYE_BASE_URL,
                headers={
                    "X-API-KEY": BIRDEYE_API_KEY,
                    "x-chain": detected_chain
                },
                params={
                    "address": self.address
                },
                timeout=45
            )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Birdeye API error for {detected_chain} chain: {response.text}"
                )
                
            data = response.json().get("data", {})
            
            try:
                if detected_chain == "base":
                    contract_control, holder_control, top10_holder_percent = self._analyze_base_token(data)
                else:  # solana
                    contract_control, holder_control, top10_holder_percent = self._analyze_solana_token(data)
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=f"Error analyzing {detected_chain} token data: {str(e)}"
                )
            
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
                "chain": detected_chain,
                "data_source": {
                    "safety": "birdeye",
                    "holders": "moralis" if detected_chain == "base" else "birdeye"
                },
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
                             else "This presents a moderate risk due to potential control functions. " if contract_control["status"] == "neutral"
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

if __name__ == "__main__":
    import json
    from datetime import datetime
    
    def print_separator(title):
        print("\n" + "="*80)
        print(f"🔍 {title}")
        print("="*80)
    
    def print_result(token_name, address, result):
        print(f"\n📋 {token_name}")
        print(f"Address: {address}")
        print(f"Chain: {result.get('chain', 'unknown')}")
        
        if result.get('success'):
            data = result['data']
            safety = data['token_safety']
            holder = data['holder_analysis']
            
            # Token Safety
            print(f"\n🔒 TOKEN SAFETY: {safety['assessment'].upper()}")
            print(f"Summary: {safety['summary']}")
            print("Key Points:")
            for point in safety['key_points']:
                print(f"  • {point}")
            
            # Holder Analysis
            print(f"\n👥 HOLDER ANALYSIS: {holder['assessment'].upper()}")
            print(f"Summary: {holder['summary']}")
            print("Key Points:")
            for point in holder['key_points']:
                print(f"  • {point}")
                
        else:
            print(f"❌ ERROR: {result}")
    
    def test_token(name, address, expected_chain=None):
        try:
            tool = TokenControl(address=address)
            result = tool.run()
            print_result(name, address, result)
            
            if expected_chain and result.get('chain') != expected_chain:
                print(f"⚠️  Chain detection mismatch! Expected: {expected_chain}, Got: {result.get('chain')}")
                
        except Exception as e:
            print(f"❌ ERROR testing {name}: {str(e)}")
    
    # Test cases
    print_separator("TOKEN CONTROL ANALYSIS - MANUAL TESTING")
    print(f"Test started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    print_separator("SOLANA TOKENS")
    
    # Solana Test Cases
    solana_tests = [
        {
            "name": "JTO Token (Well-known)",
            "address": "jtojtomepa8beP8AuQc6eXt5FriJwfFMwQx2v2f9mCL",
            "expected": "Should be safe with good distribution"
        },
        {
            "name": "BONK Token (Meme coin)",
            "address": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263", 
            "expected": "Popular meme coin"
        },
        {
            "name": "SOL Token (Native)",
            "address": "So11111111111111111111111111111111111111112",
            "expected": "Native SOL token"
        }
    ]
    
    for test in solana_tests:
        print(f"\n🧪 Testing: {test['name']}")
        print(f"Expected: {test['expected']}")
        test_token(test['name'], test['address'], 'solana')
    
    print_separator("BASE TOKENS")
    
         # Base Test Cases  
    base_tests = [
        {
            "name": "ZORA Token (Correct Address)",
            "address": "0x1111111111166b7FE7bd91427724B487980aFc69",
            "expected": "Should show realistic holder distribution with 927k+ holders"
        },
        {
            "name": "USDC on Base",
            "address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
            "expected": "Should be a safe stablecoin"
        },
        {
            "name": "Ethereum on Base (Wrapped)",
            "address": "0x4200000000000000000000000000000000000006",
            "expected": "Bridged ETH token"
        }
    ]
    
    for test in base_tests:
        print(f"\n🧪 Testing: {test['name']}")
        print(f"Expected: {test['expected']}")
        test_token(test['name'], test['address'], 'base')
    
    print_separator("CHAIN AUTO-DETECTION TESTS")
    
    # Test auto-detection
    detection_tests = [
        {
            "address": "jtojtomepa8beP8AuQc6eXt5FriJwfFMwQx2v2f9mCL",
            "expected_chain": "solana",
            "reason": "No 0x prefix"
        },
                 {
             "address": "0x1111111111166b7FE7bd91427724B487980aFc69", 
             "expected_chain": "base",
             "reason": "0x prefix (ZORA token)"
         }
    ]
    
    for test in detection_tests:
        tool = TokenControl(address=test['address'])
        detected = tool._detect_chain(test['address'])
        status = "✅" if detected == test['expected_chain'] else "❌"
        print(f"{status} {test['address'][:20]}... → {detected} ({test['reason']})")
    
    print_separator("MANUAL TESTING COMMANDS")
    
    print("""
🚀 To test manually from Python console:

# Test a specific token
from token_control import TokenControl
tool = TokenControl(address="your_address_here")
result = tool.run()
print(json.dumps(result, indent=2))

# Test chain detection only
tool = TokenControl(address="0x...")  # Base token
print(tool._detect_chain("0x..."))  # Should return 'base'

tool = TokenControl(address="abc...")  # Solana token  
print(tool._detect_chain("abc..."))  # Should return 'solana'

# Test with explicit chain
tool = TokenControl(address="your_address", chain="solana")
result = tool.run()

 🔧 Environment Setup:
 1. Required: BIRDEYE_API_KEY in your .env file (for token safety on both chains)
 2. Required: MORALIS_API_KEY in your .env file (for accurate Base holder data)
 3. Install required packages: requests, pydantic, fastapi, python-dotenv
 4. Run: python token_control.py

📝 Test Results:
- ✅ = Successful analysis
- ❌ = Error occurred  
- ⚠️ = Warning or unexpected result

 💡 Tips:
 - Base tokens start with 0x → Uses Birdeye (safety) + Moralis (holders)
 - Solana tokens are base58 encoded → Uses Birdeye (safety + holders)
 - Check the 'chain' and 'data_source' fields in results
 - Look for 'assessment' fields: positive/neutral/negative
 - Both API keys are required for accurate analysis
    """)
    
    print_separator("TESTING COMPLETED")
    print(f"Test completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("Check results above for any errors or warnings!") 
    