#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Backtest recent 30 days using REAL-TIME API data
Compare with and without 2-hour 5% gain filter
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

from okx.MarketData import MarketAPI

LIMITS_FILE = "valid_crypto_limits.json"
with open(LIMITS_FILE, "r") as f:
    limits_data = json.load(f)
    crypto_limits = limits_data["cryptos"]

BUY_FEE = 0.001
SELL_FEE = 0.001
GAIN_THRESHOLD = 5.0
LOOKBACK_HOURS = 2


def fetch_realtime_data(instId: str, days: int = 30) -> Optional[pd.DataFrame]:
    """Fetch real-time 1H candlestick data from OKX API"""
    try:
        market_api = MarketAPI(flag="0")  # Production API

        # Calculate start time (30 days ago)
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=days)

        # OKX API limit is 100 candles per request, 1H = 24 candles/day
        # 30 days = 720 candles, need multiple requests
        all_data = []
        after = None

        print(f"  Fetching {instId} data...", end=" ", flush=True)

        while True:
            # OKX get_candlesticks returns newest first
            result = market_api.get_candlesticks(
                instId=instId,
                bar="1H",
                limit="100",  # Max 100 per request
                after=after,  # Pagination
            )

            if result.get("code") != "0" or not result.get("data"):
                break

            data = result["data"]
            if not data:
                break

            # Convert to DataFrame format
            for candle in data:
                # Format: [ts, open, high, low, close, vol, volCcy, volCcyQuote, confirm]
                ts_ms = int(candle[0])
                candle_time = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)

                # Check if we've gone past our start time
                if candle_time < start_time:
                    break

                all_data.append(
                    {
                        "timestamp": ts_ms,
                        "open": float(candle[1]),
                        "high": float(candle[2]),
                        "low": float(candle[3]),
                        "close": float(candle[4]),
                        "volume": float(candle[5]),
                    }
                )

            # Check if we need more data
            if len(data) < 100:
                break

            # Get the oldest timestamp for next request
            oldest_ts = int(data[-1][0])
            after = str(oldest_ts - 1)  # Get older data

            # Rate limiting
            time.sleep(0.2)

            # Check if we've got enough data
            if (
                all_data
                and datetime.fromtimestamp(
                    all_data[-1]["timestamp"] / 1000, tz=timezone.utc
                )
                < start_time
            ):
                break

        if not all_data:
            print("No data")
            return None

        # Convert to DataFrame and sort by timestamp (oldest first)
        df = pd.DataFrame(all_data)
        df = df.sort_values("timestamp").reset_index(drop=True)

        # Filter to requested date range
        df = df[df["timestamp"] >= int(start_time.timestamp() * 1000)]
        df = df[df["timestamp"] <= int(end_time.timestamp() * 1000)]

        print(f"{len(df)} candles")
        return df

    except Exception as e:
        print(f"Error: {e}")
        return None


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


