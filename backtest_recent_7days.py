#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Backtest recent 7 days with same-hour sell strategy
Compare with morning's results
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


def backtest_crypto(
    instId: str,
    limit_percent: float,
    days: int = 7,
    use_2h_filter: bool = True,
    same_hour_sell: bool = True,
) -> Dict:
    """Backtest a single crypto"""
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
    print("Backtesting Recent 7 Days - Multiple Strategies")
    print("=" * 80)
    print()

    strategies = [
        ("当前小时卖出 + 2h过滤", True, True),
        ("当前小时卖出 + 无过滤", False, True),
        ("下一小时卖出 + 2h过滤", True, False),
        ("下一小时卖出 + 无过滤", False, False),
    ]

    for strategy_name, use_2h_filter, same_hour_sell in strategies:
        print(f"\n策略: {strategy_name}")
        print("-" * 80)

        results = []
        total_return_all = 1.0
        cryptos_with_trades = 0

        for instId, config in crypto_limits.items():
            limit_percent = config["limit_percent"]
            result = backtest_crypto(
                instId,
                limit_percent,
                days=7,
                use_2h_filter=use_2h_filter,
                same_hour_sell=same_hour_sell,
            )

            if "error" in result:
                continue

            results.append(result)

            if result["total_trades"] > 0:
                total_return_all *= result["total_return"]
                cryptos_with_trades += 1

        total_trades = sum(r["total_trades"] for r in results)

        print(f"总交易数: {total_trades}")
        print(f"有交易的币种: {cryptos_with_trades}")
        if cryptos_with_trades > 0:
            print(f"组合收益: {(total_return_all - 1.0) * 100:+.2f}%")
            avg_return = ((total_return_all ** (1.0 / cryptos_with_trades)) - 1.0) * 100
            print(f"平均收益: {avg_return:+.2f}%")
        else:
            print("组合收益: N/A")


if __name__ == "__main__":
    main()
