# AI Film Factory — Web Studio V0.3

**Mục tiêu:** Quản lý cốt truyện, storyboard, nhân vật, node workflow và mô phỏng MP4.

## Từ GitHub công khai đến website có mật khẩu

1. Mã nguồn trong **repository Public là công khai**. Không có chế độ GitHub Public "chỉ người có link mới xem".
2. Website được chạy trên **Render** qua HTTPS và yêu cầu mật khẩu trước khi mở Dashboard, API, ảnh và video.
3. Cách thiết lập chi tiết trong **[README_DEPLOY_GITHUB.md](README_DEPLOY_GITHUB.md)**.
4. Không có mật khẩu nào được đưa vào repo. `APP_ACCESS_PASSWORD` do chủ dự án nhập trong Render.

**Cài và chạy nội bộ Windows:** giải nén và chạy `START_WINDOWS.bat`, sau đó mở `http://127.0.0.1:8765`.

### V0.3 làm được
- Tạo dự án từ cốt truyện, lập ~60 shot cho 8 phút và chỉnh sửa storyboard.
- Quản lý kho nhân vật, thêm ảnh, sửa hồ sơ.
- Kéo thả/nối node, lưu workflow và kiểm tra vòng lặp.
- Chạy mô phỏng tạo ảnh storyboard và xuất MP4/SRT bằng FFmpeg.
- Đăng nhập bằng mật khẩu (khi triển khai online), bảo vệ `/api/*` và `/media/*`.
- Cấu hình Docker/Render và bài kiểm thử trên GitHub Actions.

### Giới hạn chưa triển khai
- Chưa tự kết nối mô hình tạo ảnh/video trả phí, Google Flow/TobyFlow hay AI lồng tiếng Việt.
- Clip mô phỏng là ảnh tĩnh và phụ đề, không phải phim AI chuyển động.
- Render Free **không lưu bền** tệp SQLite/ảnh/video; dùng để xem thử, không lưu dự án quan trọng.
- Repo công khai không đi kèm ảnh riêng của Mai/Tuấn; hãy tải lên qua giao diện sau khi đăng nhập hoặc sử dụng bản cục bộ V0.2 đã có ảnh.

### Kiểm thử backend

```bash
pip install -r requirements.txt httpx
python tests/test_studio.py
```

Chạy kiểm thử bảo mật với các biến môi trường như hướng dẫn trong README triển khai.