def backtest_crypto(
    instId: str,
    limit_percent: float,
    days: int = 30,
    use_2h_filter: bool = True,
    same_hour_sell: bool = True,
) -> Dict:
    """Backtest a single crypto with real-time data"""
    df = fetch_realtime_data(instId, days)

    if df is None or len(df) < 3:
        return {
            "instId": instId,
            "error": "Insufficient data",
            "total_trades": 0,
        }

    trades = []
    limit_ratio = limit_percent / 100.0

    if same_hour_sell:
        # Sell at same hour's close
        for i in range(len(df)):
            hour_data = df.iloc[i]
            open_price = hour_data["open"]
            low_price = hour_data["low"]
            close_price = hour_data["close"]

            limit_buy_price = open_price * limit_ratio

            if low_price > limit_buy_price:
                continue

            if use_2h_filter:
                should_skip, gain_pct = check_2h_gain_filter(df, i, open_price)
                if should_skip:
                    continue

            buy_price = limit_buy_price
            sell_price = close_price

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
    else:
        # Sell at next hour's close
        for i in range(len(df) - 1):
            hour_data = df.iloc[i]
            next_hour_data = df.iloc[i + 1]
            open_price = hour_data["open"]
            low_price = hour_data["low"]
            next_close = next_hour_data["close"]

            limit_buy_price = open_price * limit_ratio

            if low_price > limit_buy_price:
                continue

            if use_2h_filter:
                should_skip, gain_pct = check_2h_gain_filter(df, i, open_price)
                if should_skip:
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
    print("Real-Time 30 Days Backtest - With vs Without 2-Hour 5% Filter")
    print("Using LIVE OKX API data (current hour sell)")
    print("=" * 80)
    print()

    strategies = [
        ("有2h过滤", True),
        ("无2h过滤", False),
    ]

    all_results = {}

    for strategy_name, use_2h_filter in strategies:
        print(f"\n{'='*80}")
        print(f"策略: {strategy_name}")
        print("=" * 80)

        results = []
        total_return_all = 1.0
        cryptos_with_trades = 0
        total_trades = 0

        for instId, config in crypto_limits.items():
            limit_percent = config["limit_percent"]
            result = backtest_crypto(
                instId,
                limit_percent,
                days=30,
                use_2h_filter=use_2h_filter,
                same_hour_sell=True,
            )

            if "error" in result:
                continue

            results.append(result)
            total_trades += result["total_trades"]

            if result["total_trades"] > 0:
                total_return_all *= result["total_return"]
                cryptos_with_trades += 1

        all_results[strategy_name] = {
            "results": results,
            "total_trades": total_trades,
            "cryptos_with_trades": cryptos_with_trades,
            "portfolio_return": total_return_all,
            "portfolio_return_pct": (total_return_all - 1.0) * 100,
        }

        print(f"\n总结:")
        print(f"  总交易数: {total_trades}")
        print(f"  有交易的币种: {cryptos_with_trades}")
        if cryptos_with_trades > 0:
            print(f"  组合收益: {(total_return_all - 1.0) * 100:+.2f}%")
            print(
                f"  平均收益: {((total_return_all ** (1.0 / cryptos_with_trades)) - 1.0) * 100:+.2f}%"
            )
        else:
            print("  组合收益: N/A")

        # Show top performers
        results_sorted = sorted(
            [r for r in results if r["total_trades"] > 0],
            key=lambda x: x["total_return_pct"],
            reverse=True,
        )
        if results_sorted:
            print(f"\n  前5名:")
            for i, r in enumerate(results_sorted[:5], 1):
                print(
                    f"    {i}. {r['instId']:20s} {r['total_trades']:3d}笔 {r['total_return_pct']:+7.2f}%"
                )

    # Final comparison
    print()
    print("=" * 80)
    print("最终对比")
    print("=" * 80)

    with_filter = all_results["有2h过滤"]
    without_filter = all_results["无2h过滤"]

    print(f"有2h过滤:")
    print(f"  交易数: {with_filter['total_trades']}")
    print(f"  组合收益: {with_filter['portfolio_return_pct']:+.2f}%")
    print()
    print(f"无2h过滤:")
    print(f"  交易数: {without_filter['total_trades']}")
    print(f"  组合收益: {without_filter['portfolio_return_pct']:+.2f}%")
    print()

    improvement = (
        with_filter["portfolio_return_pct"] - without_filter["portfolio_return_pct"]
    )
    print(f"2h过滤带来的改进: {improvement:+.2f} 个百分点")

    # Save results
    output_file = "backtest_realtime_30days_results.json"
    with open(output_file, "w") as f:
        json.dump(
            {
                "backtest_date": datetime.now(timezone.utc).isoformat(),
                "days": 30,
                "strategy": "current hour sell",
                "comparison": {
                    "with_2h_filter": {
                        "total_trades": with_filter["total_trades"],
                        "portfolio_return_pct": round(
                            with_filter["portfolio_return_pct"], 2
                        ),
                    },
                    "without_2h_filter": {
                        "total_trades": without_filter["total_trades"],
                        "portfolio_return_pct": round(
                            without_filter["portfolio_return_pct"], 2
                        ),
                    },
                    "improvement": round(improvement, 2),
                },
                "detailed_results": all_results,
            },
            f,
            indent=2,
            default=str,
        )
    print()
    print(f"✅ 结果已保存到 {output_file}")


if __name__ == "__main__":
    main()
