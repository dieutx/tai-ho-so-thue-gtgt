# Portal result contracts

CORE-01/02. The five adapters now return records together with candidate, parsed,
skipped and duplicate row counts and named diagnostics. `PARSED` and
`EMPTY_CONFIRMED` are complete; `SCHEMA_CHANGED` is not. Pagination or an empty
list alone never establishes an empty result. Empty evidence requires a reviewed
visible marker inside the result context, with the appropriate legacy operation
form where relevant. Visible explicit CAPTCHA rejection remains separately
retryable; structure failures never reset the OCR failure counter.

Columns use stable data-field/data-column attributes first, then normalized
Vietnamese header aliases. Named headers support permutations, optional added
columns and multirow colspan/rowspan. Ambiguous/duplicate/missing required names
fail explicitly. Data row spans are rejected. Dates, IDs, submission counters and
GNT amount shape are checked without interpreting tax amounts; rejected raw cells
remain private in ParseDiagnostics.row_issues, not interpolated into logs.

Headerless legacy compatibility is limited to the inherited fixture fingerprint:
exact column count, reviewed operation/table and download/status markers, ID and
date/amount shape. It does not guess IDs from arbitrary columns. New headerless
formats need adapter review. Named ID columns must agree with download metadata.
Auxiliary tables outside the result context cannot contribute records.

Every pipeline stops immediately on schema drift. Valid records on a partially
read page are processed/retained before SchemaChangedError is raised; target-ID
or case-ID shortcuts cannot turn that page into success. Desktop presents
PARTIAL with retained rows and a nonzero issue count. CLI returns nonzero. Query
and dry-run paths still do not create output directories or download files.

The list-returning parse_records/parse_gnt_records/parse_tb_records functions stay
as compatibility adapters. Completeness decisions must use the new table result,
not these lists. Existing third-party PageResult producers with populated rows
remain compatible, but an empty result without diagnostics is unconfirmed.

Validation includes all-field snapshots from **pre-contract revision 3068ea9**
for eight inherited fixtures, plus synthetic permutations, missing headers,
handler changes, malformed rows, scoped empties and partial CLI/desktop results.
The inherited fixtures' original capture/anonymization provenance is unverified;
these snapshots establish regression compatibility, not live portal accuracy.
No live account/portal was used. Rollback restores preceding source, with no
catalog or tax source migration.
