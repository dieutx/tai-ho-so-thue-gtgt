# Record identity contract (CORE-03 A)

The contract increment (A) defines identity; integration (B) applies it to online
pipelines, catalogs, attachments and desktop selection. **CORE-03 is not complete**
until directory ownership and explicit legacy migration (C) are implemented.

RecordKey consists of account_key, source, document_kind and remote_id. Canonical
UTF-8 JSON arrays are encoded as URL-safe base64 with the version prefix `rk1.`;
parsing rejects noncanonical encodings and unsupported versions. Remote IDs are
preserved exactly and remain the request parameter sent to the portal. A key is
not an endpoint identifier, tax-family grouping or reason to merge filings.

Account fingerprints preserve identifier spelling/case and use SHA-256, matching
the desktop's existing convention. They provide namespace identity, not encryption
or anonymization; taxpayer identifiers can be guessed from an unsalted hash.

Old rows read as account UNKNOWN and source UNKNOWN when source is missing.
No reader accepts the active account as a migration default. Serialized keys and
plain identity columns must agree. Source/kind can only come from explicit
metadata or the known GNT/TB catalog contract. Reading/migration preview does not
rename/delete files or rewrite the old row.

Target selection requires a fully scoped key across multiple sources. A legacy
bare ID may be adapted only when exactly one source is known before requests
start. Cross-account, cross-kind or source-outside-plan keys fail. This prevents
an early exit on the first same-ID record from hiding a later source collision.

AttachmentKey adds the parent RecordKey, route source, remote notice ID and
loai_tra_cuu/loai_tbao dimensions, with prefix `ak1.`. Human title and sent time
are not identity, so a title change does not create a new attachment. Each
dimension is kept even when two routes happen to return equal bytes.

Online records are bound to the authenticated username fingerprint. Pipeline and
GUI maps, success/failure sets, targets and catalog merges use serialized RecordKey;
portal requests and human labels keep the remote ID. Known-account resume requires
matching source/account/key and validated size/hash evidence; unowned legacy files
are preserved and are never adopted as a successful authenticated download. A
selected GUI row with UNKNOWN or another account requires a new query. Dry-run
does not write catalogs or ownership evidence.

Next increment: enforce directory ownership and add explicit legacy catalog
migration with unknown ownership and rollback instructions. Existing metadata
continues to read as UNKNOWN; it is retained separately when new owned rows are
merged. Directory isolation is still pending, so do not treat this as closure of
CORE-03 or CORE-13.
Synthetic tests cover roundtrip, delimiter/Unicode preservation, collisions,
malformed versions, migration idempotency/conflicts and target scoping.
