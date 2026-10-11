# Bài giới thiệu cho cộng đồng Giải Pháp Excel

## Tiêu đề gợi ý

Chia sẻ công cụ tải tờ khai thuế từ Dịch vụ công và Thuế điện tử, xuất danh sách CSV mở bằng Excel

## Nội dung có thể đăng

Chào các anh/chị trong cộng đồng Giải Pháp Excel! Mình xin chia sẻ một công
cụ Python giúp tra cứu và tải hàng loạt tờ khai, hồ sơ thuế theo khoảng ngày,
giảm thao tác tải từng hồ sơ thủ công. Công cụ tự chia nhỏ khoảng tra cứu,
nhận dạng CAPTCHA, duyệt các trang kết quả, đặt tên file dễ nhận biết và bỏ
qua ZIP hợp lệ đã tải để có thể chạy tiếp khi bị gián đoạn. Danh sách hồ sơ
được xuất ra CSV/JSON; file CSV dùng UTF-8 BOM nên mở thuận tiện trong Excel.

Phiên bản hiện tại ưu tiên cổng Thuế điện tử cũ (`thuedientu.gdt.gov.vn`) cho
ngày trước mốc 01/07/2025. Tra cứu trên Dịch vụ công (`dichvucong.gdt.gov.vn`)
đang tạm tắt mặc định, giữ adapter để kiểm chứng và mở lại khi cần. Phần phân
nhóm GTGT/TNCN/TNDN mới dựa trên metadata; phân loại từng file và đọc chỉ tiêu
XML của từng mẫu tờ khai là hướng phát triển tiếp theo, chưa phải tính năng
đã hoàn thiện.

Công cụ chạy bằng dòng lệnh trên Windows/Linux/macOS, cần Python 3.10 trở
lên; không phải add-in Excel hay phần mềm của cơ quan thuế. Chỉ sử dụng với
tài khoản và dữ liệu mình có quyền truy cập; tài khoản, mật khẩu và hồ sơ
tải về được giữ riêng, không đưa lên repository. README có hướng dẫn cài
đặt, sử dụng và cấu hình. Rất mong nhận được góp ý về quy trình kế toán thực
tế hoặc các mẫu báo cáo cần xuất sang Excel; khi báo lỗi xin chỉ dùng dữ liệu
đã ẩn danh, không gửi mã hồ sơ, mật khẩu hay tệp thuế thật.

Mã nguồn và hướng dẫn: [tai-ho-so-thue-gtgt trên GitLab](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt).

## Mô tả dự án ngắn

Tải tờ khai thuế từ Dịch vụ công và Thuế điện tử bằng Python: tra cứu theo
khoảng ngày, tải ZIP, xuất metadata CSV/JSON và phân nhóm hồ sơ. Hiện ưu tiên
legacy trước cutoff; DVC tạm tắt mặc định. Có thể mở CSV bằng Excel.

## Trước khi đăng

Chỉ đăng sau khi repo đã thực sự public và kiểm tra link bằng phiên không
đăng nhập. Không đính kèm ảnh màn hình/log/output chứa dữ liệu tài khoản thật.
Không khẳng định hỗ trợ parser XML hoặc DVC hiện tại khi chưa kiểm chứng.
