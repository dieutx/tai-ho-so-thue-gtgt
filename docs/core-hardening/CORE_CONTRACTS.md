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

## PR B: shared sequential orchestration

orchestration.py now owns retry/budget/completeness, repeated/empty page checks,
page-boundary checkpoints and per-record target/progress/error bookkeeping. Adapter
pagination requests and document validation/storage remain with each adapter.
The page iterator yields before advancing: the caller consumes and downloads each
record on the current DSE page. Early target completion is allowed only on a complete
parse. A partial page retains records, checkpoints them and raises SCHEMA_CHANGED.

tests/test_pipeline_contracts.py runs identical immediate-download, partial, repeated
and target-stop traces through declaration, GNT and TB pipelines. No filenames,
catalog schema, parallelism or payload buffering changed.
