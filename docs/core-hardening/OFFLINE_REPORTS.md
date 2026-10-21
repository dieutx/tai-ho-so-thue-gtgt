# Offline stage and export contracts

New parse and classification files bind to a SHA-256 fingerprint of the manifest
(including source root, source hashes, schema and profile version; excluding only
the manifest creation timestamp). Export checks supported schema, row counts,
source identity `(artifact_id, source_zip, source_inner_file)`, hashes, duplicate
sources, coverage and the mapping registry fingerprint when supplied by both
stages. Different source paths remain distinct even for identical content.

CLI and desktop exports require this lineage. Regenerate inventory, parse and
classification together after changing sources or mappings. CLI
`--allow-legacy-data` permits older envelopes while still checking source
membership and hashes. The Python `build_rows` API keeps this compatibility
default for existing integrations; pass `allow_legacy=False` for strict checks.
This is provenance validation, not a signature against deliberate tampering.

All workbook writers force strings to literal text cells, including strings
starting with formulas, whitespace and control prefixes. Forbidden XML control
characters are replaced with U+FFFD for XLSX; JSON retains original data. CSV
writers prefix potentially executable text with an apostrophe. `gdt-export
--raw-csv` explicitly opts out for machine ingestion. JSON remains unescaped.

Only indicators declared numeric become Excel numeric cells. Values exceeding
15 significant decimal digits, outside the supported exponent range, nonfinite
or malformed stay text with a warning. Raw values always stay text. Identifiers,
including leading-zero tax codes, stay text. Excel uses binary floating point;
use canonical JSON decimal strings for exact calculations beyond its precision.
Missing values remain blank and zero remains numeric zero.

Export preserves parser errors, warnings, mapping version/hash, registry hash,
validation status and classification reason in rows/JSON. Workbook sheets expose
parse errors, indicator precision warnings, mapping versions and stage versions
in the audit log. No aggregation selects or sums supplementary filings.

The four offline CLIs use exit 0 for complete quality, 1 for written partial
results, 2 for invalid input/contract/output failure. `--summary-json PATH` writes
`quality-summary-v1` with status counts and incomplete count. Unmapped documents,
classification conflicts/unknowns and partial extraction are incomplete, not
silent success. Export quality is measured before display filters. This changes
the old behavior which returned 0 after writing batches containing errors.

Verification: `tests/test_offline_contracts.py` exercises mismatched inventories,
changed hashes, duplicates, coverage, legacy mode, shared IDs across sources,
malformed input, XLSX save/reload cell types, precision limits, CSV modes and CLI
quality exit behavior. All checks are offline.
