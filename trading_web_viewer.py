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

DATABASE_URL = os.getenv('DATABASE_URL')
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
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
            background-color: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        h1 {
            color: #333;
            margin-bottom: 30px;
        }
        .crypto-section {
            margin-bottom: 40px;
            border: 1px solid #ddd;
            border-radius: 6px;
            padding: 20px;
            background-color: #fafafa;
        }
        .crypto-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 15px;
            border-bottom: 2px solid #ddd;
        }
        .crypto-name {
            font-size: 24px;
            font-weight: bold;
            color: #333;
        }
        .crypto-profit {
            font-size: 20px;
            font-weight: bold;
            padding: 8px 16px;
            border-radius: 4px;
        }
        .profit-positive {
            color: #00a86b;
            background-color: #e6f7f0;
        }
        .profit-negative {
            color: #dc3545;
            background-color: #ffe6e6;
        }
        .profit-zero {
            color: #666;
            background-color: #f0f0f0;
        }
        .trades-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
        }
        .trades-table th {
            background-color: #4a5568;
            color: white;
            padding: 12px;
            text-align: left;
            font-weight: 600;
        }
        .trades-table td {
            padding: 12px;
            border-bottom: 1px solid #ddd;
        }
        .trades-table tr:hover {
            background-color: #f8f9fa;
        }
        .trade-buy {
            color: #00a86b;
        }
        .trade-sell {
            color: #dc3545;
        }
        .trade-state {
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
        }
        .state-sold {
            background-color: #e6f7f0;
            color: #00a86b;
        }
        .state-active {
            background-color: #fff3cd;
            color: #856404;
        }
        .summary {
            background-color: #e9ecef;
            padding: 20px;
            border-radius: 6px;
            margin-bottom: 30px;
        }
        .summary-item {
            display: inline-block;
            margin-right: 30px;
            font-size: 16px;
        }
        .summary-label {
            font-weight: 600;
            color: #666;
        }
        .summary-value {
            font-weight: bold;
            color: #333;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Trading Records - {{ strategy_name }}</h1>
        
        <div class="summary">
            <div class="summary-item">
                <span class="summary-label">Total Cryptos:</span>
                <span class="summary-value">{{ total_cryptos }}</span>
            </div>
            <div class="summary-item">
                <span class="summary-label">Total Trades:</span>
                <span class="summary-value">{{ total_trades }}</span>
            </div>
            <div class="summary-item">
                <span class="summary-label">Total Profit:</span>
                <span class="summary-value" style="color: {{ 'green' if total_profit > 0 else 'red' if total_profit < 0 else '#666' }}">
                    {{ "%.2f"|format(total_profit) }} USDT
                </span>
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
                        <td>{{ "%.2f"|format(trade.amount) }} USDT</td>
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
        cur.execute("""
            SELECT instId, ordId, create_time, orderType, state, price, size, sell_time, side, sell_price
            FROM orders
            WHERE flag = %s
            ORDER BY create_time DESC
        """, (STRATEGY_NAME,))
        
        rows = cur.fetchall()
        
        # Group by cryptocurrency
        cryptos = defaultdict(lambda: {
            'trades': [],
            'profit': 0.0,
            'profit_pct': 0.0,
            'buy_amount': 0.0,
            'sell_amount': 0.0
        })
        
        for row in rows:
            instId = row['instId']
            buy_price = float(row['price']) if row['price'] else 0.0
            sell_price = float(row['sell_price']) if row.get('sell_price') else 0.0
            size = float(row['size']) if row['size'] else 0.0
            
            trade = {
                'ordId': row['ordId'],
                'time': datetime.fromtimestamp(row['create_time'] / 1000).strftime('%Y-%m-%d %H:%M:%S'),
                'side': row['side'],
                'price': buy_price,
                'sell_price': sell_price,
                'size': size,
                'state': row['state'] if row['state'] else 'active',
                'state_class': 'sold' if row['state'] == 'sold out' else 'active'
            }
            
            # Calculate amount based on buy price
            if buy_price > 0 and size > 0:
                trade['amount'] = buy_price * size
            else:
                trade['amount'] = 0.0
            
            cryptos[instId]['trades'].append(trade)
            
            # Calculate profit using sell_price if available
            if trade['side'] == 'buy':
                cryptos[instId]['buy_amount'] += trade['amount']
            elif trade['side'] == 'sell':
                # Use sell_price if available, otherwise use price (shouldn't happen for sell orders)
                if sell_price > 0 and size > 0:
                    sell_amount = sell_price * size
                    cryptos[instId]['sell_amount'] += sell_amount
                else:
                    cryptos[instId]['sell_amount'] += trade['amount']
        
        # Match buy and sell orders by ordId to calculate profit
        for instId, data in cryptos.items():
            # Group trades by ordId
            trades_by_ordId = {}
            for trade in data['trades']:
                ordId = trade['ordId']
                if ordId not in trades_by_ordId:
                    trades_by_ordId[ordId] = []
                trades_by_ordId[ordId].append(trade)
            
            # Calculate profit by matching buy and sell orders
            total_profit = 0.0
            total_buy_amount = 0.0
            
            for ordId, trades in trades_by_ordId.items():
                buy_trade = next((t for t in trades if t['side'] == 'buy'), None)
                sell_trade = next((t for t in trades if t['side'] == 'sell'), None)
                
                if buy_trade:
                    buy_amount = buy_trade['amount']
                    total_buy_amount += buy_amount
                    
                    if sell_trade and sell_trade.get('sell_price', 0) > 0:
                        # Use sell_price from database
                        sell_amount = sell_trade['sell_price'] * sell_trade['size']
                        trade_profit = sell_amount - buy_amount
                        total_profit += trade_profit
                    elif sell_trade:
                        # Fallback: use price as sell price (for backward compatibility)
                        sell_amount = sell_trade['price'] * sell_trade['size'] if sell_trade['price'] > 0 else 0
                        trade_profit = sell_amount - buy_amount
                        total_profit += trade_profit
            
            data['profit'] = total_profit
            data['buy_amount'] = total_buy_amount
            data['sell_amount'] = total_buy_amount + total_profit
            if total_buy_amount > 0:
                data['profit_pct'] = (total_profit / total_buy_amount) * 100
            
            # Sort trades by time
            data['trades'].sort(key=lambda x: x['time'], reverse=True)
        
        return dict(cryptos)
    finally:
        cur.close()
        conn.close()


@app.route('/')
def index():
    """Display trading records"""
    cryptos = get_trading_records()
    
    # Calculate totals
    total_cryptos = len(cryptos)
    total_trades = sum(len(data['trades']) for data in cryptos.values())
    total_profit = sum(data['profit'] for data in cryptos.values())
    
    return render_template_string(
        HTML_TEMPLATE,
        strategy_name=STRATEGY_NAME,
        cryptos=cryptos,
        total_cryptos=total_cryptos,
        total_trades=total_trades,
        total_profit=total_profit
    )


if __name__ == '__main__':
    print(f"Starting trading records viewer...")
    print(f"Open http://localhost:5000 in your browser")
    app.run(debug=True, host='0.0.0.0', port=5000)
