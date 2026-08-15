from datetime import time


def compute_session_phase(now: time) -> str:
    if now < time(9, 15):
        return "CLOSED"
    if now < time(14, 30):
        return "CONTINUOUS"
    if now < time(15, 15):
        return "DECAY"
    if now < time(15, 35):
        return "CAS"
    if now < time(15, 40):
        return "GOLDEN_WINDOW"
    return "CLOSED"
