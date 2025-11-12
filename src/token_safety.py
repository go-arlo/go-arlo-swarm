#!/usr/bin/env python3
"""
Token Safety Analysis Module

Integrates with BirdEye API to assess token safety across different blockchain networks.
Provides comprehensive safety analysis including contract control, holder control,
and various risk factors.
"""

import os
import asyncio
import aiohttp
from typing import Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()


class TokenSafetyAnalyzer:
    """Analyzes token safety using BirdEye API"""

    def __init__(self):
        self.api_key = os.getenv("BIRDEYE_API_KEY")
        self.base_url = "https://public-api.birdeye.so"

        if not self.api_key:
            raise ValueError("BIRDEYE_API_KEY not found in environment variables")

    async def analyze_token_safety(self, token_address: str, chain: str) -> Dict[str, Any]:
        """
        Analyze token safety for given address and chain

        Args:
            token_address: Token contract address
            chain: Blockchain network (solana, ethereum, base, bnb, etc.)

        Returns:
            Dict containing safety analysis results
        """
        try:
            # Fetch raw safety data from BirdEye
            raw_data = await self._fetch_safety_data(token_address, chain)

            if not raw_data:
                return self._create_error_response("Failed to fetch safety data")

            # Analyze based on chain type
            if chain.lower() == "solana":
                analysis = self._analyze_solana_token(raw_data)
            else:
                analysis = self._analyze_evm_token(raw_data)

            return {
                "success": True,
                "chain": chain,
                "address": token_address,
                "analysis": analysis,
                "raw_data": raw_data
            }

        except Exception as e:
            return self._create_error_response(f"Safety analysis failed: {str(e)}")

    async def _fetch_safety_data(self, token_address: str, chain: str) -> Optional[Dict]:
        """Fetch token security data from BirdEye API"""

        # Map chain names to BirdEye format
        chain_mapping = {
            "solana": "solana",
            "ethereum": "ethereum",
            "base": "base",
            "bnb": "bsc",
            "bsc": "bsc",
            "shibarium": "shibarium"
        }

        birdeye_chain = chain_mapping.get(chain.lower(), chain.lower())

        url = f"{self.base_url}/defi/token_security"
        headers = {
            "X-API-KEY": self.api_key,
            "accept": "application/json",
            "x-chain": birdeye_chain
        }
        params = {"address": token_address}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("success") and data.get("data"):
                        return data["data"]
                return None

    def _analyze_solana_token(self, data: Dict) -> Dict[str, Any]:
        """Analyze Solana token safety"""

        # Contract control analysis
        contract_control = self._analyze_solana_contract_control(data)

        # Holder control analysis
        holder_control = self._analyze_solana_holder_control(data)

        # Liquidity and creator analysis
        liquidity_analysis = self._analyze_solana_liquidity(data)

        # Overall risk assessment
        risk_level = self._calculate_overall_risk([
            contract_control["status"],
            holder_control["status"],
            liquidity_analysis["status"]
        ])

        return {
            "contract_control": contract_control,
            "holder_control": holder_control,
            "liquidity_analysis": liquidity_analysis,
            "overall_risk": risk_level,
            "key_metrics": {
                "creator_percentage": data.get("creatorPercentage", 0),
                "top10_holder_percent": data.get("top10HolderPercent", 0),
                "mutable_metadata": data.get("mutableMetadata", True),
                "jupiter_strict_list": data.get("jupStrictList", False)
            }
        }

    def _analyze_evm_token(self, data: Dict) -> Dict[str, Any]:
        """Analyze EVM-based token safety (Ethereum, Base, BSC, etc.)"""

        # Contract control analysis
        contract_control = self._analyze_evm_contract_control(data)

        # Holder control analysis
        holder_control = self._analyze_evm_holder_control(data)

        # Liquidity analysis
        liquidity_analysis = self._analyze_evm_liquidity(data)

        # Honeypot and scam checks
        security_checks = self._analyze_evm_security(data)

        # Overall risk assessment
        risk_level = self._calculate_overall_risk([
            contract_control["status"],
            holder_control["status"],
            liquidity_analysis["status"],
            security_checks["status"]
        ])

        return {
            "contract_control": contract_control,
            "holder_control": holder_control,
            "liquidity_analysis": liquidity_analysis,
            "security_checks": security_checks,
            "overall_risk": risk_level,
            "key_metrics": {
                "owner_percentage": float(data.get("ownerPercentage", "0")),
                "is_honeypot": data.get("isHoneypot", "0") == "1",
                "is_open_source": data.get("isOpenSource", "0") == "1",
                "buy_tax": float(data.get("buyTax", "0")),
                "sell_tax": float(data.get("sellTax", "0")),
                "holder_count": int(data.get("holderCount", "0"))
            }
        }

    def _analyze_solana_contract_control(self, data: Dict) -> Dict[str, Any]:
        """Analyze Solana contract control status"""

        if (data.get("creatorOwnerAddress") is not None or
            data.get("ownerAddress") is not None):
            return {
                "status": "negative",
                "reason": "Contract ownership has not been renounced",
                "risk": "High manipulation risk"
            }
        elif (data.get("mutableMetadata", True) or
              (data.get("metaplexOwnerUpdateAuthority") != "11111111111111111111111111111111" and
               data.get("metaplexOwnerUpdateAuthority") is not None)):
            return {
                "status": "neutral",
                "reason": "Contract issuance renounced but metadata remains mutable",
                "risk": "Medium manipulation risk"
            }
        else:
            return {
                "status": "positive",
                "reason": "Contract has been fully renounced",
                "risk": "Low manipulation risk"
            }

    def _analyze_solana_holder_control(self, data: Dict) -> Dict[str, Any]:
        """Analyze Solana holder control restrictions"""

        control_issues = []
        if data.get("freezeAuthority") is not None:
            control_issues.append("freeze authority enabled")
        if data.get("nonTransferable"):
            control_issues.append("transfer restrictions")
        if data.get("freezeable"):
            control_issues.append("freezable functions")
        if data.get("transferFeeEnable"):
            control_issues.append("transfer fees enabled")

        if control_issues:
            return {
                "status": "negative",
                "reason": f"Holders face restrictions: {', '.join(control_issues)}",
                "risk": "High trading risk"
            }
        else:
            return {
                "status": "positive",
                "reason": "Holders have full control over their assets",
                "risk": "Low trading risk"
            }

    def _analyze_solana_liquidity(self, data: Dict) -> Dict[str, Any]:
        """Analyze Solana token liquidity and creator metrics"""

        creator_percentage = data.get("creatorPercentage", 0)
        top10_percent = data.get("top10HolderPercent", 0)

        if creator_percentage > 0.05:  # 5%
            return {
                "status": "negative",
                "reason": f"Creator holds {creator_percentage*100:.2f}% of supply",
                "risk": "High dump risk"
            }
        elif top10_percent > 0.8:  # 80%
            return {
                "status": "negative",
                "reason": f"Top 10 holders control {top10_percent*100:.1f}% of supply",
                "risk": "High concentration risk"
            }
        elif top10_percent > 0.5:  # 50%
            return {
                "status": "neutral",
                "reason": f"Moderate concentration - top 10 hold {top10_percent*100:.1f}%",
                "risk": "Medium concentration risk"
            }
        else:
            return {
                "status": "positive",
                "reason": "Well-distributed token ownership",
                "risk": "Low concentration risk"
            }

    def _analyze_evm_contract_control(self, data: Dict) -> Dict[str, Any]:
        """Analyze EVM contract control status"""

        owner_address = data.get("ownerAddress", "")
        owner_percentage = float(data.get("ownerPercentage", "0"))
        can_take_back_ownership = data.get("canTakeBackOwnership", "0") == "1"
        is_mintable = data.get("isMintable", "0") == "1"

        if owner_address and owner_address != "0x0000000000000000000000000000000000000000" and owner_percentage > 0:
            return {
                "status": "negative",
                "reason": f"Contract ownership has not been renounced ({owner_percentage:.1f}% owned)",
                "risk": "High manipulation risk"
            }
        elif can_take_back_ownership or is_mintable:
            return {
                "status": "neutral",
                "reason": "Partial renouncement but retains some control functions",
                "risk": "Medium manipulation risk"
            }
        else:
            return {
                "status": "positive",
                "reason": "Contract has been fully renounced",
                "risk": "Low manipulation risk"
            }

    def _analyze_evm_holder_control(self, data: Dict) -> Dict[str, Any]:
        """Analyze EVM holder control restrictions"""

        control_issues = []

        if data.get("cannotBuy", "0") == "1":
            control_issues.append("buying restrictions")
        if data.get("cannotSellAll", "0") == "1":
            control_issues.append("selling restrictions")
        if data.get("transferPausable", "0") == "1":
            control_issues.append("pausable transfers")
        if data.get("isBlacklisted", "0") == "1":
            control_issues.append("blacklist functionality")

        # Check for taxes
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
            return {
                "status": "negative",
                "reason": f"Holders face restrictions: {', '.join(control_issues)}",
                "risk": "High trading risk"
            }
        else:
            return {
                "status": "positive",
                "reason": "Holders have full control over their assets",
                "risk": "Low trading risk"
            }

    def _analyze_evm_liquidity(self, data: Dict) -> Dict[str, Any]:
        """Analyze EVM token liquidity"""

        lp_holder_count = int(data.get("lpHolderCount", "0"))
        lp_holders = data.get("lpHolders", [])

        # Check for locked liquidity
        locked_lp = sum(1 for holder in lp_holders if holder.get("is_locked") == 1)

        if lp_holder_count == 0:
            return {
                "status": "negative",
                "reason": "No liquidity providers detected",
                "risk": "High liquidity risk"
            }
        elif locked_lp == 0:
            return {
                "status": "negative",
                "reason": "No locked liquidity detected",
                "risk": "High rug pull risk"
            }
        elif locked_lp < lp_holder_count * 0.5:
            return {
                "status": "neutral",
                "reason": f"Partial liquidity locked ({locked_lp}/{lp_holder_count} providers)",
                "risk": "Medium liquidity risk"
            }
        else:
            return {
                "status": "positive",
                "reason": "Majority of liquidity is locked",
                "risk": "Low liquidity risk"
            }

    def _analyze_evm_security(self, data: Dict) -> Dict[str, Any]:
        """Analyze EVM token security flags"""

        security_issues = []

        if data.get("isHoneypot", "0") == "1":
            security_issues.append("honeypot detected")
        if data.get("isBlacklisted", "0") == "1":
            security_issues.append("blacklisted token")
        if data.get("honeypotWithSameCreator", "0") == "1":
            security_issues.append("creator has other honeypots")
        if data.get("isOpenSource", "0") == "0":
            security_issues.append("closed source contract")
        if data.get("isProxy", "0") == "1":
            security_issues.append("proxy contract")

        if security_issues:
            return {
                "status": "negative",
                "reason": f"Security concerns: {', '.join(security_issues)}",
                "risk": "High security risk"
            }
        else:
            return {
                "status": "positive",
                "reason": "No major security flags detected",
                "risk": "Low security risk"
            }

    def _calculate_overall_risk(self, status_list: list) -> str:
        """Calculate overall risk level based on individual assessments"""

        negative_count = status_list.count("negative")
        neutral_count = status_list.count("neutral")
        positive_count = status_list.count("positive")

        if negative_count >= 2:
            return "HIGH"
        elif negative_count == 1 and neutral_count >= 1:
            return "HIGH"
        elif negative_count == 1 or neutral_count >= 2:
            return "MEDIUM"
        else:
            return "LOW"

    def _create_error_response(self, error_message: str) -> Dict[str, Any]:
        """Create standardized error response"""
        return {
            "success": False,
            "error": error_message,
            "analysis": {
                "contract_control": {
                    "status": "unknown",
                    "reason": "Analysis unavailable",
                    "risk": "Unknown risk"
                },
                "holder_control": {
                    "status": "unknown",
                    "reason": "Analysis unavailable",
                    "risk": "Unknown risk"
                },
                "overall_risk": "UNKNOWN"
            }
        }


