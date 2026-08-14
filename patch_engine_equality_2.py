import re

with open('backend/app/strategies/trending_oi_engine.py', 'r') as f:
    content = f.read()

# Fix the bug I introduced by swapping BULLISH/BEARISH
logic = """            if last_dominant == "CALL" and curr_put_oi > curr_call_oi:
                row["crossover"] = "BULLISH_CROSSOVER"
                row["crossover_timestamp"] = row["time"]
            elif last_dominant == "PUT" and curr_call_oi > curr_put_oi:
                row["crossover"] = "BEARISH_CROSSOVER"
                row["crossover_timestamp"] = row["time"]
"""

old_logic = """            if last_dominant == "CALL" and curr_put_oi > curr_call_oi:
                row["crossover"] = "BEARISH_CROSSOVER"
                row["crossover_timestamp"] = row["time"]
            elif last_dominant == "PUT" and curr_call_oi > curr_put_oi:
                row["crossover"] = "BULLISH_CROSSOVER"
                row["crossover_timestamp"] = row["time"]
"""

content = content.replace(old_logic, logic)
with open('backend/app/strategies/trending_oi_engine.py', 'w') as f:
    f.write(content)
