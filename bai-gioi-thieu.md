Chào các bác,

Em vừa viết một công cụ nhỏ bằng Python để tự động tải hồ sơ thuế GTGT từ Cổng Dịch vụ công của Cục Thuế, chia sẻ lên diễn đàn cho ai cần.

**Vấn đề:** Cổng thuế chỉ cho tra cứu tối đa 31 ngày mỗi lần, phải nhập CAPTCHA khi đăng nhập, và tải từng hồ sơ một. Nếu cần lấy hồ sơ cả năm thì thao tác tay rất mất thời gian.

**Công cụ tự động:**
- Cắt khoảng ngày dài thành các đoạn ≤ 31 ngày
- Tự đọc CAPTCHA (dùng ddddocr, đọc đúng 6/6 lần, 0.06s/ảnh)
- Duyệt hết các trang tra cứu, tải ZIP ngay trên từng trang
- Tự phân loại hồ sơ theo loại tờ khai (GTGT, TNCN, TNDN...)
- Lưu kèm file CSV/JSON chứa metadata đầy đủ
- Bỏ qua hồ sơ đã tải nên chạy lại không bị tải trùng
- Gửi request giống Chrome nên không bị nhận diện là bot

**Lưu ý:**
- Chỉ dùng với tài khoản thuế mà mình có quyền truy cập
- Cổng chỉ phục vụ IP Việt Nam, nếu chạy trên VPS nước ngoài cần dùng proxy VN
- Hiện chỉ hỗ trợ hồ sơ trước 01/07/2025 (legacy), phần Cổng Dịch vụ công đang tạm tắt

Repo: https://gitlab.com/dieutx/tai-ho-so-thue-gtgt (MIT)

Ai dùng có vấn đề gì cứ bình luận nhé, em sẽ hỗ trợ. Cảm ơn các bác!
