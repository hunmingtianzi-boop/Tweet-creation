# Provider acquisition assurance

Formal micro assets use `org-wechat-provider-image-acquisition-v2` and bind the
verified installed release, exact adapter route, completed same-session
migration, canonical request metadata, create-once Browser download ingestion,
exact raw SHA/byte length, and the final RGBA8/Alpha pixel gate.

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

Portable assurance remains `portable-signed`. It requires a host-finalized
migration Ed25519 receipt plus an independent provider Ed25519 receipt, both
verified through a protected external public-key store. A failed or missing
portable signature cannot silently downgrade to current-session acceptance.

Old v1 ledgers, arbitrary route names, copied raw files, non-create-once
ingestion, reused provider requests, and tampered pixel chains remain blocking.
