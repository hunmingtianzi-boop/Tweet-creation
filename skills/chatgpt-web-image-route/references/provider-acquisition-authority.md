# Provider acquisition assurance

Formal micro assets use `org-wechat-provider-image-acquisition-v2` and bind the
verified installed release, exact adapter route, same-session runtime binding,
canonical request metadata, create-once Browser download ingestion,
exact raw SHA/byte length, and the final RGBA8/Alpha pixel gate.

The first real source may be either accepted native-alpha or accepted
controlled-key. Both are valid one-attempt ledgers. Only a real native-alpha
rejection followed by a controlled-key retry uses two attempts, and the rejected
raw pixel failure is recomputed rather than trusted from a string field.

The normal current-session result is
`current-session-operator-harness-trusted`. It may be used operationally only
while the complete chain still validates, and must report:

- `operationally_accepted: true`;
- `authorized: false`;
- `host_attested: false`;
- `portable: false`.

The compatibility callback `live_provider_acquisition_authority(callback)` is
only an optional trusted-harness veto policy. `True` does not upgrade
assurance; `False` or an exception blocks. Ordinary Python callables, serialized
callback fields, `ContextVar`, or interface types are not attestation.

Portable assurance remains `portable-signed`. It may use the legacy optional
host-finalized migration Ed25519 receipt plus an independent provider receipt, both
verified through a protected external public-key store. A failed or missing
portable signature cannot silently downgrade to current-session acceptance.

The synthetic RGBA migration probe is not a prerequisite. Old v1 ledgers,
arbitrary route names, copied raw files, non-create-once
ingestion, reused provider requests, and tampered pixel chains remain blocking.
