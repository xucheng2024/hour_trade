#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script to verify real-time crypto data reception and simulate buy/sell database writes
"""

import json
import os
import threading
import time
import uuid
from datetime import datetime, timedelta

import psycopg
import websocket
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LIMITS_FILE = os.path.join(BASE_DIR, "valid_crypto_limits.json")
DATABASE_URL = os.getenv("DATABASE_URL")
STRATEGY_NAME = "hourly_limit_ws_test"

# Test configuration
TEST_DURATION = 30  # seconds to receive real-time data
MAX_MESSAGES = 50  # max messages to receive before stopping

# Global variables
received_messages = {}
message_count = 0
test_cryptos = []


def get_db_connection():
    """Get PostgreSQL database connection"""
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL not found in environment variables")
    return psycopg.connect(DATABASE_URL)


def load_crypto_limits():
    """Load crypto limits from JSON file"""
    try:
        with open(LIMITS_FILE, "r") as f:
            data = json.load(f)
        cryptos = list(data["cryptos"].keys())
        print(f"✅ Loaded {len(cryptos)} cryptos from {LIMITS_FILE}")
        return cryptos[:10]  # Test with first 10 cryptos
    except Exception as e:
        print(f"❌ Failed to load crypto limits: {e}")
        return []


def on_ticker_message(ws, msg_string):
    """Handle ticker WebSocket messages"""
    global message_count, received_messages

    if msg_string == "pong":
        return

    try:
        m = json.loads(msg_string)
        ev = m.get("event")
        data = m.get("data")

        if ev == "error":
            print(f"❌ WebSocket error: {msg_string}")
        elif ev in ["subscribe", "unsubscribe"]:
            print(f"📡 {ev}: {msg_string}")
        elif data and isinstance(data, list):
            message_count += 1
            for ticker in data:
                instId = ticker.get("instId")
                if instId in test_cryptos:
                    last_price = float(ticker.get("last", 0))
                    if last_price > 0:
                        received_messages[instId] = {
                            "price": last_price,
                            "timestamp": datetime.now().isoformat(),
                            "data": ticker,
                        }
                        print(
                            f"📊 {instId}: ${last_price:.6f} (messages received: {message_count})"
                        )

                        if message_count >= MAX_MESSAGES:
                            ws.close()
                            return
    except Exception as e:
        print(f"❌ Message processing error: {e}")


def on_ticker_open(ws):
    """Handle WebSocket open event"""
    print("✅ WebSocket connected, subscribing to tickers...")

    # Subscribe to ticker channels for test cryptos
    channels = [{"channel": "tickers", "instId": instId} for instId in test_cryptos]

    # OKX allows max 20 subscriptions per message, split if needed
    batch_size = 20
    for i in range(0, len(channels), batch_size):
        batch = channels[i : i + batch_size]
        subscribe_msg = {"op": "subscribe", "args": batch}
        ws.send(json.dumps(subscribe_msg))
        print(f"📡 Subscribed to {len(batch)} tickers (batch {i//batch_size + 1})")
        time.sleep(0.1)  # Small delay between batches


def test_realtime_data():
    """Test receiving real-time crypto data"""
    print("\n" + "=" * 60)
    print("TEST 1: Real-time Crypto Data Reception")
    print("=" * 60)

    global test_cryptos
    test_cryptos = load_crypto_limits()

    if not test_cryptos:
        print("❌ No cryptos to test")
        return False

    print(f"\n📋 Testing with {len(test_cryptos)} cryptos:")
    for i, crypto in enumerate(test_cryptos[:10], 1):
        print(f"  {i}. {crypto}")

    print(
        f"\n⏱️  Receiving data for up to {TEST_DURATION} seconds or {MAX_MESSAGES} messages..."
    )
    print("🔌 Connecting to OKX WebSocket...")

    # Connect to OKX public WebSocket
    ticker_url = "wss://ws.okx.com:8443/ws/v5/public"

    ws = websocket.WebSocketApp(
        ticker_url, on_message=on_ticker_message, on_open=on_ticker_open
    )

    # Run WebSocket in a thread with timeout
    ws_thread = threading.Thread(target=ws.run_forever, daemon=True)
    ws_thread.start()

    # Wait for TEST_DURATION seconds or until max messages
    start_time = time.time()
    while time.time() - start_time < TEST_DURATION and message_count < MAX_MESSAGES:
        time.sleep(1)

    ws.close()
    time.sleep(1)

    # Print results
    print(f"\n📊 Results:")
    print(f"  - Total messages received: {message_count}")
    print(f"  - Unique cryptos with data: {len(received_messages)}")

    if received_messages:
        print(f"\n✅ Successfully received real-time data for:")
        for instId, info in list(received_messages.items())[:10]:
            print(f"  - {instId}: ${info['price']:.6f} at {info['timestamp']}")
        return True
    else:
        print("❌ No real-time data received")
        return False


def simulate_buy_order(instId: str, price: float, size: float, conn):
    """Simulate buy order database write"""
    cur = conn.cursor()
    try:
        now = datetime.now()
        next_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)

        create_time = int(now.timestamp() * 1000)
        sell_time = int(next_hour.timestamp() * 1000)
        ordId = f"TEST-BUY-{uuid.uuid4().hex[:12]}"

        cur.execute(
            """INSERT INTO orders (instId, flag, ordId, create_time, orderType, state, price, size, sell_time, side)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                instId,
                STRATEGY_NAME,
                ordId,
                create_time,
                "limit",
                "pending",
                str(price),
                str(size),
                sell_time,
                "buy",
            ),
        )
        conn.commit()
        print(
            f"  ✅ Buy order written: {instId}, ordId={ordId}, price={price}, size={size}"
        )
        return ordId
    except Exception as e:
        print(f"  ❌ Buy order write error: {e}")
        conn.rollback()
        return None
    finally:
        cur.close()


