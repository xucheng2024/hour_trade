#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vercel API - Trading Records Viewer (Standalone version)
"""

import os
from collections import defaultdict
from datetime import datetime

import psycopg2
import psycopg2.extras
from flask import Flask, jsonify, render_template_string

app = Flask(__name__)

STRATEGY_NAME = "hourly_limit_ws"

# HTML Template
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
        
        .side-buy { color: #10b981; font-weight: 600; }
        .side-sell { color: #ef4444; font-weight: 600; }
        
        .status-badge {
            padding: 2px 6px;
            border-radius: 3px;
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
        }
        
        .status-active { background: #fef3c7; color: #92400e; }
        .status-sold { background: #d1fae5; color: #065f46; }
        
        .error {
            background: #fff;
            text-align: center;
            padding: 40px 30px;
            border-radius: 6px;
            border: 1px solid #e5e5e5;
        }
        
        .error h3 {
            font-size: 18px;
            margin-bottom: 8px;
            color: #1a1a1a;
        }
        
        .error p {
            color: #666;
            font-size: 14px;
            margin-bottom: 8px;
        }
        
        .error code {
            background: #f5f5f5;
            padding: 4px 8px;
            border-radius: 4px;
            font-family: Monaco, monospace;
            color: #1a1a1a;
            font-size: 12px;
        }
        
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

        {% if cryptos %}
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
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
                    {% for trade in data.trades %}
                    <tr>
                        <td>
                            {% if trade.state == 'sold out' and trade.sell_time %}
                                {{ trade.sell_time }}
                            {% else %}
                                {{ trade.buy_time }}
                            {% endif %}
                        </td>
                        <td><span class="side-{{ trade.side }}">{{ trade.side|upper }}</span></td>
                        <td>{{ "%.2f"|format(trade.price) }}</td>
                        <td>{{ "%.6f"|format(trade.size) }}</td>
                        <td>{{ "%.2f"|format(trade.amount) }}</td>
                        <td>
                            <span class="status-badge status-{{ trade.state_class }}">
                                {{ trade.state }}
                            </span>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        {% endfor %}
        {% else %}
        <div class="error">
            <h3>No Trading Records Found</h3>
            <p>Start the trading bot to generate records:</p>
            <p><code>python websocket_limit_trading.py</code></p>
        </div>
        {% endif %}
    </div>
</body>
</html>
"""


def get_database_connection():
    """Get PostgreSQL database connection"""
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise ValueError("DATABASE_URL environment variable is required")

    if not database_url.startswith("postgresql://"):
        raise ValueError("DATABASE_URL must be a PostgreSQL connection string")

    return psycopg2.connect(database_url)


def get_trading_records():
    """Get trading records from PostgreSQL database"""
    try:
        conn = get_database_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute(
            """
            SELECT instId, ordId, create_time, orderType, state,
                   price, size, sell_time, side, sell_price
            FROM orders
            WHERE flag LIKE %s
            ORDER BY create_time DESC
            LIMIT 1000
        """,
            (f"{STRATEGY_NAME}%",),
        )

        rows = cur.fetchall()

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
            state = row["state"] if row["state"] else "active"

            # Display sell time if sold, otherwise buy time
            if state == "sold out" and row.get("sell_time"):
                display_time = datetime.fromtimestamp(row["sell_time"] / 1000).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            else:
                display_time = datetime.fromtimestamp(
                    row["create_time"] / 1000
                ).strftime("%Y-%m-%d %H:%M:%S")

            trade = {
                "ordId": row["ordid"],
                "time": display_time,
                "buy_time": datetime.fromtimestamp(row["create_time"] / 1000).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "sell_time": (
                    datetime.fromtimestamp(row["sell_time"] / 1000).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                    if row.get("sell_time")
                    else None
                ),
                "side": row["side"],
                "price": buy_price,
                "sell_price": sell_price,
                "size": size,
                "state": state,
                "state_class": "sold" if state == "sold out" else "active",
            }

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

        for instId, data in cryptos.items():
            total_buy_amount = data["buy_amount"]
            total_sell_amount = data["sell_amount"]
            total_profit = total_sell_amount - total_buy_amount
            data["profit"] = total_profit
            if total_buy_amount > 0:
                data["profit_pct"] = (total_profit / total_buy_amount) * 100
            data["trades"].sort(key=lambda x: x["time"], reverse=True)

        cur.close()
        conn.close()

        return dict(cryptos)
    except Exception as e:
        print(f"Database error: {e}")
        return {}


@app.route("/")
def index():
    """Display trading records (HTML)"""
    try:
        cryptos = get_trading_records()

        total_cryptos = len(cryptos)
        total_trades = sum(len(data["trades"]) for data in cryptos.values())
        total_profit = sum(data["profit"] for data in cryptos.values())

        return render_template_string(
            HTML_TEMPLATE,
            cryptos=cryptos,
            total_cryptos=total_cryptos,
            total_trades=total_trades,
            total_profit=total_profit,
        )
    except Exception as e:
        return (
            f"""
        <html>
        <body style="font-family: sans-serif; padding: 40px; background: #f5f5f5;">
            <div style="max-width: 600px; margin: 0 auto; background: white;
                        padding: 30px; border-radius: 8px;">
                <h1 style="color: #dc3545;">⚠️ Error</h1>
                <p><strong>Error message:</strong> {str(e)}</p>
                <hr>
                <h3>Troubleshooting:</h3>
                <ol>
                    <li>Check DATABASE_URL is configured in Vercel
                        environment variables</li>
                    <li>Verify database tables exist:
                        run <code>python init_database.py</code></li>
                    <li>Check database connection is working</li>
                </ol>
                <p>
                    <a href="https://vercel.com/xuchengs-projects-27b3e479/hour-trade/settings/environment-variables">  # noqa: E501
                        → Configure Environment Variables
                    </a>
                </p>
            </div>
        </body>
        </html>
        """,
            500,
        )


@app.route("/api/orders")
def api_orders():
    """Get trading records (JSON API)"""
    try:
        cryptos = get_trading_records()

        return jsonify(
            {
                "success": True,
                "data": {
                    "total_cryptos": len(cryptos),
                    "total_trades": sum(
                        len(data["trades"]) for data in cryptos.values()
                    ),
                    "total_profit": sum(data["profit"] for data in cryptos.values()),
                    "cryptos": cryptos,
                },
            }
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/health")
def health():
    """Health check endpoint"""
    return jsonify(
        {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "service": "hour-trade-api",
        }
    )


# For local testing
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
