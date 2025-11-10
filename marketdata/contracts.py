# marketdata/contracts.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Dict


@dataclass(frozen=True)
class SymbolSpec:
    symbol: str
    display: str
    base: str
    quote: str
    precision: int           # UI/rounding precision for prices
    pip: float               # minimum price increment (e.g. 0.0001 for most FX)
    contract_size: float     # notional per 1.00 lot
    min_lot: float = 0.01
    lot_step: float = 0.01
    max_lot: float = 1000.0
    leverage_max: int = 500
    price_bounds_pct: Optional[float] = None   # optional circuit breaker
    trading_hours: Optional[str] = None        # optional info


# --- Symbol catalog ---
SPECS: Dict[str, SymbolSpec] = {
    # Majors (existing)
    "EURUSD": SymbolSpec(
        symbol="EURUSD", display="EUR/USD", base="EUR", quote="USD",
        precision=5, pip=0.0001, contract_size=100_000,
        min_lot=0.01, lot_step=0.01, max_lot=1000.0, leverage_max=500,
    ),
    "GBPUSD": SymbolSpec(
        symbol="GBPUSD", display="GBP/USD", base="GBP", quote="USD",
        precision=5, pip=0.0001, contract_size=100_000,
        min_lot=0.01, lot_step=0.01, max_lot=1000.0, leverage_max=500,
    ),
    "USDJPY": SymbolSpec(
        symbol="USDJPY", display="USD/JPY", base="USD", quote="JPY",
        precision=3, pip=0.01, contract_size=100_000,
        min_lot=0.01, lot_step=0.01, max_lot=1000.0, leverage_max=500,
    ),
    "AUDUSD": SymbolSpec(
        symbol="AUDUSD", display="AUD/USD", base="AUD", quote="USD",
        precision=5, pip=0.0001, contract_size=100_000,
        min_lot=0.01, lot_step=0.01, max_lot=1000.0, leverage_max=500,
    ),
    "USDCAD": SymbolSpec(
        symbol="USDCAD", display="USD/CAD", base="USD", quote="CAD",
        precision=5, pip=0.0001, contract_size=100_000,
        min_lot=0.01, lot_step=0.01, max_lot=1000.0, leverage_max=500,
    ),

    # Crypto (existing)
    "BTCUSDT": SymbolSpec(
        symbol="BTCUSDT", display="BTC/USDT", base="BTC", quote="USDT",
        precision=2, pip=0.01, contract_size=1.0,           # 1 lot = 1 BTC
        min_lot=0.001, lot_step=0.001, max_lot=100.0, leverage_max=500,
        price_bounds_pct=0.20,  # optional 20% guardrail
    ),

    # --- NEW: Metals ---
    # Gold
    "XAUUSD": SymbolSpec(
        symbol="XAUUSD", display="XAU/USD", base="XAU", quote="USD",
        precision=2, pip=0.01, contract_size=100.0,          # 1 lot = 100 oz
        min_lot=0.01, lot_step=0.01, max_lot=500.0, leverage_max=500,
    ),
    # Silver
    "XAGUSD": SymbolSpec(
        symbol="XAGUSD", display="XAG/USD", base="XAG", quote="USD",
        precision=3, pip=0.001, contract_size=5000.0,        # 1 lot = 5,000 oz
        min_lot=0.01, lot_step=0.01, max_lot=500.0, leverage_max=500,
    ),

    # --- NEW: FX ---
    "NZDUSD": SymbolSpec(
        symbol="NZDUSD", display="NZD/USD", base="NZD", quote="USD",
        precision=5, pip=0.0001, contract_size=100_000,
        min_lot=0.01, lot_step=0.01, max_lot=1000.0, leverage_max=500,
    ),
}


def spec_for(symbol: str) -> SymbolSpec:
    """
    Fetch a SymbolSpec by symbol, case-insensitive.
    Raises KeyError if the symbol isn't configured.
    """
    key = (symbol or "").upper()
    return SPECS[key]
