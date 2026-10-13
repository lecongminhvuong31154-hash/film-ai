# Hướng dẫn nâng cấp từ V0.3 lên V0.4 trên GitHub + Render

## 1. Cập nhật GitHub

1. **Sao lưu dữ liệu đang dùng:** nếu Render Free còn dữ liệu, tải `shots.json` và các file cần giữ trước khi deploy.
2. Giải nén `AI_Film_Factory_V04_GitHub_Render_Ready.zip`.
3. Vào GitHub repository `film-ai` → nhánh `main`.
4. Tải **các thư mục và file bên trong ZIP** lên đúng thư mục gốc, ghi đè bản V0.3. Giữ nguyên tên `Dockerfile`, `render.yaml`, `backend/`, `frontend/`.
5. Commit thay đổi. Có thể dùng GitHub Desktop hoặc `git add . && git commit -m "Upgrade AI Film Factory to V0.4" && git push`.
6. GitHub không lưu thư mục rỗng: `Dockerfile` V0.4 đã sử dụng `RUN mkdir -p /app/assets` thay vì `COPY assets ./assets`, tránh lỗi triển khai V0.3.

**Không tải lên:** `.env`, mật khẩu, API key, `runtime_data/`, ảnh dự án riêng tư, `.venv/`, `node_modules/`, file SQLite.

## 2. Triển khai Render

- Giữ nguyên dịch vụ `ai-film-factory-studio` hiện tại, không cần tạo dịch vụ mới.
- Render cấu hình Blueprint `main` thường tự deploy sau commit.
- Nếu chưa tự chạy: Render → dịch vụ → Manual Deploy → Deploy latest commit.
- Đọc Logs nếu có lỗi; chờ trạng thái `Live` rồi mở URL Render đã cấp.
- Địa chỉ hiện dùng: `https://ai-film-factory-studio.onrender.com` (chỉ hoạt động sau khi deploy Live).
- Trình duyệt đôi khi giữ tài nguyên cũ: nhấn Ctrl+Shift+R để làm mới.

## 3. Dùng thử không cần API key

Tổng quan → nhập cốt truyện → tạo dự án (bản nháp miễn phí) → tab **Kịch bản**. Trạng thái sẽ ghi `Chưa kết nối API` và không tự phát sinh chi phí. Vào **Nhân vật** để thêm ảnh của phim mới, và **Node Editor** / **Mô phỏng & file** để kiểm tra chức năng cũ.

## 4. Bật AI biên kịch thật (tùy chọn)

**Chỉ áp dụng nếu tài khoản và người sử dụng đủ điều kiện sử dụng API của nhà cung cấp.** OpenAI API là dịch vụ tính phí token độc lập với việc sử dụng website hoặc ChatGPT thông thường.

- Vào Render → web service `ai-film-factory-studio` → **Environment**.
- Thêm `OPENAI_API_KEY` = khóa API riêng của bạn. Không gửi khóa qua chat, không ghi vào repo Public.
- Có thể thêm `AI_WRITER_MODEL` = tên mô hình được API hỗ trợ; mặc định `gpt-4.1-mini`.
- Có thể thêm `AI_WRITER_MAX_CALLS` = `12` cho thử nghiệm giới hạn số nhóm gọi API; nếu phim 8 phút cần 9 calls, giá trị nhỏ hơn sẽ chặn trước khi gọi.
- Lưu để Render restart; vào tab **Kịch bản** kiểm tra `API đã cấu hình`.
- Lưu cốt truyện, bấm **Viết storyboard bằng AI thật** và xác nhận. Theo dõi tiến độ. Nếu gặp lỗi, bản storyboard cũ không bị ghi đè.
- Duyệt từng shot, sau đó bấm **Duyệt kịch bản AI**. Trạng thái `approved` chỉ có nghĩa là kịch bản được duyệt; chưa tạo video bằng AI thật.

**Chi phí:** một phim 8 phút / 60 shot thường cần 1 yêu cầu dàn ý + 8 yêu cầu phân cảnh, tối đa số lần bị cấu hình giới hạn. Mỗi yêu cầu có giới hạn đầu ra; phí tùy model, số token thực tế. V0.4 chưa đo hoặc giới hạn được tổng tiền USD, nên nên kiểm tra hạn mức API bên nhà cung cấp trước khi bấm.

## 5. Giới hạn kiến trúc hiện tại

- Blueprint Render `plan: free`. Dữ liệu máy chủ **không bền vững**; deploy/restart có thể xóa toàn bộ bản đã lưu. Không lưu nội dung quan trọng nếu chưa bật persistent storage.
- `SQLite` + Render Free chỉ phù hợp chạy thử cho một người. Muốn làm bản sản xuất cần thay bằng DB và storage bền vững.
- Node Editor chỉ mô phỏng, không điều khiển TobyFlow.
- FFmpeg xuất clip ảnh tĩnh, không tạo video chuyển động hoặc giọng Việt.
- Người dùng phải có quyền đối với hình ảnh/giọng nói/tài nguyên được đưa vào hệ thống.

## 6. Xử lý lỗi

- `AI chưa kết nối`: chưa thêm `OPENAI_API_KEY`; đây là trạng thái bình thường nếu chỉ dùng mock.
- `401`/`403` ở AI: key sai hoặc tài khoản không được cấp quyền; kiểm tra API trực tiếp với nhà cung cấp.
- `429`: chạm giới hạn API; dừng và kiểm tra hạn mức.
- `Lỗi JSON`: AI trả sai cấu trúc. Hệ thống giữ storyboard cũ; có thể thử lại sau khi kiểm tra hạn mức.
- `Failed deploy`: Render → service → Logs để lấy dòng `ERROR`; không tạo lại dịch vụ khi chưa biết lỗi.
- Dữ liệu mất sau khi Render restart: đây là giới hạn Render Free, không phải dữ liệu đã được lưu lâu dài.
