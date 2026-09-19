# 🚀 VNStock-TradingBot-247: Hệ Thống Auto-Trading & Quét Dòng Tiền Lớn 24/7 (Multi-Agent AI x Telegram)

> **Hệ thống Bot Giao Dịch & Đầu Tư Tự Động 24/7 dành riêng cho Thị trường Chứng khoán Việt Nam (HOSE / HNX / UPCoM).**  
> Tích hợp thuật toán nhận diện Dòng tiền Cá mập (Smart Money Inflow), mô hình trí tuệ nhân tạo Multi-Agent (Google Gemini), quản lý danh mục tuân thủ luật T+2.5 và tương tác 2 chiều qua Telegram Bot.

---

## 🌟 Tính Năng Nổi Bật

### 1. 🌊 Quét Dòng Tiền Cá Mập (Smart Money Scanner) Real-Time
- Tự động giám sát toàn bộ rổ **VN30** và hơn **50 cổ phiếu Midcap dẫn sóng** (Thép, Chứng khoán, Bất động sản, Ngân hàng, Bán lẻ...).
- Phát hiện đột biến khối lượng: $Volume \ge 1.5x - 3.0x$ bình quân 20 phiên ($MA20_{vol}$).
- Lọc điều kiện bùng nổ giá: Tăng mạnh từ $+1.5\%$ đến trần $+7\%$, vượt kháng cự ngắn hạn EMA10 / MA50.
- Tự động bắn cảnh báo khẩn cấp về Telegram kèm giá khuyến nghị, mục tiêu chốt lời và điểm cắt lỗ.

### 2. 🧠 Phân Tích Kỹ Thuật, Cơ Bản & Báo Chí (Multi-Agent AI)
- Gõ thẳng tên mã cổ phiếu (ví dụ: `HPG`, `FPT`, `SSI`) trên Telegram để nhận ngay báo cáo phân tích toàn diện.
- Tự động tổng hợp chỉ số tài chính P/E, P/B, EPS, xu hướng kỹ thuật ngắn hạn.
- Tích hợp bộ cào tin tức báo chí tài chính Việt Nam (CafeF, Vietstock, VnEconomy, 24hmoney) để đánh giá tâm lý thị trường.

### 3. 💼 Quản Lý Danh Mục Đầu Tư Tự Động (Dual-Portfolio Engine)
- **Danh mục Lướt sóng (Short-term Trading):**
  - Tuân thủ nghiêm ngặt **chu kỳ thanh toán T+2.5** của thị trường Việt Nam (không cho phép bán non trước ngày T+2.5).
  - Tự động cắt lỗ dứt khoát khi vi phạm ngưỡng **Stop Loss -5%**.
  - Tự động kích hoạt chốt lời từng phần khi chạm mục tiêu **Take Profit +12% đến +18%**.
- **Danh mục Tích sản (Long-term Investment):**
  - Quản lý vị thế mua gom cổ phiếu cơ bản tốt, định giá thấp, không bị ép cắt lỗ ngắn hạn.
- **Tính toán chi tiết Phí & Thuế:** Khấu trừ phí giao dịch (0.15%) và thuế thu nhập chứng khoán (0.10%) theo chuẩn Bộ Tài Chính.

### 4. ⏰ Vận Hành 24/7 Tự Động Hóa Hoàn Toàn (Trading Scheduler)
- **Trong phiên (Thứ 2 - Thứ 6, 09:15 - 11:30 & 13:00 - 14:45):** Quét dòng tiền định kỳ mỗi 15 phút, phát hiện điểm nổ vol và kiểm tra trạng thái SL/TP danh mục.
- **Kết phiên (15:15):** Gửi báo cáo tổng kết thị trường, tổng tài sản, lãi/lỗ trong ngày về Telegram.
- **Buổi tối (20:00):** Tự động phân tích chuyên sâu mã cổ phiếu hút tiền mạnh nhất hôm nay để chuẩn bị kế hoạch giải ngân cho phiên sáng mai.
- **Cơ chế Watchdog:** Tự động hồi sinh tiến trình khi gặp sự cố gián đoạn kết nối mạng hoặc lỗi máy chủ.

---

## 📱 Bảng Lệnh Điều Khiển Telegram (@NinhVNStock_bot)

