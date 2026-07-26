# Tomato Sentinel policy engine

Deterministic, side-effect-free authorization domain for registered Tomato
Sentinel tools.

The initial package models:

- actors and organization roles;
- trusted devices and verified capabilities;
- operating profiles;
- resource grants and operation scopes;
- registered tool manifests;
- immutable confirmations;
- allow and denial decisions with stable reason codes.

It intentionally contains no HTTP framework, database, LLM or provider code.