def simulate_sell_order(instId: str, ordId: str, sell_price: float, conn):
    """Simulate sell order database update"""
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE orders SET state = %s, sell_price = %s WHERE instId = %s AND ordId = %s AND flag = %s",
            ("sold out", str(sell_price), instId, ordId, STRATEGY_NAME),
        )
        conn.commit()
        rows_updated = cur.rowcount
        if rows_updated > 0:
            print(
                f"  ✅ Sell order updated: {instId}, ordId={ordId}, sell_price={sell_price}"
            )
            return True
        else:
            print(f"  ⚠️  No order found to update: {instId}, ordId={ordId}")
            return False
    except Exception as e:
        print(f"  ❌ Sell order update error: {e}")
        conn.rollback()
        return False
    finally:
        cur.close()


def test_database_writes():
    """Test buy/sell database writes"""
    print("\n" + "=" * 60)
    print("TEST 2: Buy/Sell Database Writes")
    print("=" * 60)

    # Test database connection
    try:
        conn = get_db_connection()
        print("✅ Database connection established")
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False

    try:
        # Initialize orders table if needed
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY,
                instId VARCHAR(50) NOT NULL,
                flag VARCHAR(50) NOT NULL,
                ordId VARCHAR(100) NOT NULL,
                create_time BIGINT NOT NULL,
                orderType VARCHAR(20),
                state TEXT,
                price VARCHAR(50),
                size VARCHAR(50),
                sell_time BIGINT,
                side VARCHAR(10),
                sell_price VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Add sell_price column if it doesn't exist
        cur.execute(
            """
            ALTER TABLE orders 
            ADD COLUMN IF NOT EXISTS sell_price VARCHAR(50)
        """
        )
        conn.commit()
        cur.close()
        print("✅ Orders table ready")
    except Exception as e:
        print(f"⚠️  Table initialization: {e}")

    try:
        # Test buy order writes
        print("\n📝 Simulating buy orders...")
        buy_orders = []

        test_data = [
            ("BTC-USDT", 50000.0, 0.001),
            ("ETH-USDT", 3000.0, 0.01),
            ("SOL-USDT", 100.0, 0.1),
        ]

        for instId, price, size in test_data:
            ordId = simulate_buy_order(instId, price, size, conn)
            if ordId:
                buy_orders.append((instId, ordId, price))

        # Test sell order updates
        print("\n💰 Simulating sell orders...")
        for instId, ordId, buy_price in buy_orders:
            # Simulate selling at 2% profit
            sell_price = buy_price * 1.02
            simulate_sell_order(instId, ordId, sell_price, conn)

        # Verify writes
        print("\n🔍 Verifying database writes...")
        cur = conn.cursor()
        cur.execute(
            "SELECT instId, ordId, price, sell_price, state, side FROM orders WHERE flag = %s ORDER BY create_time DESC LIMIT 10",
            (STRATEGY_NAME,),
        )
        rows = cur.fetchall()
        cur.close()

        if rows:
            print(f"\n✅ Found {len(rows)} test orders in database:")
            for row in rows:
                instId, ordId, price, sell_price, state, side = row
                print(
                    f"  - {instId} ({side}): price={price}, sell_price={sell_price}, state={state}"
                )
            return True
        else:
            print("⚠️  No test orders found in database")
            return False
    finally:
        conn.close()


def main():
    """Main test function"""
    print("\n" + "=" * 60)
    print("CRYPTO REAL-TIME DATA & DATABASE TEST")
    print("=" * 60)

    # Test 1: Real-time data reception
    realtime_success = test_realtime_data()

    # Test 2: Database writes
    db_success = test_database_writes()

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"Real-time data reception: {'✅ PASS' if realtime_success else '❌ FAIL'}")
    print(f"Database writes: {'✅ PASS' if db_success else '❌ FAIL'}")

    if realtime_success and db_success:
        print("\n✅ All tests passed!")
        return 0
    else:
        print("\n❌ Some tests failed")
        return 1


if __name__ == "__main__":
    exit(main())
