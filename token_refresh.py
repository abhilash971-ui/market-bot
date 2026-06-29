"""
token_refresh.py
================
Runs every weekday at 8:00 AM on PythonAnywhere.

HOW IT WORKS:
1. Sends you a Telegram message with Upstox login link
2. You tap the link on your phone and login (30 seconds)
3. After login Upstox redirects to your redirect URL
4. You copy the "code" from that URL and send it to Telegram bot
5. Script captures the code and gets your access token automatically
6. Sends confirmation and market report runs at 8:45 AM
"""

import os
import re
import time
import requests
from dotenv import load_dotenv

# Load credentials
load_dotenv("credentials.env")

API_KEY       = os.getenv("UPSTOX_API_KEY")
SECRET_KEY    = os.getenv("UPSTOX_SECRET_KEY")
REDIRECT_URL  = os.getenv("UPSTOX_REDIRECT_URL")
BOT_TOKEN     = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID       = os.getenv("TELEGRAM_CHAT_ID")


def send_telegram(message):
    """Send a message to Telegram."""
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, data={
            "chat_id": CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }, timeout=10)
        print(f"Telegram sent: {message[:50]}...")
    except Exception as e:
        print(f"Telegram error: {e}")


def get_telegram_updates(offset=None):
    """Check for new messages sent to bot."""
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
    """
    Wait for user to send the auth code via Telegram.
    User pastes the full redirect URL or just the code.
    Waits up to timeout_minutes before giving up.
    """
    print(f"Waiting for auth code via Telegram (timeout: {timeout_minutes} mins)...")
    
    # Get current update offset to ignore old messages
    updates = get_telegram_updates()
    offset = None
    if updates:
        offset = updates[-1]["update_id"] + 1

    timeout_seconds = timeout_minutes * 60
    elapsed = 0
    check_interval = 5  # Check every 5 seconds

    while elapsed < timeout_seconds:
        time.sleep(check_interval)
        elapsed += check_interval

        updates = get_telegram_updates(offset)
        for update in updates:
            offset = update["update_id"] + 1
            message = update.get("message", {})
            text = message.get("text", "")
            chat_id = str(message.get("chat", {}).get("id", ""))

            # Only accept messages from your chat
            if chat_id != str(CHAT_ID):
                continue

            print(f"Received message: {text[:100]}")

            # Try to extract auth code from full URL
            code_match = re.search(r"code=([^&\s]+)", text)
            if code_match:
                return code_match.group(1)

            # Accept if user sends just the code directly
            # Auth codes are typically long alphanumeric strings
            if len(text) > 20 and " " not in text and "=" not in text:
                return text.strip()

        remaining = timeout_seconds - elapsed
        if elapsed % 60 == 0 and remaining > 0:  # Reminder every minute
            send_telegram(
                f"⏳ Still waiting for your login...\n"
                f"Time remaining: {int(remaining/60)} minutes\n"
                f"Please complete login and send the code."
            )

    return None


def get_access_token(auth_code):
    """Exchange authorization code for access token."""
    print("Exchanging auth code for access token...")
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
    print(f"Token response: {response.status_code}")

    if response.status_code == 200:
        token = response.json().get("access_token")
        if token:
            return token
        raise Exception(f"No token in response: {response.json()}")
    else:
        raise Exception(f"Token failed: {response.status_code} - {response.text}")


def save_token(token):
    """Save token to file."""
    with open("token.txt", "w") as f:
        f.write(token)
    print("Token saved to token.txt")


def main():
    print("=" * 50)
    print("Starting token refresh...")
    print("=" * 50)

    try:
        # Step 1 — Build Upstox login URL
        auth_url = (
            f"https://api.upstox.com/v2/login/authorization/dialog"
            f"?response_type=code"
            f"&client_id={API_KEY}"
            f"&redirect_uri={REDIRECT_URL}"
        )

        # Step 2 — Send login link to Telegram
        send_telegram(
            f"🔐 <b>Good Morning!</b>\n\n"
            f"Tap the link below to login to Upstox:\n\n"
            f"{auth_url}\n\n"
            f"After login your browser will show a page.\n"
            f"Copy the full URL from browser address bar.\n"
            f"Paste it here in this chat.\n\n"
            f"⏰ You have 10 minutes."
        )
        print("Login link sent to Telegram.")

        # Step 3 — Wait for user to send auth code
        auth_code = wait_for_auth_code(timeout_minutes=10)

        if not auth_code:
            send_telegram(
                "❌ Login timeout. No code received.\n"
                "Market report will not run today.\n"
                "Please try again tomorrow."
            )
            return

        print(f"Auth code received.")

        # Step 4 — Exchange for access token
        access_token = get_access_token(auth_code)
        print("Access token received.")

        # Step 5 — Save token
        save_token(access_token)

        # Step 6 — Confirm success
        send_telegram(
            "✅ <b>Login successful!</b>\n\n"
            "📊 Market analysis starting at 8:45 AM.\n"
            "Report will arrive before 9:00 AM.\n\n"
            "☕ Enjoy your commute!"
        )
        print("Token refresh complete.")

    except Exception as e:
        error_msg = f"❌ Token refresh failed.\nError: {str(e)}"
        print(error_msg)
        send_telegram(error_msg)


if __name__ == "__main__":
    main()
