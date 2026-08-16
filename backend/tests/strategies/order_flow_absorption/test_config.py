import pytest

from backend.app.strategies.order_flow_absorption.config import OFAOConfig, OFAOConfigError, validate_config


def test_default_config_is_disabled():
    config = OFAOConfig()
    assert config.enabled is False


def test_default_config_is_valid():
    validate_config(OFAOConfig())  # should not raise


def test_rejects_empty_underlyings():
    with pytest.raises(OFAOConfigError):
        validate_config(OFAOConfig(underlyings=[]))


def test_rejects_unsupported_underlying():
    with pytest.raises(OFAOConfigError):
        validate_config(OFAOConfig(underlyings=["GOLD"]))


def test_rejects_invalid_imbalance_ratio():
    with pytest.raises(OFAOConfigError):
        validate_config(OFAOConfig(imbalance_ratio_pct=250.0))


def test_accepts_all_valid_imbalance_ratios():
    for ratio in (200.0, 300.0, 400.0, 500.0):
        validate_config(OFAOConfig(imbalance_ratio_pct=ratio))


def test_rejects_risk_reward_below_1():
    with pytest.raises(OFAOConfigError):
        validate_config(OFAOConfig(risk_reward_min=0.5))


def test_rejects_zero_lots():
    with pytest.raises(OFAOConfigError):
        validate_config(OFAOConfig(lots=0))