async def analyze_token_safety(token_address: str, chain: str) -> Dict[str, Any]:
    """
    Convenience function to analyze token safety

    Args:
        token_address: Token contract address
        chain: Blockchain network

    Returns:
        Dict containing safety analysis results
    """
    analyzer = TokenSafetyAnalyzer()
    return await analyzer.analyze_token_safety(token_address, chain)


# Test function
async def test_safety_analysis():
    """Test the safety analysis with sample tokens"""

    test_cases = [
        {
            "name": "Solana Token",
            "address": "So11111111111111111111111111111111111111112",
            "chain": "solana"
        },
        {
            "name": "Base Token",
            "address": "0x95AF4aF910c28E8EcE4512BFE46F1F33687424ce",
            "chain": "base"
        },
        {
            "name": "Ethereum Token",
            "address": "0x95aD61b0a150d79219dCF64E1E6Cc01f0B64C4cE",
            "chain": "ethereum"
        }
    ]

    for test in test_cases:
        print(f"\n{'='*50}")
        print(f"Testing {test['name']}")
        print(f"Address: {test['address']}")
        print(f"Chain: {test['chain']}")
        print(f"{'='*50}")

        result = await analyze_token_safety(test["address"], test["chain"])

        if result["success"]:
            analysis = result["analysis"]
            print(f"✅ Overall Risk: {analysis['overall_risk']}")
            print(f"🏛️  Contract Control: {analysis['contract_control']['status']} - {analysis['contract_control']['reason']}")
            print(f"👥 Holder Control: {analysis['holder_control']['status']} - {analysis['holder_control']['reason']}")

            if "liquidity_analysis" in analysis:
                print(f"💧 Liquidity: {analysis['liquidity_analysis']['status']} - {analysis['liquidity_analysis']['reason']}")

            if "security_checks" in analysis:
                print(f"🔒 Security: {analysis['security_checks']['status']} - {analysis['security_checks']['reason']}")
        else:
            print(f"❌ Error: {result['error']}")


if __name__ == "__main__":
    asyncio.run(test_safety_analysis())