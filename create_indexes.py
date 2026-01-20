#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Create recommended database indexes for order_sync performance
"""

import os
import sys

import psycopg
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL not found in environment variables")

# Recommended indexes from order_sync.py
indexes = [
    {
        "name": "idx_orders_flag_state_sell_price",
        "sql": """
        CREATE INDEX IF NOT EXISTS idx_orders_flag_state_sell_price
        ON orders(flag, state, sell_price)
        WHERE sell_price IS NULL OR sell_price = '';
        """,
        "description": (
            "Index for recovery queries filtering by flag, state, and sell_price"
        ),
    },
    {
        "name": "idx_orders_instid_ordid_flag",
        "sql": """
        CREATE INDEX IF NOT EXISTS idx_orders_instid_ordid_flag
        ON orders(instId, ordId, flag);
        """,
        "description": "Index for sync queries filtering by instId, ordId, and flag",
    },
    {
        "name": "idx_orders_flag_createtime",
        "sql": """
        CREATE INDEX IF NOT EXISTS idx_orders_flag_createtime 
        ON orders(flag, create_time DESC);
        """,
        "description": "Index for time-based scans ordered by create_time",
    },
]


def main():
    """Create all recommended indexes"""
    try:
        conn = psycopg.connect(DATABASE_URL, connect_timeout=10)
        cur = conn.cursor()

        print("Creating database indexes for order_sync performance...")
        print("-" * 60)

        for idx in indexes:
            try:
                print(f"\nCreating index: {idx['name']}")
                print(f"Description: {idx['description']}")
                cur.execute(idx["sql"])
                conn.commit()
                print(f"✅ Successfully created index: {idx['name']}")
            except psycopg.Error as e:
                conn.rollback()
                if "already exists" in str(e).lower():
                    print(f"⚠️  Index {idx['name']} already exists, skipping")
                else:
                    print(f"❌ Error creating index {idx['name']}: {e}")

        # Verify indexes were created
        print("\n" + "-" * 60)
        print("Verifying indexes...")
        cur.execute(
            """
            SELECT indexname, indexdef 
            FROM pg_indexes 
            WHERE tablename = 'orders' 
            AND indexname LIKE 'idx_orders_%'
            ORDER BY indexname;
        """
        )
        existing_indexes = cur.fetchall()

        if existing_indexes:
            print(f"\n✅ Found {len(existing_indexes)} index(es) on orders table:")
            for idx_name, idx_def in existing_indexes:
                print(f"  - {idx_name}")
        else:
            print(
                "\n⚠️  No indexes found (this might be normal if they weren't created)"
            )

        cur.close()
        conn.close()
        print("\n✅ Index creation completed!")

    except psycopg.Error as e:
        print(f"❌ Database error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
