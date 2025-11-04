# contracts.py
from dataclasses import dataclass

@dataclass(frozen=True)
class SymbolSpec:
    symbol: str
    display: str
    base: str
    quote: str
    precision: int       # price decimals to show
    pip: float           # 0.0001 for majors, 0.001 for JPY, 0.01 for XAU
    contract_size: int   # 100000 for FX, 100 for XAU
    min_lot: float
    lot_step: float
    max_lot: float
    leverage_max: int
    margin_currency: str
    trading_hours: str   # "24x5" placeholder
    price_bounds_pct: float  # reject orders +/- this pct from mark

SPECS: dict[str, SymbolSpec] = {
    "EURUSD": SymbolSpec(
        symbol="EURUSD", display="EUR/USD", base="EUR", quote="USD",
        precision=5, pip=0.0001, contract_size=100000,
        min_lot=0.01, lot_step=0.01, max_lot=100.0,
        leverage_max=5000, margin_currency="USD", trading_hours="24x5",
        price_bounds_pct=0.02,
    ),
    "GBPUSD": SymbolSpec(
        symbol="GBPUSD", display="GBP/USD", base="GBP", quote="USD",
        precision=5, pip=0.0001, contract_size=100000,
        min_lot=0.01, lot_step=0.01, max_lot=100.0,
        leverage_max=5000, margin_currency="USD", trading_hours="24x5",
        price_bounds_pct=0.02,
    ),
    "USDJPY": SymbolSpec(
        symbol="USDJPY", display="USD/JPY", base="USD", quote="JPY",
        precision=3, pip=0.001, contract_size=100000,
        min_lot=0.01, lot_step=0.01, max_lot=100.0,
        leverage_max=5000, margin_currency="USD", trading_hours="24x5",
        price_bounds_pct=0.02,
    ),
    "AUDUSD": SymbolSpec(
        symbol="AUDUSD", display="AUD/USD", base="AUD", quote="USD",
        precision=5, pip=0.0001, contract_size=100000,
        min_lot=0.01, lot_step=0.01, max_lot=100.0,
        leverage_max=5000, margin_currency="USD", trading_hours="24x5",
        price_bounds_pct=0.02,
    ),
    "USDCAD": SymbolSpec(
        symbol="USDCAD", display="USD/CAD", base="USD", quote="CAD",
        precision=5, pip=0.0001, contract_size=100000,
        min_lot=0.01, lot_step=0.01, max_lot=100.0,
        leverage_max=5000, margin_currency="USD", trading_hours="24x5",
        price_bounds_pct=0.02,
    ),
}

SPECS.update({
    "BTCUSDT": SymbolSpec(
        symbol="BTCUSDT", display="BTC/USDT", base="BTC", quote="USDT",
        precision=2, pip=0.01, contract_size=1,
        min_lot=0.001, lot_step=0.001, max_lot=1000.0,
        leverage_max=5000, margin_currency="USDT", trading_hours="24x7",
        price_bounds_pct=0.05,
    ),
})

def spec_for(symbol: str) -> SymbolSpec:
    s = symbol.upper()
    if s not in SPECS:
        raise KeyError(f"Unknown symbol: {s}")
    return SPECS[s]
