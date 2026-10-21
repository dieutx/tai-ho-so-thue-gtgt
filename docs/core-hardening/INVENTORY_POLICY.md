# Inventory cache and document quality

CORE-07, CORE-10, CORE-26; baseline review revision
`559892f1ff22f3e68d2fbea7be0608fd0ac597c9`.

Inventory metadata is read from the selected main document, using its namespace
URI and excluding appendix metadata. The full document still contributes to the
structural skeleton. Namespace aliases do not change metadata extraction. The
profile records the document root and structural markers used for classification.

Cache entries are reusable only with the same resolved source root, inventory
schema, profiler version and resource policy. The v5 profiler adds scoped
indicator codes. Old manifests remain readable as stage inputs but their cache
is invalidated and rebuilt without modifying sources. A plain dictionary cache
has no root provenance and is not reused. Cache hits are copied before attaching
current metadata; errors are rescanned. Symbolic links are rejected.

The fast cache compares path, size and mtime. It cannot detect a same-size edit
whose mtime was restored: use `gdt-inventory FOLDER --rehash` for integrity checks.
Raw sources exceeding their format limit are rejected before hashing/reading the
whole file. Stat, read and hash failures become per-file diagnostics and do not
discard successful sibling files.

Classification distinguishes declarations, appendices, notices, unknown and
conflicting structures. Mapping coverage lists form/version/namespace, expected,
present, missing and unmapped indicator codes. Presence counts are structural;
they do not validate amounts or infer the meaning of an unmapped `ctXX` code.
Mapping fields using custom XPath still require parser extraction validation.

Exports expose parse quality, file integrity and acceptance separately. A file
that parses successfully does not establish legal acceptance. Case metadata is
retained as raw/unverified evidence, with its source. Verified acceptance remains
UNKNOWN and verification time stays empty until an artifact-specific evidence
policy exists. Every filing remains in the export.

Rollback: return to the preceding source revision and regenerate derived
manifest/classification/parsed/export stages together; source files and catalog
metadata are never renamed or deleted. Tests in `test_inventory_contracts.py`
use hand-authored XML and in-memory mutations from `test_inventory.py`; no live
portal capture, credential, taxpayer document or schema authenticity is claimed.
