# Portal change playbook — CORE-24

Start with `python -m gdt_tax.health --output doctor.json`: it inspects local mapping
and profile versions without connecting. Use `--validate-inputs FOLDER` to check the
existing offline bundle read-only. `--fixture FILE --source DVC --operation search`
analyzes local evidence and emits only structure/counts/outcome, never its body.
The report includes trace/run/operation IDs, profile/routing versions, timing and safe
schema fingerprint. Actual searches emit matching support events to DEBUG and an
optional local RunHooks.support callback; there is no automatic telemetry.

`--probe --source DVC` is explicit: one public unauthenticated GET, no redirect,
15-second deadline, 10-second timeout and 2 MiB decoded budget. Legacy probes its
public entry page only. No login/solver, business search, download or submission is
performed. Public reachability says nothing about authenticated business capability.
No live probe was executed during this review; last_verified_at remains unset in
offline reports. Live probe records its limited scope, timestamp and environment.

| Symptom / outcome | Stop and route to | Offline evidence / owner |
| --- | --- | --- |
| INVALID_CREDENTIALS | Stop auth retries; check account in supported login flow | CORE-19, authentication maintainer |
| CAPTCHA_INVALID | Finite challenge retry only | CORE-19, solver/auth maintainer |
| ACCESS_VERIFICATION / OTP / SSO | Stop automation; supported interactive action | CORE-14/19, access/auth maintainer |
| MAINTENANCE / HTTP transport | Stop repeated jobs, retry later after operator review | CORE-14/15/19, transport maintainer |
| SCHEMA_CHANGED / unknown modal | Keep good records/files; do not declare empty | CORE-01/02/17/20/22, portal adapter maintainer |
| Expiry repeats after one reauth | Stop and retain completed files | CORE-19, session maintainer |
| OFFLINE_INPUT_INVALID / mapping partial | Re-inventory same root, verify lineage/profile/mapping versions | CORE-04/07/08/09/10/26, offline maintainer |
| Release receipt mismatch | Stop before link mutation; recover saved snapshot | CORE-23/25, release maintainer |

Response workflow: stop retries; save structure-only report and sanitized support
events; construct a synthetic fixture with explicit provenance; add a failing contract
test; change one adapter/profile; run offline/desktop gates. A later live smoke requires
the operator's account, scope and budget and must be documented separately with
last_verified_at/environment. Never upload raw HTML, tokens, CAPTCHA or tax payloads.

Rollback: retain completed documents and their integrity evidence; select the previous
reviewed packaged profile/build, rerun dry query to inspect coverage, then resume with
the same scoped ownership. Do not invent remote profile values from an unknown page,
erase catalogs or silently adopt UNKNOWN files. For release rollback use the persisted
release snapshot/recovery path, not a moved tag. Compare report versions/fingerprints
before and after; a public 200 is not acceptance of all operations.
