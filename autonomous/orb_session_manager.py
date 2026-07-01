"""ORB Phase 2.3 — strategy configuration, modes, and autonomous session controls.

Trader-facing persistence and control layer for the Opening Range Breakout
(ORB) strategy. Lets a trader create/edit an ORB strategy, choose a mode,
arm/disarm a session, and inspect readiness — all without writing Python.

Safety posture (Prime Directive):
- This module never places orders. It only persists configuration and session
  arming intent, evaluates readiness gates, and audit-logs control actions.
- Live modes (tiny live candidate, assisted live) are *locked* in this phase:
  they can be selected only for display and can never arm a session.
- Paper-autonomous can be configured but does not execute; arming it requires
  paper-readiness gates (saved READY_FOR_PAPER backtest evidence) to pass.
- Recommend-only may arm even with missing execution readiness; the dashboard
  surfaces the missing execution gates explicitly.

Configuration is persisted to a JSON file so it survives app restarts. Control
actions (arm/disarm/disable-today/emergency-stop) are written to the autonomous
audit log.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import fields
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from autonomous.audit import AuditLogger
from autonomous.opening_range import OpeningRangeConfig

logger = logging.getLogger(__name__)


class ORBMode(str, Enum):
    """ORB operating modes; live modes are locked in this phase."""

    OFF = "off"
    BACKTEST_ONLY = "backtest_only"
    RECOMMEND_ONLY = "recommend_only"
    PAPER_AUTONOMOUS = "paper_autonomous"
    TINY_LIVE_CANDIDATE = "tiny_live_candidate"  # locked
    ASSISTED_LIVE = "assisted_live"  # locked


# Modes that must never arm or execute real money in this phase.
LOCKED_MODES = frozenset({ORBMode.TINY_LIVE_CANDIDATE, ORBMode.ASSISTED_LIVE})

# Modes that cannot arm a live/paper session (no session state should persist).
NON_ARMABLE_MODES = LOCKED_MODES | frozenset({ORBMode.OFF, ORBMode.BACKTEST_ONLY})

# Strategy fields whose change invalidates any standing armed session.
_SESSION_CRITICAL_KEYS = ("mode", "symbols", "symbols_enabled", "parameters")


def _is_armable_mode(mode: ORBMode) -> bool:
    """True if ``mode`` may arm a session (paper-autonomous or recommend-only)."""
    return mode not in NON_ARMABLE_MODES


class ORBValidationError(ValueError):
    """Raised when a submitted ORB strategy config is invalid."""

    def __init__(self, errors: List[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def _coerce_mode(value: Any) -> ORBMode:
    try:
        return ORBMode(str(value))
    except ValueError as exc:
        raise ORBValidationError([f"unknown mode '{value}'"]) from exc


def validate_strategy(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and normalize a strategy config payload.

    Raises :class:`ORBValidationError` with actionable messages on invalid input.
    Returns a normalized record dict ready for persistence.
    """
    errors: List[str] = []

    name = str(data.get("name", "")).strip()
    if not name:
        errors.append("name is required")

    symbols = [s.strip().upper() for s in (data.get("symbols") or []) if str(s).strip()]
    if not symbols:
        errors.append("at least one symbol is required")

    mode = _coerce_mode(data.get("mode", ORBMode.OFF.value))

    # Per-symbol enabled flags default to enabled for any listed symbol.
    raw_enabled = data.get("symbols_enabled") or {}
    symbols_enabled = {s: bool(raw_enabled.get(s, True)) for s in symbols}

    params: Dict[str, Any] = dict(data.get("parameters") or {})
    params["symbols"] = symbols

    # Numeric / range validations against ORB config semantics.
    rng = params.get("opening_range_minutes", 15)
    try:
        if int(rng) <= 0:
            errors.append("opening_range_minutes must be positive")
    except (TypeError, ValueError):
        errors.append("opening_range_minutes must be an integer")

    risk = params.get("risk_per_trade_equity_pct", 0.002)
    try:
        if not (0 < float(risk) <= 0.05):
            errors.append("risk_per_trade_equity_pct must be between 0 and 0.05")
    except (TypeError, ValueError):
        errors.append("risk_per_trade_equity_pct must be a number")

    slip = params.get("max_entry_slippage_bps", 10.0)
    try:
        if float(slip) < 0:
            errors.append("max_entry_slippage_bps must be >= 0")
    except (TypeError, ValueError):
        errors.append("max_entry_slippage_bps must be a number")

    for key in ("max_trades_per_symbol_per_session", "max_total_orb_trades_per_session"):
        val = params.get(key, 1)
        try:
            if int(val) < 1:
                errors.append(f"{key} must be >= 1")
        except (TypeError, ValueError):
            errors.append(f"{key} must be an integer")

    require_stop = bool(data.get("require_stop", True))
    require_target = bool(data.get("require_target", True))
    if not require_stop:
        errors.append("require_stop must remain enabled (safety gate)")
    if not require_target:
        errors.append("require_target must remain enabled (safety gate)")

    # Times must be HH:MM and entry cutoff before force-flat.
    cutoff = str(params.get("entry_cutoff_time", "11:30"))
    flat = str(params.get("force_flat_time", "15:55"))
    for label, t in (("entry_cutoff_time", cutoff), ("force_flat_time", flat)):
        try:
            datetime.strptime(t, "%H:%M")
        except ValueError:
            errors.append(f"{label} must be HH:MM")
    try:
        if datetime.strptime(cutoff, "%H:%M") >= datetime.strptime(flat, "%H:%M"):
            errors.append("entry_cutoff_time must be before force_flat_time")
    except ValueError:
        pass

    # Optional max holding time cap.
    mhm = params.get("max_holding_minutes")
    if mhm is not None:
        try:
            mhm_int = int(mhm)
            if mhm_int <= 0:
                errors.append("max_holding_minutes must be a positive integer")
            else:
                params["max_holding_minutes"] = mhm_int
        except (TypeError, ValueError):
            errors.append("max_holding_minutes must be a positive integer")

    # Reject params that aren't recognised by OpeningRangeConfig to avoid silent drops.
    valid = {f.name for f in fields(OpeningRangeConfig)}
    unknown = [k for k in params if k not in valid]
    if unknown:
        errors.append("unknown parameters: " + ", ".join(sorted(unknown)))

    # Model C remains diagnostic-only (locked off) in this phase.
    params["model_c_enabled"] = False
    params["short_enabled"] = False
    params["require_bracket_order"] = bool(data.get("require_bracket", True))

    if errors:
        raise ORBValidationError(errors)

    return {
        "name": name,
        "symbols": symbols,
        "symbols_enabled": symbols_enabled,
        "mode": mode.value,
        "require_stop": require_stop,
        "require_target": require_target,
        "require_bracket": params["require_bracket_order"],
        "parameters": params,
    }


