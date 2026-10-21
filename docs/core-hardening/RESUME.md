# Tiến trình sửa 26 mục core — cập nhật 20/10/2026

**Chưa hoàn thành toàn bộ 26 mục. Đã mở các MR riêng; chưa merge/build EXE/release.**

Người dùng đã cho phép sửa cả 26 mục, commit/push/tạo MR; không hỏi lại phạm vi.
Không đăng nhập cổng thật hoặc dùng dữ liệu/tài khoản thuế để test.

## Checkout đang làm

- Repo gốc: `C:/Users/dieut/tai-ho-so-thue-gtgt`; giữ nguyên UI/DVC/prompt chưa commit của người dùng.
- Checkout cô lập: `C:/Users/dieut/tai-ho-so-thue-gtgt/.cache/pr-worktrees/core-review`.
- Nhánh hiện tại: `codex/core-auth-outcomes`, kế thừa !16; CORE-19 lưu WIP, chưa tạo MR.
- Người dùng yêu cầu lưu và dừng ngày 20/10/2026 để hôm sau tiếp tục; không tự tiếp tục khi chưa được yêu cầu.
- Baseline review: `559892f1ff22f3e68d2fbea7be0608fd0ac597c9`.

## MR

| MR | Source | Target | Commit |
| --- | --- | --- | --- |
| [!4](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/merge_requests/4) | `codex/core-review-20261020` | `main` | `c4d63d30` |
| [!5](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/merge_requests/5) | `codex/core-xml-policy` | `main` | `d83a8423` |
| [!6](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/merge_requests/6) | `codex/core-mapping-numbers` | `codex/core-xml-policy` | `41796042` |
| [!7](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/merge_requests/7) | `codex/core-offline-reports` | `codex/core-mapping-numbers` | `1f1b7020` |
| [!8](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/merge_requests/8) | `codex/core-inventory-profiles` | `codex/core-offline-reports` | `b50ed6eb` |
| [!9](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/merge_requests/9) | `codex/core-http-policy` | `codex/core-inventory-profiles` | `105396ce` |
| [!10](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/merge_requests/10) | `codex/core-diagnostics-policy` | `codex/core-http-policy` | `c52ed71c` |
| [!11](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/merge_requests/11) | `codex/core-download-integrity` | `codex/core-diagnostics-policy` | `35f2bc8d` |
| [!12](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/merge_requests/12) | `codex/core-table-contracts` | `codex/core-download-integrity` | `8bccd2e0` |
| [!13](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/merge_requests/13) | `codex/core-record-key-contract` | `codex/core-table-contracts` | `36184447` |
| [!14](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/merge_requests/14) | `codex/core-record-key-integration` | `codex/core-record-key-contract` | `9c94161d` |
| [!15](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/merge_requests/15) | `codex/core-directory-ownership` | `codex/core-record-key-integration` | `0950e80b` |
| [!16](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/merge_requests/16) | `codex/core-catalog-checkpoints` | `codex/core-directory-ownership` | `b913e5d5` |

MR !4 được sửa CI import bằng commit `547eae5`; !7 bằng `3068ea9`.
Ledger MR có thể còn SHA ban đầu của !4/!7. CI !4–!13 đã xác nhận xanh;
cần kiểm tra CI !14–!16. Không coi mergeable là CI đã đạt.

## Trạng thái 26 mục

| ID | Trạng thái | MR | Ghi chú |
| --- | --- | --- | --- |
| CORE-01 | implemented_mr | !12 | Named contracts/census/confirmed empty/partial results; CI green, unmerged |
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
| CORE-16 | implemented_mr | !10 | Metadata-only support output; separate bounded PRIVATE capture; sanitized crash frames |
| CORE-17 | partial | !7 | Offline provenance done; attachment quality pending |
| CORE-18 | implemented_mr | !16 | OS writer lock, page/count/time checkpoints, generation/rebuild, process crash/race tests; measured benchmark with explicit modeled large legacy counts |
| CORE-19 | implemented_local | pending | WIP checkpoint only: shared auth outcomes integrated; matrix fixtures, full acceptance and MR still pending |
| CORE-20 | todo |  | Tách profile năng lực portal và chính sách định tuyến nguồn |
| CORE-21 | todo |  | Định nghĩa Protocol/Result rồi mới rút gọn ba pipeline lặp |
| CORE-22 | todo |  | Fixture có nguồn gốc, contract tests và phép biến đổi cấu trúc |
| CORE-23 | todo |  | Tách test tối thiểu, desktop Windows và nâng dependency có kiểm chứng |
| CORE-24 | todo |  | Health report và playbook chẩn đoán thay đổi cổng |
| CORE-25 | todo |  | Preflight, verify đủ asset và rollback khi thay release |
| CORE-26 | implemented_mr | !8 | Structural document roles, mapping coverage and independent UNKNOWN acceptance; unmerged |

