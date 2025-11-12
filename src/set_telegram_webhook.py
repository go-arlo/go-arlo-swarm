#!/usr/bin/env python3
"""
Telegram Webhook Setup Utility

Sets up the Telegram webhook URL for the GoArlo bot.
Run this script after deploying your application to register the webhook.
"""

import asyncio
import os
import sys
from dotenv import load_dotenv

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from telegram_handler import set_telegram_webhook

load_dotenv()


async def main():
    """Set up Telegram webhook"""

    # Check required environment variables
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    public_url = os.getenv('PUBLIC_URL')
    bot_name = os.getenv('BOT_NAME')

    if not bot_token:
        print("❌ TELEGRAM_BOT_TOKEN environment variable is required")
        return

    if not public_url:
        print("❌ PUBLIC_URL environment variable is required")
        print("   Example: https://your-domain.com")
        return

    if not bot_name:
        print("⚠️ BOT_NAME not set, using default: @goarlo_bot")
        bot_name = "@goarlo_bot"

    print("🔧 Setting up Telegram webhook...")
    print(f"   Bot Token: {bot_token[:10]}...{bot_token[-4:]}")
    print(f"   Bot Name: {bot_name}")
    print(f"   Public URL: {public_url}")
    print()

    # Remove trailing slash from public URL if present
    public_url = public_url.rstrip('/')

    try:
        result = await set_telegram_webhook(public_url)

        if result.get('ok'):
            print("✅ Webhook setup successful!")
            webhook_info = result.get('result', {})
            if webhook_info:
                print(f"   Webhook URL: {webhook_info}")
            print()
            print("🤖 Your Telegram bot is now ready to receive messages!")
            print(f"   Users can mention {bot_name} with token addresses or $SYMBOLS")
            print("   Example: '@your_bot $SOL' or '@your_bot So11111111111111111111111111111111111111112'")
        else:
            print("❌ Webhook setup failed!")
            print(f"   Error: {result.get('description', 'Unknown error')}")
            if result.get('error_code'):
                print(f"   Error Code: {result['error_code']}")

    except Exception as e:
        print(f"❌ Error setting up webhook: {str(e)}")


if __name__ == "__main__":
    asyncio.run(main())