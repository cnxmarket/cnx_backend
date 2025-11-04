# pricing.py
from .contracts import spec_for

def mark_price_from_tick(tick: dict) -> float:
    # With zero-spread normalization, tick carries mid in bid/ask
    bid = tick.get("bid")
    ask = tick.get("ask")
    if bid is None or ask is None:
        raise ValueError("Missing bid/ask in normalized tick")
    return (float(bid) + float(ask)) / 2.0

def pip_value(symbol: str, lots: float) -> float:
    sp = spec_for(symbol)
    return sp.contract_size * sp.pip * float(lots)

def unrealized_pnl(symbol: str, lots: float, entry: float, mark: float) -> float:
    qty = float(lots)
    direction = 1.0 if qty >= 0 else -1.0
    return (mark - entry) * sp_contract_size(symbol) * qty

def sp_contract_size(symbol: str) -> int:
    return spec_for(symbol).contract_size

def margin_required(symbol: str, lots: float, mark: float, leverage: int) -> float:
    sp = spec_for(symbol)
    notional = sp.contract_size * float(lots) * mark
    return abs(notional) / max(1, int(leverage))
