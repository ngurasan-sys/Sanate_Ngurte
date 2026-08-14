from datetime import datetime, time

def is_oh_signal_valid(timestamp_str: str, probability: float, is_red_dot_active: bool):
    current_time = datetime.strptime(timestamp_str, "%H:%M").time()
    cutoff_time = time(9, 30)

    # Filter 1: High Conviction required before 9:30 AM
    if current_time < cutoff_time:
        if probability >= 90.0 and is_red_dot_active:
            return True, "VALID_HIGH_PROBABILITY"
        else:
            return False, "REJECTED: Low probability before 9:30 AM"

    # Post 9:30 AM logic would require Trending OI confirmation
    return True, "VALID_PENDING_OI_CONFIRMATION"

def check_atr_exhaustion(current_price: float, yesterday_close: float, atr_value: float):
    total_movement = abs(current_price - yesterday_close)

    # Filter: Reject trade if daily movement exceeds or is near ATR
    if total_movement >= (atr_value * 0.95): # using a 95% threshold buffer
        return True, "MARKET_EXHAUSTED"

    return False, "MARKET_HEALTHY"
