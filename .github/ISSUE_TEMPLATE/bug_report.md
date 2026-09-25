---
name: Báo lỗi
about: Công cụ chạy sai, treo, hoặc cổng thuế đổi giao diện
title: "[Lỗi] "
labels: bug
---

## Hiện tượng

<!-- Bạn mong đợi điều gì, thực tế xảy ra điều gì. -->

## Lệnh đã chạy

```
python -m gdt_tax --from-date ... --to-date ...
```

## Log

<!--
Chạy lại kèm --log-file để có log đầy đủ (mức DEBUG, gồm header/body của từng
request). Mật khẩu, Cookie, CSRF, matKhau đã được che bằng *** tự động:

    python -m gdt_tax --from-date ... --to-date ... --log-file logs/run.log --dump-http http-dump

Đính kèm file log; nếu cổng đổi giao diện thì đính kèm thêm file
`*.response.txt` liên quan trong `http-dump/`. Nhớ che mã số thuế, mã hồ sơ và
mọi thông tin của bạn trước khi dán — log không tự che phần nội dung HTML.
-->

## Môi trường

- Hệ điều hành:
- Phiên bản Python:
- Bộ nhận dạng CAPTCHA (`GDT_CAPTCHA_SOLVER`):
- Profile header (`GDT_HEADER_PROFILE`, mặc định `browser`):
- Có dùng proxy không (`GDT_PROXY_URL`), dạng `http` hay `socks`:
  <!-- Chỉ cần nói có/không. ĐỪNG dán chuỗi proxy kèm tài khoản/mật khẩu. -->
- Địa chỉ IP mà cổng nhìn thấy (`curl -x <proxy> https://ipinfo.io/json`):
