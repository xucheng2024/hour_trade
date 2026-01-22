#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compare backtest with and without 2-hour gain filter
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Dict

import numpy as np

# Add ex_okx to path
sys.path.insert(0, "/Users/mac/Downloads/stocks/ex_okx")
sys.path.insert(0, os.path.join("/Users/mac/Downloads/stocks/ex_okx", "src"))

from strategies.historical_data_loader import get_historical_data_loader  # noqa: E402

LIMITS_FILE = "valid_crypto_limits.json"
with open(LIMITS_FILE, "r") as f:
    limits_data = json.load(f)
    crypto_limits = limits_data["cryptos"]

BUY_FEE = 0.001
SELL_FEE = 0.001
GAIN_THRESHOLD = 5.0
LOOKBACK_HOURS = 2


def backtest_crypto_with_filter(
    instId: str, limit_percent: float, days: int = 30, use_filter: bool = True
) -> Dict:
    """Backtest with or without 2-hour gain filter"""
    loader = get_historical_data_loader()

    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)

    df = loader.get_data_for_date_range(
        instId,
        days,
        bar="1H",
        return_dataframe=True,
        start_date=start_date,
        end_date=end_date,
    )

    if df is None or len(df) < 3:
        return {"instId": instId, "total_trades": 0, "error": "Insufficient data"}

    df = df.sort_values("timestamp").reset_index(drop=True)
    trades = []
    limit_ratio = limit_percent / 100.0

    for i in range(len(df) - 1):
        hour_data = df.iloc[i]
        next_hour_data = df.iloc[i + 1]

        open_price = hour_data["open"]
        low_price = hour_data["low"]
        next_close = next_hour_data["close"]

        limit_buy_price = open_price * limit_ratio

        if low_price > limit_buy_price:
            continue

        # Apply 2-hour gain filter if enabled
        if use_filter:
            if i < LOOKBACK_HOURS:
                continue
            close_2h_ago = df.iloc[i - LOOKBACK_HOURS]["close"]
            if close_2h_ago > 0:
                gain_pct = ((open_price - close_2h_ago) / close_2h_ago) * 100
                if gain_pct > GAIN_THRESHOLD:
                    continue

        buy_price = limit_buy_price
        sell_price = next_close

        effective_buy_price = buy_price * (1 + BUY_FEE)
        effective_sell_price = sell_price * (1 - SELL_FEE)
        return_rate = (effective_sell_price / effective_buy_price) - 1.0
        return_multiplier = effective_sell_price / effective_buy_price

        trades.append(
            {
                "return_rate": return_rate,
                "return_multiplier": return_multiplier,
            }
        )

    if len(trades) == 0:
        return {
            "instId": instId,
            "total_trades": 0,
            "total_return": 1.0,
            "total_return_pct": 0.0,
        }

    return_multipliers = np.array([t["return_multiplier"] for t in trades])
    total_return = np.prod(return_multipliers)

    return {
        "instId": instId,
        "total_trades": len(trades),
        "total_return": round(total_return, 4),
        "total_return_pct": round((total_return - 1.0) * 100, 2),
    }


def main():
    print("=" * 80)
    print("Comparing Backtest: With vs Without 2-Hour Gain Filter")
    print("=" * 80)
    print()

    results_with = []
    results_without = []

    for instId, config in list(crypto_limits.items())[:10]:  # Test first 10 for speed
        limit_percent = config["limit_percent"]
        print(f"Testing {instId}...", end=" ", flush=True)

        result_with = backtest_crypto_with_filter(
            instId, limit_percent, days=30, use_filter=True
        )
        result_without = backtest_crypto_with_filter(
            instId, limit_percent, days=30, use_filter=False
        )

        results_with.append(result_with)
        results_without.append(result_without)

        print(
            f"With filter: {result_with['total_trades']} trades, "
            f"{result_with['total_return_pct']:+.2f}% | "
            f"Without: {result_without['total_trades']} trades, "
            f"{result_without['total_return_pct']:+.2f}%"
        )

    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)

    # Calculate portfolio returns
    portfolio_with = 1.0
    portfolio_without = 1.0
    trades_with = 0
    trades_without = 0

    for rw, rwo in zip(results_with, results_without):
        if rw["total_trades"] > 0:
            portfolio_with *= rw["total_return"]
            trades_with += rw["total_trades"]
        if rwo["total_trades"] > 0:
            portfolio_without *= rwo["total_return"]
            trades_without += rwo["total_trades"]

    print("With 2h Filter:")
    print(f"  Total Trades: {trades_with}")
    print(f"  Portfolio Return: {(portfolio_with - 1.0) * 100:+.2f}%")
    print()
    print("Without 2h Filter:")
    print(f"  Total Trades: {trades_without}")
    print(f"  Portfolio Return: {(portfolio_without - 1.0) * 100:+.2f}%")
    print()
    diff_pct = ((portfolio_with - portfolio_without) / portfolio_without) * 100
    print(f"Difference: {diff_pct:+.2f}%")


if __name__ == "__main__":
    main()
