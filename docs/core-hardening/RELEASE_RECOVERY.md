# Verified replacement and compensating rollback — CORE-25

`scripts/release_gitlab.py replace --tag desktop-vX.Y.Z --notes FILE` now requires
dist/release-manifest.json from the build provenance gate. Preflight checks desktop/
core version, tag, source revision, build timestamp, dependency inventory and gate
hashes, exactly two local assets, their hashes/sizes and checksum semantics. The tag's
remote commit must equal the bundle source SHA. Replacement never creates a release
or creates/moves a tag; mismatched source needs a separately reviewed release plan.

Before mutation, verify the existing EXE/checksum via public permalinks and persist
the original notes, asset IDs/URLs, hashes/sizes and tag revision in
.cache/release-recovery/TAG.json. Credentials stay in memory; token-file loading is
removed. Snapshot URLs reject user-info, query secrets and unexpected origins. Raw
exceptions are never recorded in the recovery state.

Upload both content-addressed packages and verify their bytes before switching links.
An existing content-addressed package is reused only after matching its hash/size,
so a retry after a partial upload sequence does not require duplicate package uploads.
Then retain IDs/permalinks, update notes, verify both package/public permalink paths
and re-read the tag. The API is not an atomic multi-link transaction. Any failure
after an attempted mutation compensates both links and notes, then verifies the old
public bytes and tag. Packages are never deleted to make a switch succeed.

If compensation cannot be verified, the command fails with RECOVERY_REQUIRED and
retains the original snapshot. Run `recover --recovery FILE` after resolving the API
failure. Recovery is idempotent and refuses to overwrite a tag, URL or notes changed
by another operator. A pending snapshot blocks a new replacement; a fully verified
switch interrupted before its final receipt can be recognized on rerun. A completed
same-bundle rerun verifies bytes and performs no further mutations.

`verify --tag TAG` verifies the local receipt, both public asset paths and tag without
mutation. `publish` remains the separate existing explicit creation command; it is
not called by replacement or recovery. No production release/tag/package was changed
and no EXE was built while implementing these tests.

Offline tests inject failures into both uploads, each upload verification, both link
updates (including a PUT applied before timeout), notes, both public package checks
and permalinks. They also exercise hash mismatch, rollback API failure with subsequent
recovery, interrupted final receipt, source/build/checksum preflight, URL secret
rejection and concurrent operator changes. Keep the recovery receipt for auditing.
