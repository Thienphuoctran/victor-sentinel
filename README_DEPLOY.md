# HƯỚNG DẪN TRIỂN KHAI VICTOR SENTINEL 24/7 TRÊN CLOUD HOÀN TOÀN MIỄN PHÍ
*(Tắt máy tính cá nhân 100% — Victor vẫn trực chiến 24/7 trên mây và bắn tin Telegram)*

Thư mục `cloud_sentinel/` đã được đóng gói sẵn toàn bộ mã nguồn, cấu hình Telegram của bạn (`@Chuyenvienvictor_bot`), và danh mục 22 siêu cổ phiếu đang đầu tư.

---

## 🏆 CÁCH 1: TRIỂN KHAI TRÊN HUGGING FACE SPACES (KHUYÊN DÙNG — 100% MIỄN PHÍ, KHÔNG CẦN THẺ TÍN DỤNG, MẤT 3 PHÚT)

Hugging Face là nền tảng AI lớn nhất thế giới, cung cấp máy chủ đám mây **2 CPU, 16GB RAM Miễn Phí Vĩnh Viễn** để chạy code Python/Docker 24/7 mà không bao giờ hỏi thẻ tín dụng!

### Các Bước Thực Hiện Cực Kỳ Đơn Giản:
1. **Đăng ký tài khoản miễn phí**:
   - Truy cập: [https://huggingface.co/join](https://huggingface.co/join) (Đăng ký bằng email của bạn, mất 30 giây).
2. **Tạo Một Không Gian Mới (New Space)**:
   - Bấm vào ảnh đại diện góc phải ➔ Chọn **`New Space`** (hoặc vào thẳng [https://huggingface.co/new-space](https://huggingface.co/new-space)).
   - **Space name**: Đặt tên bất kỳ, ví dụ: `victor-sentinel-phuoc`
   - **Space SDK**: Chọn **`Docker`** ➔ Chọn **`Blank`**.
   - **Space Hardware**: Giữ mặc định **`CPU basic • 2 vCPU • 16GB • Free`** (Miễn phí 100%).
   - **Visibility**: Chọn **`Private`** (để chỉ một mình bạn xem được và bảo mật danh mục) hoặc **`Public`**.
   - Bấm nút **`Create Space`**.
3. **Tải 5 File Lên**:
   - Trong trang Space vừa tạo, bấm tab **`Files`** ➔ Chọn **`Add file`** ➔ **`Upload files`**.
   - Kéo thả toàn bộ **5 file** trong thư mục `cloud_sentinel/` trên máy tính của bạn lên:
     1. `main.py`
     2. `portfolio_data.json`
     3. `sentinel_config.json`
     4. `requirements.txt`
     5. `Dockerfile`
   - Bấm **`Commit changes to main`**.
4. **HOÀN TẤT**:
   - Hugging Face sẽ tự động cài đặt và khởi động Victor trong 1 phút.
   - Bạn sẽ nhận được 1 đường link trang web Dashboard riêng (ví dụ `https://phuoc-victor-sentinel.hf.space`).
   - Kể từ giờ: **BẠN TẮT HẲN MÁY TÍNH CÁ NHÂN, GẬP LAPTOP ĐI NGỦ**, Victor trên máy chủ đám mây vẫn âm thầm quét mỗi 60 giây và rung chuông Telegram báo động ngay khi có biến!

---

## 🚀 CÁCH 2: TRIỂN KHAI TRÊN RENDER.COM (100% MIỄN PHÍ)

1. Đăng ký tài khoản miễn phí tại [https://render.com](https://render.com) (đăng nhập bằng tài khoản GitHub hoặc Google).
2. Tạo **`New Web Service`** ➔ Kết nối repository hoặc chọn Docker Image.
3. Để giữ Render không bị ngủ sau 15 phút không có người vào:
   - Vào trang [https://cron-job.org](https://cron-job.org) (miễn phí), tạo 1 cron job ping vào link `https://tên-app-của-bạn.onrender.com/health` mỗi 5 phút một lần.

---

## 💻 CÁCH 3: TỰ ĐỘNG CHẠY TRÊN MÁY TÍNH WINDOWS MỖI KHI MỞ MÁY (KHÔNG DÙNG CLOUD)

Nếu bạn chỉ muốn Victor tự động khởi động cùng máy tính Windows mà bạn không cần phải gõ lệnh mỗi ngày:
1. Nhấn tổ hợp phím **`Windows + R`**, gõ: `shell:startup` rồi nhấn Enter (Thư mục Startup tự chạy khi mở máy sẽ hiện ra).
2. Tạo một file shortcut hoặc file `run_victor_auto.bat` với nội dung:
   ```bat
   @echo off
   cd /d "C:\Users\phuoc\Downloads\antigravity\Chứng khoán"
   python scripts\intraday_portfolio_sentinel.py --daemon
   ```
3. Mỗi khi bạn bật máy tính lên làm việc, Victor sẽ tự động chạy ngầm bảo vệ danh mục!
