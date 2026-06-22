from __future__ import annotations

from autonomous.replay_engine import (
    STALE_QUOTE_FAULT,
    ReplayChaosHarness,
    default_phase_11_scenarios,
)


def _run(tmp_path, scenario_name):
    scenario = next(
        item for item in default_phase_11_scenarios()
        if item.name == scenario_name
    )
    return ReplayChaosHarness(tmp_path / scenario.name).run(scenario)


def test_default_phase_11_scenarios_are_reproducible_and_no_duplicate_exposure(tmp_path):
    scenario_names = [scenario.name for scenario in default_phase_11_scenarios()]

    assert scenario_names == [
        "normal_fill",
        "partial_fill",
        "order_rejection",
        "broker_disconnect",
        "stale_quote",
        "restart_after_submission",
        "restart_after_fill_before_evidence",
        "basket_one_failed_leg",
        "stop_hit",
        "target_hit",
        "unconfirmed_protective_stop",
    ]

    first = [
        ReplayChaosHarness(tmp_path / "a" / scenario.name).run(scenario)
        for scenario in default_phase_11_scenarios()
    ]
    second = [
        ReplayChaosHarness(tmp_path / "b" / scenario.name).run(scenario)
        for scenario in default_phase_11_scenarios()
    ]

    assert [result.scenario for result in first] == [result.scenario for result in second]
    assert [
        [step.kind for step in result.steps]
        for result in first
    ] == [
        [step.kind for step in result.steps]
        for result in second
    ]
    assert all(not result.duplicate_exposure_detected for result in first)


def test_restart_and_missing_protection_scenarios_fail_closed(tmp_path):
    restart = _run(tmp_path, "restart_after_submission")
    missing_stop = _run(tmp_path, "unconfirmed_protective_stop")

    assert restart.recovery["recovery_required"] is True
    assert restart.steps[-1].supervisor_status == "PAUSED"
    restart_codes = {
        issue["code"] for issue in restart.recovery["issues"]
    }
    assert "idempotency_lock_without_trade" in restart_codes
    assert "unmatched_broker_entry_order" in restart_codes

    assert missing_stop.recovery["recovery_required"] is True
    assert missing_stop.steps[-1].supervisor_reason == "unreconciled_lifecycle_state"
    assert missing_stop.recovery["protection_diagnostics"][0]["recovery_required"] is True


def test_disconnect_and_stale_quote_pause_supervisor(tmp_path):
    disconnect = _run(tmp_path, "broker_disconnect")
    stale = _run(tmp_path, "stale_quote")

    assert disconnect.steps[-1].supervisor_status == "PAUSED"
    assert disconnect.steps[-1].supervisor_reason == "broker_disconnected"
    assert disconnect.broker_connected is False

    assert stale.steps[-1].supervisor_status == "PAUSED"
    assert stale.steps[-1].supervisor_reason == STALE_QUOTE_FAULT
    assert stale.steps[-1].market_data_health["allowed"] is False
    assert "quote age" in stale.steps[-1].market_data_health["reason"]


def test_fill_scenarios_preserve_reconstructable_evidence(tmp_path):
    normal = _run(tmp_path, "normal_fill")
    target = _run(tmp_path, "target_hit")
    stop = _run(tmp_path, "stop_hit")
    lost = _run(tmp_path, "restart_after_fill_before_evidence")

    assert normal.evidence_reconstructable is True
    assert target.evidence_reconstructable is True
    assert stop.evidence_reconstructable is True
    assert target.steps[-1].ingestion["outcomes_emitted"] == 1
    assert stop.steps[-1].ingestion["outcomes_emitted"] == 1
    assert target.trades[0]["status"] == "CLOSED"
    assert stop.trades[0]["status"] == "CLOSED"

    assert lost.recovery["recovery_required"] is True
    assert lost.evidence_reconstructable is False
    assert any(
        note.startswith("unmatched broker fill")
        for note in lost.steps[-1].notes
    )


def test_partial_fill_and_rejected_basket_leg_are_classified(tmp_path):
    partial = _run(tmp_path, "partial_fill")
    basket = _run(tmp_path, "basket_one_failed_leg")

    assert partial.recovery["recovery_required"] is True
    assert any(
        issue["code"] == "local_broker_quantity_mismatch"
        for issue in partial.recovery["issues"]
    )
    assert partial.steps[-1].supervisor_status == "PAUSED"

    assert basket.duplicate_exposure_detected is False
    assert basket.evidence_reconstructable is True
    assert {trade["symbol"]: trade["status"] for trade in basket.trades} == {
        "AAA": "OPEN",
        "BBB": "FAILED",
    }
