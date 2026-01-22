#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Backtest recent 30 days with latest strategy (2-hour 5% gain filter)
Strategy:
- Buy at limit price (open * limit_percent) if low <= limit
- Skip buy if 2-hour gain > 5%
- Sell at next hour's 55 minutes
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

# Add ex_okx to path for data loader
sys.path.insert(0, "/Users/mac/Downloads/stocks/ex_okx")
sys.path.insert(0, os.path.join("/Users/mac/Downloads/stocks/ex_okx", "src"))

from strategies.historical_data_loader import get_historical_data_loader  # noqa: E402

# Load crypto limits
LIMITS_FILE = "valid_crypto_limits.json"
with open(LIMITS_FILE, "r") as f:
    limits_data = json.load(f)
    crypto_limits = limits_data["cryptos"]

# Strategy parameters
BUY_FEE = 0.001  # 0.1%
SELL_FEE = 0.001  # 0.1%
GAIN_THRESHOLD = 5.0  # 5% gain threshold
LOOKBACK_HOURS = 2  # 2 hours lookback


def check_2h_gain_filter(
    df: pd.DataFrame, current_idx: int, current_open: float
) -> Tuple[bool, Optional[float]]:
    """Check if 2-hour gain exceeds threshold

    Args:
        df: DataFrame with OHLCV data
        current_idx: Current hour index
        current_open: Current hour's open price

    Returns:
        Tuple of (should_skip_buy, gain_percentage)
    """
    if current_idx < LOOKBACK_HOURS:
        # Not enough history, allow buy (fail open)
        return False, None

    # Get close price from 2 hours ago
    close_2h_ago = df.iloc[current_idx - LOOKBACK_HOURS]["close"]

    if close_2h_ago <= 0:
        return False, None

    # Calculate gain
    gain_pct = ((current_open - close_2h_ago) / close_2h_ago) * 100
    should_skip = gain_pct > GAIN_THRESHOLD

    return should_skip, gain_pct


def backtest_crypto(instId: str, limit_percent: float, days: int = 30) -> Dict:
    """Backtest a single crypto for recent N days"""
    loader = get_historical_data_loader()

    # Get recent N days of 1H data
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

    # Sort by timestamp
    df = df.sort_values("timestamp").reset_index(drop=True)

    trades = []
    limit_ratio = limit_percent / 100.0

    # Process each hour
    for i in range(len(df) - 1):  # Leave room for next hour to sell
        hour_data = df.iloc[i]
        next_hour_data = df.iloc[i + 1]

        # Get prices
        open_price = hour_data["open"]
        low_price = hour_data["low"]
        next_close = next_hour_data["close"]

        # Calculate limit price
        limit_buy_price = open_price * limit_ratio

        # Check if we can buy (low <= limit)
        if low_price > limit_buy_price:
            continue

        # ✅ NEW: Check 2-hour gain filter
        should_skip, gain_pct = check_2h_gain_filter(df, i, open_price)
        if should_skip:
            continue  # Skip buy if gain > 5%

        # Buy at limit price
        buy_price = limit_buy_price
        sell_price = next_close  # Sell at next hour's close

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
                next_hour_data["timestamp"] / 1000, tz=timezone.utc
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
    print("Backtesting Recent 30 Days with Latest Strategy")
    print("Strategy: 2-hour 5% gain filter + hourly limit buy")
    print("=" * 80)
    print()

    results = []
    total_trades_all = 0
    total_return_all = 1.0
    cryptos_with_trades = 0

    for instId, config in crypto_limits.items():
        limit_percent = config["limit_percent"]
        print(f"Testing {instId} (limit: {limit_percent}%)...", end=" ", flush=True)

        result = backtest_crypto(instId, limit_percent, days=30)

        if "error" in result:
            print(f"❌ {result['error']}")
            continue

        results.append(result)
        total_trades_all += result["total_trades"]

        # Only multiply return if there were trades
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
    print("SUMMARY")
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
        print(
            f"{i:2d}. {r['instId']:20s} "
            f"{r['total_trades']:3d} trades, "
            f"{r['total_return_pct']:+7.2f}%, "
            f"win: {r['win_rate']:5.1f}%"
        )

    # Save results
    output_file = "backtest_recent_30days_results.json"
    with open(output_file, "w") as f:
        json.dump(
            {
                "backtest_date": datetime.now(timezone.utc).isoformat(),
                "days": 30,
                "strategy": "2-hour 5% gain filter + hourly limit",
                "total_cryptos": len(results),
                "total_trades": total_trades_all,
                "portfolio_return_pct": round((total_return_all - 1.0) * 100, 2),
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
