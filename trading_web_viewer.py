#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Trading Records Web Viewer
Display trading records grouped by cryptocurrency with profit calculation
"""

import os
from collections import defaultdict
from datetime import datetime

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from flask import Flask, render_template_string

# Load environment variables
load_dotenv()

app = Flask(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL not found in environment variables")

STRATEGY_NAME = "hourly_limit_ws"


def get_db_connection():
    """Get PostgreSQL database connection"""
    return psycopg2.connect(DATABASE_URL)


HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Trading Records</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #fafafa;
            color: #1a1a1a;
            line-height: 1.5;
            padding: 16px;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        
        h1 {
            font-size: 18px;
            font-weight: 600;
            color: #1a1a1a;
            margin-bottom: 16px;
        }
        
        .summary {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 12px;
            margin-bottom: 16px;
        }
        
        .summary-item {
            background: #fff;
            padding: 12px;
            border-radius: 6px;
            border: 1px solid #e5e5e5;
        }
        
        .summary-label {
            font-size: 11px;
            color: #666;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 4px;
        }
        
        .summary-value {
            font-size: 20px;
            font-weight: 600;
            color: #1a1a1a;
        }
        
        .summary-value.profit-positive { color: #10b981; }
        .summary-value.profit-negative { color: #ef4444; }
        
        .crypto-section {
            background: #fff;
            border: 1px solid #e5e5e5;
            border-radius: 6px;
            margin-bottom: 12px;
            overflow: hidden;
        }
        
        .crypto-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 12px 16px;
            border-bottom: 1px solid #e5e5e5;
            background: #fafafa;
        }
        
        .crypto-name {
            font-size: 14px;
            font-weight: 600;
            color: #1a1a1a;
        }
        
        .crypto-profit {
            font-size: 14px;
            font-weight: 600;
            padding: 4px 8px;
            border-radius: 4px;
        }
        
        .profit-positive { color: #10b981; background: #d1fae5; }
        .profit-negative { color: #ef4444; background: #fee2e2; }
        .profit-zero { color: #666; background: #f3f4f6; }
        
        .trades-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }
        
        .trades-table th {
            background: #fafafa;
            color: #666;
            font-weight: 600;
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            padding: 8px 16px;
            text-align: left;
            border-bottom: 1px solid #e5e5e5;
        }
        
        .trades-table td {
            padding: 10px 16px;
            border-bottom: 1px solid #f0f0f0;
            color: #1a1a1a;
        }
        
        .trades-table tbody tr:hover {
            background: #fafafa;
        }
        
        .trades-table tbody tr:last-child td {
            border-bottom: none;
        }
        
        .trade-buy { color: #10b981; font-weight: 600; }
        .trade-sell { color: #ef4444; font-weight: 600; }
        
        .trade-state {
            padding: 2px 6px;
            border-radius: 3px;
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
        }
        
        .state-sold { background: #d1fae5; color: #065f46; }
        .state-active { background: #fef3c7; color: #92400e; }
        
        @media (max-width: 768px) {
            body { padding: 12px; }
            .summary { grid-template-columns: 1fr; }
            .crypto-header { flex-direction: column; align-items: flex-start; gap: 8px; }
            .trades-table th, .trades-table td { padding: 8px 12px; font-size: 12px; }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Trading Records</h1>
        
        <div class="summary">
            <div class="summary-item">
                <div class="summary-label">Cryptos</div>
                <div class="summary-value">{{ total_cryptos }}</div>
            </div>
            <div class="summary-item">
                <div class="summary-label">Trades</div>
                <div class="summary-value">{{ total_trades }}</div>
            </div>
            <div class="summary-item">
                <div class="summary-label">Profit</div>
                <div class="summary-value {{ 'profit-positive' if total_profit > 0 else 'profit-negative' if total_profit < 0 else '' }}">
                    {{ "%.2f"|format(total_profit) }} USDT
                </div>
            </div>
        </div>

        {% for crypto, data in cryptos.items() %}
        <div class="crypto-section">
            <div class="crypto-header">
                <div class="crypto-name">{{ crypto }}</div>
                <div class="crypto-profit {{ 'profit-positive' if data.profit > 0 else 'profit-negative' if data.profit < 0 else 'profit-zero' }}">
                    {{ "%.2f"|format(data.profit) }} USDT ({{ "%.2f"|format(data.profit_pct) }}%)
                </div>
            </div>
            <table class="trades-table">
                <thead>
                    <tr>
                        <th>Time</th>
                        <th>Type</th>
                        <th>Price</th>
                        <th>Size</th>
                        <th>Amount</th>
                        <th>State</th>
                    </tr>
                </thead>
                <tbody>
                    {% for trade in data.trades %}
                    <tr>
                        <td>{{ trade.time }}</td>
                        <td class="trade-{{ trade.side }}">{{ trade.side|upper }}</td>
                        <td>{{ trade.price }}</td>
                        <td>{{ trade.size }}</td>
                        <td>{{ "%.2f"|format(trade.amount) }}</td>
                        <td>
                            <span class="trade-state state-{{ trade.state_class }}">
                                {{ trade.state }}
                            </span>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        {% endfor %}
    </div>
</body>
</html>
"""


