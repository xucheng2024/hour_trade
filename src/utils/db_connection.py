#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Database Connection - Neon PostgreSQL Only
"""

import os
from contextlib import contextmanager
from typing import Optional

import psycopg2
from psycopg2.extras import RealDictCursor

# Load environment variables
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "")
DB_TYPE = "postgresql"

if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is required")

if not DATABASE_URL.startswith("postgresql://"):
    raise ValueError("DATABASE_URL must be a PostgreSQL connection string")


def get_database_connection():
    """Get PostgreSQL database connection"""
    return psycopg2.connect(DATABASE_URL)


@contextmanager
def get_db_cursor():
    """Get database cursor as context manager"""
    conn = get_database_connection()
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        yield cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def execute_query(query: str, params: Optional[tuple] = None):
    """Execute query and return results"""
    with get_db_cursor() as cursor:
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        return cursor.fetchall()


def execute_update(query: str, params: Optional[tuple] = None):
    """Execute update query"""
    with get_db_cursor() as cursor:
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)


def get_placeholder():
    """Get SQL placeholder style (%s for PostgreSQL)"""
    return "%s"


def get_orders_table_schema():
    """Get CREATE TABLE statement for orders table"""
    return """
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


def init_orders_table():
    """Initialize orders table"""
    with get_db_cursor() as cursor:
        cursor.execute(get_orders_table_schema())

        # Add sell_price column if it doesn't exist (for existing databases)
        cursor.execute(
            """
            ALTER TABLE orders
            ADD COLUMN IF NOT EXISTS sell_price VARCHAR(50)
        """
        )

        # Create indexes for better performance
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_orders_flag ON orders(flag)
        """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_orders_instId ON orders(instId)
        """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_orders_ordId ON orders(ordId)
        """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_orders_create_time ON orders(create_time)
        """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_orders_flag_instId ON orders(flag, instId)
        """
        )
        # Composite index for optimized web viewer queries
        # (flag LIKE + ORDER BY create_time)
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_orders_flag_create_time
            ON orders(flag, create_time DESC)
        """
        )


if __name__ == "__main__":
    # Test database connection
    print(f"Database type: {DB_TYPE}")
    try:
        init_orders_table()
        print("✅ Orders table initialized successfully")
    except Exception as e:
        print(f"❌ Error initializing orders table: {e}")
