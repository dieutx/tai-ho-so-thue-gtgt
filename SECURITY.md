# Chính sách bảo mật

## Phạm vi hỗ trợ

Các bản sửa bảo mật được áp dụng cho nhánh `main`. Dự án hiện chưa cam kết
bảo trì các phiên bản cũ. Không dùng công cụ cho tài khoản/hồ sơ ngoài quyền
truy cập của bạn; đây không phải sản phẩm của cơ quan thuế.

## Báo cáo riêng tư

Không đăng credentials, cookie/token, mã số thuế, mã hồ sơ, XML/ZIP thuế hoặc
raw log/dump lên issue/MR công khai. Nếu phát hiện lỗ hổng hoặc dữ liệu bị lộ:

1. Liên hệ maintainer qua GitLab; dùng **confidential issue** nếu tài khoản
   của bạn có quyền tạo loại issue này. Kiểm tra trạng thái confidential trước
   khi gửi; nếu không có kênh riêng, chỉ hỏi cách liên hệ, không mô tả dữ liệu nhạy cảm.
2. Cung cấp phiên bản, module/vị trí, tác động và cách tái hiện bằng dữ liệu
   dummy. Không gửi secret thật, kể cả để chứng minh lỗ hổng.
3. Không khai thác tài khoản khác. Phối hợp thời điểm công bố sau khi có bản
   sửa; dự án không hứa SLA hoặc chương trình bug bounty.

## Giữ dữ liệu trên máy của bạn

- `.env`, output tải về, log/dump, venv/cache và backup Git phải nằm ngoài
  nội dung commit. Gitignore không xóa file đã từng được commit.
- CSV/JSON chứa dữ liệu thuế cũng là riêng tư, dù không có mật khẩu.
- Chỉ dùng mã synthetic `DEMO-*` trong fixture, CLI example và tên ZIP minh họa.
- Bộ che log chưa bảo đảm che mọi URL/Referer/HTML/XML; raw dump không an toàn
  để chia sẻ. Bỏ cả ID, thời điểm, địa điểm và trường có thể liên kết người nộp.
- Nếu secret đã lộ, thu hồi/đổi secret trước; xóa một commit không vô hiệu hóa secret.

## Kiểm tra trước public hoặc merge

CI (`.gitlab-ci.yml`) chạy test offline và lint:

```bash
python -m unittest discover -s tests -t .
ruff check .
mypy gdt_tax
```

Trước khi public hoặc merge, tự kiểm thêm:

```bash
# Quét lịch sử Git để tìm secret đã lỡ commit (nếu có gitleaks)
gitleaks git . --log-opts="--all" --redact=100 --no-banner
# Liệt kê file riêng tư lọt vào cây làm việc
git ls-files | grep -E '(\.env$|\.zip$|\.log$|^download/|^logs/|^http-dump/|^repo-tam/)' \
  && echo "CẢNH BÁO: có file riêng tư trong repo"
```

Các công cụ này có giới hạn và false positive, không quét hết mọi dạng ID thuế,
và **không** thay thế review thủ công hay là chứng nhận bảo mật. Không tắt rule
hoặc bỏ qua toàn bộ fixture chỉ để lấy điểm cao.

Làm lại một commit không đảm bảo dữ liệu cũ đã mất khỏi cache GitLab,
merge request refs, pipeline logs/artifacts, fork hoặc clone ở nơi khác.
Trước khi chuyển public, maintainer phải xử lý các nguồn đó, kiểm tra không
còn nhánh/tag cũ và xác minh truy cập bằng người chưa đăng nhập. Xem
[hướng dẫn GitLab về xóa dữ liệu nhạy cảm](https://docs.gitlab.com/user/project/repository/repository_size/#remove-data-from-a-repository).

Nếu chưa có quyền thực hiện hoặc chưa kiểm chứng cleanup trên máy chủ,
giữ repo private. Không mô tả điểm scanner là chứng nhận bảo mật.
