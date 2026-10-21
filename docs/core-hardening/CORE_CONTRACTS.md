# Typed core contracts — CORE-21 A

contracts.py defines structural Transport/HttpResponse, Solver, Record, Store and
QueryOutcome interfaces. The response interface contains only the fields operations
need; fake transports need not construct requests.Response. Portal and CAPTCHA
boundaries consume Transport/Solver. The type-checked assignments in
tests/test_core_contracts.py gate all three concrete record/store/query contracts.

DownloadArtifact carries bounded bytes, media/document kind, scoped RecordKey and
SHA-256. Legacy declaration download now emits it directly after packaging XML as
ZIP. The fake response/JSON/base64 allocation is removed. Pipeline verifies its key
and kind before saving. decode_zip_bytes accepts it as a compatibility boundary for
older callers; output names and schemas remain unchanged. No new payload copies
are retained and no unbounded stream is introduced.

This is PR A, before sharing orchestration (B) or composing the navigator (C).
