"""
token_refresh.py - Fixed version with proper URL encoding
"""

import os
import re
import time
import requests
from urllib.parse import quote

# Read from environment variables
API_KEY      = os.environ.get("UPSTOX_API_KEY", "")
SECRET_KEY   = os.environ.get("UPSTOX_SECRET_KEY", "")
REDIRECT_URL = os.environ.get("UPSTOX_REDIRECT_URL", "")
BOT_TOKEN    = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID      = os.environ.get("TELEGRAM_CHAT_ID", "")

def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        response = requests.post(url, data={
            "chat_id": CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }, timeout=10)
        print(f"Telegram response: {response.status_code}")
        print(f"Telegram sent: {message[:80]}")
    except Exception as e:
        print(f"Telegram error: {e}")

def get_telegram_updates(offset=None):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
        params = {"timeout": 10}
        if offset:
            params["offset"] = offset
        response = requests.get(url, params=params, timeout=15)
        if response.status_code == 200:
            return response.json().get("result", [])
        return []
    except Exception as e:
        print(f"Error getting updates: {e}")
        return []

def wait_for_auth_code(timeout_minutes=10):
    print(f"Waiting for auth code via Telegram...")
    updates = get_telegram_updates()
    offset = None
    if updates:
        offset = updates[-1]["update_id"] + 1

    timeout_seconds = timeout_minutes * 60
    elapsed = 0
    check_interval = 5

    while elapsed < timeout_seconds:
        time.sleep(check_interval)
        elapsed += check_interval

        updates = get_telegram_updates(offset)
        for update in updates:
            offset = update["update_id"] + 1
            message = update.get("message", {})
            text = message.get("text", "")
            chat_id = str(message.get("chat", {}).get("id", ""))

            if chat_id != str(CHAT_ID):
                continue

            print(f"Received: {text[:100]}")

            # Extract code from full URL
            code_match = re.search(r"code=([^&\s]+)", text)
            if code_match:
                return code_match.group(1)

            # Accept raw code
            if len(text) > 20 and " " not in text and "=" not in text:
                return text.strip()

        remaining = timeout_seconds - elapsed
        if elapsed % 60 == 0 and remaining > 0:
            send_telegram(
                f"⏳ Still waiting for your login...\n"
                f"Time remaining: {int(remaining/60)} minutes"
            )

    return None

def get_access_token(auth_code):
    print("Getting access token...")
    url = "https://api.upstox.com/v2/login/authorization/token"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json"
    }
    data = {
        "code": auth_code,
        "client_id": API_KEY,
        "client_secret": SECRET_KEY,
        "redirect_uri": REDIRECT_URL,
        "grant_type": "authorization_code"
    }
    response = requests.post(url, headers=headers, data=data, timeout=30)
    print(f"Token response: {response.status_code} - {response.text[:200]}")
    if response.status_code == 200:
        token = response.json().get("access_token")
        if token:
            return token
        raise Exception(f"No token: {response.json()}")
    else:
        raise Exception(f"Token failed: {response.status_code} - {response.text}")

def save_token(token):
    with open("token.txt", "w") as f:
        f.write(token)
    print("Token saved.")

def main():
    print("=" * 50)
    print("Starting token refresh...")
    print(f"API_KEY present: {bool(API_KEY)}")
    print(f"API_KEY value: {API_KEY}")
    print(f"SECRET_KEY present: {bool(SECRET_KEY)}")
    print(f"REDIRECT_URL: {REDIRECT_URL}")
    print(f"BOT_TOKEN present: {bool(BOT_TOKEN)}")
    print(f"CHAT_ID: {CHAT_ID}")
    print("=" * 50)

    try:
        # Build login URL with proper encoding
        encoded_redirect = quote(REDIRECT_URL, safe='')
        auth_url = (
            f"https://api.upstox.com/v2/login/authorization/dialog"
            f"?response_type=code"
            f"&client_id={API_KEY}"
            f"&redirect_uri={encoded_redirect}"
        )

        print(f"Auth URL: {auth_url}")

        # Send to Telegram
        send_telegram(
            f"🔐 <b>Good Morning Abhilash!</b>\n\n"
            f"Tap below to login to Upstox:\n\n"
            f"{auth_url}\n\n"
            f"After login — copy the full URL from browser address bar and paste it here.\n\n"
            f"⏰ You have 10 minutes."
        )

        # Wait for auth code
        auth_code = wait_for_auth_code(timeout_minutes=10)

        if not auth_code:
            send_telegram("❌ Login timeout. No code received. Try again tomorrow.")
            return

        print(f"Auth code received.")

        # Get token
        access_token = get_access_token(auth_code)
        save_token(access_token)

        send_telegram(
            "✅ <b>Login successful!</b>\n\n"
            "📊 Market analysis starting at 8:45 AM.\n"
            "Report will arrive before 9:00 AM.\n\n"
            "☕ Enjoy your commute!"
        )
        print("Done.")

    except Exception as e:
        error_msg = f"❌ Token refresh failed: {str(e)}"
        print(error_msg)
        send_telegram(error_msg)

if __name__ == "__main__":
    main()
