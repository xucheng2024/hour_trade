#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vercel API - Trading Records Viewer
Read-only API for viewing trading records
"""

import os
import sys
from datetime import datetime
from collections import defaultdict
from flask import Flask, jsonify, render_template_string

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Import database connection
try:
    from src.utils.db_connection import get_database_connection
    import psycopg2.extras
except ImportError as e:
    print(f"Import error: {e}")
    sys.exit(1)

app = Flask(__name__)

STRATEGY_NAME = "hourly_limit_ws"

# HTML Template for web UI
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

        {% for crypto, data in cryptos.items() %}
        <div class="crypto-section">
            <div class="crypto-header">
                <div class="crypto-name">{{ crypto }}</div>
                <div class="profit-badge {{ 'profit-positive' if data.profit > 0 else 'profit-negative' }}">
                    {{ "%.2f"|format(data.profit) }} USDT ({{ "%.2f"|format(data.profit_pct) }}%)
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
    </div>
</body>
</html>
"""


def get_trading_records():
    """Get trading records from PostgreSQL database"""
    try:
        conn = get_database_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Get all orders for this strategy
        cur.execute("""
            SELECT instId, ordId, create_time, orderType, state, price, size, sell_time, side, sell_price
            FROM orders
            WHERE flag = %s
            ORDER BY create_time DESC
            LIMIT 1000
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
            instId = row['instid']
            buy_price = float(row['price']) if row['price'] else 0.0
            sell_price = float(row['sell_price']) if row.get('sell_price') else 0.0
            size = float(row['size']) if row['size'] else 0.0
            
            trade = {
                'ordId': row['ordid'],
                'time': datetime.fromtimestamp(row['create_time'] / 1000).strftime('%Y-%m-%d %H:%M:%S'),
                'side': row['side'],
                'price': buy_price,
                'sell_price': sell_price,
                'size': size,
                'state': row['state'] if row['state'] else 'active',
                'state_class': 'sold' if row['state'] == 'sold out' else 'active'
            }
            
            # Calculate amount
            if buy_price > 0 and size > 0:
                trade['amount'] = buy_price * size
            else:
                trade['amount'] = 0.0
            
            cryptos[instId]['trades'].append(trade)
            
            # Calculate profit
            if trade['side'] == 'buy':
                cryptos[instId]['buy_amount'] += trade['amount']
            elif trade['side'] == 'sell' and sell_price > 0 and size > 0:
                cryptos[instId]['sell_amount'] += sell_price * size
        
        # Calculate profit percentages
        for instId, data in cryptos.items():
            total_profit = data['sell_amount'] - data['buy_amount']
            data['profit'] = total_profit
            if data['buy_amount'] > 0:
                data['profit_pct'] = (total_profit / data['buy_amount']) * 100
            data['trades'].sort(key=lambda x: x['time'], reverse=True)
        
        cur.close()
        conn.close()
        
        return dict(cryptos)
    except Exception as e:
        print(f"Database error: {e}")
        return {}


@app.route('/')
def index():
    """Display trading records (HTML)"""
    cryptos = get_trading_records()
    
    total_cryptos = len(cryptos)
    total_trades = sum(len(data['trades']) for data in cryptos.values())
    total_profit = sum(data['profit'] for data in cryptos.values())
    
    return render_template_string(
        HTML_TEMPLATE,
        cryptos=cryptos,
        total_cryptos=total_cryptos,
        total_trades=total_trades,
        total_profit=total_profit
    )


@app.route('/api/orders')
def api_orders():
    """Get trading records (JSON API)"""
    cryptos = get_trading_records()
    
    return jsonify({
        'success': True,
        'data': {
            'total_cryptos': len(cryptos),
            'total_trades': sum(len(data['trades']) for data in cryptos.values()),
            'total_profit': sum(data['profit'] for data in cryptos.values()),
            'cryptos': cryptos
        }
    })


@app.route('/api/health')
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat()
    })


# Vercel serverless function handler
def handler(event, context):
    """Vercel serverless handler"""
    return app(event, context)


if __name__ == '__main__':
    # Local development
    app.run(debug=True, host='0.0.0.0', port=5000)
