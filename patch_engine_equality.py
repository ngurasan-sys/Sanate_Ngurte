import re

with open('backend/app/strategies/trending_oi_engine.py', 'r') as f:
    content = f.read()

# Fix crossover equality edge case by finding the last unequal difference.
# We will just traverse backward if they are equal, or keep it simple.
# Wait, "prev_call_oi > prev_put_oi and curr_put_oi > curr_call_oi"
# Let's fix this in _calculate_current_row

logic = """        row["crossover"] = "NO_CROSSOVER"
        row["crossover_timestamp"] = None

        curr_call_oi = row["ce_oi"]
        curr_put_oi = row["pe_oi"]

        if self.completed_rows:
            # Find the last dominant side
            last_dominant = None
            for r in reversed(self.completed_rows):
                if r["ce_oi"] > r["pe_oi"]:
                    last_dominant = "CALL"
                    break
                elif r["pe_oi"] > r["ce_oi"]:
                    last_dominant = "PUT"
                    break

            if last_dominant == "CALL" and curr_put_oi > curr_call_oi:
                row["crossover"] = "BEARISH_CROSSOVER"
                row["crossover_timestamp"] = row["time"]
            elif last_dominant == "PUT" and curr_call_oi > curr_put_oi:
                row["crossover"] = "BULLISH_CROSSOVER"
                row["crossover_timestamp"] = row["time"]
"""

old_logic = """        row["crossover"] = "NO_CROSSOVER"
        row["crossover_timestamp"] = None
        if self.completed_rows:
            prev_row = self.completed_rows[-1]
            prev_call_oi = prev_row["ce_oi"]
            prev_put_oi = prev_row["pe_oi"]

            curr_call_oi = row["ce_oi"]
            curr_put_oi = row["pe_oi"]

            # Crossover logic
            if prev_call_oi > prev_put_oi and curr_put_oi > curr_call_oi:
                row["crossover"] = "BULLISH_CROSSOVER"
                row["crossover_timestamp"] = row["time"]
            elif prev_put_oi > prev_call_oi and curr_call_oi > curr_put_oi:
                row["crossover"] = "BEARISH_CROSSOVER"
                row["crossover_timestamp"] = row["time"]"""

content = content.replace(old_logic, logic)
with open('backend/app/strategies/trending_oi_engine.py', 'w') as f:
    f.write(content)
