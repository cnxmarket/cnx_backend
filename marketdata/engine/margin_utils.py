from decimal import Decimal
from marketdata.models import UserAccount

def calc_required_margin(lots: Decimal, price: Decimal, contract_size: int, leverage: int) -> Decimal:
    notional = abs(lots) * price * Decimal(contract_size)
    margin = notional / Decimal(leverage)
    return margin


def can_user_afford_order(account: UserAccount, required_margin: Decimal) -> bool:
    return account.free_margin >= required_margin


def validate_order(account: UserAccount, lots: Decimal, price: Decimal, contract_size: int, leverage: int):
    required_margin = calc_required_margin(lots, price, contract_size, leverage)

    if not can_user_afford_order(account, required_margin):
        return {
            "ok": False,
            "error": f"Insufficient funds. Required: {required_margin:.2f}, Free Margin: {account.free_margin:.2f}"
        }

    return {
        "ok": True,
        "margin_required": required_margin
    }


def calculate_unrealized_pnl(side: str, open_price: Decimal, mark_price: Decimal, lots: Decimal, contract_size: int) -> Decimal:
    """
    Calculate PnL for an open position.
    side: "Buy" or "Sell"
    open_price: entry price
    mark_price: current (market) price
    lots: volume (positive always)
    contract_size: lot contract size (e.g., 1 for spot, 100000 for forex, etc).
    """
    lots = Decimal(lots)
    contract_size = Decimal(str(contract_size))
    if side.lower() == "buy":
        pnl = (mark_price - open_price) * lots * contract_size
    else:
        pnl = (open_price - mark_price) * lots * contract_size
    return pnl


def calculate_used_margin(open_price: Decimal, lots: Decimal, contract_size: int, leverage: int) -> Decimal:
    """
    Margin required for an open position.
    """
    notional = lots * open_price * Decimal(contract_size)
    used_margin = notional / Decimal(leverage)
    return used_margin


def aggregate_user_margin_and_pnl(positions, market_prices):
    """
    positions: iterable of dicts with keys: side, open_price, lots, contract_size, leverage, symbol
    market_prices: dict mapping symbol->current_price
    Returns: total_used_margin (Decimal), total_unrealized_pnl (Decimal)
    """
    total_used_margin = Decimal("0")
    total_unrealized_pnl = Decimal("0")
    for pos in positions:
        mark = Decimal(str(market_prices[pos["symbol"]]))
        open_price = Decimal(str(pos["open_price"]))
        lots = Decimal(str(pos["lots"]))
        contract_size = int(pos["contract_size"])
        leverage = int(pos["leverage"])
        side = pos["side"]

        used_m = calculate_used_margin(open_price, lots, contract_size, leverage)
        pnl = calculate_unrealized_pnl(side, open_price, mark, lots, contract_size)

        total_used_margin += used_m
        total_unrealized_pnl += pnl
    return total_used_margin, total_unrealized_pnl


def calculate_free_margin(balance, total_unrealized_pnl, total_used_margin):
    """
    Free margin = balance + unrealized_pnl - used_margin
    """
    return Decimal(balance) + Decimal(total_unrealized_pnl) - Decimal(total_used_margin)