def get_trading_records():
    """Get trading records from database grouped by cryptocurrency"""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        # Get all orders for this strategy (including sell_price)
        # Use LIKE to match both 'hourly_limit_ws' and 'hourly_limit_ws_test'
        cur.execute(
            """
            SELECT instId, ordId, create_time, orderType, state, price, size, sell_time, side, sell_price
            FROM orders
            WHERE flag LIKE %s
            ORDER BY create_time DESC
        """,
            (f"{STRATEGY_NAME}%",),
        )

        rows = cur.fetchall()

        # Group by cryptocurrency
        cryptos = defaultdict(
            lambda: {
                "trades": [],
                "profit": 0.0,
                "profit_pct": 0.0,
                "buy_amount": 0.0,
                "sell_amount": 0.0,
            }
        )

        for row in rows:
            instId = row["instid"]
            buy_price = float(row["price"]) if row["price"] else 0.0
            sell_price = float(row["sell_price"]) if row.get("sell_price") else 0.0
            size = float(row["size"]) if row["size"] else 0.0

            trade = {
                "ordId": row["ordid"],
                "time": datetime.fromtimestamp(row["create_time"] / 1000).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "side": row["side"],
                "price": buy_price,
                "sell_price": sell_price,
                "size": size,
                "state": row["state"] if row["state"] else "active",
                "state_class": "sold" if row["state"] == "sold out" else "active",
            }

            # Calculate amount based on buy price
            if buy_price > 0 and size > 0:
                trade["amount"] = buy_price * size
            else:
                trade["amount"] = 0.0

            cryptos[instId]["trades"].append(trade)

            # Calculate profit using sell_price from the same buy order
            if trade["side"] == "buy":
                cryptos[instId]["buy_amount"] += trade["amount"]
                # If sell_price exists, calculate sell amount
                if sell_price > 0 and size > 0:
                    sell_amount = sell_price * size
                    cryptos[instId]["sell_amount"] += sell_amount

        # Calculate profit for each crypto
        for instId, data in cryptos.items():
            total_buy_amount = data["buy_amount"]
            total_sell_amount = data["sell_amount"]
            total_profit = total_sell_amount - total_buy_amount

            data["profit"] = total_profit
            if total_buy_amount > 0:
                data["profit_pct"] = (total_profit / total_buy_amount) * 100

            # Sort trades by time
            data["trades"].sort(key=lambda x: x["time"], reverse=True)

        return dict(cryptos)
    finally:
        cur.close()
        conn.close()


@app.route("/")
def index():
    """Display trading records"""
    cryptos = get_trading_records()

    # Calculate totals
    total_cryptos = len(cryptos)
    total_trades = sum(len(data["trades"]) for data in cryptos.values())
    total_profit = sum(data["profit"] for data in cryptos.values())

    return render_template_string(
        HTML_TEMPLATE,
        strategy_name=STRATEGY_NAME,
        cryptos=cryptos,
        total_cryptos=total_cryptos,
        total_trades=total_trades,
        total_profit=total_profit,
    )


if __name__ == "__main__":
    print(f"Starting trading records viewer...")
    print(f"Open http://localhost:5000 in your browser")
    app.run(debug=True, host="0.0.0.0", port=5000)
