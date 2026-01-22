#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Initialize database tables - Neon PostgreSQL
"""

import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from utils.db_connection import DB_TYPE, init_orders_table  # noqa: E402


def main():
    """Initialize database tables"""
    print(f"🔧 Initializing database ({DB_TYPE})...")
    try:
        init_orders_table()
        print("✅ Database tables initialized successfully")
        return 0
    except Exception as e:
        print(f"❌ Error initializing database: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
