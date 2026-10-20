# Phụ lục — phần DVC thông báo chưa commit

Phụ lục này bổ sung cho [REPORT.md](REPORT.md), **không thay baseline commit của 26 ticket**. Khi tiếp tục lượt review, workspace đã có thay đổi DVC/thông báo và UI mới. Đã đọc phần core mới, diff tích hợp pipeline/portal và diff UI liên quan; đã copy source sang snapshot riêng trước khi chạy kiểm tra.

Source chưa có commit ổn định. [WORKTREE_EVIDENCE.json](WORKTREE_EVIDENCE.json) ghi **SHA-256 từng file và vị trí định nghĩa**, để không gán kết quả này cho một bản code khác. Các thay đổi ở workspace vẫn được giữ nguyên, không sửa để làm test xanh.

## Phạm vi bổ sung

- `gdt_tax/dvc_notices.py`: parse modal, phân nhóm tên thông báo, decode response, tên tệp và NoticeStore.
- `gdt_tax/pipeline.py`: gọi tải thông báo sau khi tải/reuse ZIP.
- `gdt_tax/portals/dvc.py` và `base.py`: giữ detail HTML, đọc danh sách và gửi request tải thông báo.
- `desktop/main.py`: cơ chế crash log mới; diff chọn dòng/proxy trong desktop chỉ được đọc, chưa kiểm chứng tương tác hoặc nguyên nhân native crash.
- `tests/test_dvc_notices.py`: **9 test hiện có đạt** trên snapshot cô lập. Đây không phải toàn bộ suite của worktree mới.

Không gọi cổng, không đọc credential và không dùng dữ liệu thuế thực. Bốn ca W01–W04 dùng dữ liệu tự tạo; script có chặn kết nối socket. Chúng là quan sát hiện trạng, chưa phải regression tests sau bản vá.

## Các phát hiện và cách giao PR

| Ca | Quan sát trên snapshot | Hướng xử lý / ticket |
|---|---|---|
| W01 | JSON khai `fileType=xml`, base64 chứa HTML lỗi vẫn tạo NoticeFile, extension `xml` | CORE-13, CORE-15: validate nội dung và trần decode/HTTP, không tin phần mở rộng hoặc khai báo từ server |
| W02 | `NoticeFile(data=b'x', file_type='xml')` vẫn save; lần sau `find_existing` nhận lại vì tệp không rỗng | CORE-13: cùng validator cho decode/save/resume; hash, size và integrity status rõ |
| W03 | Hai thông báo có cùng ID nhưng khác `is_tdt` nhận cùng tệp khi lookup | CORE-03: key phải giữ source/route dimension xuyên parse/store/resume |
| W04 | Hai ZIP tải thành công; cả hai request tải thông báo trả HTTP 500; primary summary vẫn complete, không có field/counter lỗi thông báo | CORE-01, CORE-17: tách completeness của primary và attachment; giữ ZIP thành công nhưng thể hiện rõ phần thông báo chưa đủ |

### W01/W02 — nội dung và resume

`decode_notice_response` kiểm base64 và kích thước nhưng chưa kiểm document kind thực. Với nhánh JSON, bất kỳ bytes không rỗng dưới trần đều có thể được nhận. Với nhánh binary, prefix `<` chưa phân biệt XML thông báo với HTML trang lỗi. `NoticeStore.save` ghi trực tiếp payload; `find_existing` chỉ xét file không rỗng.

**PR bổ sung cho CORE-13:** dùng chung validator theo kind, không định nghĩa một validator yếu mới cho attachment. File hỏng đã có phải được báo cần tải lại/quarantine theo policy, không xóa tự động. Trần dung lượng cần áp trước khi tạo nhiều bản sao chuỗi/base64/bytes (CORE-15).

**Nghiệm thu riêng:** HTML khai XML, base64 text tùy ý, XML lỗi cú pháp, PDF cụt và tệp một byte không được báo attachment downloaded. Tệp cũ hợp lệ vẫn reuse được. Không chuyển lỗi attachment thành mất ZIP đã hoàn thành.

### W03 — identity mất chiều nguồn

