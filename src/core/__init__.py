"""
Core trading functionality module.
Contains order management, WebSocket handling, and core trading functions.
"""

# Avoid circular imports by using lazy imports
# Only import what's actually needed, and make imports optional
from typing import Any, Callable, Optional

GetTradeApiFunc = Callable[
    [Optional[str], Optional[str], Optional[str], str, bool], Any
]
GetMarketApiFunc = Callable[[str], Any]
GetPublicApiFunc = Callable[[str], Any]
GetInstrumentPrecisionFunc = Callable[[str, bool, str], Optional[dict]]
FormatNumberFunc = Callable[[Any, Optional[str], str], Any]

get_trade_api: Optional[GetTradeApiFunc]
get_market_api: Optional[GetMarketApiFunc]
get_public_api: Optional[GetPublicApiFunc]
get_instrument_precision: Optional[GetInstrumentPrecisionFunc]
format_number: Optional[FormatNumberFunc]
try:
    from .okx_functions import (
        format_number,
        get_instrument_precision,
        get_market_api,
        get_public_api,
        get_trade_api,
    )
except ImportError:
    # If okx_functions fails to import (e.g., numpy missing), set to None
    get_trade_api = None
    get_market_api = None
    get_public_api = None
    get_instrument_precision = None
    format_number = None

# Don't import okx_order_manage, okx_ws_manage, okx_ws_buy here
# They are not used by websocket_limit_trading.py directly
# and they cause circular import issues

__all__ = [
    "get_trade_api",
    "get_market_api",
    "get_public_api",
    "get_instrument_precision",
    "format_number",
]
