# Versioned portal capabilities and routing — CORE-20

The first migrated adapter is DVC, as required by the staged rollout. PortalProfile
controls reviewed search/validate/download/form endpoints, form ID, page parameter,
result scope, total/input pagination IDs, document kinds, date limit and the table
response contract. DvcPortal consumes these descriptors; generic orchestration does
not change when a profile changes. Profiles are immutable packaged Python data,
validated before use. There is no remote config or executable selector loader.
Legacy/ETAX retain the compatibility adapter until their own fixture-backed migration;
their existing behavior is explicitly identified as legacy-v1 in record lineage.

Settings.execution_plan uses RoutingPolicy effective dates and source windows. It
segments dates at all boundaries, reports gaps, overlaps and disabled sources, and
keeps source-specific record identity in overlap regions. Gaps/overlaps prevent a
complete summary. Limits combine the configured maximum and adapter capability.
Old cutoff/legacy/DVC options create an equivalent compatibility policy. The complete
plan is logged before authentication; profile/routing versions are in summary and
each new record's JSON/CSV lineage. No source is silently substituted after failure.

Validation mutates endpoint/form/page/result IDs through the actual adapter and
checks cutoff boundaries, effective date, missing/overlap windows, source disable,
date limits, diagnostics and record lineage. All tests run offline.