| Lệnh | Ý nghĩa | Ví dụ |
| :--- | :--- | :--- |
| `/start` hoặc `/help` | Khởi tạo bot, hiển thị menu và các nút bấm nhanh | `/start` |
| `/scan` hoặc `/top` | Quét ngay các mã có dòng tiền lớn cá mập hôm nay | `/scan` |
| `/portfolio` hoặc `/p` | Xem chi tiết danh mục nắm giữ, lãi/lỗ thực tế và lịch hàng về T+2.5 | `/portfolio` |
| `/buy <MÃ> <KL> [ngan/dai]` | Đặt lệnh mua cổ phiếu vào danh mục lướt sóng hoặc tích sản | `/buy HPG 1000 ngan` |
| `/sell <MÃ> [KL]` | Bán chốt lời / cắt lỗ cổ phiếu (kiểm tra T+2.5 tự động) | `/sell SSI 500` |
| `<MÃ>` | Gõ trực tiếp tên mã để AI phân tích kỹ thuật và định giá | `FPT` |
| `/status` | Kiểm tra tình trạng hoạt động CPU, RAM và tiến trình bot 24/7 | `/status` |

---

## 🏗️ Cấu Trúc Thư Mục Dự Án

```
├── TradingAgents/              # Module AI Multi-Agent phân tích sâu
├── data/                       # Thư mục lưu dữ liệu cục bộ
│   ├── portfolio.json          # Trạng thái danh mục tài khoản (Paper Trading)
│   ├── subscribers.json        # Danh sách người dùng nhận thông báo
│   └── bot_247.log             # Nhật ký hoạt động chi tiết
├── smart_money_scanner.py      # Thuật toán quét dòng tiền lớn toàn thị trường
├── portfolio_manager.py        # Engine quản lý danh mục, phí thuế và luật T+2.5
├── telegram_trading_bot.py     # Server Telegram Bot tương tác 2 chiều
├── trading_scheduler.py        # Lập lịch quét trong phiên, tổng kết ngày & chiến lược tối
├── run_bot_247.py              # Master Runner đa luồng chạy 24/7 kèm Watchdog
├── ra_lenh_trading_247.bat     # File Batch khởi động 1-click trên Windows
├── requirements.txt            # Danh sách thư viện Python cần thiết
├── .env.example                # File mẫu cấu hình biến môi trường
└── README.md                   # Tài liệu hướng dẫn sử dụng
```

---

## ⚡ Hướng Dẫn Cài Đặt & Chạy Bot

### Bước 1: Cài đặt thư viện phụ thuộc
Yêu cầu Python 3.10 trở lên:
```bash
pip install -r requirements.txt
```

### Bước 2: Cấu hình biến môi trường
Sao chép file `.env.example` thành `.env` và điền thông tin:
```bash
cp .env.example .env
```
Nội dung file `.env`:
```ini
TELEGRAM_TRADING_BOT_TOKEN=8751866432:AAGYb-FoT9-bo43xm-WcwmFODWA1VvCKbpk
TELEGRAM_CHAT_ID=6383178389
GEMINI_API_KEY=your_gemini_api_key_here
```

### Bước 3: Khởi động hệ thống
- **Trên Windows:** Nhấp đúp chuột vào file `ra_lenh_trading_247.bat`
- **Trên Linux / macOS / Cloud VPS:**
```bash
python run_bot_247.py
```

Để chạy ngầm liên tục trên Linux (VPS Ubuntu):
```bash
nohup python run_bot_247.py > data/bot_247.log 2>&1 &
```

---

## ⚠️ Tuyên Bố Miễn Trừ Trách Nhiệm (Disclaimer)
- Hệ thống này được xây dựng cho mục đích nghiên cứu định lượng, quản trị danh mục khoa học và hỗ trợ ra quyết định đầu tư.
- Thị trường chứng khoán luôn có rủi ro biến động. Mọi tín hiệu từ AI và thuật toán mang tính tham khảo; nhà đầu tư cần tự chịu trách nhiệm với quyết định giải ngân tài sản của mình.

---
**Tác giả:** MyAgent Engineering Team 🇻🇳  
**Bản quyền:** MIT License (2026)
