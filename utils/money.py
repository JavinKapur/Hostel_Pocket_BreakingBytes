from decimal import Decimal, ROUND_HALF_UP

def format_inr(amount) -> str:
    """Formats a numeric amount in Indian Rupees (₹X,XXX.XX or ₹X,XXX)."""
    if amount is None:
        return "₹0"
    val = float(amount)
    if val.is_integer():
        return f"₹{int(val):,}"
    return f"₹{val:,.2f}"

def validate_item_totals(header_amount: float, line_totals: list[float], tolerance: float = 0.01) -> bool:
    """Validates that the sum of line totals matches the header amount within 0.01 INR tolerance."""
    if not line_totals:
        return True
    diff = abs(sum(line_totals) - header_amount)
    return diff <= tolerance
