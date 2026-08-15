"""CAS Dislocation Engine package.

Deliberately does NOT re-export .engine here (unlike manual_trading/
option_analytics's __init__.py convention) — risk_limits.py imports
.models directly for CASDislocationConfig, and pulling in the full
engine module (network clients, event_bus wiring) just to reach a
Pydantic model would make an otherwise pure, stateless module import
httpx-based network code at import time. Import .engine / .config_state
directly from their submodules (main.py does).
"""
