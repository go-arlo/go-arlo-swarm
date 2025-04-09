import requests
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
PUBLIC_URL = os.getenv("PUBLIC_URL")

def set_webhook():
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook"
    webhook_url = f"{PUBLIC_URL}/webhook/telegram"
    
    response = requests.post(url, json={"url": webhook_url})
    print(f"Setting webhook to: {webhook_url}")
    print(f"Response: {response.json()}")

if __name__ == "__main__":
    set_webhook() 