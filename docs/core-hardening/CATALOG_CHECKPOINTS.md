# Catalog commits and report recovery (CORE-18)

JSON remains the canonical catalog. Each writer holds a process-level OS lock
across read/merge/atomic replace and report materialization. The lock file persists;
the OS releases the lock if a process crashes. A second writer waits at most 30
seconds, then reports CATALOG_BUSY. This coordinates local CLI/desktop processes;
network filesystems must provide the corresponding OS locking semantics.

Pipelines checkpoint JSON every page, 100 accumulated records or 30 seconds at a
record boundary. They build CSV/XLSX only at completion or a controlled error/cancel
flush. Primary files and matching integrity evidence are independently committed;
a crash before catalog checkpoint can rediscover and validate them on the next
query. A file without complete matching evidence is never counted as reused for
an authenticated account. Query/dry-run still writes nothing.

JSON replacement keeps fsync and atomic replacement. Derived files are not a
multi-file transaction. `.gdt-<catalog>.generation.json` records PENDING after the
catalog commit and READY only after all derived hashes are captured. Readers can
call reports_current; a crash before the marker update is also detected by the
catalog hash. A locked workbook/disk failure leaves the committed JSON available
and reports stale. Recover without credentials/network:

```powershell
python -m gdt_tax.rebuild_reports --catalog download/danh_sach_ho_so.json --kind DECLARATION
```

Use GNT/NOTICE for their canonical catalogs. Extra metadata fields are preserved.
Keep the JSON if recovery fails; resolve disk space/Excel locks before retrying.

The JSON checkpoint approach retains compatibility with existing catalogs and
simple rollback. SQLite would require a separate migration and changes to offline
consumers; it is deferred. Checkpoint merge cost still grows with catalog size;
this change removes repeated workbook builds, rather than claiming linear total
runtime for arbitrary catalog sizes.

Reproduce: `python scripts/benchmark_catalog.py --output benchmark.json`.
The checked-in CATALOG_BENCHMARK.json records Windows/Python and measured real
fsync/atomic writes plus openpyxl saves: checkpointed 100/1000/5000 records took
0.0928/1.5369/26.9205 seconds and built one workbook each. At 100 records, simulating
the old per-record report schedule with the current writer took 5.2925 seconds,
100 workbook saves and 4,775,145 bytes, versus 147,377 bytes after checkpointing.
The 1000/5000 legacy workbook counts are exact schedule counts, **not measured
elapsed times or byte totals**. No timing assertion is imposed on shared CI.

Fault tests run actual separate writer processes, process termination between
JSON and XLSX, lock timeout, full-disk injection, locked-report injection, recovery,
controlled cancellation and resume of a valid uncheckpointed primary file.
