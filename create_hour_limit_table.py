#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
创建 hour_limit 表并导入 valid_crypto_limits.json 的数据
"""

import json
import os

import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL not found in environment variables")

LIMITS_FILE = "valid_crypto_limits.json"


def create_hour_limit_table():
    """创建 hour_limit 表"""
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    try:
        # 创建表
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS hour_limit (
                id SERIAL PRIMARY KEY,
                inst_id VARCHAR(50) NOT NULL UNIQUE,
                limit_percent NUMERIC(5,2) NOT NULL,
                limit_ratio NUMERIC(10,8) NOT NULL,
                consistency NUMERIC(5,2),
                mean_return_timeslices NUMERIC(10,4),
                median_return_timeslices NUMERIC(10,4),
                recent_12m_return NUMERIC(10,4),
                sharpe_like NUMERIC(10,4),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # 创建索引
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_hour_limit_inst_id
            ON hour_limit(inst_id)
        """
        )

        conn.commit()
        print("✅ hour_limit 表创建成功")
        return True
    except Exception as e:
        print(f"❌ 创建表失败: {e}")
        conn.rollback()
        return False
    finally:
        cur.close()
        conn.close()


def import_limits_from_json():
    """从 valid_crypto_limits.json 导入数据到 hour_limit 表"""
    if not os.path.exists(LIMITS_FILE):
        print(f"❌ 文件不存在: {LIMITS_FILE}")
        return False

    # 读取 JSON 文件
    with open(LIMITS_FILE, "r") as f:
        data = json.load(f)

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    try:
        count = 0
        for inst_id, info in data["cryptos"].items():
            # 使用 INSERT ... ON CONFLICT UPDATE
            cur.execute(
                """
                INSERT INTO hour_limit
                (inst_id, limit_percent, limit_ratio, consistency,
                 mean_return_timeslices, median_return_timeslices,
                 recent_12m_return, sharpe_like, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (inst_id)
                DO UPDATE SET
                    limit_percent = EXCLUDED.limit_percent,
                    limit_ratio = EXCLUDED.limit_ratio,
                    consistency = EXCLUDED.consistency,
                    mean_return_timeslices = EXCLUDED.mean_return_timeslices,
                    median_return_timeslices = EXCLUDED.median_return_timeslices,
                    recent_12m_return = EXCLUDED.recent_12m_return,
                    sharpe_like = EXCLUDED.sharpe_like,
                    updated_at = CURRENT_TIMESTAMP
            """,
                (
                    inst_id,
                    info.get("limit_percent"),
                    info.get("limit_ratio"),
                    info.get("consistency"),
                    info.get("mean_return_timeslices"),
                    info.get("median_return_timeslices"),
                    info.get("recent_12m_return"),
                    info.get("sharpe_like"),
                ),
            )
            count += 1

        conn.commit()
        print(f"✅ 成功导入 {count} 条记录到 hour_limit 表")
        return True
    except Exception as e:
        print(f"❌ 导入数据失败: {e}")
        conn.rollback()
        return False
    finally:
        cur.close()
        conn.close()


def main():
    print("=" * 60)
    print("创建 hour_limit 表并导入数据")
    print("=" * 60)
    print()

    # 创建表
    if not create_hour_limit_table():
        return

    print()

    # 导入数据
    if not import_limits_from_json():
        return

    print()
    print("=" * 60)
    print("✅ 完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
