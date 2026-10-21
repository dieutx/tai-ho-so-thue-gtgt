# Tiến trình sửa 26 mục core — 21/10/2026

**Đã triển khai đủ 26/26 mục trong các MR; chưa merge MR, build EXE hoặc phát hành.**

`implemented_mr` nghĩa đã có code và kiểm thử trong MR, chưa có nghĩa thay đổi đã vào main/release.
Người dùng đã cho phép sửa toàn bộ, commit/push/tạo MR. Không dùng tài khoản/dữ liệu thuế hoặc gọi cổng thật để test.

## Checkout và dữ liệu gốc

- Checkout core: `.cache/pr-worktrees/core-review`, nhánh `codex/core-progress-complete`.
- Repo gốc giữ nguyên các thay đổi UI/DVC/prompt chưa commit của người dùng; không reset/clean/stash.
- Baseline review: `559892f1ff22f3e68d2fbea7be0608fd0ac597c9`.
- Acceptance gốc ở MR !4 và `docs/core-review-20261020/{REPORT.md,TASKS.md,BACKLOG.json}` tại repo gốc.

## Trạng thái 26 mục

| ID | Trạng thái | MR | Kết quả |
| --- | --- | --- | --- |
| CORE-01 | implemented_mr | !12, !28 | Named schemas, confirmed empty/partial rows; unknown legacy query stops after one request. |
| CORE-02 | implemented_mr | !12 | Five adapters, header permutation and conservative fingerprints; unmerged |
| CORE-03 | implemented_mr | !13, !14, !15 | A/B/C scoped identity, pre-auth folder owner and reversible UNKNOWN legacy migration; unmerged |
| CORE-04 | implemented_mr | !7 | Lineage/schema/count/source/hash/coverage; unmerged |
| CORE-05 | implemented_mr | !7 | Common literal XLSX text and safe CSV; unmerged |
| CORE-06 | implemented_mr | !7 | Typed numeric cells and precision policy; unmerged |
| CORE-07 | implemented_mr | !5, !6, !8 | Parser and inventory namespace/scope done; unmerged |
| CORE-08 | implemented_mr | !6 | Explicit numeric formats and ambiguity handling; unmerged |
| CORE-09 | implemented_mr | !6 | Registry schema/duplicates/version policy; unmerged |
| CORE-10 | implemented_mr | !8 | Root/profile/policy cache binding and regression tests; unmerged |
| CORE-11 | implemented_mr | !7 | Four offline CLI quality exits/summaries; unmerged |
| CORE-12 | implemented_mr | !5, !11 | Shared XML reader also in download validators; unmerged |
| CORE-13 | implemented_mr | !11, !14, !15 | Kinds/PDF/ZIP/source/hash evidence plus account ownership; unmerged |
| CORE-14 | implemented_mr | !9 | Reviewed HTTPS origins, manual redirects and parsed routing; unmerged |
| CORE-15 | implemented_mr | !9, !11 | Decoded streaming limits/spool/run budget/finite Retry-After/base64 bounds; unmerged |
| CORE-16 | implemented_mr | !10, !27 | Metadata-only support/crash output; unknown-page evidence never echoes portal text. |
| CORE-17 | implemented_mr | !7, !18 | Offline provenance plus independent attachment counters, per-item evidence and selective retry. |
| CORE-18 | implemented_mr | !16 | OS writer lock, page/count/time checkpoints, generation/rebuild, process crash/race tests; measured benchmark with explicit modeled large legacy counts |
| CORE-19 | implemented_mr | !17, !27 | Eight outcomes, conservative home navigation, rotating tokens, finite reauth and shared safe codes. |
| CORE-20 | implemented_mr | !19, !28 | All five adapter profiles, effective routing, date capabilities, operation/form/page/download descriptors and lineage. |
| CORE-21 | implemented_mr | !20, !21, !22 | Protocols/artifacts first, shared sequential orchestration, composed DSE navigator; three PRs. |
| CORE-22 | implemented_mr | !23 | Manifest/hash/provenance, synthetic OCR image, structural sanitizer and real-adapter drift contracts. |
| CORE-23 | implemented_mr | !24 | Minimal/Full gates, controlled transitive inventories, build/source receipts; MR test/lint rules corrected. |
| CORE-24 | implemented_mr | !25, !27 | Offline doctor/validate-inputs, safe structured events, explicit bounded public probe and rollback playbook. |
| CORE-25 | implemented_mr | !26 | Strict replacement preflight, both-asset verification, durable compensation/recovery, staged reuse and idempotence. |
| CORE-26 | implemented_mr | !8 | Structural document roles, mapping coverage and independent UNKNOWN acceptance; unmerged |

## Merge requests

Các MR triển khai xếp chồng theo cột Target; !4 là review, !5 bắt đầu chuỗi code trên main.
Không tự merge chuỗi hoặc phát hành khi chưa có yêu cầu riêng.
SHA là head ghi nhận tại lần đồng bộ tài liệu; thay đổi chỉ tài liệu sau đó có thể có SHA mới.

