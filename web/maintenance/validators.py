"""Validation helpers for system maintenance artifacts."""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Mapping, Optional, Sequence

from web.maintenance.tasks import STATUS_FAILED, STATUS_SUCCESS, ValidationResult


REQUIRED_CONSTITUENT_COLUMNS = ("symbol", "security", "sector", "sub_industry")

_MARKET_RULES = {
    "sp500": {
        "min_count": 450,
        "symbol_re": re.compile(r"^[A-Z0-9]{1,10}(-[A-Z0-9]{1,5})?$"),
        "label": "S&P 500",
    },
    "sti": {
        "min_count": 25,
        "symbol_re": re.compile(r"^[A-Z0-9]{1,10}\.SI$"),
        "label": "STI",
    },
    "hsi": {
        "min_count": 70,
        "symbol_re": re.compile(r"^\d{4,5}\.HK$"),
        "label": "HSI",
    },
}


def validate_constituent_rows(
    rows: Sequence[Mapping[str, object]],
    *,
    market: str,
    before_count: Optional[int] = None,
    allow_large_change: bool = False,
) -> ValidationResult:
    """Validate normalized constituent rows before they are applied.

    The function deliberately returns all errors/warnings instead of raising so
    the Maintenance UI can surface a useful operator-facing report.
    """
    rules = _MARKET_RULES.get(market)
    if rules is None:
        return ValidationResult(
            status=STATUS_FAILED,
            errors=[f"Unknown constituent market: {market}"],
        )

    warnings: List[str] = []
    errors: List[str] = []
    after_count = len(rows)

    if after_count == 0:
        errors.append(f"{rules['label']} source produced no rows")

    if after_count < int(rules["min_count"]):
        errors.append(
            f"{rules['label']} row count {after_count} is below minimum threshold {rules['min_count']}"
        )

    missing_columns = _missing_required_columns(rows, REQUIRED_CONSTITUENT_COLUMNS)
    if missing_columns:
        errors.append("Missing required columns: " + ", ".join(sorted(missing_columns)))

    symbols = [str(row.get("symbol") or "").strip().upper() for row in rows]
    blank_symbols = [idx + 1 for idx, sym in enumerate(symbols) if not sym]
    if blank_symbols:
        errors.append(f"Blank symbols found at rows: {blank_symbols[:10]}")

    duplicates = sorted(_duplicates(sym for sym in symbols if sym))
    if duplicates:
        errors.append("Duplicate symbols found: " + ", ".join(duplicates[:20]))

    symbol_re = rules["symbol_re"]
    invalid_symbols = [sym for sym in symbols if sym and not symbol_re.match(sym)]
    if invalid_symbols:
        errors.append("Invalid symbol format: " + ", ".join(invalid_symbols[:20]))

    if before_count and before_count > 0:
        pct_change = abs(after_count - before_count) / before_count
        if pct_change > 0.25 and not allow_large_change:
            errors.append(
                f"Suspicious count change: {before_count} -> {after_count} ({pct_change:.1%})"
            )
        elif pct_change > 0.10:
            warnings.append(
                f"Large count change: {before_count} -> {after_count} ({pct_change:.1%})"
            )

    status = STATUS_SUCCESS if not errors else STATUS_FAILED
    return ValidationResult(
        status=status,
        warnings=warnings,
        errors=errors,
        detail={
            "market": market,
            "before_count": before_count,
            "after_count": after_count,
            "minimum_count": rules["min_count"],
            "required_columns": list(REQUIRED_CONSTITUENT_COLUMNS),
        },
    )


def _missing_required_columns(
    rows: Sequence[Mapping[str, object]],
    required_columns: Iterable[str],
) -> List[str]:
    if not rows:
        return list(required_columns)
    seen = set()
    for row in rows:
        seen.update(str(key) for key in row.keys())
    return [col for col in required_columns if col not in seen]


def _duplicates(values: Iterable[str]) -> List[str]:
    seen = set()
    duplicates = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)
