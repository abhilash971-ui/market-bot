"""
market_report.py
================
Runs every weekday at 8:45 AM on PythonAnywhere.
1. Reads fresh Upstox access token from token.txt
2. Scans Nifty 50 stocks for best setups today
3. Runs Technical + Sentiment analysis via Claude API
4. Sends clean report to your Telegram
"""

import os
import json
import requests
from datetime import datetime
from dotenv import load_dotenv

# Load credentials
load_dotenv("credentials.env")

BOT_TOKEN       = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID         = os.getenv("TELEGRAM_CHAT_ID")
ANTHROPIC_KEY   = os.getenv("ANTHROPIC_API_KEY")

# ============================================
# NIFTY 50 STOCK LIST
# ============================================
NIFTY_50 = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
    "HINDUNILVR", "ITC", "SBIN", "BHARTIARTL", "KOTAKBANK",
    "LT", "AXISBANK", "ASIANPAINT", "MARUTI", "SUNPHARMA",
    "TITAN", "BAJFINANCE", "WIPRO", "ULTRACEMCO", "NESTLEIND",
    "POWERGRID", "NTPC", "M&M", "TECHM", "HCLTECH",
    "BAJAJFINSV", "TATAMOTORS", "ADANIENT", "ADANIPORTS", "COALINDIA",
    "ONGC", "JSWSTEEL", "TATASTEEL", "GRASIM", "CIPLA",
    "BPCL", "DRREDDY", "EICHERMOT", "DIVISLAB", "HEROMOTOCO",
    "HINDALCO", "INDUSINDBK", "SBILIFE", "BRITANNIA", "APOLLOHOSP",
    "TATACONSUM", "HDFCLIFE", "UPL", "LTIM", "SHRIRAMFIN"
]


# ============================================
# HELPER FUNCTIONS
# ============================================

def load_token():
    """Read access token saved by token_refresh.py"""
    try:
        with open("token.txt", "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        raise Exception("token.txt not found. Token refresh may have failed.")


def send_telegram(message):
    """Send message to Telegram."""
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        # Telegram has 4096 char limit per message
        # Split if needed
        if len(message) <= 4096:
            requests.post(url, data={
                "chat_id": CHAT_ID,
                "text": message,
                "parse_mode": "HTML"
            })
        else:
            chunks = [message[i:i+4096] for i in range(0, len(message), 4096)]
            for chunk in chunks:
                requests.post(url, data={
                    "chat_id": CHAT_ID,
                    "text": chunk,
                    "parse_mode": "HTML"
                })
    except Exception as e:
        print(f"Telegram error: {e}")


def get_stock_data(token, symbol):
    """Fetch live quote from Upstox for a stock."""
    try:
        url = f"https://api.upstox.com/v2/market-quote/quotes"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json"
        }
        params = {"symbol": f"NSE_EQ|{symbol}"}
        response = requests.get(url, headers=headers, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return data.get("data", {})
        return None
    except Exception as e:
        print(f"Error fetching {symbol}: {e}")
        return None


def get_historical_data(token, symbol):
    """Fetch historical OHLCV data for technical analysis."""
    try:
        url = f"https://api.upstox.com/v2/historical-candle/NSE_EQ|{symbol}/day/2024-01-01"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json"
        }
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            candles = data.get("data", {}).get("candles", [])
            return candles[-60:] if len(candles) >= 60 else candles
        return []
    except Exception as e:
        print(f"Historical data error for {symbol}: {e}")
        return []


def calculate_rsi(candles, period=14):
    """Calculate RSI from candle data."""
    if len(candles) < period + 1:
        return None
    closes = [c[4] for c in candles]
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def calculate_sma(candles, period):
    """Calculate Simple Moving Average."""
    if len(candles) < period:
        return None
    closes = [c[4] for c in candles[-period:]]
    return round(sum(closes) / period, 2)


def calculate_macd(candles):
    """Calculate MACD line and signal."""
    if len(candles) < 26:
        return None, None
    closes = [c[4] for c in candles]

    def ema(data, period):
        k = 2 / (period + 1)
        ema_val = data[0]
        for price in data[1:]:
            ema_val = price * k + ema_val * (1 - k)
        return ema_val

    ema12 = ema(closes[-26:], 12)
    ema26 = ema(closes[-26:], 26)
    macd_line = round(ema12 - ema26, 2)

    # Signal line (9 period EMA of MACD)
    macd_values = []
    for i in range(9, len(closes)):
        e12 = ema(closes[i-25:i+1], 12)
        e26 = ema(closes[i-25:i+1], 26)
        macd_values.append(e12 - e26)

    signal = round(ema(macd_values, 9), 2) if macd_values else None
    return macd_line, signal


