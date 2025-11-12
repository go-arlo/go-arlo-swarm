#!/usr/bin/env python3
"""
Telegram Integration Module for GoArlo Crypto Summary Bot

Handles Telegram webhook requests, message parsing, token search, and response formatting.
Provides intelligent handling of addresses, cashtags, and multiple results.
"""

import os
import re
import asyncio
import aiohttp
from typing import Dict, Any, Optional, List, Tuple
from fastapi import Request
from dotenv import load_dotenv

from token_search import search_tokens, TokenSearchResult, SUPPORTED_CHAINS
# Avoid circular import - analyze_token and format_analysis_for_twitter imported lazily in functions

load_dotenv()


class TelegramHandler:
    """Handles Telegram webhook processing and message responses"""

    def __init__(self):
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.bot_name = os.getenv('BOT_NAME', '@goarlo_bot')  # Default bot name
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}"

        if not self.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")

    async def process_webhook(self, request: Request) -> Dict[str, Any]:
        """
        Process incoming Telegram webhook request.

        Args:
            request: FastAPI Request object containing webhook data

        Returns:
            Dict with success status
        """
        try:
            update = await request.json()
            print(f"Received Telegram update: {update}")

            # Extract message (can be regular message or channel post)
            message = update.get("message") or update.get("channel_post")
            if not message:
                return {"ok": True}

            chat_id = message["chat"]["id"]
            text = message.get("text", "")
            message_id = message["message_id"]

            # Check if bot is mentioned
            if not self._is_bot_mentioned(message, text):
                return {"ok": True}

            print(f"Bot mentioned in message: {text}")

            # Parse token information from message
            parse_result = await self._parse_token_from_message(text)

            if not parse_result["found"]:
                # Only reply if we found a mention but no valid token data
                if parse_result.get("should_reply", False):
                    await self._send_message(
                        chat_id,
                        parse_result["message"],
                        message_id
                    )
                return {"ok": True}

            # Send acknowledgment
            await self._send_message(
                chat_id,
                "Copy that. Will reply with the report shortly.",
                message_id
            )

            # Perform analysis
            token_data = parse_result["token_data"]
            await self._perform_analysis_and_reply(
                token_data,
                chat_id,
                message_id
            )

        except Exception as e:
            print(f"Error processing Telegram webhook: {str(e)}")
            if 'chat_id' in locals() and 'message_id' in locals():
                await self._send_message(
                    chat_id,
                    "Sorry, I encountered an error processing your request.",
                    message_id
                )

        return {"ok": True}

    def _is_bot_mentioned(self, message: Dict[str, Any], text: str) -> bool:
        """
        Check if the bot is mentioned in the message.

        Args:
            message: Telegram message object
            text: Message text

        Returns:
            True if bot is mentioned
        """
        # Check entities for mentions
        for entity in message.get("entities", []):
            if entity["type"] == "mention":
                mention_text = text[entity["offset"]:entity["offset"]+entity["length"]]
                if mention_text.lower() == self.bot_name.lower():
                    return True

        # Also check for bot name in text (fallback)
        return self.bot_name.lower() in text.lower()

    async def _parse_token_from_message(self, text: str) -> Dict[str, Any]:
        """
        Parse token address or symbol from message text with intelligent handling.

        Args:
            text: Message text to parse

        Returns:
            Dict with parsing results and token data
        """
        # Priority 1: Look for contract addresses (32-44 characters alphanumeric)
        address_pattern = r'\b[a-zA-Z0-9]{32,44}\b'
        address_matches = re.findall(address_pattern, text)

        if address_matches:
            # Use first address if multiple found
            contract_address = address_matches[0]
            print(f"Found contract address: {contract_address}")

            search_results = await search_tokens(contract_address, search_by="address")

            if not search_results:
                return {
                    "found": False,
                    "should_reply": True,
                    "message": f"⚠️ No verified token found for address: {contract_address}"
                }

            # Filter for supported chains and use first result
            supported_token = self._get_first_supported_token(search_results)
            if not supported_token:
                return {
                    "found": False,
                    "should_reply": True,
                    "message": f"⚠️ Token address found but chain not supported. Supported chains: {', '.join(SUPPORTED_CHAINS)}"
                }

            return {
                "found": True,
                "token_data": supported_token,
                "search_type": "address"
            }

        # Priority 2: Look for cashtags ($TOKEN)
        cashtag_pattern = r'\$([A-Za-z0-9]+)(?=[\s.,!?]|$)'
        cashtag_matches = re.findall(cashtag_pattern, text)

        if cashtag_matches:
            # Use first cashtag if multiple found
            token_symbol = cashtag_matches[0]
            print(f"Found cashtag: ${token_symbol}")

            search_results = await search_tokens(token_symbol, search_by="symbol")

            if not search_results:
                return {
                    "found": False,
                    "should_reply": True,
                    "message": f"⚠️ No verified token found for symbol: ${token_symbol}"
                }

            # Try to find exact symbol match first, then any supported token
            token_data = self._find_best_symbol_match(search_results, token_symbol)
            if not token_data:
                return {
                    "found": False,
                    "should_reply": True,
                    "message": f"⚠️ Token symbol found but chain not supported. Supported chains: {', '.join(SUPPORTED_CHAINS)}"
                }

            return {
                "found": True,
                "token_data": token_data,
                "search_type": "symbol"
            }

        # No valid token data found, but don't reply (ignore silently)
        return {
            "found": False,
            "should_reply": False,
            "message": ""
        }

    def _get_first_supported_token(self, search_results: List[TokenSearchResult]) -> Optional[Dict[str, Any]]:
        """
        Get first token from supported chain.

        Args:
            search_results: List of search results

        Returns:
            Token data dict or None
        """
        for token in search_results:
            if token.network.lower() in SUPPORTED_CHAINS:
                return {
                    "name": token.name,
                    "symbol": token.symbol,
                    "address": token.address,
                    "chain": token.network.lower()
                }
        return None

    def _find_best_symbol_match(self, search_results: List[TokenSearchResult], symbol: str) -> Optional[Dict[str, Any]]:
        """
        Find best matching token for symbol, preferring exact matches from supported chains.

        Args:
            search_results: List of search results
            symbol: Target symbol

        Returns:
            Token data dict or None
        """
        # First pass: exact symbol match on supported chain
        for token in search_results:
            if (token.symbol.upper() == symbol.upper() and
                token.network.lower() in SUPPORTED_CHAINS):
                return {
                    "name": token.name,
                    "symbol": token.symbol,
                    "address": token.address,
                    "chain": token.network.lower()
                }

        # Second pass: any supported chain
        for token in search_results:
            if token.network.lower() in SUPPORTED_CHAINS:
                return {
                    "name": token.name,
                    "symbol": token.symbol,
                    "address": token.address,
                    "chain": token.network.lower()
                }

        return None

    async def _perform_analysis_and_reply(
        self,
        token_data: Dict[str, Any],
        chat_id: int,
        message_id: int
    ) -> None:
        """
        Perform token analysis and send formatted reply.

        Args:
            token_data: Token information dict
            chat_id: Telegram chat ID
            message_id: Original message ID to reply to
        """
        try:
            # Lazy imports to avoid circular dependency
            from main import analyze_token_with_cache, format_analysis_for_twitter
            
            print(f"Starting analysis for {token_data['symbol']} on {token_data['chain']}")

            # Perform token analysis (with caching and deduplication)
            analysis_result = await analyze_token_with_cache(
                token_address=token_data["address"],
                chain=token_data["chain"],
                token_symbol=token_data["symbol"]
            )

            if not analysis_result["success"]:
                await self._send_message(
                    chat_id,
                    f"❌ Analysis failed for ${token_data['symbol']}: {analysis_result['error']}",
                    message_id
                )
                return

            # Format analysis for Telegram (same as Twitter)
            data = analysis_result["data"]
            formatted_analysis = format_analysis_for_twitter(
                analysis_response=data["analysis_response"],
                token_info=data["token_info"],
                market_data=data["market_data"],
                analysis_data=data
            )

            # Send formatted analysis
            await self._send_message(chat_id, formatted_analysis, message_id)
            print(f"Successfully sent analysis for {token_data['symbol']}")

        except Exception as e:
            print(f"Error during analysis for {token_data['symbol']}: {str(e)}")
            await self._send_message(
                chat_id,
                f"❌ Sorry, analysis failed for ${token_data['symbol']}. Please try again later.",
                message_id
            )

    async def _send_message(
        self,
        chat_id: int,
        text: str,
        reply_to_message_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Send message via Telegram Bot API.

        Args:
            chat_id: Telegram chat ID
            text: Message text
            reply_to_message_id: Optional message ID to reply to

        Returns:
            API response dict
        """
        url = f"{self.api_url}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text
            # No parse_mode - send as plain text to avoid markdown parsing errors
        }

        if reply_to_message_id:
            payload["reply_to_message_id"] = reply_to_message_id

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    result = await response.json()
                    if not result.get('ok'):
                        print(f"Telegram API error: {result}")
                    return result
        except Exception as e:
            print(f"Error sending Telegram message: {str(e)}")
            return {"ok": False, "error": str(e)}


# Global handler instance (only initialize if token is available)
telegram_handler = None
try:
    if os.getenv('TELEGRAM_BOT_TOKEN'):
        telegram_handler = TelegramHandler()
except Exception as e:
    print(f"Warning: Telegram handler initialization failed: {e}")
    telegram_handler = None


# Webhook setup utility function
async def set_telegram_webhook(public_url: str) -> Dict[str, Any]:
    """
    Set Telegram webhook URL.

    Args:
        public_url: Public URL of the application

    Returns:
        API response dict
    """
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")

    webhook_url = f"{public_url}/webhook/telegram"
    api_url = f"https://api.telegram.org/bot{bot_token}/setWebhook"

    payload = {"url": webhook_url}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(api_url, json=payload) as response:
                result = await response.json()
                print(f"Setting Telegram webhook to: {webhook_url}")
                print(f"Webhook setup response: {result}")
                return result
    except Exception as e:
        print(f"Error setting webhook: {str(e)}")
        return {"ok": False, "error": str(e)}


if __name__ == "__main__":
    # Test the handler
    import asyncio

    async def test_parse():
        handler = TelegramHandler()

        # Test cases
        test_messages = [
            "@goarlo_bot check $SOL",
            "@goarlo_bot analyze So11111111111111111111111111111111111111112",
            "@goarlo_bot what about $PEPE and $DOGE",
            "@goarlo_bot So11111111111111111111111111111111111111112 and EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            "@goarlo_bot hello there"
        ]

        for msg in test_messages:
            print(f"\nTesting: {msg}")
            result = await handler._parse_token_from_message(msg)
            print(f"Result: {result}")

    asyncio.run(test_parse())