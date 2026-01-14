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
    <title>🚀 Crypto Trading Dashboard</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }

        :root {
            --primary: #6366f1;
            --primary-dark: #4f46e5;
            --success: #10b981;
            --danger: #ef4444;
        }

        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 50%, #f093fb 100%);
            min-height: 100vh;
            padding: 12px;
            animation: gradientShift 15s ease infinite;
            background-size: 200% 200%;
        }

        @keyframes gradientShift {
            0% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
            100% { background-position: 0% 50%; }
        }

        .container {
            max-width: 1800px;
            margin: 0 auto;
        }

        .header {
            text-align: center;
            margin-bottom: 20px;
        }

        .header h1 {
            color: white;
            font-size: 2rem;
            font-weight: 800;
            margin-bottom: 5px;
            text-shadow: 0 4px 12px rgba(0,0,0,0.3);
        }

        .header p {
            color: rgba(255,255,255,0.95);
            font-size: 0.9rem;
        }

        .controls {
            display: flex;
            justify-content: center;
            gap: 10px;
            margin-bottom: 20px;
        }

        .btn {
            background: rgba(255,255,255,0.25);
            backdrop-filter: blur(10px);
            color: white;
            border: 2px solid rgba(255,255,255,0.3);
            padding: 8px 20px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 600;
            transition: all 0.3s;
        }

        .btn:hover {
            background: rgba(255,255,255,0.35);
            transform: translateY(-2px);
            box-shadow: 0 8px 20px rgba(0,0,0,0.15);
        }

        .summary {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }

        .stat-card {
            background: rgba(255,255,255,0.95);
            backdrop-filter: blur(10px);
            padding: 20px;
            border-radius: 12px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
            transition: all 0.3s;
        }

        .stat-card:hover {
            transform: translateY(-3px);
            box-shadow: 0 15px 50px rgba(0,0,0,0.15);
        }

        .stat-icon {
            width: 40px;
            height: 40px;
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 20px;
            margin-bottom: 12px;
        }

        .stat-card:nth-child(1) .stat-icon {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }

        .stat-card:nth-child(2) .stat-icon {
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
        }

        .stat-card:nth-child(3) .stat-icon {
            background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
        }

        .stat-label {
            font-size: 11px;
            color: #64748b;
            margin-bottom: 6px;
            text-transform: uppercase;
            letter-spacing: 1px;
            font-weight: 600;
        }

        .stat-value {
            font-size: 28px;
            font-weight: 800;
            color: #1e293b;
        }

        .crypto-section {
            background: rgba(255,255,255,0.95);
            backdrop-filter: blur(10px);
            margin-bottom: 15px;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
            transition: all 0.3s;
        }

        .crypto-section:hover {
            box-shadow: 0 15px 50px rgba(0,0,0,0.15);
        }

        .crypto-header {
            background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%);
            padding: 16px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 10px;
        }

        .crypto-name {
            font-size: 20px;
            font-weight: 800;
            color: white;
        }

        .crypto-name::before {
            content: '💎 ';
        }

        .profit-badge {
            padding: 8px 16px;
            border-radius: 8px;
            font-weight: 700;
            font-size: 14px;
            backdrop-filter: blur(10px);
        }

        .profit-positive {
            background: rgba(16, 185, 129, 0.2);
            color: #dcfce7;
            border: 2px solid rgba(255,255,255,0.3);
        }

        .profit-positive::before {
            content: '📈 ';
        }

        .profit-negative {
            background: rgba(239, 68, 68, 0.2);
            color: #fee2e2;
            border: 2px solid rgba(255,255,255,0.3);
        }

        .profit-negative::before {
            content: '📉 ';
        }

        table {
            width: 100%;
            border-collapse: collapse;
        }

        thead {
            background: linear-gradient(135deg, #1e293b 0%, #334155 100%);
        }

        th {
            color: white;
            padding: 10px 12px;
            text-align: left;
            font-weight: 700;
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        td {
            padding: 10px 12px;
            border-bottom: 1px solid #e2e8f0;
            color: #1e293b;
            font-weight: 500;
            font-size: 13px;
        }

        tbody tr {
            transition: all 0.2s;
        }

        tbody tr:hover {
            background: linear-gradient(90deg, #f8fafc 0%, #f1f5f9 100%);
            transform: translateX(3px);
        }

        .side-buy {
            color: var(--success);
            font-weight: 700;
        }

        .side-sell {
            color: var(--danger);
            font-weight: 700;
        }

        .status-badge {
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 10px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.3px;
        }

        .status-active {
            background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%);
            color: #1e40af;
        }

        .status-sold {
            background: linear-gradient(135deg, #d1fae5 0%, #a7f3d0 100%);
            color: #065f46;
        }

        .error {
            background: rgba(255,255,255,0.95);
            backdrop-filter: blur(10px);
            text-align: center;
            padding: 40px 30px;
            border-radius: 12px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
        }

        .error h3 {
            font-size: 22px;
            margin-bottom: 10px;
            color: #1e293b;
        }

        .error p {
            color: #64748b;
            font-size: 14px;
        }

        .error code {
            background: #f1f5f9;
            padding: 6px 12px;
            border-radius: 6px;
            font-family: Monaco, monospace;
            color: #6366f1;
            font-weight: 600;
            font-size: 13px;
        }

        @media (max-width: 768px) {
            .header h1 { font-size: 1.5rem; }
            .crypto-header { padding: 12px 15px; }
            .crypto-name { font-size: 18px; }
            td, th { padding: 8px 10px; font-size: 12px; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚀 Crypto Trading Dashboard</h1>
            <p>Real-time trading records and performance analytics</p>
        </div>

        <div class="controls">
            <button class="btn" onclick="location.reload()">🔄 Refresh Data</button>
            <button class="btn" onclick="window.location.href='/api/orders'">
                📊 JSON API
            </button>
        </div>

        <div class="summary">
            <div class="stat-card">
                <div class="stat-icon">💰</div>
                <div class="stat-label">Total Cryptos</div>
                <div class="stat-value">{{ total_cryptos }}</div>
            </div>
            <div class="stat-card">
                <div class="stat-icon">📈</div>
                <div class="stat-label">Total Trades</div>
                <div class="stat-value">{{ total_trades }}</div>
            </div>
            <div class="stat-card">
                <div class="stat-icon">💎</div>
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
                        <td><span class="side-{{ trade.side }}">
                            {{ trade.side|upper }}
                        </span></td>
                        <td>{{ "%.2f"|format(trade.price) }}</td>
                        <td>{{ "%.6f"|format(trade.size) }}</td>
                        <td><strong>{{ "%.2f"|format(trade.amount) }}</strong> USDT</td>
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
            <h3>🔍 No Trading Records Found</h3>
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