def scan_and_shortlist(token):
    """
    Scan all Nifty 50 stocks.
    Calculate RSI, MACD, SMA for each.
    Return top 5 stocks with best setups.
    """
    print("Scanning Nifty 50 stocks...")
    candidates = []

    for symbol in NIFTY_50:
        try:
            candles = get_historical_data(token, symbol)
            if not candles:
                continue

            rsi = calculate_rsi(candles)
            sma50 = calculate_sma(candles, 50)
            sma200 = calculate_sma(candles, 200)
            macd, signal = calculate_macd(candles)
            current_price = candles[-1][4] if candles else None

            if not all([rsi, sma50, macd, signal, current_price]):
                continue

            # Scoring system
            score = 0

            # RSI scoring
            if 25 <= rsi <= 40:
                score += 3   # Oversold — best buy zone
            elif 40 < rsi <= 55:
                score += 2   # Neutral bullish
            elif rsi < 25:
                score += 1   # Too oversold — risky
            elif rsi > 70:
                score -= 2   # Overbought — avoid

            # MACD scoring
            if macd > signal:
                score += 2   # Bullish crossover
            elif macd > 0:
                score += 1   # Positive momentum

            # SMA scoring
            if current_price > sma50:
                score += 2   # Above 50 DMA — bullish
            if sma200 and current_price > sma200:
                score += 1   # Above 200 DMA — strong trend

            candidates.append({
                "symbol": symbol,
                "score": score,
                "rsi": rsi,
                "macd": macd,
                "signal": signal,
                "sma50": sma50,
                "sma200": sma200,
                "price": current_price
            })

        except Exception as e:
            print(f"Error scanning {symbol}: {e}")
            continue

    # Sort by score and return top 5
    candidates.sort(key=lambda x: x["score"], reverse=True)
    top5 = candidates[:5]
    print(f"Top 5 stocks selected: {[s['symbol'] for s in top5]}")
    return top5


def analyse_with_claude(stocks_data):
    """
    Send stock data to Claude API for 
    deep technical + sentiment analysis.
    Returns formatted report.
    """
    today = datetime.now().strftime("%d %b %Y")

    # Build the prompt
    stocks_text = json.dumps(stocks_data, indent=2)

    prompt = f"""
You are an expert Indian stock market analyst specialising in NSE stocks.

Today is {today}. Indian market opens at 9:15 AM IST.

I have scanned the entire Nifty 50 and shortlisted these top 5 stocks based on 
technical indicators. Here is the data:

{stocks_text}

For each stock please do the following:

1. TECHNICAL ANALYSIS
   - Interpret RSI value (oversold/neutral/overbought)
   - Interpret MACD vs Signal (bullish/bearish crossover)
   - Interpret price vs SMA50 and SMA200 (trend direction)
   - Give Technical Score out of 10

2. SENTIMENT ANALYSIS
   - Based on your knowledge of recent news, FII activity, 
     sector trends for this stock
   - Any upcoming events, results, or risks
   - Give Sentiment Score out of 10

3. FINAL SIGNAL
   - BUY / AVOID / WAIT
   - Trade Type: Positional (2-4 weeks) or Swing (2-5 days)
   - Entry Price (use current price with small buffer)
   - Target Price (realistic upside %)
   - Stop Loss (strict downside protection)
   - Reason in 2 simple lines

4. OVERALL MARKET MOOD
   - One paragraph on what the market is likely to do today
   - Any global cues to watch

Format the output cleanly for Telegram with emojis.
Use 🟢 for BUY, 🔴 for AVOID, 🟡 for WAIT.
Keep language simple — the reader is a busy professor 
who has only 10 minutes to read and act.
"""

    # Call Claude API
    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        },
        json={
            "model": "claude-sonnet-4-6",
            "max_tokens": 2000,
            "messages": [{"role": "user", "content": prompt}]
        },
        timeout=60
    )

    if response.status_code == 200:
        data = response.json()
        return data["content"][0]["text"]
    else:
        raise Exception(f"Claude API error: {response.status_code} - {response.text}")


def main():
    today = datetime.now().strftime("%d %b %Y")
    print(f"Starting market report for {today}...")

    try:
        # Step 1 — Load token
        token = load_token()
        print("Token loaded.")

        # Step 2 — Scan Nifty 50 and shortlist top 5
        top_stocks = scan_and_shortlist(token)

        if not top_stocks:
            send_telegram("⚠️ No strong setups found today. Stay in cash.")
            return

        # Step 3 — Analyse with Claude
        print("Running Claude analysis...")
        report = analyse_with_claude(top_stocks)

        # Step 4 — Format final message
        header = f"📊 <b>Morning Market Report</b>\n📅 {today}\n{'━'*30}\n\n"
        footer = f"\n\n{'━'*30}\n⚠️ <i>This is analysis only. Always use stop loss. Trade at your own risk.</i>"
        full_report = header + report + footer

        # Step 5 — Send to Telegram
        send_telegram(full_report)
        print("Report sent to Telegram successfully.")

    except Exception as e:
        error_msg = f"❌ Market report failed: {str(e)}"
        print(error_msg)
        send_telegram(error_msg)


if __name__ == "__main__":
    main()
