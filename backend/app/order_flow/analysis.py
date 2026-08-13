def calculate_trade_size(ltq, current_cumulative_volume, previous_cumulative_volume):
    volume_delta = current_cumulative_volume - previous_cumulative_volume if current_cumulative_volume is not None and previous_cumulative_volume is not None else None

    if volume_delta is not None and volume_delta == 0:
        return 0, 'NONE', 'UNKNOWN'

    if ltq is not None and ltq > 0 and (volume_delta is None or volume_delta <= 0):
        return ltq, 'LTQ', 'VALID'
    elif volume_delta is not None and volume_delta > 0 and (ltq is None or ltq <= 0):
        return volume_delta, 'CUMULATIVE', 'VALID'
    elif ltq is not None and ltq > 0 and volume_delta is not None and volume_delta > 0:
        if ltq == volume_delta:
            return ltq, 'LTQ', 'VALID'
        else:
            return ltq, 'LTQ', 'MISMATCH'
    else:
        return 0, 'NONE', 'UNKNOWN'

def classify_trade_direction(trade_price, best_ask, best_bid, previous_trade_price):
    if best_ask is not None and trade_price >= best_ask:
        return "AGGRESSIVE_BUY"
    if best_bid is not None and trade_price <= best_bid:
        return "AGGRESSIVE_SELL"

    # Tick rule
    if previous_trade_price is not None:
        if trade_price > previous_trade_price:
            return "AGGRESSIVE_BUY"
        if trade_price < previous_trade_price:
            return "AGGRESSIVE_SELL"

    return "UNKNOWN"

def calculate_classification_confidence(buy_volume, sell_volume, unknown_volume):
    total = buy_volume + sell_volume + unknown_volume
    if total == 0:
        return 0.0
    confidence = (1 - unknown_volume / total) * 100
    return max(0.0, min(100.0, confidence))

def calculate_spread_and_mid(best_bid, best_ask):
    if best_bid is None or best_ask is None or best_ask < best_bid:
        return None, None
    spread = best_ask - best_bid
    mid_price = (best_bid + best_ask) / 2
    return spread, mid_price

def calculate_depth_imbalance(bids, asks, levels):
    bid_sum = sum(b.quantity for b in bids[:levels]) if bids else 0
    ask_sum = sum(a.quantity for a in asks[:levels]) if asks else 0

    total = bid_sum + ask_sum
    if total == 0:
        return 0.0
    return (bid_sum - ask_sum) / total

def check_diagonal_imbalance(footprint, ratio=3.0):
    sorted_prices = sorted(footprint.keys())
    for i in range(len(sorted_prices) - 1):
        lower_price = sorted_prices[i]
        higher_price = sorted_prices[i+1]

        bid_vol_lower = footprint[lower_price].bid_volume
        ask_vol_current = footprint[higher_price].ask_volume

        if bid_vol_lower > 0 and ask_vol_current >= ratio * bid_vol_lower:
             footprint[higher_price].buy_imbalance = True

        bid_vol_current = footprint[higher_price].bid_volume
        ask_vol_higher = footprint[lower_price].ask_volume

        if ask_vol_higher > 0 and bid_vol_current >= ratio * ask_vol_higher:
             footprint[higher_price].sell_imbalance = True

def check_stacked_imbalance(footprint, min_consecutive=3):
    sorted_prices = sorted(footprint.keys())
    buy_stack = []
    sell_stack = []

    for p in sorted_prices:
        if footprint[p].buy_imbalance:
            buy_stack.append(p)
        else:
            buy_stack = []

        if footprint[p].sell_imbalance:
            sell_stack.append(p)
        else:
            sell_stack = []

        if len(buy_stack) >= min_consecutive:
            pass # We could emit a signal here
        if len(sell_stack) >= min_consecutive:
            pass # We could emit a signal here