`parse_notices` đã deduplicate bằng `tdt/dvc + id`, nhưng storage lookup chỉ nhận `case_id, notice_id`. Thông tin phân biệt nguồn bị mất ở biên lưu trữ. Phép thử không chứng minh cổng thật đang trả hai ID trùng nhau; nó chứng minh giả định ID toàn cục chưa được bảo vệ.

**PR bổ sung cho CORE-03:** `NoticeKey` có account/parent record key, route/source, remote notice ID và chiều `loai_tra_cuu/loai_tbao` nếu cổng xác định uniqueness theo các trường này. Kiểm chứng contract trước khi chọn key. Remote ID gửi cổng phải giữ nguyên.

**Nghiệm thu riêng:** cùng ID trên hai route không skip nhau; title thay đổi không sinh một bản ghi identity mới; dữ liệu/tệp cũ có migration không đoán source hoặc xóa file.

### W04 — kết quả primary và attachment cần độc lập

Code mới chủ đích coi lỗi thông báo là warning để giữ kết quả ZIP. Đây là lựa chọn có ích cho dữ liệu đã tải, nhưng summary/counters chưa thể hiện “ZIP đủ, thông báo thiếu”. Không được sửa bằng cách đánh dấu mọi ZIP thất bại khi một attachment lỗi.

**PR bổ sung cho CORE-17:** thêm kết quả attachment riêng: discovered/downloaded/reused/failed/skipped, danh sách notice key và error code, retryability, source hash/path; nối vào JobResult/report và lựa chọn thử lại. CORE-01 định nghĩa completeness cho bundle nếu người dùng yêu cầu tải kèm thông báo.

**Nghiệm thu riêng:** lỗi 500, mất CSRF, modal chưa hiểu, failure khi save và session expired đều có summary rõ; primary file giữ nguyên, retry chỉ attachment còn thiếu. Phân biệt `no notices confirmed` với `cannot parse notices`.

## Nhận xét đọc code chưa có phép thử riêng

1. **CORE-16 — crash log:** `desktop.main._install_crash_log` ghi `traceback.format_exception` trực tiếp vào log. Exception text có thể chứa URL/token hoặc dữ liệu đầu vào; kênh này không đi qua Redactor hiện có. Cần xem crash log là dữ liệu private, thêm rotation/retention và sanitize khi xuất support bundle. Chưa gây crash hoặc ghi exception chứa dữ liệu thật để thử.
2. **CORE-26 — phân loại tiêu đề:** `DvcNotice.loai` nhóm cả “xác nhận” vào `chap-nhan`. Đây là heuristic để nhóm/tên tệp, chưa phải bằng chứng hồ sơ được chấp nhận về nghiệp vụ. Cần giữ raw title, classification basis/confidence và không đưa heuristic thành acceptance status cuối cùng.
3. **CORE-01/22 — modal và handler:** khi thiếu `#modalThongBao`, parser quét toàn trang; danh sách rỗng chưa có chứng cứ phân biệt không có thông báo với markup đã đổi. Thêm contract tests cho modal mất/đổi, nhiều modal và link tải ngoài scope.
4. **CORE-19 — lớp lỗi:** helper attachment chỉ bắt NetworkError; access verification/session/auth/schema errors cần đi qua outcome policy chung. Không nên bắt mọi Exception để nuốt lỗi, cũng không để lỗi phụ làm mất trạng thái ZIP đã lưu.

Các nhận xét này không xác nhận thay đổi UI đã sửa tận gốc native crash. Cần bài kiểm tra Windows riêng nếu giao nhiệm vụ đó.

## Chạy lại trên snapshot tương ứng

```powershell
.venv-release-1.1/Scripts/python.exe docs/core-review-20261020/reproduce_worktree_addendum.py --source-root <thu-muc-source-snapshot>
```

Sau khi source được commit hoặc thay đổi, so SHA-256 trong `WORKTREE_EVIDENCE.json` trước khi đối chiếu kết quả. Agent nhận CORE-03/13/15/16/17/19/26 cần đọc phụ lục này ngoài ticket baseline, tránh làm một bản sửa chỉ phủ đường cũ.
