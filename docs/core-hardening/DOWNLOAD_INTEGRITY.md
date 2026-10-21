# Download integrity and compatibility

CORE-12 shared XML limits are now also used by legacy declaration and GNT
download validators. CORE-13 introduces content-kind checks before save/resume
and desktop file verification. Unknown XML roots/namespaces report unsupported;
HTML, status/SOAP/error envelopes, malformed XML and DTDs are rejected. The
reviewed root set is intentionally conservative and does not validate tax law,
XML signatures or legal acceptance.

PDF checks use pypdf 6.21.1 in strict mode, checking the end/xref marker and
resolving the page tree; encrypted/empty/unreadable documents remain unverified.
This replaces prefix-only detection. pypdf is pure Python, now a required core
dependency and pinned in the desktop build requirements, with its license added
to the packaging allowlist. API rationale: [official PdfReader documentation](https://pypdf.readthedocs.io/en/stable/modules/PdfReader.html).
No rendering, script execution or signature verification is performed. The
synthetic PDF fixture was regenerated with PdfWriter because its previous
header/catalog stub had no xref or pages. PDF files are marked binary in Git to
preserve byte offsets across Windows checkouts. No EXE rebuild was performed.

Archives must pass the existing resource/CRC limits, reject unsafe member paths,
and contain the required document kind. A valid ZIP is not sufficient evidence
of a declaration. Legacy test helpers now use a recognized synthetic declaration
root instead of the unrecognized `<to-khai/>` placeholder.

New files receive `.integrity.json` evidence containing validator version, kind,
size, SHA-256 and source reference. Resume revalidates bytes and checks evidence
when present. Conflicting/suspect originals are preserved with new incoming
content under a distinct filename; old files are no longer renamed on resume.
Sidecars are ignored by inventory. Core and desktop share the validators.

Compatibility limitation awaiting CORE-03: legacy primary files with no evidence
still use the previous content-only resume path. Their account/source ownership
has not been established. **CORE-13 is not closed until account/source migration
and target/catalog binding are finished.** Notice attachments require evidence
and the full route object; bare notice IDs cannot select files. The notice module
was ported from the reviewed WIP snapshot for validators/storage only; runtime
attachment orchestration and completeness are separate CORE-17 work.

Rollback restores preceding code and regenerates reports; source files are not
deleted. Preserve sidecars for later migration. Unit fixtures are hand-authored
or generated, not captured tax data; no portal was contacted.
