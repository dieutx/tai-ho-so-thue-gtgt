# Bộ prompt phát triển theo từng lần

Đọc [HANDOFF.md](HANDOFF.md) khi chuyển máy, rồi [REVIEW.md](REVIEW.md) để biết
lỗi đã sửa, kết quả test offline/thật và hạn chế còn lại. Copy
[MASTER.md](prompts/MASTER.md), chọn một STAGE rồi copy prompt tương ứng vào
cùng phiên làm việc. Mỗi stage phải giao code, kiểm thử và tài liệu; không chỉ
trả lời kế hoạch. Cập nhật trạng thái ở đây sau khi hoàn thành.

Stage 01 có phần nền tảng đã làm trong lần rà soát này: legacy trực tiếp, DVC
tạm tắt, summary cho khoảng bỏ qua, sửa dry-run và metadata. Phân loại metadata
cũng đã có. Prompt vẫn yêu cầu đọc code hiện tại và chỉ làm phần thiếu.

Cập nhật 27/09/2026: 297 test/lint/mypy qua; test thật legacy 6/6, chạy lại
không tải lại ZIP, không có request DVC. Các kết quả này **không** có nghĩa
stage 01 hoặc parser GTGT/TNCN/TNDN đã hoàn tất.

| Stage | Kết quả cần có | Phụ thuộc | Prompt | Trạng thái |
|---|---|---|---|---|
| 01 | Tải/resume/auth/config/storage ổn định, không phụ thuộc DVC khi tắt | Baseline hiện tại | [01](prompts/01-stability.md) | Đã làm phần nền tảng; còn hardening trong REVIEW |
| 02 | Inventory file bên trong ZIP, identity/hash/provenance và lệnh offline | 01 | [02](prompts/02-artifacts.md) | Chưa làm |
| 03 | Phân loại từng artifact theo nội dung, mã mẫu/phiên bản, conflict/unknown | 02 | [03](prompts/03-classification.md) | Mới có phân loại metadata cấp hồ sơ |
| 04 | Framework parser và schema output chung có phiên bản | 02–03 | [04](prompts/04-parser-core.md) | Chưa làm |
| 05 | Parser một mẫu GTGT có fixture đại diện | 04 | [05](prompts/05-gtgt.md) | Chưa làm |
| 06 | Parser TNCN, bảng chi tiết/phụ lục được chọn | 04; ưu tiên sau 05 | [06](prompts/06-tncn.md) | Chưa làm |
| 07 | Parser TNDN, phiên bản/phụ lục được chọn | 04; ưu tiên sau 05 | [07](prompts/07-tndn.md) | Chưa làm |
| 08 | Export và truy vấn theo nhóm/kỳ/phiên bản nộp, báo cáo chất lượng | 05; tận dụng 06–07 nếu có | [08](prompts/08-export.md) | Chưa làm |
| 09 | Xác minh adapter DVC, có thể bật lại chủ động, vẫn giữ mặc định tắt | 01; không chặn 02–08 | [09](prompts/09-dvc.md) | Hoãn tới khi cần |

Trật tự chính: 01 → 02 → 03 → 04 → 05 → 06 → 07 → 08. Stage 09 độc lập.
Không làm parser GTGT/TNCN/TNDN đồng loạt trước khi kiểm chứng khung parser với
một mẫu. Không cần GUI ở các stage này; CLI/offline trước, giao diện sau.

Đích dữ liệu, chưa phải schema đang được triển khai:

```text
Case (nguồn, tài khoản, mã hồ sơ, ngày nộp, chính thức/bổ sung)
  └─ Artifact[] (ZIP/member, hash, định dạng, đường dẫn, trạng thái)
       ├─ Classification (nhóm thuế, vai trò, mã mẫu, phiên bản, bằng chứng)
       └─ ParsedDeclaration (parser/version, thông tin chung, chỉ tiêu, phụ lục, lỗi)
```

Nhóm thuế (GTGT/TNCN/TNDN) khác vai trò tài liệu (tờ khai/phụ lục/thông báo),
khác loại lần nộp (chính thức/bổ sung), khác định dạng (XML/PDF/ZIP). Giữ các
chiều này riêng để thêm nhóm mới không phải sửa pipeline tải.

## Lần làm tiếp được đề xuất

Chọn stage 01, đối chiếu REVIEW, chia các mục hardening còn lại thành thay
đổi nhỏ có test: che log/dump chia sẻ, giới hạn ZIP/XML, identity/resume,
config/retry/session. Không viết lại phần legacy/DVC flag đã có. Cập nhật
tiến độ sau mỗi lần; khi stage 01 đạt tiêu chí mới chuyển stage 02.

Ở stage 02 cần kiểm kê và tạo fixture ẩn danh cho các mẫu thực tế, gồm
`04/GTGT`, `02TH`, `BC26/AC` nếu có quyền sử dụng. Không commit raw hồ sơ thật;
không chọn parser `01/GTGT` chỉ vì phổ biến nếu chưa có mẫu đại diện.
