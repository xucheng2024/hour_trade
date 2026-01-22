#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Backtest with same-hour sell strategy
Strategy:
- Buy at limit price (open * limit_percent) if low <= limit
- Skip buy if 2-hour gain > 5%
- Sell at SAME hour's close (or 55 minutes) instead of next hour
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

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


def check_2h_gain_filter(
    df: pd.DataFrame, current_idx: int, current_open: float
) -> Tuple[bool, Optional[float]]:
    """Check if 2-hour gain exceeds threshold"""
    if current_idx < LOOKBACK_HOURS:
        return False, None

    close_2h_ago = df.iloc[current_idx - LOOKBACK_HOURS]["close"]

    if close_2h_ago <= 0:
        return False, None

    gain_pct = ((current_open - close_2h_ago) / close_2h_ago) * 100
    should_skip = gain_pct > GAIN_THRESHOLD

    return should_skip, gain_pct


def backtest_crypto_same_hour_sell(
    instId: str, limit_percent: float, days: int = 30
) -> Dict:
    """Backtest with same-hour sell strategy"""
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
        return {
            "instId": instId,
            "error": "Insufficient data",
            "total_trades": 0,
        }

    df = df.sort_values("timestamp").reset_index(drop=True)
    trades = []
    limit_ratio = limit_percent / 100.0

    # Process each hour - sell at same hour's close
    for i in range(len(df)):
        hour_data = df.iloc[i]

        # Get prices
        open_price = hour_data["open"]
        low_price = hour_data["low"]
        close_price = hour_data["close"]  # Sell at same hour's close

        # Calculate limit price
        limit_buy_price = open_price * limit_ratio

        # Check if we can buy (low <= limit)
        if low_price > limit_buy_price:
            continue

        # ✅ Check 2-hour gain filter
        should_skip, gain_pct = check_2h_gain_filter(df, i, open_price)
        if should_skip:
            continue  # Skip buy if gain > 5%

        # Buy at limit price, sell at same hour's close
        buy_price = limit_buy_price
        sell_price = close_price  # ✅ FIX: Sell at same hour's close

        # Calculate return with fees
        effective_buy_price = buy_price * (1 + BUY_FEE)
        effective_sell_price = sell_price * (1 - SELL_FEE)
        return_rate = (effective_sell_price / effective_buy_price) - 1.0
        return_multiplier = effective_sell_price / effective_buy_price

        trade = {
            "buy_time": datetime.fromtimestamp(
                hour_data["timestamp"] / 1000, tz=timezone.utc
            ),
            "sell_time": datetime.fromtimestamp(
                hour_data["timestamp"] / 1000, tz=timezone.utc
            ),
            "buy_price": buy_price,
            "sell_price": sell_price,
            "return_rate": return_rate,
            "return_multiplier": return_multiplier,
            "gain_2h": gain_pct,
        }
        trades.append(trade)

    # Calculate statistics
    if len(trades) == 0:
        return {
            "instId": instId,
            "total_trades": 0,
            "total_return": 0.0,
            "total_return_pct": 0.0,
            "win_rate": 0.0,
            "avg_return": 0.0,
        }

    return_rates = np.array([t["return_rate"] for t in trades])
    return_multipliers = np.array([t["return_multiplier"] for t in trades])

    total_return = np.prod(return_multipliers)
    avg_return = np.mean(return_rates)
    profitable_trades = np.sum(return_rates > 0)
    win_rate = profitable_trades / len(trades) * 100

    return {
        "instId": instId,
        "total_trades": len(trades),
        "profitable_trades": int(profitable_trades),
        "losing_trades": int(len(trades) - profitable_trades),
        "win_rate": round(win_rate, 2),
        "avg_return": round(avg_return * 100, 2),
        "total_return": round(total_return, 4),
        "total_return_pct": round((total_return - 1.0) * 100, 2),
        "trades": trades,
    }


def main():
    """Run backtest for all cryptos"""
    print("=" * 80)
    print("Backtesting Recent 30 Days - SAME HOUR SELL Strategy")
    print("Strategy: 2-hour 5% gain filter + hourly limit buy + SAME hour sell")
    print("=" * 80)
    print()

    results = []
    total_trades_all = 0
    total_return_all = 1.0
    cryptos_with_trades = 0

    for instId, config in crypto_limits.items():
        limit_percent = config["limit_percent"]
        print(f"Testing {instId} (limit: {limit_percent}%)...", end=" ", flush=True)

        result = backtest_crypto_same_hour_sell(instId, limit_percent, days=30)

        if "error" in result:
            print(f"❌ {result['error']}")
            continue

        results.append(result)
        total_trades_all += result["total_trades"]

        if result["total_trades"] > 0:
            total_return_all *= result["total_return"]
            cryptos_with_trades += 1

        print(
            f"✅ {result['total_trades']} trades, "
            f"{result['total_return_pct']:+.2f}% return, "
            f"{result['win_rate']:.1f}% win rate"
        )

    print()
    print("=" * 80)
    print("SUMMARY - SAME HOUR SELL")
    print("=" * 80)
    print(f"Total Cryptos Tested: {len(results)}")
    print(f"Cryptos with Trades: {cryptos_with_trades}")
    print(f"Total Trades: {total_trades_all}")
    if cryptos_with_trades > 0:
        print(f"Portfolio Return: {(total_return_all - 1.0) * 100:+.2f}%")
        avg_return = ((total_return_all ** (1.0 / cryptos_with_trades)) - 1.0) * 100
        print(f"Average Return per Crypto: {avg_return:+.2f}%")
    else:
        print("Portfolio Return: N/A (no trades)")
    print()

    # Sort by return
    results_sorted = sorted(results, key=lambda x: x["total_return_pct"], reverse=True)

    print("Top 10 Performers:")
    print("-" * 80)
    for i, r in enumerate(results_sorted[:10], 1):
        if r["total_trades"] > 0:
            print(
                f"{i:2d}. {r['instId']:20s} "
                f"{r['total_trades']:3d} trades, "
                f"{r['total_return_pct']:+7.2f}%, "
                f"win: {r['win_rate']:5.1f}%"
            )

    print()
    print("Bottom 10 Performers:")
    print("-" * 80)
    for i, r in enumerate(results_sorted[-10:], 1):
        if r["total_trades"] > 0:
            print(
                f"{i:2d}. {r['instId']:20s} "
                f"{r['total_trades']:3d} trades, "
                f"{r['total_return_pct']:+7.2f}%, "
                f"win: {r['win_rate']:5.1f}%"
            )

    # Save results
    output_file = "backtest_same_hour_sell_results.json"
    with open(output_file, "w") as f:
        json.dump(
            {
                "backtest_date": datetime.now(timezone.utc).isoformat(),
                "days": 30,
                "strategy": "2-hour 5% gain filter + hourly limit + SAME hour sell",
                "total_cryptos": len(results),
                "total_trades": total_trades_all,
                "portfolio_return_pct": (
                    round((total_return_all - 1.0) * 100, 2)
                    if cryptos_with_trades > 0
                    else 0
                ),
                "results": results,
            },
            f,
            indent=2,
            default=str,
        )
    print()
    print(f"✅ Results saved to {output_file}")


if __name__ == "__main__":
    main()
