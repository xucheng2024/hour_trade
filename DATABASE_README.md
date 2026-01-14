# Database Configuration - Neon PostgreSQL

## Overview

This project uses **Neon PostgreSQL** as the database backend.

## Configuration

### Environment Variable

Set `DATABASE_URL` in `.env` file:

```bash
DATABASE_URL=postgresql://neondb_owner:npg_F4epMLXJ8ity@ep-wispy-smoke-a1qg30ip-pooler.ap-southeast-1.aws.neon.tech/crypto_trading?sslmode=require&channel_binding=require
```

## Database Tables

The following tables are automatically created:

### Main Project Tables

1. **orders** - Trading orders
   - `id` - Primary key
   - `instId` - Instrument ID (e.g., BTC-USDT)
   - `flag` - Strategy flag (e.g., hourly_limit_ws)
   - `ordId` - Order ID
   - `create_time` - Order creation timestamp
   - `orderType` - Order type (limit, market)
   - `state` - Order state (sold out, active, etc.)
   - `price` - Buy price
   - `size` - Order size
   - `sell_time` - Planned sell time
   - `side` - Order side (buy, sell)
   - `sell_price` - Actual sell price
   - `created_at` - Database record creation time

### crypto_remote Tables

2. **filled_orders** - Filled order history
3. **okx_announcements** - OKX announcements
4. **trading_history** - Trading history
5. **monitoring_logs** - System monitoring logs
6. **limits_config** - Strategy configuration
7. **crypto_limits** - Crypto-specific limits
8. **crypto_7day_drops** - 7-day drop configurations
9. **blacklist** - Blacklisted cryptos
10. **active_blacklist** - Active blacklist entries
11. **processed_announcements** - Processed announcements

## Initialization

### First Time Setup

```bash
# Initialize all tables
python3 init_database.py
```

### Verify Tables

```bash
# Check existing tables
python3 -c "
import os, sys
sys.path.insert(0, 'src')
from dotenv import load_dotenv
load_dotenv()
import psycopg2

conn = psycopg2.connect(os.getenv('DATABASE_URL'))
cur = conn.cursor()
cur.execute(\"SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name\")
print('Tables:', [t[0] for t in cur.fetchall()])
cur.close()
conn.close()
"
```

## Usage

### Main Project

```python
from utils.db_connection import get_database_connection

conn = get_database_connection()
cur = conn.cursor()
# Your queries here
cur.close()
conn.close()
```

### crypto_remote

```python
from lib.database import Database

db = Database()
db.connect()
# Your operations here
db.disconnect()
```

## Shared Database

Both the main project and `crypto_remote` modules share the same Neon PostgreSQL database, ensuring data consistency across all components.

## Connection Details

- **Provider**: Neon PostgreSQL
- **Region**: ap-southeast-1 (Singapore)
- **Version**: PostgreSQL 17.7
- **Connection**: IPv4 supported (no IPv6 required)
- **SSL**: Required

## Backup & Maintenance

Neon provides automatic backups. For manual operations:

1. Access Neon Console: https://console.neon.tech
2. Navigate to your project
3. Use SQL Editor or pg_dump for backups

## Troubleshooting

### Connection Issues

```bash
# Test connection
python3 -c "
import os, sys
sys.path.insert(0, 'src')
from dotenv import load_dotenv
load_dotenv()
import psycopg2
conn = psycopg2.connect(os.getenv('DATABASE_URL'))
print('✅ Connected successfully')
conn.close()
"
```

### Missing Tables

```bash
# Reinitialize tables
python3 init_database.py
```

## Migration from SQLite/Supabase

SQLite and Supabase support has been removed. This project now exclusively uses Neon PostgreSQL for:
- Better performance
- IPv4 connectivity
- Unified database across all modules
- Cloud-native scalability

---

**Last Updated**: 2026-01-14
**Database**: Neon PostgreSQL
**Status**: ✅ Production Ready
