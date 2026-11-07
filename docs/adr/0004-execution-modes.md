# ADR 0004 — Three execution modes, no silent fallback

`LIVE`, `SANDBOX`, and `SIMULATOR` are explicit. A failed live call is an integration error. It is not replaced with fixture data.

A complete saved ServiceNow or Dynatrace connection is used in every mode, including `SIMULATOR`. Fixture adapters are used only when that connection is incomplete and the mode is `SIMULATOR`. `SANDBOX` and `LIVE` without the connection raise an integration error. Demo 1 and Demo 2 load through `fixtures_only`, so those catalogs stay on fixtures even after a connection is saved. `LIVE` still requires credentials at startup and still refuses the local runbook runner.
