#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Update limit_percent values in hour_limit table
"""

import os
import sys

import psycopg
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL not found in environment variables")

# Limits to update: inst_id -> limit_percent
LIMITS_TO_UPDATE = {
    "1INCH-USDT": 91.0,
    "AAVE-USDT": 92.0,
    "ADA-USDT": 93.0,
    "ALGO-USDT": 92.0,
    "APE-USDT": 90.0,
    "API3-USDT": 90.0,
    "APT-USDT": 90.0,
    "AR-USDT": 92.0,
    "ASTR-USDT": 90.0,
    "AVAX-USDT": 92.0,
    "AXS-USDT": 92.0,
    "BABYDOGE-USDT": 89.0,
    "BAND-USDT": 91.0,
    "BAT-USDT": 92.0,
    "BCH-USDT": 93.0,
    "BETH-USDT": 94.0,
    "BICO-USDT": 91.0,
    "BLUR-USDT": 90.0,
    "BONK-USDT": 91.0,
    "CELR-USDT": 91.0,
    "CFX-USDT": 89.0,
    "CHZ-USDT": 91.0,
    "COMP-USDT": 91.0,
    "CORE-USDT": 87.0,
    "CRV-USDT": 91.0,
    "CTC-USDT": 90.0,
    "CVX-USDT": 91.0,
    "DGB-USDT": 91.0,
    "DOGE-USDT": 91.0,
    "DORA-USDT": 88.0,
    "DYDX-USDT": 89.0,
    "EGLD-USDT": 92.0,
    "ENS-USDT": 91.0,
    "ETC-USDT": 91.0,
    "ETHFI-USDT": 93.0,
    "ETHW-USDT": 88.0,
    "FLOW-USDT": 91.0,
    "FLR-USDT": 93.0,
    "GALA-USDT": 89.0,
    "GALFT-USDT": 92.0,
    "GAS-USDT": 88.0,
    "GMT-USDT": 89.0,
    "GODS-USDT": 87.0,
    "GRT-USDT": 91.0,
    "HBAR-USDT": 92.0,
    "ICP-USDT": 92.0,
    "ICX-USDT": 92.0,
    "ILV-USDT": 92.0,
    "IMX-USDT": 91.0,
    "JTO-USDT": 93.0,
    "JUP-USDT": 95.0,
    "KNC-USDT": 92.0,
    "KSM-USDT": 91.0,
    "LAT-USDT": 89.0,
    "LDO-USDT": 91.0,
    "LPT-USDT": 90.0,
    "LRC-USDT": 91.0,
    "LTC-USDT": 93.0,
    "LUNA-USDT": 85.0,
    "MAGIC-USDT": 88.0,
    "MANA-USDT": 91.0,
    "MEME-USDT": 89.0,
    "METIS-USDT": 93.0,
    "MINA-USDT": 91.0,
    "NEAR-USDT": 92.0,
    "NMR-USDT": 91.0,
    "OKB-USDT": 94.0,
    "ONE-USDT": 90.0,
    "ONT-USDT": 92.0,
    "OP-USDT": 90.0,
    "ORBS-USDT": 91.0,
    "ORDI-USDT": 90.0,
    "PEOPLE-USDT": 85.0,
    "PEPE-USDT": 90.0,
    "RAY-USDT": 91.0,
    "RENDER-USDT": 94.0,
    "RIO-USDT": 86.0,
    "RON-USDT": 92.0,
    "RSR-USDT": 90.0,
    "RSS3-USDT": 90.0,
    "RVN-USDT": 91.0,
    "SAND-USDT": 91.0,
    "SATS-USDT": 90.0,
    "SD-USDT": 89.0,
    "SHIB-USDT": 90.0,
    "SKL-USDT": 91.0,
    "SNX-USDT": 91.0,
    "SOL-USDT": 92.0,
    "STETH-USDT": 95.0,
    "STORJ-USDT": 90.0,
    "STRK-USDT": 93.0,
    "STX-USDT": 91.0,
    "SUI-USDT": 92.0,
    "T-USDT": 90.0,
    "THETA-USDT": 92.0,
    "TIA-USDT": 92.0,
    "TNSR-USDT": 93.0,
    "TON-USDT": 92.0,
    "TURBO-USDT": 87.0,
    "UNI-USDT": 92.0,
    "VELO-USDT": 90.0,
    "WAXP-USDT": 92.0,
    "WIF-USDT": 93.0,
    "WLD-USDT": 92.0,
    "WOO-USDT": 91.0,
    "XLM-USDT": 93.0,
    "XRP-USDT": 92.0,
    "XTZ-USDT": 93.0,
    "YGG-USDT": 88.0,
    "ZBCN-USDT": 92.0,
    "ZEUS-USDT": 92.0,
    "ZIL-USDT": 91.0,
    "ZK-USDT": 94.0,
    "ZRX-USDT": 90.0,
}


def update_limits(limits_dict):
    """Update or insert limit_percent and limit_ratio in hour_limit table (UPSERT).

    Args:
        limits_dict: Dictionary with inst_id as key and limit_percent as value
    """
    conn = psycopg.connect(DATABASE_URL)
    cur = conn.cursor()

    try:
        print(f"Upserting {len(limits_dict)} limits...")
        print("=" * 60)

        for inst_id, limit_percent in limits_dict.items():
            limit_ratio = limit_percent / 100.0

            cur.execute(
                """
                INSERT INTO hour_limit (inst_id, limit_percent, limit_ratio, updated_at)
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (inst_id)
                DO UPDATE SET
                    limit_percent = EXCLUDED.limit_percent,
                    limit_ratio = EXCLUDED.limit_ratio,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (inst_id, limit_percent, limit_ratio),
            )
            print(f"✅ {inst_id}: {limit_percent}% (ratio: {limit_ratio:.6f})")

        conn.commit()
        print()
        print("=" * 60)
        print(f"✅ Successfully upserted {len(limits_dict)} records")
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
