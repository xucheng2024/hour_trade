# OKX Trading Bot

A comprehensive cryptocurrency trading bot system for the OKX exchange platform.

## Requirements

- **Python**: 3.6 or higher (required for f-string support)
- **Dependencies**: See `requirements.txt`

## Quick Start

1. **Install Python 3.6+**
   ```bash
   # Check your Python version
   python3 --version
   ```

2. **Install dependencies**
   ```bash
   pip3 install -r requirements.txt
   ```

3. **Run the bot**
   ```bash
   python3 main.py
   ```

## Project Structure

- `src/core/` - Core trading functionality
- `src/strategies/` - Trading strategies
- `src/data/` - Data management
- `src/system/` - System utilities
- `src/utils/` - Utility functions
- `src/config/` - Configuration files

## Configuration

Edit `src/config/cryptos_selected.json` to select cryptocurrencies for trading.

## Database

The bot uses SQLite (`okx.db`) for storing order history and market data.

## Logging

Logs are written to `trading_bot.log` and displayed in the console.

## Development

- Use `python3` for all Python commands
- Follow the modular structure in `src/`
- Check `PROJECT_SUMMARY.md` for detailed project information
