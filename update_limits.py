#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Update limit_percent values in hour_limit table
"""

import os
import sys

import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL not found in environment variables")

# Limits to update
LIMITS_TO_UPDATE = {
    "BABYDOGE-USDT": 95.0,
    "RSS3-USDT": 97.5,
    "TURBO-USDT": 91.5,
    "ENS-USDT": 96.5,
    "DORA-USDT": 94.5,
    "BONK-USDT": 96.0,
    "JTO-USDT": 96.0,
    "APT-USDT": 88.0,
    "NFT-USDT": 96.5,
    "IMX-USDT": 88.0,
    "LDO-USDT": 92.0,
    "ASTR-USDT": 88.5,
    "SUI-USDT": 96.5,
    "STORJ-USDT": 90.0,
    "LUNA-USDT": 85.0,
    "BICO-USDT": 88.0,
    "LTC-USDT": 97.0,
    "APE-USDT": 87.5,
    "LRC-USDT": 88.0,
    "UMA-USDT": 87.5,
    "CELO-USDT": 85.0,
    "NEO-USDT": 90.5,
    "RVN-USDT": 88.5,
    "ZIL-USDT": 87.0,
    "VRA-USDT": 96.5,
    "DOGE-USDT": 95.0,
    "STX-USDT": 96.5,
    "SKL-USDT": 90.5,
    "GRT-USDT": 87.5,
    "SOL-USDT": 96.0,
    "IOTA-USDT": 95.5,
    "FET-USDT": 97.0,
    "SAND-USDT": 96.5,
    "KSM-USDT": 88.0,
    "OKB-USDT": 97.5,
    "AR-USDT": 86.5,
}


def update_limits(limits_dict):
    """Update limit_percent and limit_ratio in hour_limit table

    Args:
        limits_dict: Dictionary with inst_id as key and limit_percent as value
    """
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    try:
        updated = 0
        not_found = []

        print(f"Updating {len(limits_dict)} limits...")
        print("=" * 60)

        for inst_id, limit_percent in limits_dict.items():
            limit_ratio = limit_percent / 100.0

            # Update existing records only
            cur.execute(
                """
                UPDATE hour_limit
                SET limit_percent = %s,
                    limit_ratio = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE inst_id = %s
                """,
                (limit_percent, limit_ratio, inst_id),
            )

            if cur.rowcount > 0:
                updated += 1
                print(f"✅ {inst_id}: {limit_percent}% (ratio: {limit_ratio:.6f})")
            else:
                not_found.append(inst_id)
                print(f"⚠️  {inst_id}: NOT FOUND in database")

        conn.commit()
        print()
        print("=" * 60)
        print(f"✅ Successfully updated {updated} out of {len(limits_dict)} records")
        if not_found:
            print(f"⚠️  {len(not_found)} records not found: {', '.join(not_found)}")
        return True
    except Exception as e:
        print(f"❌ Update failed: {e}")
        import traceback

        traceback.print_exc()
        conn.rollback()
        return False
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    print("=" * 60)
    print("Update Database Limits")
    print("=" * 60)
    print()

    if not update_limits(LIMITS_TO_UPDATE):
        sys.exit(1)

    print()
    print("=" * 60)
    print("✅ Done!")
    print("=" * 60)
