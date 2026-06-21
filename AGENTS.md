## Review guidelines

This repository contains autonomous trading functionality. Treat the following as high-priority review concerns:

* No live trading path should be enabled accidentally.
* Paper-trading, dry-run, and simulation modes must remain clearly separated from live execution.
* Risk limits, kill switches, audit logs, and safety checks must not be bypassed.
* No secrets, account IDs, credentials, API keys, or local machine paths may be committed.
* New trading, evidence-learning, or automation behavior must include tests and smoke-test coverage.
* PRs must update relevant documentation and progress trackers when behavior changes.
* Any change affecting order placement, broker connectivity, position sizing, risk controls, or autonomous decision-making requires extra scrutiny.