| MR | Source | Target | Head ghi nhận |
| --- | --- | --- | --- |
| [!4](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/merge_requests/4) | `codex/core-review-20261020` | `main` | `547eae5d` |
| [!5](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/merge_requests/5) | `codex/core-xml-policy` | `main` | `d83a8423` |
| [!6](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/merge_requests/6) | `codex/core-mapping-numbers` | `codex/core-xml-policy` | `41796042` |
| [!7](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/merge_requests/7) | `codex/core-offline-reports` | `codex/core-mapping-numbers` | `3068ea96` |
| [!8](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/merge_requests/8) | `codex/core-inventory-profiles` | `codex/core-offline-reports` | `b50ed6eb` |
| [!9](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/merge_requests/9) | `codex/core-http-policy` | `codex/core-inventory-profiles` | `105396ce` |
| [!10](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/merge_requests/10) | `codex/core-diagnostics-policy` | `codex/core-http-policy` | `c52ed71c` |
| [!11](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/merge_requests/11) | `codex/core-download-integrity` | `codex/core-diagnostics-policy` | `35f2bc8d` |
| [!12](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/merge_requests/12) | `codex/core-table-contracts` | `codex/core-download-integrity` | `8bccd2e0` |
| [!13](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/merge_requests/13) | `codex/core-record-key-contract` | `codex/core-table-contracts` | `36184447` |
| [!14](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/merge_requests/14) | `codex/core-record-key-integration` | `codex/core-record-key-contract` | `9c94161d` |
| [!15](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/merge_requests/15) | `codex/core-directory-ownership` | `codex/core-record-key-integration` | `0950e80b` |
| [!16](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/merge_requests/16) | `codex/core-catalog-checkpoints` | `codex/core-directory-ownership` | `b913e5d5` |
| [!17](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/merge_requests/17) | `codex/core-auth-outcomes` | `codex/core-catalog-checkpoints` | `0d225bdd` |
| [!18](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/merge_requests/18) | `codex/core-attachment-outcomes` | `codex/core-auth-outcomes` | `d4390775` |
| [!19](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/merge_requests/19) | `codex/core-portal-profiles` | `codex/core-attachment-outcomes` | `6c886c6f` |
| [!20](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/merge_requests/20) | `codex/core-typed-contracts` | `codex/core-portal-profiles` | `9dc4c832` |
| [!21](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/merge_requests/21) | `codex/core-shared-orchestration` | `codex/core-typed-contracts` | `c9e23b60` |
| [!22](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/merge_requests/22) | `codex/core-legacy-navigator` | `codex/core-shared-orchestration` | `75fa567d` |
| [!23](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/merge_requests/23) | `codex/core-fixture-provenance` | `codex/core-legacy-navigator` | `fa5ac544` |
| [!24](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/merge_requests/24) | `codex/core-ci-provenance` | `codex/core-fixture-provenance` | `862e8f1b` |
| [!25](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/merge_requests/25) | `codex/core-health-reports` | `codex/core-ci-provenance` | `0e04b01d` |
| [!26](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/merge_requests/26) | `codex/core-release-recovery` | `codex/core-health-reports` | `ee09255f` |
| [!27](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/merge_requests/27) | `codex/core-final-acceptance` | `codex/core-release-recovery` | `6bb05d25` |
| [!28](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/merge_requests/28) | `codex/core-profile-coverage` | `codex/core-final-acceptance` | `f9694223` |

## Kiểm chứng cuối

- Full desktop/CPU OCR: 669 tests, 663 đạt, 6 skip ngoài profile Full; không skip Qt/OCR mặc định.
- Môi trường core sạch không Qt/OCR: 669 tests, 630 đạt, 39 skip tùy chọn, có danh sách trong receipt.
- Ruff toàn checkout và mypy core + concrete Protocol assignments: đạt (89 file được mypy kiểm tra).
- Inventory runtime/tooling CPython 3.11 Windows x64: exact versions + METADATA/WHEEL hashes đã verify.
- CI bắt buộc: Linux Python 3.10/3.12 và lint; kiểm tra success đúng head SHA, không coi mergeable/manual/skipped là đã đạt.
- CI !4–!28 đã xác nhận xanh, đúng head SHA và đủ test/lint bắt buộc.
- Chứng cứ CI hiện hành ở `.cache/optimization/core-ci-latest.json`; gate receipts ở `.cache/pr-worktrees/core-review/.cache/ci/`.
- Windows frozen runner/gate đã cấu hình; chưa chạy build/frozen smoke trong lượt này theo phạm vi đã lưu. Không có release/tag/package thật nào bị thay đổi.

## Chính sách và giới hạn

- Profile migration đã phủ DVC, ETAX, ETAX_LEGACY, GNT, TB; không tải cấu hình thực thi từ remote.
- Fixture mới là tổng hợp. Fixture lịch sử giữ provenance chưa xác minh, không gán ngày capture/sanitize giả; ảnh OCR hiện tại được tạo từ chữ tổng hợp.
- Lock dùng controlled inventory, chưa tuyên bố hash-locked wheel downloads hoặc build bit-for-bit.
- CORE-18: benchmark legacy lớn có operation counts mô hình; số đo baseline thời gian ở N=100, checkpoint N=100/1000/5000. Giữ rõ giới hạn này.
- Chỉ public probe opt-in một GET có budget; không thực thi probe thật trong lượt sửa này.
- Migration giữ UNKNOWN ownership/source, không tự nhận file cũ cho tài khoản đang mở.

Tài liệu policy trong `docs/core-hardening`: AUTH_POLICY, ATTACHMENT_POLICY, PORTAL_PROFILES,
CORE_CONTRACTS, FIXTURE_CONTRACTS, BUILD_PROVENANCE, PORTAL_PLAYBOOK, RELEASE_RECOVERY,
và các policy XML/HTTP/diagnostics/integrity/ownership/catalog đã có.

## Tiếp tục

Phần triển khai 26 mục đã xong; tiếp theo là review/merge theo thứ tự dependency nếu người dùng yêu cầu.
Build EXE, frozen smoke và release là các bước riêng chưa được thực hiện. Không mở lại AUTH_WIP như một mục chưa xong.
