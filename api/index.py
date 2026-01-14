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
    <title>📊 Trading Records</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 12px;
            padding: 30px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }
        h1 {
            color: #333;
            margin-bottom: 20px;
            font-size: 28px;
        }
        .summary {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            border-radius: 8px;
            color: white;
        }
        .stat-label {
            font-size: 14px;
            opacity: 0.9;
            margin-bottom: 8px;
        }
        .stat-value {
            font-size: 32px;
            font-weight: bold;
        }
        .crypto-section {
            margin-bottom: 30px;
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            overflow: hidden;
        }
        .crypto-header {
            background: #f8f9fa;
            padding: 15px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .crypto-name {
            font-size: 20px;
            font-weight: bold;
            color: #333;
        }
        .profit-badge {
            padding: 8px 16px;
            border-radius: 20px;
            font-weight: bold;
            font-size: 14px;
        }
        .profit-positive {
            background: #d4edda;
            color: #155724;
        }
        .profit-negative {
            background: #f8d7da;
            color: #721c24;
        }
        table {
            width: 100%;
            border-collapse: collapse;
        }
        th {
            background: #667eea;
            color: white;
            padding: 12px;
            text-align: left;
            font-weight: 600;
        }
        td {
            padding: 12px;
            border-bottom: 1px solid #e0e0e0;
        }
        tr:hover {
            background: #f8f9fa;
        }
        .status-badge {
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 600;
        }
        .status-sold {
            background: #d4edda;
            color: #155724;
        }
        .status-active {
            background: #fff3cd;
            color: #856404;
        }
        .refresh-btn {
            background: #667eea;
            color: white;
            padding: 10px 20px;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 14px;
            margin-bottom: 20px;
        }
        .refresh-btn:hover {
            background: #5568d3;
        }
        .error {
            background: #f8d7da;
            color: #721c24;
            padding: 20px;
            border-radius: 8px;
            margin: 20px 0;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 Trading Records</h1>
        <button class="refresh-btn" onclick="location.reload()">🔄 Refresh</button>

        <div class="summary">
            <div class="stat-card">
                <div class="stat-label">Total Cryptos</div>
                <div class="stat-value">{{ total_cryptos }}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Total Trades</div>
                <div class="stat-value">{{ total_trades }}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Total Profit</div>
                <div class="stat-value">{{ "%.2f"|format(total_profit) }} USDT</div>
            </div>
        </div>

        {% if cryptos %}
        {% for crypto, data in cryptos.items() %}
        <div class="crypto-section">
            <div class="crypto-header">
                <div class="crypto-name">{{ crypto }}</div>
                <div class="profit-badge {{ 'profit-positive' if data.profit > 0 else 'profit-negative' }}">  # noqa: E501
                    {{ "%.2f"|format(data.profit) }} USDT ({{ "%.2f"|format(data.profit_pct) }}%)  # noqa: E501
                </div>
            </div>
            <table>
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
                        <td>{{ trade.time }}</td>
                        <td>{{ trade.side|upper }}</td>
                        <td>{{ trade.price }}</td>
                        <td>{{ trade.size }}</td>
                        <td>{{ "%.2f"|format(trade.amount) }} USDT</td>
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
            <h3>No trading records found</h3>
            <p>Start the trading bot to generate records: <code>python websocket_limit_trading.py</code></p>
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
            WHERE flag = %s
            ORDER BY create_time DESC
            LIMIT 1000
        """,
            (STRATEGY_NAME,),
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

            if buy_price > 0 and size > 0:
                trade["amount"] = buy_price * size
            else:
                trade["amount"] = 0.0

            cryptos[instId]["trades"].append(trade)

            if trade["side"] == "buy":
                cryptos[instId]["buy_amount"] += trade["amount"]
            elif trade["side"] == "sell" and sell_price > 0 and size > 0:
                cryptos[instId]["sell_amount"] += sell_price * size

        for instId, data in cryptos.items():
            total_profit = data["sell_amount"] - data["buy_amount"]
            data["profit"] = total_profit
            if data["buy_amount"] > 0:
                data["profit_pct"] = (total_profit / data["buy_amount"]) * 100
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
