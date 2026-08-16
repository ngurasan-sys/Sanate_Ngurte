"""Backtest package. __init__.py deliberately stays empty — engine.py and
jobs.py import vectorbt/pandas/numba (heavy), so callers that only need
the lightweight Pydantic models (models.py) should import that submodule
directly rather than trigger the whole chain via package-level re-exports.
"""
