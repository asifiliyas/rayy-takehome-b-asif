"""Pure money math for discounts. No I/O, no HTTP — integer paise only.

Rounding: round-half-up on fractional paise, using integer arithmetic only
(see NOTES.md). ``round_half_up_div(numerator, 10000)`` rounds
``numerator / 10000`` to the nearest integer, ties rounding up.
"""


def round_half_up_div(numerator: int, denominator: int) -> int:
    return (numerator + denominator // 2) // denominator


def compute_discount(subtotal_paise: int, percent_off_bps: int, cap_paise: int) -> int:
    """The amount taken off, before the partner/RAYY split."""
    raw = round_half_up_div(subtotal_paise * percent_off_bps, 10000)
    return min(raw, cap_paise)


def split_discount(discount_paise: int, partner_share_bps: int) -> tuple[int, int]:
    """(partner_share_paise, rayy_share_paise); the pair always sums to
    ``discount_paise`` — any rounding remainder is given to RAYY rather than
    the partner (see NOTES.md)."""
    partner_share_paise = round_half_up_div(discount_paise * partner_share_bps, 10000)
    rayy_share_paise = discount_paise - partner_share_paise
    return partner_share_paise, rayy_share_paise
