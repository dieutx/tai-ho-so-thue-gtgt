# Attachment orchestration — CORE-17

DVC downloads include notices by default. Pipeline(download_notices=False) opts out.
Primary ZIP success and attachment completeness are separate: RunSummary.primary_complete
keeps the primary counts; complete requires both. CLI exits 1 for incomplete attachments.
Dry-run reads no detail/attachment and writes no catalogs. Other sources are unaffected.

Only one reviewed modal is read. Confirmed empty requires an explicit empty marker;
missing/duplicate modal, renamed handler and ambiguous lists are SCHEMA_UNKNOWN. No
fallback scans unrelated page links. AttachmentKey includes account, parent, route,
remote ID, lookup and type. Titles are display grouping, never acceptance evidence.

Results retain discovered/downloaded/reused/failed/skipped and discovery failures,
per-item key, error code, retryability, path/size/SHA-256. Metadata JSON/CSV retain the
structured JSON result; core and desktop XLSX reports include an Attachments sheet.
Desktop JobResult carries attachment_results independently from primary download errors.
Rerun or select the parent again to retry: valid primary and attachment evidence is
reused, only missing/invalid notices download. Legacy UNKNOWN files are not adopted.

Network/auth/schema/CSRF/save errors preserve completed ZIPs. Cancellation propagates
with CANCELLED quality persisted by the checkpoint. Programming errors are not swallowed.
All payloads pass the common bounded integrity validators before save/resume.

Validation: 619 offline tests (613 passed, 6 optional skips), Ruff/mypy 82 modules.
Synthetic fixtures exercise route collisions, confirmed empty/unknown, HTTP 500,
expiry, maintenance, network/storage failures, cancellation and selective retry.
