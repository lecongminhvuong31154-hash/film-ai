# AI Film Factory — Web Studio V0.4

Website quản lý phim AI theo từng dự án, chạy bằng React (giao diện) và FastAPI (máy chủ). **Đây không phải công cụ tạo video AI thật**; FFmpeg chỉ tạo video mô phỏng. V0.4 bổ sung **AI Script Writer tùy chọn** và **thư viện nhân vật riêng cho từng bộ phim**.

## V0.4 có gì mới?

- **Biên kịch AI (tùy chọn):** Nhận một cốt truyện → dàn ý 8 nhịp → toàn bộ shot (8 giây/shot), góc máy, bối cảnh, hành động, lời thoại tiếng Việt, prompt ảnh/video tiếng Anh. Viết theo nhóm 8 shot, kiểm tra tổng thời lượng trước khi lưu.
- **Không giả vờ có AI:** Nếu không có `OPENAI_API_KEY`, nút AI Writer bị khóa và cho biết thiếu gì. Storyboard miễn phí ban đầu vẫn dùng thuật toán mô phỏng.
- **Chỉ chạy AI theo yêu cầu:** Không tự gọi API khi mở website, tạo dự án, tải trang hay chạy FFmpeg. Người dùng cần bấm nút và xác nhận chi phí token. Không thống kê chi phí API trong bản này.
- **Duyệt kịch bản:** AI hoàn thành → `ai_draft` → người dùng kiểm tra nội dung trong Storyboard → bấm `Duyệt kịch bản AI`. Video vẫn chưa được sản xuất bằng AI thật.
- **Nhân vật riêng cho từng phim:** ảnh, vai trò, giọng và trang phục lưu trong `runtime_data/projects/{project_id}/characters/`. Phim mới không tự lấy nhân vật Mai/Tuấn từ phim cũ. Dự án V0.3 được di chuyển tự động khi mở bằng V0.4.
- **Sao lưu dự án:** Nút `Sao lưu phim ZIP` xuất thông tin dự án, JSON, ảnh tham chiếu đã tải lên và các clip mô phỏng; cần tải về trước khi Render Free restart.
- **Node Editor**, mô phỏng **FFmpeg MP4/SRT**, bảo vệ bằng mật khẩu và triển khai **GitHub → Render** vẫn được giữ lại.

## Bản phát hành có hai giao diện

- `frontend/dist/`: giao diện React đã đóng gói, dùng trực tiếp trên Render, không cần npm. Editor kéo-thả tương thích chạy offline và **không phải** thư viện React Flow chính thức.
- `frontend/src/`: mã nguồn React dùng `@xyflow/react` chính thức khi xây lại bằng `npm install && npm run build`; lúc đó ghi đè `frontend/dist/`.

## Triển khai

Đọc [README_DEPLOY_GITHUB.md](README_DEPLOY_GITHUB.md). `Dockerfile` và `render.yaml` ở thư mục gốc. Khi cập nhật từ V0.3, giữ nguyên mật khẩu cũ trên Render, không đưa secret lên GitHub.

## Về bảo mật và dữ liệu

- GitHub `Public` luôn công khai mã nguồn. Trang web tách riêng, có lớp đăng nhập.
- Khóa `OPENAI_API_KEY` chỉ cấu hình trong Render → Environment; tuyệt đối không ghi vào `.env` đưa lên GitHub.
- **Render Free không lưu bền vững** SQLite, ảnh, kịch bản và video khi restart/redeploy. Chỉ dùng bản thử nghiệm; muốn lưu lâu dài phải dùng persistent disk hoặc DB/storage bền vững.
- Khuyến nghị sao lưu `shots.json` và ảnh nhân vật trước khi triển khai lại.
- Không có tích hợp trực tiếp TobyFlow, Google Flow, Kling, Dola hoặc ElevenLabs trong V0.4.
- Mô hình OpenAI mặc định `gpt-4.1-mini`, có thể điều chỉnh bằng `AI_WRITER_MODEL` tùy quyền API và mô hình hỗ trợ trong tài khoản.

## Thử nhanh API trên máy cá nhân

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn backend.main:app --host 127.0.0.1 --port 8765
```

Mở `http://127.0.0.1:8765` (chỉ trên máy cục bộ). Nếu muốn chạy AI Writer ở máy riêng, cấu hình biến môi trường `OPENAI_API_KEY` trong terminal **mà không ghi khóa vào mã nguồn**.

## Kiểm thử không tốn token

```bash
python tests/test_studio.py
python tests/test_v04.py
```

Kiểm thử bảo mật (dùng secret kiểm thử, không dùng với website thật):

```bash
APP_MODE=production APP_ACCESS_PASSWORD='replace_with_very_long_test_password' APP_SESSION_SECRET='replace_with_random_secret_minimum_32_chars' python tests/test_security.py
```

Bộ kiểm thử AI Writer dùng nhà cung cấp **giả lập trong bộ nhớ**, không gửi nội dung ra Internet.
