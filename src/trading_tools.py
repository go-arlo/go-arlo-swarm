"""
Consolidated Trading Tools Module

This module provides all trading functionality including:
- Jupiter quote fetching
- Position size calculation
- Trade execution via Jupiter
- Auto-execution based on analysis
"""

import os
import json
import base64
import time
import logging
import httpx
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.backends import default_backend

logger = logging.getLogger(__name__)
load_dotenv()


class WalletManager:
    """Wallet manager for delegated wallet operations with Turnkey."""

    def __init__(
        self,
        delegated_wallet_address: str,
        turnkey_organization_id: str,
        turnkey_api_public_key: str = None,
        turnkey_api_private_key: str = None,
        main_turnkey_api_public_key: str = None,
        main_turnkey_api_private_key: str = None,
        turnkey_api_base_url: str = "https://api.turnkey.com",
        solana_rpc_url: str = "https://api.mainnet-beta.solana.com"
    ):
        self.delegated_wallet_address = delegated_wallet_address
        self.turnkey_organization_id = turnkey_organization_id
        # Delegated user API keys (for transaction signing)
        self.turnkey_api_public_key = turnkey_api_public_key
        self.turnkey_api_private_key = turnkey_api_private_key
        # Main account API keys (for creating API keys)
        self.main_turnkey_api_public_key = main_turnkey_api_public_key
        self.main_turnkey_api_private_key = main_turnkey_api_private_key
        self.turnkey_api_base_url = turnkey_api_base_url.rstrip('/')
        self.solana_rpc_url = solana_rpc_url

    def create_api_stamp(self, request_body: Dict[str, Any]) -> str:
        """Create an API stamp for Turnkey requests."""
        if not self.turnkey_api_private_key or not self.turnkey_api_public_key:
            raise ValueError("Turnkey API keys not configured")

        payload_str = json.dumps(request_body, separators=(',', ':'))
        private_key = ec.derive_private_key(int(self.turnkey_api_private_key, 16), ec.SECP256R1())
        signature = private_key.sign(payload_str.encode(), ec.ECDSA(hashes.SHA256()))

        stamp = {
            "publicKey": self.turnkey_api_public_key,
            "scheme": "SIGNATURE_SCHEME_TK_API_P256",
            "signature": signature.hex(),
        }

        stamp_encoded = base64.urlsafe_b64encode(
            json.dumps(stamp, separators=(',', ':')).encode()
        ).decode().rstrip("=")

        return stamp_encoded

    def _create_stamp_with_main_keys(self, request_body: Dict[str, Any]) -> str:
        """Create an API stamp using main account keys."""
        if not self.main_turnkey_api_private_key or not self.main_turnkey_api_public_key:
            raise ValueError("Main Turnkey API keys not configured")

        payload_str = json.dumps(request_body, separators=(',', ':'))
        private_key = ec.derive_private_key(int(self.main_turnkey_api_private_key, 16), ec.SECP256R1())
        signature = private_key.sign(payload_str.encode(), ec.ECDSA(hashes.SHA256()))

        stamp = {
            "publicKey": self.main_turnkey_api_public_key,
            "scheme": "SIGNATURE_SCHEME_TK_API_P256",
            "signature": signature.hex(),
        }

        stamp_encoded = base64.urlsafe_b64encode(
            json.dumps(stamp, separators=(',', ':')).encode()
        ).decode().rstrip("=")

        return stamp_encoded

    def sign_transaction(
        self,
        unsigned_transaction: str,
        transaction_type: str = "TRANSACTION_TYPE_SOLANA"
    ) -> Dict[str, Any]:
        """Sign a transaction using the delegated wallet."""
        if not self.turnkey_api_private_key or not self.turnkey_api_public_key:
            raise ValueError("Turnkey API keys not configured for signing")

        request_body = {
            "type": "ACTIVITY_TYPE_SIGN_TRANSACTION_V2",
            "timestampMs": str(int(time.time() * 1000)),
            "organizationId": self.turnkey_organization_id,
            "parameters": {
                "type": transaction_type,
                "signWith": self.delegated_wallet_address,
                "unsignedTransaction": unsigned_transaction
            }
        }

        stamp = self.create_api_stamp(request_body)
        headers = {"Content-Type": "application/json", "X-Stamp": stamp}

        with httpx.Client() as client:
            response = client.post(
                f"{self.turnkey_api_base_url}/public/v1/submit/sign_transaction",
                json=request_body,
                headers=headers,
                timeout=30
            )

        if response.status_code == 200:
            result = response.json()
            activity = result.get("activity", {})
            if activity.get("status") == "ACTIVITY_STATUS_PENDING":
                return self._poll_activity(activity.get("id"))
            return result
        else:
            raise Exception(f"Transaction signing failed: {response.status_code}")

    def _poll_activity(self, activity_id: str, max_attempts: int = 30) -> Dict[str, Any]:
        """Poll for activity completion."""
        for _ in range(max_attempts):
            time.sleep(1)
            request_body = {"organizationId": self.turnkey_organization_id}
            stamp = self.create_api_stamp(request_body)

            with httpx.Client() as client:
                response = client.get(
                    f"{self.turnkey_api_base_url}/public/v1/activity/{activity_id}",
                    headers={"X-Stamp": stamp},
                    params={"organizationId": self.turnkey_organization_id},
                    timeout=30.0
                )

            if response.status_code == 200:
                result = response.json()
                activity = result.get("activity", {})
                if activity.get("status") == "ACTIVITY_STATUS_COMPLETED":
                    return result
                elif activity.get("status") == "ACTIVITY_STATUS_FAILED":
                    raise Exception(f"Activity failed: {activity}")

        raise Exception("Activity polling timeout")

    def _make_solana_rpc_request(self, method: str, params: list = None) -> Dict[str, Any]:
        """Make a JSON-RPC request to Solana."""
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params or []
        }

        try:
            with httpx.Client() as client:
                response = client.post(
                    self.solana_rpc_url,
                    json=payload,
                    timeout=30.0
                )

            if response.status_code == 200:
                result = response.json()
                if "error" in result:
                    raise Exception(f"RPC error: {result['error']}")
                return result.get("result")
            else:
                raise Exception(f"RPC request failed: {response.status_code}")

        except httpx.RequestError as e:
            raise Exception(f"Failed to connect to Solana RPC: {e}")

    def get_sol_balance(self) -> Optional[float]:
        """Get SOL balance for the delegated wallet."""
        try:
            result = self._make_solana_rpc_request(
                "getBalance",
                [self.delegated_wallet_address]
            )
            return result.get("value", 0) / 1_000_000_000  # Convert to SOL
        except Exception as e:
            logger.error(f"Error getting SOL balance: {e}")
        return None

    def execute_swap(self, swap_params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a Jupiter swap using Ultra API through Turnkey."""
        try:
            # Get Jupiter Ultra order
            order_params = {
                "inputMint": swap_params["inputMint"],
                "outputMint": swap_params["outputMint"],
                "amount": str(swap_params["amount"]),
                "taker": self.delegated_wallet_address,
                "slippageBps": swap_params.get("slippageBps", 500)
            }

            jup_api_key = os.getenv("JUP_API_KEY")
            headers = {"User-Agent": "Trading-Agent/1.0"}
            if jup_api_key:
                headers["x-api-key"] = jup_api_key

            # Build URL with query params for GET request
            order_url = (
                "https://api.jup.ag/ultra/v1/order?"
                f"inputMint={order_params['inputMint']}"
                f"&outputMint={order_params['outputMint']}"
                f"&amount={order_params['amount']}"
                f"&taker={order_params['taker']}"
                f"&slippageBps={order_params['slippageBps']}"
            )

            logger.info(f"Getting Jupiter Ultra order for {swap_params['amount']} units")

            with httpx.Client(timeout=30.0) as client:
                order_response = client.get(
                    order_url,
                    headers=headers
                )

            if order_response.status_code != 200:
                error_text = order_response.text
                try:
                    error_json = order_response.json()
                    if "Failed to get quotes" in error_json.get("error", ""):
                        logger.warning(f"No liquidity available for swap: {error_json}")
                        raise Exception(f"No liquidity: Token cannot be swapped (no routes available)")
                except:
                    pass
                raise Exception(f"Failed to get Ultra order: {error_text}")

            order_data = order_response.json()
            unsigned_transaction_b64 = order_data.get("transaction")
            request_id = order_data.get("requestId")

            if not unsigned_transaction_b64 or not request_id:
                raise Exception(f"Invalid Ultra order response: missing transaction or requestId")

            logger.info(f"Got Ultra order with requestId: {request_id}")
            logger.info(f"Output amount: {order_data.get('outAmount')}")

            # Convert base64 to hex for Turnkey
            try:
                transaction_bytes = base64.b64decode(unsigned_transaction_b64)
                unsigned_transaction_hex = transaction_bytes.hex()
                logger.info(f"Converted transaction to hex for Turnkey signing")
            except Exception as e:
                logger.error(f"Failed to decode base64 from Jupiter Ultra: {e}")
                raise Exception(f"Invalid base64 transaction from Jupiter Ultra: {e}")

            # Sign transaction with Turnkey
            signed_result = self.sign_transaction(
                unsigned_transaction=unsigned_transaction_hex,
                transaction_type="TRANSACTION_TYPE_SOLANA"
            )

            # Extract signed transaction
            activity = signed_result.get("activity", {})
            result = activity.get("result", {})
            sign_result = result.get("signTransactionResult", {})
            signed_transaction = sign_result.get("signedTransaction")

            if not signed_transaction:
                raise Exception("Failed to get signed transaction from Turnkey")

            # Convert hex back to base64 for Jupiter Ultra execute
            try:
                # Validate hex format first
                if len(signed_transaction) % 2 != 0:
                    raise ValueError(f"Signed transaction hex has odd length: {len(signed_transaction)}")

                signed_bytes = bytes.fromhex(signed_transaction)
                signed_transaction_b64 = base64.b64encode(signed_bytes).decode()
                logger.info(f"Converted signed transaction back to base64 for Ultra execute")
            except Exception as e:
                logger.error(f"Failed to convert signed transaction from hex: {e}")
                raise Exception(f"Invalid hex transaction from Turnkey: {e}")

            # Execute the signed transaction via Jupiter Ultra
            execute_payload = {
                "signedTransaction": signed_transaction_b64,
                "requestId": request_id
            }

            headers = {
                "Content-Type": "application/json",
                "User-Agent": "Trading-Agent/1.0"
            }
            if jup_api_key:
                headers["x-api-key"] = jup_api_key

            logger.info(f"Executing Ultra transaction with requestId: {request_id}")

            with httpx.Client(timeout=30.0) as client:
                execute_response = client.post(
                    "https://api.jup.ag/ultra/v1/execute",
                    json=execute_payload,
                    headers=headers
                )

            if execute_response.status_code != 200:
                error_text = execute_response.text
                logger.error(f"Ultra execute failed: {error_text}")
                raise Exception(f"Failed to execute Ultra transaction: {error_text}")

            execute_result = execute_response.json()

            # Check execution status
            status = execute_result.get("status")
            signature = execute_result.get("signature")

            if status != "Success":
                error_msg = execute_result.get("error", "Unknown error")
                raise Exception(f"Ultra execution failed: {error_msg}")

            logger.info(f"Transaction executed successfully: {signature}")

            return {
                "success": True,
                "transactionHash": signature,
                "inputAmount": swap_params["amount"],
                "outputAmount": order_data.get("outAmount"),
                "requestId": request_id,
                "route": order_data.get("routePlan")
            }

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Swap execution failed: {error_msg}")

            # Provide more user-friendly error messages
            if "no liquidity" in error_msg.lower() or "no routes" in error_msg.lower():
                return {
                    "success": False,
                    "error": "💀 Token appears dead or has no liquidity for trading"
                }
            elif "failed to get quotes" in error_msg.lower():
                return {
                    "success": False,
                    "error": "📉 No trading routes available (token may be dead or illiquid)"
                }

            return {"success": False, "error": error_msg}


class GetJupiterQuote(BaseModel):
    """Get a swap quote from Jupiter Ultra."""

    input_mint: str = Field(description="Input token mint address")
    output_mint: str = Field(description="Output token mint address")
    amount: str = Field(description="Amount to swap (in smallest unit)")
    slippage_bps: int = Field(default=500, description="Max slippage tolerance in basis points (500 = 5%)")
    taker: Optional[str] = Field(default=None, description="Taker wallet address")

    def run(self) -> str:
        """Get Jupiter Ultra swap quote."""
        try:
            # Map common symbols to mint addresses
            mint_map = {
                "SOL": "So11111111111111111111111111111111111111112",
                "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                "USDT": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"
            }

            input_mint = mint_map.get(self.input_mint, self.input_mint)
            output_mint = mint_map.get(self.output_mint, self.output_mint)

            # Use delegated wallet address if taker not provided
            taker_address = self.taker or os.getenv("DELEGATED_WALLET_ADDRESS")
            if not taker_address:
                return "❌ No taker wallet address available"

            # Get JUP API key from environment
            jup_api_key = os.getenv("JUP_API_KEY")
            headers = {"User-Agent": "Trading-Agent/1.0"}
            if jup_api_key:
                headers["x-api-key"] = jup_api_key

            # Build URL with query params for Ultra order (which includes quote info)
            order_url = (
                "https://api.jup.ag/ultra/v1/order?"
                f"inputMint={input_mint}"
                f"&outputMint={output_mint}"
                f"&amount={self.amount}"
                f"&taker={taker_address}"
                f"&slippageBps={self.slippage_bps}"
            )

            with httpx.Client(timeout=30.0) as client:
                response = client.get(
                    order_url,
                    headers=headers
                )

                if response.status_code == 200:
                    order_data = response.json()

                    # Parse the order response which includes quote info
                    in_amount = int(order_data.get("inAmount", 0))
                    out_amount = int(order_data.get("outAmount", 0))
                    price_impact = float(order_data.get("priceImpactPct", 0))

                    # Format amounts (assuming 9 decimals for SOL, 6 for USDC/USDT)
                    in_decimals = 9 if input_mint == mint_map.get("SOL") else 6
                    out_decimals = 9 if output_mint == mint_map.get("SOL") else 6

                    in_formatted = in_amount / (10 ** in_decimals)
                    out_formatted = out_amount / (10 ** out_decimals)

                    return f"""
📊 **Jupiter Ultra Quote**
- Input: {in_formatted:.6f} {self.input_mint}
- Output: {out_formatted:.6f} {self.output_mint}
- Price Impact: {price_impact:.2f}%
- Slippage: {self.slippage_bps / 100:.1f}%
- Request ID: {order_data.get('requestId', 'N/A')}
                    """
                else:
                    return f"❌ Failed to get Ultra quote: {response.status_code}"

        except Exception as e:
            logger.error(f"Error getting Jupiter Ultra quote: {e}")
            return f"❌ Error getting quote: {str(e)}"


class CalculatePositionSize(BaseModel):
    """Calculate appropriate position size for trading."""

    trading_decision: Dict[str, Any] = Field(description="Trading decision data")
    token_address: str = Field(description="Token contract address")
    token_symbol: str = Field(description="Token symbol")

    def run(self) -> str:
        """Calculate position size based on risk factors."""
        try:
            # Get wallet balance
            wallet_address = os.getenv("DELEGATED_WALLET_ADDRESS")
            if not wallet_address:
                return "❌ No delegated wallet configured"

            wallet_manager = WalletManager(
                delegated_wallet_address=wallet_address,
                turnkey_organization_id=os.getenv("TURNKEY_ORGANIZATION_ID"),
                turnkey_api_public_key=os.getenv("TURNKEY_API_PUBLIC_KEY"),
                turnkey_api_private_key=os.getenv("TURNKEY_API_PRIVATE_KEY"),
                main_turnkey_api_public_key=os.getenv("MAIN_TURNKEY_API_PUBLIC_KEY"),
                main_turnkey_api_private_key=os.getenv("MAIN_TURNKEY_API_PRIVATE_KEY"),
                turnkey_api_base_url=os.getenv("TURNKEY_API_BASE_URL", "https://api.turnkey.com"),
                solana_rpc_url=os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
            )

            sol_balance = wallet_manager.get_sol_balance()
            if sol_balance is None:
                return "❌ Could not fetch wallet balance"

            # Get max amount from environment
            max_amount = float(os.getenv("MAX_AMOUNT", "0.1"))

            # Reserve for fees
            fee_reserve = 0.01
            available_balance = max(0, sol_balance - fee_reserve)

            # Extract decision factors
            recommendation = self.trading_decision.get("recommendation", "HOLD")
            confidence = self.trading_decision.get("confidence", "MEDIUM")
            score = self.trading_decision.get("score", 50)
            risk_score = self.trading_decision.get("risk_score", 50)
            position_size_category = self.trading_decision.get("position_size", "SMALL")

            # Base position sizing
            base_percentages = {
                "SMALL": 0.02,   # 2% of available balance
                "MEDIUM": 0.05,  # 5% of available balance
                "LARGE": 0.10    # 10% of available balance
            }

            # Confidence multipliers
            confidence_multipliers = {
                "HIGH": 1.5,
                "MEDIUM": 1.0,
                "LOW": 0.5
            }

            # Calculate position
            base_pct = base_percentages.get(position_size_category, 0.02)
            confidence_mult = confidence_multipliers.get(confidence, 1.0)
            risk_multiplier = max(0.2, 1.0 - (risk_score / 200))

            adjusted_pct = base_pct * confidence_mult * risk_multiplier
            balance_based_amount = available_balance * adjusted_pct

            # Apply constraints
            constrained_amount = min(
                balance_based_amount,
                max_amount,
                available_balance * 0.2  # Never use more than 20% of balance
            )

            # Ensure minimum viable trade
            minimum_trade = 0.001
            if constrained_amount < minimum_trade:
                constrained_amount = minimum_trade if available_balance >= minimum_trade else 0

            can_execute = constrained_amount > 0 and recommendation == "BUY"

            return f"""
📊 **Position Size Analysis for {self.token_symbol}**

**Wallet Status:**
- Current SOL Balance: {sol_balance:.6f} SOL
- Available for Trading: {available_balance:.6f} SOL
- MAX_AMOUNT Policy: {max_amount:.6f} SOL

**Recommended Position:**
- Amount: **{constrained_amount:.6f} SOL**
- Percentage of Balance: {(constrained_amount / sol_balance * 100):.2f}%
- Can Execute: {"✅ Yes" if can_execute else "❌ No"}
            """

        except Exception as e:
            logger.error(f"Error calculating position size: {e}")
            return f"❌ Position size calculation failed: {str(e)}"


class ExecuteJupiterSwap(BaseModel):
    """Execute a swap via Jupiter Ultra."""

    input_mint: str = Field(description="Input token mint address")
    output_mint: str = Field(description="Output token mint address")
    amount: str = Field(description="Amount to swap (in smallest unit)")
    slippage_bps: int = Field(default=500, description="Max slippage tolerance in basis points (500 = 5%)")

    def run(self) -> str:
        """Execute the swap via Jupiter Ultra."""
        try:
            # Map common symbols to mint addresses
            mint_map = {
                "SOL": "So11111111111111111111111111111111111111112",
                "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                "USDT": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"
            }

            input_mint = mint_map.get(self.input_mint, self.input_mint)
            output_mint = mint_map.get(self.output_mint, self.output_mint)

            # Initialize wallet manager with Turnkey credentials
            wallet_address = os.getenv("DELEGATED_WALLET_ADDRESS")
            if not wallet_address:
                return "❌ No delegated wallet configured"

            wallet_manager = WalletManager(
                delegated_wallet_address=wallet_address,
                turnkey_organization_id=os.getenv("TURNKEY_ORGANIZATION_ID"),
                turnkey_api_public_key=os.getenv("TURNKEY_API_PUBLIC_KEY"),
                turnkey_api_private_key=os.getenv("TURNKEY_API_PRIVATE_KEY"),
                main_turnkey_api_public_key=os.getenv("MAIN_TURNKEY_API_PUBLIC_KEY"),
                main_turnkey_api_private_key=os.getenv("MAIN_TURNKEY_API_PRIVATE_KEY"),
                turnkey_api_base_url=os.getenv("TURNKEY_API_BASE_URL", "https://api.turnkey.com"),
                solana_rpc_url=os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
            )

            # Execute the swap using Ultra API
            swap_params = {
                "inputMint": input_mint,
                "outputMint": output_mint,
                "amount": int(self.amount),
                "slippageBps": self.slippage_bps
            }

            result = wallet_manager.execute_swap(swap_params)

            if result.get("success"):
                tx_hash = result.get("transactionHash", "N/A")
                request_id = result.get("requestId", "N/A")
                in_amount = int(self.amount)
                out_amount = int(result.get("outputAmount", 0))

                # Format amounts
                in_decimals = 9 if input_mint == mint_map.get("SOL") else 6
                out_decimals = 9 if output_mint == mint_map.get("SOL") else 6
                in_formatted = in_amount / (10 ** in_decimals)
                out_formatted = out_amount / (10 ** out_decimals)

                return f"""
🚀 **Trade Executed Successfully via Jupiter Ultra**

**Transaction Details:**
- Input: {in_formatted:.6f} {self.input_mint}
- Output: {out_formatted:.6f} {self.output_mint}
- Transaction Hash: `{tx_hash}`
- Request ID: {request_id}
- Explorer: https://solscan.io/tx/{tx_hash}
- Slippage: {self.slippage_bps / 100:.1f}%
                """
            else:
                error = result.get("error", "Unknown error")
                return f"❌ Swap execution failed: {error}"

        except Exception as e:
            logger.error(f"Error executing swap: {e}")
            return f"❌ Swap execution failed: {str(e)}"


class AutoExecuteSwap(BaseModel):
    """Auto-execute swap based on analysis."""

    message_content: str = Field(description="Analysis report content")
    input_token: str = Field(default="SOL", description="Input token symbol")
    token_address: Optional[str] = Field(default=None, description="Token contract address (optional, will extract from report if not provided)")

    def run(self) -> str:
        """Auto-execute trade based on analysis."""
        try:
            import re

            # Use provided token_address if available, otherwise extract from report
            if self.token_address:
                token_address = self.token_address
            else:
                # Try multiple extraction methods
                token_address = None

                # Method 1: Look for address after token/chain info
                lines = self.message_content.split('\n')
                for i, line in enumerate(lines):
                    if '**Token:**' in line and '**Chain:**' in line:
                        # Check next few lines for the address
                        for j in range(i + 1, min(i + 5, len(lines))):
                            next_line = lines[j].strip()
                            if next_line:
                                # Remove any emoji or special chars and extract address
                                # Solana addresses are base58: [1-9A-HJ-NP-Za-km-z]
                                address_match = re.search(r'[1-9A-HJ-NP-Za-km-z]{32,44}', next_line)
                                if address_match:
                                    token_address = address_match.group(0)
                                    break
                        if token_address:
                            break

                # Method 2: Look for address patterns in the entire report
                if not token_address:
                    # Try to find any valid Solana address in the report
                    # Note: \b word boundary might not work with all characters, so using lookaround instead
                    all_addresses = re.findall(r'(?<![1-9A-HJ-NP-Za-km-z])[1-9A-HJ-NP-Za-km-z]{32,44}(?![1-9A-HJ-NP-Za-km-z])', self.message_content)
                    # Filter out common false positives (like transaction hashes)
                    for addr in all_addresses:
                        # Solana addresses typically end with "pump" for pump.fun tokens
                        # or have certain patterns
                        if len(addr) >= 32 and len(addr) <= 44:
                            token_address = addr
                            break

                # Method 3: Look for explicit address mentions
                if not token_address:
                    patterns = [
                        r"Address:\s*([1-9A-HJ-NP-Za-km-z]{32,44})",
                        r"Contract:\s*([1-9A-HJ-NP-Za-km-z]{32,44})",
                        r"Token Address:\s*([1-9A-HJ-NP-Za-km-z]{32,44})",
                    ]
                    for pattern in patterns:
                        match = re.search(pattern, self.message_content, re.IGNORECASE)
                        if match:
                            token_address = match.group(1)
                            break

                if not token_address:
                    # Log what we found for debugging
                    logger.error(f"Failed to extract token address. First 500 chars of report: {self.message_content[:500]}")
                    return "❌ Could not extract token address from report. Please provide token_address parameter."

            # Log successful extraction
            logger.info(f"Successfully extracted token address: {token_address}")

            # Extract token symbol
            symbol_match = re.search(r"\*\*Token:\*\*\s*\$?([A-Z0-9]+)", self.message_content, re.IGNORECASE)
            token_symbol = symbol_match.group(1).upper() if symbol_match else "UNKNOWN"

            # Check wallet balance
            wallet_address = os.getenv("DELEGATED_WALLET_ADDRESS")
            if not wallet_address:
                return "❌ No delegated wallet configured"

            wallet_manager = WalletManager(
                delegated_wallet_address=wallet_address,
                turnkey_organization_id=os.getenv("TURNKEY_ORGANIZATION_ID"),
                turnkey_api_public_key=os.getenv("TURNKEY_API_PUBLIC_KEY"),
                turnkey_api_private_key=os.getenv("TURNKEY_API_PRIVATE_KEY"),
                main_turnkey_api_public_key=os.getenv("MAIN_TURNKEY_API_PUBLIC_KEY"),
                main_turnkey_api_private_key=os.getenv("MAIN_TURNKEY_API_PRIVATE_KEY"),
                turnkey_api_base_url=os.getenv("TURNKEY_API_BASE_URL", "https://api.turnkey.com"),
                solana_rpc_url=os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
            )

            sol_balance = wallet_manager.get_sol_balance()
            if not sol_balance:
                return "❌ Could not fetch wallet balance"

            # Calculate position size (10% of balance or MAX_AMOUNT)
            max_amount = float(os.getenv("MAX_AMOUNT", "0.1"))
            swap_amount = min(sol_balance * 0.1, max_amount)

            # Convert to lamports
            amount_lamports = str(int(swap_amount * 1e9))

            # Execute swap with actual transaction
            swap_params = {
                "inputMint": "So11111111111111111111111111111111111111112",
                "outputMint": token_address,
                "amount": int(swap_amount * 1e9),
                "slippageBps": 500
            }

            result = wallet_manager.execute_swap(swap_params)

            if result.get("success"):
                tx_hash = result.get("transactionHash", "N/A")
                out_amount = int(result.get("outputAmount", 0))
                # Assume 9 decimals for most tokens
                out_formatted = out_amount / 1e9

                return f"""
🤖 **Auto-Execution Complete**

**Token:** ${token_symbol} ({token_address[:8]}...)
**Amount In:** {swap_amount:.6f} SOL
**Amount Out:** {out_formatted:.6f} {token_symbol}
**Transaction:** `{tx_hash}`
**Explorer:** https://solscan.io/tx/{tx_hash}
                """
            else:
                error = result.get("error", "Unknown error")
                return f"""
❌ **Auto-Execution Failed**

Token: ${token_symbol} ({token_address[:8]}...)
Attempted Amount: {swap_amount:.6f} SOL
Error: {error}
                """

        except Exception as e:
            logger.error(f"Error in auto-execute: {e}")
            return f"❌ Auto-execution failed: {str(e)}"