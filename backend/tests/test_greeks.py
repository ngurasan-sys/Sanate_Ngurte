from backend.app.engines.greeks import BlackScholes, ExpectedMove, IVSkew, IVTermStructure
from backend.app.models.greeks import OptionType, CalcStatus
import math

def test_black_scholes_call():
    bs = BlackScholes(risk_free_rate=0.05)
    price = bs.price(S=100, K=100, T=1.0, sigma=0.2, option_type=OptionType.CALL)
    assert math.isclose(price, 10.450583, rel_tol=1e-4)

def test_implied_volatility():
    bs = BlackScholes(risk_free_rate=0.0)
    target_price = bs.price(S=100, K=100, T=1.0, sigma=0.2, option_type=OptionType.CALL)
    iv, status = bs.implied_volatility(S=100, K=100, T=1.0, market_price=target_price, option_type=OptionType.CALL)

    assert status == CalcStatus.VALID
    assert math.isclose(iv, 0.2, rel_tol=1e-3)

def test_expected_move():
    move = ExpectedMove.calculate(spot_price=100.0, iv=0.16, dte=365.0)
    assert math.isclose(move, 16.0, rel_tol=1e-4)

def test_iv_skew():
    result = IVSkew.calculate_skew(otm_put_iv=0.25, atm_iv=0.20, otm_call_iv=0.22)
    assert result["shape"] == "SMILE"
    assert math.isclose(result["skew"], 0.03, abs_tol=1e-4)

def test_iv_term_structure():
    result = IVTermStructure.calculate_slope(front_expiry_iv=0.15, next_expiry_iv=0.20, front_dte=30.0, next_dte=60.0)
    assert result["structure"] == "CONTANGO"
    assert result["slope"] > 0
