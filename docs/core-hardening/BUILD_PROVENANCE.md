# Offline CI and controlled builds — CORE-23

Linux minimal jobs (Python 3.10/3.12) install only core and publish a JSON receipt
listing every optional skip. The Full Windows gate requires Qt, ddddocr and ONNX;
skipping Qt/default OCR fails that gate. Other optional OCR engines remain optional.
Windows frozen build/smoke runs on a windows-x64 runner: manual on review branches,
required for desktop-v tags. No portal/account/network smoke is part of these tests.
Runner availability and a real frozen build are external validation, not claimed by
this implementation. No EXE was built or published during this review.

requirements-*-windows-py311.lock pins the full runtime/build-tool transitive graph
from the previously tested CPython 3.11 x64 environment. Installation uses --no-deps,
followed by pip check and exact inventory verification. Checked-in inventory includes
package versions plus METADATA/WHEEL hashes; it is a controlled inventory, not a
claim of hash-locked wheel download or bit-for-bit reproducibility. Pip bootstrap
and the editable project itself are excluded; package contents remain subject to the
bundle/model audit and artifact hashes. Capture is an explicit reviewed update step.

Dependency update workflow: change one pin in a small MR, capture/review both platform
inventories/locks, run source desktop gate, then frozen parity/model/bundle/size gates.
Keep ORT/model unchanged without parity evidence. This MR preserves the verified
versions; it does not upgrade dependencies for novelty.

Build metadata refuses dirty tracked sources (except its two generated metadata files)
or a CI SHA mismatch. It records core 1.0.0, desktop 2.0.0 and source SHA separately;
the About dialog exposes all three. Desktop updater still compares desktop version.
No release version bump is introduced. Frozen/source smoke checks source and OCR parity.

build_provenance.py requires successful source, frozen and bundle gates bound to that
revision, then writes both asset hashes/sizes, checksum and dist/release-manifest.json.
The receipt includes inventory/audit/gate hashes and no credentials or raw fixtures.
Release preflight consumes this receipt. CI artifacts contain receipts, not captures.
