# AGENTS.md

## Project context

This repository is for TWS Robot, an Interactive Brokers / Trader Workstation automation project.

The system may contain autonomous trading, paper-trading, evidence-learning, broker connectivity, order-routing, risk-control, and audit/logging functionality.

Treat all trading-related changes as safety-critical.

## Prime Directive

The Prime Directive must be upheld at all times:

* Do not accidentally enable live trading.
* Do not bypass or weaken dry-run, simulation, or paper-trading protections.
* Do not bypass or weaken risk controls, kill switches, audit logging, validation checks, or safety gates.
* Do not introduce behavior that can place real-money orders unless it is explicitly required, clearly documented, fully tested, and protected by existing safety controls.
* Prefer the safest interpretation when requirements are unclear.

## Important documentation

Autonomous trading and evidence-learning requirements are documented under `docs/`.

Before implementing or modifying autonomous trading or evidence-learning functionality, read:

* `docs/AUTONOMOUS_TRADING_SYSTEM_SPEC.md`
* `docs/AUTONOMOUS_EVIDENCE_LEARNING_SPEC.md`

When working on Issue #161 or related autonomous functionality, update these trackers:

* `docs/AUTONOMOUS_IMPLEMENTATION_TRACKER.md`
* `docs/AUTONOMOUS_EVIDENCE_LEARNING_TRACKER.md`

Tracker updates should include:

* Work completed.
* Work remaining, if any.
* Test evidence.
* Smoke-test evidence.
* Known limitations.
* Risks or manual checks required before merge.

## Development workflow

Before making code changes:

1. Inspect the repository structure.
2. Read the relevant specs, trackers, README, and existing tests.
3. Produce a concise implementation plan.
4. Identify impacted modules/files.
5. Identify required tests, smoke tests, and documentation updates.
6. Note any assumptions or unclear requirements.

During implementation:

* Keep changes focused on the issue being worked on.
* Avoid unrelated refactors.
* Preserve existing public interfaces unless there is a clear reason to change them.
* Do not hardcode secrets, credentials, account IDs, API keys, tokens, or local machine paths.
* Do not commit generated caches, local environment files, logs, database files, or broker session artifacts.
* Prefer clear, maintainable, testable code over clever code.

## Testing requirements

New functionality must be covered by tests.

For autonomous trading, order handling, broker integration, risk controls, or evidence-learning changes, include appropriate tests for:

* Safe default behavior.
* Dry-run or simulation behavior.
* Paper-trading behavior, where applicable.
* Risk limits and rejection paths.
* Kill-switch or stop conditions, where applicable.
* Audit/logging behavior, where applicable.
* Error handling and failure modes.

Before opening or updating a PR, run the relevant test commands available in the repository.

If test commands are not obvious, inspect the repo for common project files such as:

* `pyproject.toml`
* `pytest.ini`
* `tox.ini`
* `Makefile`
* `.github/workflows/`
* `requirements.txt`

Document exactly which tests were run and their results in the PR summary.

## Smoke-test requirements

Any new autonomous trading or evidence-learning functionality must be covered by smoke tests where practical.

Smoke tests should verify that:

* The system starts in a safe mode.
* No live order is placed during test execution.
* Required safety gates are active.
* The new functionality can execute its basic path without unsafe side effects.
* Logs or evidence outputs are produced as expected, where applicable.

If a smoke test cannot be automated, document the reason and provide a manual smoke-test checklist.

## Documentation requirements

When behavior changes, update the relevant documentation.

Documentation should explain:

* What changed.
* How to use the new functionality.
* What safety controls apply.
* How to run tests or smoke tests.
* Any configuration required.
* Any limitations or risks.

## Pull request expectations

Every PR should include:

* Summary of changes.
* Issue being resolved.
* Requirements covered.
* Tests run.
* Smoke tests run.
* Documentation updated.
* Tracker files updated, if applicable.
* Safety/risk notes.
* Known limitations or follow-up items.

For Issue #161, the PR should clearly state whether the issue is fully resolved and ready to close.

## Review and merge policy

Codex may implement changes, open PRs, review PRs, and address review feedback.

Codex must not merge PRs automatically.

When Codex believes a PR is ready, it should leave a final readiness summary stating:

* Whether the issue is fully resolved.
* Which requirements are covered.
* Which tests passed.
* Which smoke tests passed.
* Which documentation and tracker files were updated.
* Any remaining risks or manual checks required before human merge approval.

A human maintainer must make the final merge decision.

## Safety review checklist

For any trading-related PR, review the following carefully:

* Could this change place a live order accidentally?
* Are paper-trading and live-trading paths clearly separated?
* Are risk limits still enforced?
* Are kill switches still enforced?
* Are audit logs still written?
* Are unsafe configurations rejected?
* Are defaults safe?
* Are secrets and account identifiers excluded?
* Are tests and smoke tests sufficient?
* Is documentation updated?

## Style guidance

* Prefer small, focused commits.
* Prefer explicit names for trading, risk, and evidence-learning concepts.
* Keep logging useful but avoid leaking secrets or sensitive account information.
* Keep test fixtures deterministic.
* Use existing project conventions where they are clear.
* If unsure, document the assumption and choose the safer implementation.
