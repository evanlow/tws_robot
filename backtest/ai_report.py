"""AI Backtest Report — Enhancement 3.

Provides narrative generation for backtest results using OpenAI.

Usage::

    from backtest.ai_report import generate_narrative, generate_comparison_narrative
    from backtest.performance import PerformanceMetrics

    narrative_md = generate_narrative(metrics, strategy_name="MA Cross")
"""

import json
import logging
from typing import Dict, List, Optional, Tuple, Union

from ai.client import get_client
from ai.prompts import Prompts

logger = logging.getLogger(__name__)

# Module-level cache: run_id -> markdown string
_report_cache: dict = {}


def generate_narrative(
    metrics: "Union[PerformanceMetrics, dict]",  # type: ignore[name-defined]
    strategy_name: str,
) -> str:
    """Generate a markdown narrative report for a single backtest run.

    Args:
        metrics:       ``PerformanceMetrics`` instance **or** a plain dict
                       (e.g. the result of ``PerformanceMetrics.to_dict()``).
        strategy_name: Human-readable strategy name for the report header.

    Returns:
        Markdown-formatted report string, or an error message if AI is
        unavailable or the request fails.
    """
    client = get_client()
    if client is None:
        return (
            "_AI report unavailable. Set `AI_ENABLED=true` and "
            "`OPENAI_API_KEY` to generate narrative reports._"
        )

    if isinstance(metrics, dict):
        metrics_dict = metrics
    elif hasattr(metrics, "to_dict"):
        metrics_dict = metrics.to_dict()
    else:
        metrics_dict = {}

    metrics_json = json.dumps(metrics_dict, indent=2, default=str)

    system_prompt = Prompts.BACKTEST_NARRATOR.format(
        strategy_name=strategy_name,
        metrics_json=metrics_json,
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "Please generate the performance report."},
    ]

    try:
        return client.chat(messages, temperature=0.4)
    except RuntimeError as exc:
        logger.error("AI backtest narrative error: %s", exc)
        return "_Failed to generate AI report. Please check logs for details._"


def generate_comparison_narrative(
    results: List[Tuple[str, "PerformanceMetrics"]]  # type: ignore[name-defined]
) -> str:
    """Generate a comparative markdown report for multiple strategy backtests.

    Args:
        results: List of (strategy_name, PerformanceMetrics) tuples.

    Returns:
        Markdown-formatted comparison report string.
    """
    client = get_client()
    if client is None:
        return (
            "_AI comparison unavailable. Set `AI_ENABLED=true` and "
            "`OPENAI_API_KEY` to generate comparison reports._"
        )

    results_dict = {
        name: (metrics.to_dict() if hasattr(metrics, "to_dict") else {})
        for name, metrics in results
    }
    results_json = json.dumps(results_dict, indent=2, default=str)

    system_prompt = Prompts.BACKTEST_COMPARISON.format(results_json=results_json)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "Please generate the comparison report."},
    ]

    try:
        return client.chat(messages, temperature=0.4)
    except RuntimeError as exc:
        logger.error("AI backtest comparison error: %s", exc)
        return "_Failed to generate AI comparison report. Please check logs for details._"


def get_cached_report(run_id: str) -> Optional[str]:
    """Return a previously generated report, or None if not cached."""
    return _report_cache.get(run_id)


def cache_report(run_id: str, report: str) -> None:
    """Store a generated report in the module-level cache."""
    _report_cache[run_id] = report
