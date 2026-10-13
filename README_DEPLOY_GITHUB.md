# AI Film Factory V0.3 — GitHub công khai + Studio yêu cầu mật khẩu

> **Điểm cần hiểu rõ:** Public repository trên GitHub không có chế độ "chỉ người có link mới xem". Mã nguồn trong repo là **công khai**. Website do Render chạy có thể yêu cầu mật khẩu: mọi người có thể mở địa chỉ URL, nhưng chỉ người có **đường link VÀ mật khẩu** mới sử dụng được ứng dụng.

## Mô hình triển khai

- **GitHub (Public):** giữ mã nguồn; không chứa dữ liệu phim, database, nhân vật riêng tư, API key hoặc mật khẩu.
- **Render Web Service (HTTPS):** chạy đồng thời giao diện React đã đóng gói + Python FastAPI + SQLite + FFmpeg trên *một domain*, tránh lỗi CORS.
- **Password gate:** đăng nhập bằng `APP_ACCESS_PASSWORD` do người quản lý thiết lập trong Render; cookie HttpOnly, Secure, SameSite Strict có thời hạn 12 giờ, URL /api và /media được bảo vệ.
- **AI hiện ở MOCK MODE:** chỉ dùng ảnh tĩnh mô phỏng, tự chia shot và FFmpeg, không gọi AI có phí.

## Triển khai dễ nhất: Render Blueprint

1. Tại **repository GitHub hiện có**, chọn **Add file → Upload files** rồi tải các file/thư mục **bên trong ZIP V0.3 đã giải nén**, thay thế file cũ. Đảm bảo có `Dockerfile` và `render.yaml` ở **thư mục gốc repository**. Giữ repository **Public** nếu muốn code công khai.
2. Mở [Render](https://dashboard.render.com/) và đăng nhập theo điều kiện của dịch vụ. Tạo **New → Blueprint** và kết nối repository GitHub. Nếu bạn không muốn cấp quyền Render truy cập GitHub, có thể deploy bằng phương án khác tương thích Docker nhưng phải tự cấu hình.
3. Kiểm tra Blueprint đọc `render.yaml` rồi chọn Deploy. Đây là cấu hình **Free để thử nghiệm**, không thu phí dịch vụ theo giờ của gói paid; lưu ý giới hạn free có thể thay đổi.
4. Trong phần Environment, nhập bí mật `APP_ACCESS_PASSWORD` **ít nhất 12 ký tự**, KHÔNG đưa vào GitHub. `APP_SESSION_SECRET` được Render tự sinh từ Blueprint. Nếu được nhắc về biến mật khẩu trong lúc tạo Blueprint, hãy nhập trong giao diện Render.
5. Khi Render báo **Live**, mở URL `https://...onrender.com`. Trang yêu cầu mật khẩu sẽ xuất hiện. Nhập mật khẩu để vào Dashboard / Nhân vật / Storyboard / Node Editor.
6. Bảo đảm chức năng `Create project`, tải ảnh nhân vật, lưu workflow và dựng clip 16 giây hoạt động. Nếu máy chủ miễn phí thiếu tài nguyên khi dựng, hãy thử clip ngắn và không chạy nhiều việc cùng lúc.

**Không sử dụng GitHub Pages cho backend:** GitHub Pages chỉ lưu nội dung tĩnh, không chạy FastAPI, SQLite, FFmpeg. Giao diện và API trong gói này được phục vụ chung bởi Render.

## CẢNH BÁO quan trọng: dữ liệu trên Render Free không bền

Với `render.yaml` (plan `free`), thư mục dữ liệu SQLite và các ảnh tải lên nằm trên filesystem tạm thời, có thể **mất hoàn toàn sau restart/redeploy**. Không lưu phim thật hoặc nội dung khó khôi phục trên plan free.

Khi cần dữ liệu phim lâu dài, sử dụng **paid Render Starter + Persistent Disk** theo `render.persistent.yaml` (đổi tên/chép nội dung thành `render.yaml` trước khi tạo dịch vụ). Đây là phương án có chi phí và bạn phải tự xem giá ở Render trước khi xác nhận. Tệp dùng `sizeGB: 5` cho bản đầu, có thể cần nâng dung lượng khi xuất nhiều video. Bạn cũng nên sao lưu dự án ngoài dịch vụ. Không đổi blueprint trả phí nếu chưa đồng ý chi phí.

## Giữ bảo mật

- Không commit file `.env`, API key, mật khẩu, ảnh nhân vật riêng, video/MP4, database, token.
- Bản V0.3 không chứa ảnh Mai/Tuấn trong repo công khai; bạn đăng nhập website rồi tải các ảnh đó lên phần **Nhân vật**. Đối với Render Free, ảnh tải lên cũng có thể mất nếu máy chủ khởi động lại.
- Mật khẩu nên là chuỗi ngẫu nhiên độc lập; gửi riêng qua kênh an toàn cho người cộng tác, không đặt trong URL.
- Không dùng mật khẩu chung của những dịch vụ khác. Nên thay mật khẩu nếu bị lộ; thay password sẽ vô hiệu hóa cookie cũ sau khi service tải lại cấu hình.
- Các giới hạn đăng nhập trong RAM chỉ phù hợp MVP một người dùng; khi mở rộng nhiều người cần giải pháp tài khoản từng người, rate limiting tập trung, audit log và lưu trữ riêng.
- Website có thể bị tìm ra qua link được chia sẻ, log hoặc công cụ tìm kiếm. `robots.txt`/noindex chỉ giảm khả năng lập chỉ mục, **không thay thế đăng nhập**.

## Chạy trên Windows nội bộ

`START_WINDOWS.bat` vẫn hoạt động như V0.2 (localhost không cần mật khẩu theo mặc định). Không expose cổng này trực tiếp ra Internet. Để kiểm tra đăng nhập cục bộ, đặt các biến `APP_REQUIRE_AUTH=1`, `APP_ACCESS_PASSWORD` và `APP_SESSION_SECRET` trước khi khởi chạy.

## Kiểm thử

```bash
pip install -r requirements.txt httpx
python tests/test_studio.py
APP_MODE=production APP_ACCESS_PASSWORD='example-strong-password-123' APP_SESSION_SECRET='example-super-secret-for-tests-only-123456789' python tests/test_security.py
```

Trong Windows PowerShell, đặt các biến môi trường với `$env:APP_MODE="production"` etc. Không dùng các secret ví dụ khi triển khai thật.

## Giới hạn của V0.3

- Không tự kết nối TobyFlow, Google Flow, Dolai.video hoặc mô hình trả phí; chưa có giọng nói tiếng Việt tự động.
- Không có đăng ký nhiều người; một mật khẩu chung truy cập tất cả dự án.
- Dựng MP4 tốn CPU/RAM và đĩa: chỉ thử preview ngắn trên dịch vụ miễn phí.
- Không có sao lưu tự động, cần giải pháp lưu bền trước khi lưu dự án thật.
