from autonomous.drawdown_governor import DrawdownGovernor


def test_drawdown_governor_full_size_below_two_percent():
    decision = DrawdownGovernor(enabled=True, current_drawdown_pct=0.01).evaluate()

    assert decision.multiplier == 1.0
    assert decision.halted is False


def test_drawdown_governor_reduces_size_in_drawdown_bands():
    assert DrawdownGovernor(enabled=True, current_drawdown_pct=0.03).evaluate().multiplier == 0.75
    assert DrawdownGovernor(enabled=True, current_drawdown_pct=0.05).evaluate().multiplier == 0.50
    assert DrawdownGovernor(enabled=True, current_drawdown_pct=0.07).evaluate().multiplier == 0.25


def test_drawdown_governor_halts_above_eight_percent():
    decision = DrawdownGovernor(enabled=True, current_drawdown_pct=0.081).evaluate()

    assert decision.multiplier == 0.0
    assert decision.halted is True
