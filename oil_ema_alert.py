#!/usr/bin/env python3
"""
Oil EMA Cross Alert — 9/21 EMA on 5m and 15m WTI charts.
- Alerts on fresh 5m cross
- Alerts on fresh 15m cross
- Alerts "CONFIRMED" when both timeframes cross in the same direction
State is stored in state.json and committed back to the repo.
"""

import json
import os
import sys
from datetime import timezone, timedelta
import requests
import yfinance as yf

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
SYMBOL = "CL=F"
STATE_FILE = "state.json"
OSLO = timezone(timedelta(hours=2))


def send_telegram(message: str) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message}, timeout=10)


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {
        "5m": {"last_cross": None, "last_cross_time": None},
        "15m": {"last_cross": None, "last_cross_time": None},
        "confirmed_time": None,
    }


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def to_oslo(ts) -> str:
    try:
        return ts.to_pydatetime().astimezone(OSLO).strftime("%d %b  %H:%M")
    except Exception:
        return str(ts)


def get_ema_data(interval: str):
    period = "5d" if interval == "15m" else "3d"
    df = yf.download(SYMBOL, period=period, interval=interval, progress=False, auto_adjust=True)
    if df.empty or len(df) < 30:
        return None
    close = df["Close"].squeeze()
    ema9  = close.ewm(span=9,  adjust=False).mean()
    ema21 = close.ewm(span=21, adjust=False).mean()
    return {
        "prev_9":   float(ema9.iloc[-3]),
        "prev_21":  float(ema21.iloc[-3]),
        "curr_9":   float(ema9.iloc[-2]),
        "curr_21":  float(ema21.iloc[-2]),
        "price":    float(close.iloc[-2]),
        "time":     str(df.index[-2]),
        "time_fmt": to_oslo(df.index[-2]),
    }


def detect_cross(data: dict):
    if data["prev_9"] < data["prev_21"] and data["curr_9"] > data["curr_21"]:
        return "bullish"
    if data["prev_9"] > data["prev_21"] and data["curr_9"] < data["curr_21"]:
        return "bearish"
    return None


def current_direction(data: dict) -> str:
    return "bullish" if data["curr_9"] > data["curr_21"] else "bearish"


def main():
    data_5m  = get_ema_data("5m")
    data_15m = get_ema_data("15m")

    if not data_5m or not data_15m:
        print("Not enough data.", file=sys.stderr)
        sys.exit(1)

    state     = load_state()
    cross_5m  = detect_cross(data_5m)
    cross_15m = detect_cross(data_15m)

    # 5m alert
    if cross_5m and state["5m"]["last_cross_time"] != data_5m["time"]:
        icon      = "📈" if cross_5m == "bullish" else "📉"
        direction = "ABOVE" if cross_5m == "bullish" else "BELOW"
        send_telegram(
            f"{icon} OIL 5m EMA CROSS — {cross_5m.upper()}\n"
            f"9 EMA crossed {direction} 21 EMA\n"
            f"Price: ${data_5m['price']:.2f}\n"
            f"Time: {data_5m['time_fmt']} (Oslo)"
        )
        print(f"Sent 5m {cross_5m} alert")
        state["5m"]["last_cross"] = cross_5m
        state["5m"]["last_cross_time"] = data_5m["time"]

    # 15m alert
    if cross_15m and state["15m"]["last_cross_time"] != data_15m["time"]:
        icon      = "📈" if cross_15m == "bullish" else "📉"
        direction = "ABOVE" if cross_15m == "bullish" else "BELOW"
        send_telegram(
            f"{icon} OIL 15m EMA CROSS — {cross_15m.upper()}\n"
            f"9 EMA crossed {direction} 21 EMA\n"
            f"Price: ${data_15m['price']:.2f}\n"
            f"Time: {data_15m['time_fmt']} (Oslo)"
        )
        print(f"Sent 15m {cross_15m} alert")
        state["15m"]["last_cross"] = cross_15m
        state["15m"]["last_cross_time"] = data_15m["time"]

    # Confirmation alert
    dir_5m      = current_direction(data_5m)
    dir_15m     = current_direction(data_15m)
    fresh_cross = cross_5m or cross_15m
    aligned     = dir_5m == dir_15m
    confirm_key = f"{dir_5m}_{data_5m['time']}_{data_15m['time']}"

    if fresh_cross and aligned and state.get("confirmed_time") != confirm_key:
        icon = "✅📈" if dir_5m == "bullish" else "✅📉"
        send_telegram(
            f"{icon} OIL EMA CROSS CONFIRMED — {dir_5m.upper()}\n"
            f"Both 5m and 15m EMAs aligned {dir_5m}\n"
            f"5m Price:  ${data_5m['price']:.2f}  |  15m Price: ${data_15m['price']:.2f}\n"
            f"5m EMA9: {data_5m['curr_9']:.3f}  |  15m EMA9: {data_15m['curr_9']:.3f}"
        )
        print(f"Sent CONFIRMED {dir_5m} alert")
        state["confirmed_time"] = confirm_key

    if not fresh_cross:
        print(
            f"No cross. "
            f"5m diff={data_5m['curr_9'] - data_5m['curr_21']:.3f} | "
            f"15m diff={data_15m['curr_9'] - data_15m['curr_21']:.3f}"
        )

    save_state(state)


if __name__ == "__main__":
    main()