class ORBSessionManager:
    """Persisted ORB strategies plus arm/disarm/disable session controls.

    Thread-safe. Persists strategies to ``<config_dir>/orb_strategies.json`` and
    writes control actions to the autonomous audit log. Never places orders.
    """

    def __init__(self, config_dir: str = "config", evidence_dir: str = "logs",
                 audit: Optional[AuditLogger] = None,
                 now_fn: Optional[Callable[[ZoneInfo], datetime]] = None) -> None:
        self._config_dir = Path(config_dir)
        self._evidence_dir = Path(evidence_dir)
        self._path = self._config_dir / "orb_strategies.json"
        self._lock = threading.Lock()
        self._audit = audit or AuditLogger(str(evidence_dir))
        self._now_fn = now_fn or (lambda tz: datetime.now(tz))
        self._strategies: Dict[str, Dict[str, Any]] = {}
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._load()

    # ---- session-date helper ----------------------------------------
    def _session_date(self, rec: Dict[str, Any], offset_days: int = 0) -> date:
        """ORB trading-session date in the strategy timezone (New York by default).

        Using the strategy timezone (not server-local time) keeps "today" aligned
        with the intended New York session around midnight on UTC/Asia servers.
        """
        tz_name = (rec.get("parameters") or {}).get("timezone", "America/New_York")
        try:
            tz = ZoneInfo(tz_name)
        except (ZoneInfoNotFoundError, ValueError):  # pragma: no cover - defensive
            tz = ZoneInfo("America/New_York")
        return self._now_fn(tz).date() + timedelta(days=offset_days)

    # ---- persistence -------------------------------------------------
    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._strategies = data.get("strategies", {})
            self._sessions = data.get("sessions", {})
        except (OSError, json.JSONDecodeError) as exc:  # pragma: no cover - defensive
            logger.error("Failed to load ORB strategies: %s", exc)

    def _save(self) -> None:
        try:
            self._config_dir.mkdir(parents=True, exist_ok=True)
            payload = {"strategies": self._strategies, "sessions": self._sessions}
            content = json.dumps(payload, indent=2, sort_keys=True)
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(content, encoding="utf-8")
            os.replace(tmp, self._path)
        except OSError as exc:  # pragma: no cover - defensive
            logger.error("Failed to save ORB strategies: %s", exc)

    # ---- strategy CRUD ----------------------------------------------
    def list_strategies(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [self._with_status(rec) for rec in self._strategies.values()]

    def get_strategy(self, name: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            rec = self._strategies.get(name)
            return self._with_status(rec) if rec else None

    def upsert_strategy(self, data: Dict[str, Any]) -> Dict[str, Any]:
        rec = validate_strategy(data)
        with self._lock:
            name = rec["name"]
            prev = self._strategies.get(name)
            self._strategies[name] = rec
            # Clear any standing session state when the update could invalidate it:
            # a non-armable new mode must not leave a stale armed session, and any
            # mode/symbol/session-critical change conservatively disarms.
            if name in self._sessions:
                non_armable = not _is_armable_mode(ORBMode(rec["mode"]))
                critical_change = prev is not None and any(
                    prev.get(k) != rec.get(k) for k in _SESSION_CRITICAL_KEYS
                )
                if non_armable or critical_change:
                    self._sessions.pop(name, None)
                    self._log("disarm_on_update", name, {})
            self._save()
            return self._with_status(rec)

    # ---- session controls -------------------------------------------
    def arm(self, name: str, when: str = "today") -> Dict[str, Any]:
        if when not in ("today", "tomorrow"):
            raise ORBValidationError(["arm 'when' must be today or tomorrow"])
        with self._lock:
            rec = self._require(name)
            mode = ORBMode(rec["mode"])
            if mode in LOCKED_MODES:
                raise ORBValidationError([f"mode '{mode.value}' is locked and cannot arm"])
            if mode in (ORBMode.OFF, ORBMode.BACKTEST_ONLY):
                raise ORBValidationError([f"mode '{mode.value}' cannot arm a session"])
            gates = self._readiness(rec)
            if mode == ORBMode.PAPER_AUTONOMOUS and not gates["paper_ready"]:
                raise ORBValidationError(
                    ["paper readiness gates not met: " + ", ".join(gates["missing"])]
                )
            target = self._session_date(rec, 1 if when == "tomorrow" else 0)
            # Do not let arm-for-today override an explicit disable-today for the
            # same session date; arm-for-tomorrow remains allowed.
            existing = self._sessions.get(name, {})
            if (existing.get("disabled_today")
                    and existing.get("disabled_date") == target.isoformat()):
                raise ORBValidationError(
                    [f"strategy '{name}' is disabled for session {target.isoformat()}; "
                     "arm for tomorrow instead"]
                )
            self._sessions[name] = {
                "armed": True, "armed_for": target.isoformat(),
                "disabled_today": False, "mode": rec["mode"],
            }
            self._save()
            self._log("arm", name, {"when": when, "for": target.isoformat()})
            return self._with_status(rec)

    def disarm(self, name: str) -> Dict[str, Any]:
        with self._lock:
            rec = self._require(name)
            self._sessions.pop(name, None)
            self._save()
            self._log("disarm", name, {})
            return self._with_status(rec)

    def disable_today(self, name: str) -> Dict[str, Any]:
        with self._lock:
            rec = self._require(name)
            self._sessions[name] = {
                "armed": False, "disabled_today": True,
                "disabled_date": self._session_date(rec).isoformat(),
                "mode": rec["mode"],
            }
            self._save()
            self._log("disable_today", name, {})
            return self._with_status(rec)

    def emergency_stop(self) -> Dict[str, Any]:
        """Disarm all ORB strategies immediately (no orders placed)."""
        with self._lock:
            self._sessions = {}
            self._save()
            self._log("emergency_stop", "*", {})
            return {"stopped": True, "armed": []}

    # ---- status / readiness -----------------------------------------
    def status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "strategies": [self._with_status(r) for r in self._strategies.values()],
                "locked_modes": [m.value for m in LOCKED_MODES],
                "modes": [m.value for m in ORBMode],
            }

    def _require(self, name: str) -> Dict[str, Any]:
        rec = self._strategies.get(name)
        if rec is None:
            raise ORBValidationError([f"strategy '{name}' not found"])
        return rec

    def _readiness(self, rec: Dict[str, Any]) -> Dict[str, Any]:
        missing: List[str] = []
        paper_ready = self._has_paper_evidence(rec["symbols"])
        if not paper_ready:
            missing.append("paper_backtest_evidence")
        if not rec.get("require_stop", True):
            missing.append("require_stop")
        if not rec.get("require_target", True):
            missing.append("require_target")
        return {
            "paper_ready": paper_ready and not missing,
            "missing": missing,
            "execution_ready": paper_ready,
        }

    def _has_paper_evidence(self, symbols: List[str]) -> bool:
        """True if any saved backtest evidence is READY_FOR_PAPER for a symbol."""
        want = {s.upper() for s in symbols}
        try:
            files = sorted(self._evidence_dir.glob("orb_backtest_evidence_*.jsonl"))
        except OSError:  # pragma: no cover - defensive
            return False
        for path in files:
            try:
                for line in path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    rec = json.loads(line)
                    if (rec.get("readiness") or {}).get("status") != "READY_FOR_PAPER":
                        continue
                    syms = {str(s).upper() for s in (rec.get("symbols") or [])}
                    if not want or syms & want:
                        return True
            except (OSError, json.JSONDecodeError):  # pragma: no cover - defensive
                continue
        return False

    def _with_status(self, rec: Dict[str, Any]) -> Dict[str, Any]:
        session = self._sessions.get(rec["name"], {})
        gates = self._readiness(rec)
        out = dict(rec)
        out["session"] = session
        out["readiness"] = gates
        out["mode_locked"] = ORBMode(rec["mode"]) in LOCKED_MODES
        return out

    def _log(self, action: str, name: str, extra: Dict[str, Any]) -> None:
        self._audit.log_decision({
            "kind": "orb_session_control",
            "action": action,
            "strategy": name,
            **extra,
        })
