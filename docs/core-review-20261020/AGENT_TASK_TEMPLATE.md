# Prompt giao coding agent tạo PR

Chọn một hoặc một phần ID trong [TASKS.md](TASKS.md), điền chỗ trống rồi giao prompt dưới đây. Với đầu việc L, chọn PR A/B/C hoặc một phạm vi nhỏ rõ ràng; không giao “fix toàn bộ report” trong một PR.

```text
Repo: tai-ho-so-thue-gtgt
Task ID: CORE-__
Phạm vi PR lần này: ____________________
Base branch: main
Kết quả mong muốn: triển khai, kiểm thử và tạo PR để review; chưa merge hoặc release.

Đọc:
- docs/core-review-20261020/REPORT.md
- Phần Task ID tương ứng trong docs/core-review-20261020/TASKS.md
- docs/core-review-20261020/BACKLOG.json
- Ca R__ tương ứng trong EVIDENCE.json và reproduce_findings.py nếu có.
- WORKTREE_ADDENDUM.md và WORKTREE_EVIDENCE.json nếu liên quan DVC attachment,
  identity, file validation, crash log hoặc chất lượng kết quả tải kèm.
- AGENTS.md/CONTRIBUTING và quy tắc repo đang có tại HEAD.

Report dùng baseline 559892f1ff22f3e68d2fbea7be0608fd0ac597c9.
Trước khi sửa, đối chiếu HEAD: code có thể đã đổi hoặc ticket đã được giải quyết.
Mức P1 là ưu tiên rủi ro, không chứng minh có dữ liệu thật bị sai/exploit.

1. Kiểm tra lại vấn đề ở HEAD bằng fixture tổng hợp; ghi rõ input, actual,
   expected và loại bằng chứng. Nếu không còn tái hiện, báo chứng cứ,
   không làm refactor không cần thiết để tạo PR.
2. Nếu ticket là đề xuất kiến trúc, xác nhận đường gọi, tradeoff và thiết kế
   hợp đồng tối thiểu trước khi triển khai. Nêu decision trong PR.
3. Tạo regression test có ý nghĩa ở biên lỗi, gồm cả input hợp lệ cũ và
   negative case; không đổi golden output hàng loạt mà không giải thích.
4. Thực hiện đúng scope, acceptance và non_goals của ticket.
   Nếu phụ thuộc chưa có, chọn contract PR nhỏ hoặc giải thích blocker.
5. Không sửa file nguồn/tax output của người dùng. Không dùng account/password
   từ chat, .env thật, raw HTML/log, CAPTCHA thật hoặc tài liệu thuế thật làm test.
   Tests mặc định offline; không đăng nhập hoặc gọi portal thật nếu chưa có
   nhiệm vụ live smoke riêng được cho phép.
6. Giữ query/dry_run không tải/ghi output. Giữ NULL khác 0, UNKNOWN/NEED_MAPPING
   và PARTIAL. Không đồng nhất file hợp lệ với tờ khai đã được chấp nhận.
7. Không bật huge_tree/verify=False, retry mọi POST, hoặc thêm fallback rộng
   để làm xanh test. Không tải song song trong cùng phiên DSE.
8. Nếu đổi schema/catalog/key/CLI contract: có migration hoặc compatibility
   adapter, test nâng cấp và rollback; giữ file đã có và metadata tốt khi lỗi.
9. Chạy targeted tests và checks phù hợp; xem validation commands bên dưới.
   Chỉ chạy Windows/frozen build khi scope cần, không rebuild chỉ để review docs.
10. Tạo branch/commit/PR riêng, không force-push main, không đổi tag/version,
    không publish/replace GitLab asset. Không đưa prompt cá nhân/untracked
    files của người dùng vào commit.

PR description phải có:
- Trigger và trước/sau của lỗi, ví dụ tối thiểu.
- Thay đổi cụ thể và vì sao đủ xử lý vấn đề.
- Acceptance nào đã đạt, test commands + kết quả; skip và phần chưa test.
- Compatibility/migration, tác động dữ liệu, rủi ro và rollback.
- Link Task ID, source revision và fixture/evidence liên quan.

Nếu cần mở rộng scope, ghi rõ việc thêm và lý do trong PR; không tự triển khai
các ticket khác không có quan hệ bắt buộc.
```

## Các lệnh kiểm tra tham khảo

Chạy tại repo root. Chọn Python/venv đúng với môi trường hiện tại; đường venv dưới đây là môi trường có sẵn trên máy lúc review, không phải yêu cầu cài giống tên.

```powershell
# Quan sát baseline: đây không phải bộ test kỳ vọng hành vi đã sửa.
.venv-release-1.1/Scripts/python.exe docs/core-review-20261020/reproduce_findings.py

# Test đúng module thay đổi trước, ví dụ:
.venv-release-1.1/Scripts/python.exe -m unittest tests.test_parsing tests.test_pipeline

# Kiểm tra chung:
.venv-release-1.1/Scripts/python.exe -m unittest discover -s tests -t .
.venv-review/Scripts/python.exe -m ruff check .
.venv-review/Scripts/python.exe -m mypy gdt_tax
```

Sau khi fix, không sửa script minh họa để cố duy trì output sai cũ. Chuyển hành vi mong muốn thành test trong `tests/`; lưu kết quả review mới riêng và ghi revision. Chỉ dùng `--output` khi muốn ghi quan sát, tránh ghi đè `EVIDENCE.json` của baseline trong một PR sửa code.

## Checklist của người nhận PR

- Đúng một ID hoặc một phần L đã giao; không có thay đổi ngoài phạm vi khó review.
- Có test đỏ trước bản vá và xanh sau bản vá, hoặc bằng chứng tương đương nếu là refactor.
- Fixture không chứa dữ liệu thật; không có network side effect trong test mặc định.
- Hợp đồng đủ/thiếu/rỗng/không hiểu được phân biệt rõ.
- Các consumer CLI/desktop/storage/export bị ảnh hưởng đã được kiểm tra.
- Có migration/recovery nếu cần; không dùng broad catch để làm mất lỗi.
- Nêu chính xác kiểm chứng source/frozen/live, không đánh đồng chúng.
- Version/tag/release asset không bị tự thay đổi.