`implemented_mr` nghĩa đã triển khai trong MR, chưa merge; `partial` còn acceptance.

## Kiểm chứng mới nhất

- !8: 524 test (518 đạt/6 skip), Ruff/mypy 70 module đạt.
- !9: 536 test (530 đạt/6 skip), Ruff/mypy 71 module đạt.
- !10: 543 test (537 đạt/6 skip), Ruff/mypy 72 module đạt.
- !11: 553 test (547 đạt/6 skip), Ruff/mypy 74 module đạt.
- !12: 568 test (562 đạt/6 skip), Ruff/mypy 75 module đạt.
- !13: 579 test (573 đạt/6 skip), Ruff/mypy 76 module đạt.
- !14: 589 test (583 đạt/6 skip), Ruff/mypy 76 module đạt.
- !15: 597 test (591 đạt/6 skip), Ruff/mypy 78 module đạt.
- !16: 605 test (599 đạt/6 skip); Ruff/mypy 80 module đạt.
- CORE-19 WIP: 63 test auth/legacy/session targeted đạt; Ruff/mypy 81 module đạt.
- Full suite của checkpoint auth: `.cache/optimization/checkpoint-auth-wip-tests.log` (xem kết quả cuối log).
- Logs: `.cache/optimization/pr-{inventory-final,http-final,diagnostics-verified,download-integrity}-tests.log`.
- pypdf 6.21.1 đã cài vào `.venv-release-1.1`; dependency/pin/license packaging đã cập nhật trong !11.
- Fixture PDF cũ chỉ là stub không có xref/pages; đã tạo fixture tổng hợp hợp lệ, đặt `*.pdf binary`.

## Việc tiếp theo

1. Tiếp tục CORE-19 tại nhánh WIP: thêm fixture matrix cho cả 8 outcome/2 adapter, test DVC retry/CLI-desktop code/cancel, đọc AUTH_WIP.md.
2. CORE-03/13 đã triển khai A/B/C: không nhận file UNKNOWN làm resume tài khoản đã xác thực.
3. CORE-17: tích hợp attachment orchestration và counters/partial độc lập khỏi primary ZIP.
   !11 chỉ port `dvc_notices.py` từ snapshot để sửa decoder/storage, chưa gọi từ pipeline/portal.
4. CORE-20/21/22/23/24/25 vẫn còn theo acceptance gốc, không đóng bằng scaffold.

## Tài liệu và công cụ

- Acceptance đầy đủ: `docs/core-review-20261020/{REPORT.md,TASKS.md,BACKLOG.json}` tại repo gốc/MR !4.
- Đọc WORKTREE_ADDENDUM/WORKTREE_EVIDENCE khi sửa DVC attachment/identity/auth/crash.
- Policy/migration mới: `docs/core-hardening/{INVENTORY_POLICY,HTTP_POLICY,DIAGNOSTICS_POLICY,DOWNLOAD_INTEGRITY}.md` ở checkout.
- Test: `.venv-release-1.1/Scripts/python.exe .cache/optimization/check_core.py TEN_MOC` từ repo gốc.
- Ruff/mypy dùng `.venv-review/Scripts/python.exe`; Ruff cần `--no-respect-gitignore` trong checkout cache.
- Tạo MR bằng `.cache/optimization/open_core_mr.py`; credentials chỉ đọc trong bộ nhớ.
- Git metadata/CredentialManager cần escalation sandbox; user đã cho phép commit/push/MR.
- Không chạy lại edit_offline.py/edit_outcomes.py; không reset/clean/stash repo gốc.

## Continuation 2026-10-21

CORE-19 complete locally; 612 tests (606 pass/6 optional skip), Ruff/mypy 81 modules. See AUTH_POLICY.md. Continue CORE-17 and CORE-20 through CORE-25.
