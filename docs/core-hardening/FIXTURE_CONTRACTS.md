# Fixture provenance and drift matrix — CORE-22

tests/fixtures/manifest.json records every fixture, content hash, source, operation,
adapter contract, content kind, expected rows/outcome and sanitization provenance.
Text hashes normalize CRLF to LF for Linux/Windows parity; binary hashes are exact.
Inherited fixtures remain explicitly inherited_unverified with unknown sanitized_at.
Their historical capture/anonymization is not established by this review. The OCR
sample has been replaced with generated text abc12 (scripts/synthetic_captcha.py,
Arial Bold 28, Pillow, white background), so current tests need no portal CAPTCHA.
No new portal capture/CAPTCHA/account was added.
Do not include inherited bodies in support bundles or CI evidence artifacts.

New variants should be constructed synthetically from the named schema. Add a test
using the actual parser/adapter, assert fields and diagnostics (not only list length),
and declare provenance before running scripts/fixture_manifest.py. Review the manifest
diff. Never generate golden expectations from the new implementation merely to pass.
safe_schema_evidence exports only allowlisted structural counts and known field names;
it deliberately does not claim to anonymize arbitrary HTML into a replayable fixture.

Regression matrix:

- test_table_contracts: all five adapters, column permutations/addition/aliases,
  missing columns/handlers, auxiliary tables, colspan, partial/empty results and fields.
- test_xml_policy/test_inventory_profiles/test_parser: namespace prefix equivalence,
  scope and XML policy (see existing module names in tests).
- test_auth_outcomes/test_sessions: eight outcomes, hidden validators, rotating tokens,
  login redirect, finite reauth, isolation and cancellation.
- test_pipeline_contracts: three pipelines, sequential replay, repeated/missing pages,
  partial records and target stop; test_attachments covers modal changes and retries.
- test_fixture_provenance: manifest membership/hash, actual-parser outcomes and
  metadata sanitization against invented secrets.

Run python -m unittest discover -s tests -t .; use the named modules for a focused
adapter change. CI is offline. No live smoke is run from secrets in CI. Any future
opt-in live smoke needs an explicit account, operation scope and budget; it must not
download/submit tax documents merely to update fixtures.
