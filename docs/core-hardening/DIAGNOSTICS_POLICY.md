# Diagnostic data boundaries

CORE-16, including the uncommitted DVC/crash-log review addendum. The source
checkout containing that UI/DVC work is left untouched; this branch provides a
sanitized crash hook without copying the unrelated UI changes.

Default HTTP logs and `--dump-http DIRECTORY` contain method, sanitized endpoint,
status, size/hash and selected safe headers. Payloads, query credentials,
Referer/Location queries, cookie/authorization/token headers and taxpayer/login
fields are omitted or masked. Structured redaction supports JSON strings,
nested arrays, form encoding and HTML fields. This is defense in depth, not a
promise that arbitrary raw HTML or XML has been anonymized.

`--dump-http-private` with a dump directory, or `GDT_HTTP_DUMP_PRIVATE=true`,
explicitly enables raw response bytes. They live under `DIRECTORY/PRIVATE`,
with a PRIVATE label, capped at 2 MB/body, 100 requests and a 15-minute capture
window. Delete after diagnosis. These files must never be collected in support
archives or committed. Existing raw dumps remain private and are not
retroactively sanitized. Default support dumps never contain `.body` files.

Python exception logs/crash records retain exception class and frame locations,
omitting message, source lines and locals. The frozen crash hook uses a PRIVATE
directory with one backup above 1 MiB and removes crash records older than seven
days on startup. Native faulthandler output is private because it cannot pass
through the Python redactor. No native crash was triggered during validation.

Migration: `--dump-http` now records metadata only. Request raw bytes explicitly
when necessary. No tax source or catalog schema changes. Rollback restores the
preceding source revision; captured PRIVATE data must remain private regardless
of version. Contract fixtures use synthetic tokens and taxpayer strings only.
