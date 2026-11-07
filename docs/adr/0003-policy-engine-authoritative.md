# ADR 0003 — Policy engine is authoritative

The Governance Agent may explain a decision. `aegisops.policy.engine` accepts or rejects it. LLM output is not an authorization source. High-risk actions remain approval-gated even when L4 is enabled later.

L4 is off unless `AUTONOMY_L4_ENABLED=true`. The default level cannot be L4 while that flag is false.
