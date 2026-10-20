# Directory ownership and legacy migration (CORE-03 C / CORE-13)

Online jobs validate `.gdt-owner.json` before authentication and downloads. A new
output namespace is claimed exclusively for the exact username fingerprint;
another account, malformed/future manifest, symlink, or unowned tax-data folder
fails clearly. Dry-run validates but never creates a directory or manifest.
The manifest is an isolation guard, not encryption or proof of taxpayer ownership.
Do not edit it to adopt old files. Each account should use a separate output folder.

Known-account primary/attachment resume also requires matching identity and
validated kind, size and SHA-256 evidence. Unknown legacy files never satisfy it.
Conflicting or suspect primary/alternate files are retained at their original
paths; a distinct incoming destination is chosen. These checks establish local
integrity, not digital signature validity or legal acceptance.

Old catalogs remain readable with UNKNOWN account/source. For explicit conversion,
first preview (no credentials/network):

```powershell
python -m gdt_tax.migrate_identity --catalog old/danh_sach_ho_so.json --kind DECLARATION
python -m gdt_tax.migrate_identity --catalog old/danh_sach_ho_so.json --kind DECLARATION --apply
```

Use `GNT` for the GNT catalog and `NOTICE` for the notice catalog. GNT/TB source
comes only from that explicit catalog contract; a missing declaration source stays
UNKNOWN. Conversion preserves extra columns, remote IDs and all file references;
it does not rename/delete/rewrite downloaded files, create integrity sidecars,
assign the active account, or claim the directory. Keep this legacy directory for
offline viewing; choose a fresh output folder for future online work.

The immutable `.gdt-<catalog>.identity-original` backup and migration journal hold
original/migrated hashes. Reapplying is idempotent. Rollback restores the exact
original catalog bytes:

```powershell
python -m gdt_tax.migrate_identity --catalog old/danh_sach_ho_so.json --kind DECLARATION --rollback
```

Rollback refuses if the catalog or backup changed after migration, preventing
loss of later updates. Preserve both files with the legacy directory. Duplicate
keys, conflicting identity columns and unsupported versions require explicit
review before any catalog write. The CSV/XLSX reports are derived snapshots and
are not rewritten by this catalog-only migration.

Online entrypoints enforce ownership; low-level catalog/report writers and store
objects also serve offline tooling and do not claim an account by themselves.
Their callers must use the ownership boundary for authenticated operations.
