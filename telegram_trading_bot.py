# -*- coding: utf-8 -*-
"""
TELEGRAM TRADING BOT 24/7 - CHỨNG KHOÁN VIỆT NAM (@NinhstockTrading_bot)
Tích hợp:
1. Quét dòng tiền lớn (Smart Money Scanner) real-time trong phiên.
2. Tự động quản lý danh mục Đầu tư Ngắn hạn (Lướt sóng T+) và Dài hạn (Tích sản).
3. Phân tích cổ phiếu theo yêu cầu người dùng (Fast AI / TradingAgents).
4. Tương tác 2 chiều 24/7 qua tin nhắn Telegram.
"""

import os
import sys
import time
import json
import threading
import logging
from datetime import datetime
from typing import Optional

import telebot
from telebot import types
import yfinance as yf

# Đảm bảo UTF-8 cho console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("VNTradingBot")

# Đường dẫn thư mục
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
TA_DIR = os.path.join(BASE_DIR, "TradingAgents")
if TA_DIR not in sys.path:
    sys.path.insert(0, TA_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

# Import các module nội bộ
from smart_money_scanner import scan_smart_money, format_scan_report, trim_memory
from portfolio_manager import PortfolioManager

BOT_START_TIME = time.time()

# Cấu hình Token & Chat ID
BOT_TOKEN = os.getenv("TELEGRAM_TRADING_BOT_TOKEN", "8456004015:AAESODZZNeVs5E6YjpEEivb5DQHTiYek_9g")
DEFAULT_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "6383178389")

class GlobalExceptionHandler(telebot.ExceptionHandler):
    def handle(self, exception):
        logger.error(f"[TeleBot Global Exception] {exception}", exc_info=True)
        return True  # Đánh dấu đã xử lý ngoại lệ, ngăn bot ngừng polling

bot = telebot.TeleBot(
    BOT_TOKEN,
    parse_mode="Markdown",
    num_threads=10,
    exception_handler=GlobalExceptionHandler()
)
portfolio = PortfolioManager()

# Quản lý danh sách chat_id đăng ký nhận thông báo tự động
SUBSCRIBERS_FILE = os.path.join(BASE_DIR, "data", "subscribers.json")

def get_subscribers() -> set:
    """Đọc danh sách chat_id đã đăng ký."""
    chats = set()
    if DEFAULT_CHAT_ID:
        try:
            chats.add(int(DEFAULT_CHAT_ID))
        except Exception:
            pass
    if os.path.exists(SUBSCRIBERS_FILE):
        try:
            with open(SUBSCRIBERS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                for c in data:
                    chats.add(int(c))
        except Exception:
            pass
    return chats

def add_subscriber(chat_id: int):
    """Lưu thêm chat_id người dùng mới tương tác."""
    chats = get_subscribers()
    if chat_id not in chats:
        chats.add(chat_id)
        try:
            os.makedirs(os.path.dirname(SUBSCRIBERS_FILE), exist_ok=True)
            with open(SUBSCRIBERS_FILE, "w", encoding="utf-8") as f:
                json.dump(list(chats), f)
        except Exception as e:
            logger.warning(f"Không thể lưu subscriber: {e}")

SUBSCRIBED_CHATS = get_subscribers()


def safe_send_message(chat_id: int, text: str, reply_markup=None, parse_mode: Optional[str] = "Markdown"):
    """
    Gửi tin nhắn an toàn tuyệt đối:
    1. Thử gửi với parse_mode (mặc định Markdown).
    2. Nếu lỗi Markdown (400 Bad Request/entity error), tự động xóa định dạng và gửi plain text (parse_mode=None).
    3. Tự động chia nhỏ nếu tin nhắn vượt quá 4000 ký tự.
    4. Bắt mọi ngoại lệ để không bao giờ làm gián đoạn luồng bot.
    """
    if not text:
        return None

    max_len = 4000
    parts = []
    if len(text) <= max_len:
        parts = [text]
    else:
        remaining = text
        while len(remaining) > max_len:
            split_idx = remaining.rfind("\n\n", 0, max_len)
            if split_idx == -1:
                split_idx = remaining.rfind("\n", 0, max_len)
            if split_idx == -1:
                split_idx = max_len
            parts.append(remaining[:split_idx])
            remaining = remaining[split_idx:].lstrip()
        if remaining:
            parts.append(remaining)

    res = None
    for i, p in enumerate(parts):
        markup = reply_markup if i == len(parts) - 1 else None
        try:
            res = bot.send_message(chat_id, p, parse_mode=parse_mode, reply_markup=markup)
        except Exception as e:
            logger.warning(f"Lỗi gửi tin nhắn {parse_mode} tới {chat_id}: {e}. Đang gửi lại dạng plain text...")
            try:
                clean_p = p.replace("*", "").replace("`", "").replace("_", " ").replace("[", "(").replace("]", ")")
                res = bot.send_message(chat_id, clean_p, parse_mode=None, reply_markup=markup)
            except Exception as e2:
                logger.error(f"Thất bại hoàn toàn khi gửi tin nhắn tới {chat_id}: {e2}")
    return res

# Alias tương thích ngược
send_chunked_message = safe_send_message


def broadcast_message(text: str, reply_markup=None):
    """Gửi thông báo tới toàn bộ người dùng đã đăng ký."""
    subscribers = get_subscribers()
    for cid in subscribers:
        try:
            safe_send_message(cid, text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Lỗi gửi broadcast đến chat_id {cid}: {e}")


def get_main_keyboard():
    """Tạo bàn phím điều khiển nhanh trên Telegram."""
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    btn_scan = types.KeyboardButton("🌊 Quét Dòng Tiền")
    btn_portfolio = types.KeyboardButton("💼 Xem Danh Mục")
    btn_sheet = types.KeyboardButton("📈 Google Sheet")
    btn_autotrade = types.KeyboardButton("🤖 Auto-Trading")
    btn_top = types.KeyboardButton("🔥 Top Cổ Phiếu")
    btn_help = types.KeyboardButton("❓ Trợ Giúp")
    markup.add(btn_scan, btn_portfolio)
    markup.add(btn_sheet, btn_autotrade)
    markup.add(btn_top, btn_help)
    return markup


@bot.message_handler(commands=["start", "help"])
def handle_start(message):
    chat_id = message.chat.id
    add_subscriber(chat_id)
    welcome_text = (
        "🤖 *CHÀO MỪNG BẠN ĐẾN VỚI BOT GIAO DỊCH CHỨNG KHOÁN VIỆT NAM 24/7*\n"
        "───────────────────\n"
        "Hệ thống Multi-Agent AI tự động giám sát thị trường, phát hiện dòng tiền lớn và quản lý danh mục đầu tư.\n\n"
        "📌 *CÁC CÂU LỆNH CHÍNH:*\n"
        "• `/scan` : Quét ngay các mã có dòng tiền lớn cá mập vào phiên hôm nay\n"
        "• `/portfolio` hoặc `/p` : Xem danh mục đầu tư (Lướt sóng T+ & Tích sản dài hạn)\n"
        "• `/sheet` : Lấy đường link mở Google Sheet & Drive theo dõi danh mục trực tuyến\n"
        "• `/autotrade [on/off]` : Bật / tắt chế độ tự động mua bán khi phát hiện cá mập\n"
        "• `/analyze <mã>` (hoặc gõ thẳng `HPG`, `FPT`): Yêu cầu AI phân tích kỹ thuật, cơ bản & tin tức\n"
        "• `/buy <mã> <khối_lượng> [ngan/dai]` : Mua cổ phiếu vào danh mục\n"
        "• `/sell <mã> [khối_lượng]` : Bán chốt lời/cắt lỗ (tuân thủ T+2.5)\n"
        "• `/status` : Kiểm tra trạng thái máy chủ và tiến trình 24/7\n\n"
        "⚡ *Bạn cũng có thể bấm các nút menu nhanh bên dưới!*"
    )
    send_chunked_message(chat_id, welcome_text, reply_markup=get_main_keyboard())


@bot.message_handler(commands=["scan", "top"])
def handle_scan(message):
    chat_id = message.chat.id
    add_subscriber(chat_id)
    bot.send_chat_action(chat_id, "typing")
    safe_send_message(chat_id, "⏳ Đang quét dữ liệu toàn bộ cổ phiếu hàng đầu thị trường...")

    results = scan_smart_money(min_vol_ratio=1.3, min_price_change=0.5, top_n=8)
    report = format_scan_report(results)
    safe_send_message(chat_id, report, reply_markup=get_main_keyboard())
    trim_memory()


@bot.message_handler(commands=["portfolio", "p"])
def handle_portfolio(message):
    chat_id = message.chat.id
    add_subscriber(chat_id)
    bot.send_chat_action(chat_id, "typing")
    summary = portfolio.get_summary()
    safe_send_message(chat_id, summary, reply_markup=get_main_keyboard())


@bot.message_handler(commands=["buy"])
def handle_buy(message):
    chat_id = message.chat.id
    add_subscriber(chat_id)
    # Cú pháp: /buy <MÃ> <KHỐI_LƯỢNG> [ngan/dai]
    parts = message.text.strip().split()
    if len(parts) < 3:
        safe_send_message(chat_id, "⚠️ Cú pháp: `/buy <MÃ> <SỐ_LƯỢNG> [ngan/dai]`\nVí dụ: `/buy HPG 2000 ngan`")
        return

    ticker = parts[1].upper()
    try:
        shares = int(parts[2])
    except ValueError:
        safe_send_message(chat_id, "⚠️ Số lượng cổ phiếu phải là số nguyên!")
        return

    p_type = "short_term"
    if len(parts) >= 4 and parts[3].lower() in ("dai", "long", "tich_san"):
        p_type = "long_term"

    # Lấy giá thị trường gần nhất
    bot.send_chat_action(chat_id, "typing")
    sym = f"{ticker}.VN" if not ticker.endswith(".VN") else ticker
    try:
        t_obj = yf.Ticker(sym)
        hist = t_obj.history(period="5d")
        hist = hist.dropna(subset=["Close"])
        hist = hist[hist["Close"] > 0]
        if hist.empty:
            safe_send_message(chat_id, f"❌ Không tìm thấy mã cổ phiếu {ticker} trên sàn!")
            return
        cur_price = float(hist["Close"].iloc[-1])
    except Exception as e:
        safe_send_message(chat_id, f"❌ Lỗi lấy giá cổ phiếu: {e}")
        return

    res = portfolio.buy(ticker, cur_price, shares, portfolio_type=p_type, rationale="Lệnh đặt qua Telegram")
    safe_send_message(chat_id, res["message"])


@bot.message_handler(commands=["sell"])
def handle_sell(message):
    chat_id = message.chat.id
    add_subscriber(chat_id)
    # Cú pháp: /sell <MÃ> [KHỐI_LƯỢNG]
    parts = message.text.strip().split()
    if len(parts) < 2:
        safe_send_message(chat_id, "⚠️ Cú pháp: `/sell <MÃ> [SỐ_LƯỢNG]`\nVí dụ: `/sell HPG 1000` (bỏ trống số lượng sẽ bán hết)")
        return

    ticker = parts[1].upper()
    shares = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else None

    # Lấy giá thị trường gần nhất
    bot.send_chat_action(chat_id, "typing")
    sym = f"{ticker}.VN" if not ticker.endswith(".VN") else ticker
    try:
        t_obj = yf.Ticker(sym)
        hist = t_obj.history(period="5d")
        hist = hist.dropna(subset=["Close"])
        hist = hist[hist["Close"] > 0]
        if hist.empty:
            safe_send_message(chat_id, f"❌ Không tìm thấy mã cổ phiếu {ticker} trên sàn!")
            return
        cur_price = float(hist["Close"].iloc[-1])
    except Exception as e:
        safe_send_message(chat_id, f"❌ Lỗi lấy giá cổ phiếu: {e}")
        return

    res = portfolio.sell(ticker, cur_price, shares=shares, rationale="Lệnh bán chủ động qua Telegram")
    safe_send_message(chat_id, res["message"])


@bot.message_handler(commands=["sheet"])
def handle_sheet(message):
    chat_id = message.chat.id
    add_subscriber(chat_id)
    try:
        from trading_sheet_sync import sheet_sync
        link = sheet_sync.get_sheet_link()
    except Exception:
        link = "https://docs.google.com/spreadsheets/d/1mjYsI-sXYgqAaebNXJb8BA4hwLZWxh-Cqji8p_F-dwo/edit"

    msg = (
        "📈 *GOOGLE SHEETS & GOOGLE DRIVE - AUTO-TRADING*\n"
        "───────────────────\n"
        "Toàn bộ dữ liệu danh mục, lịch sử lệnh mua/bán và tín hiệu dòng tiền được đồng bộ trực tiếp lên Google Drive:\n\n"
        f"🔗 [BẤM ĐỂ MỞ GOOGLE SHEET TRÊN DRIVER]({link})\n\n"
        "📌 *Các Tab Trong Bảng Tính:*\n"
        "• `Trading_Portfolio`: Danh mục đang nắm giữ, giá vốn, giá hiện tại, lãi/lỗ & ngày về T+2.5\n"
        "• `Trading_Orders`: Nhật ký mọi lệnh mua/bán, chốt lời, cắt lỗ, thuế phí\n"
        "• `Smart_Money_Alerts`: Lịch sử các mã cá mập bùng nổ thanh khoản trong phiên"
    )
    send_chunked_message(chat_id, msg, reply_markup=get_main_keyboard())


@bot.message_handler(commands=["autotrade"])
def handle_autotrade(message):
    chat_id = message.chat.id
    add_subscriber(chat_id)
    try:
        from trading_scheduler import get_autotrade_config, set_autotrade_enabled
    except Exception:
        safe_send_message(chat_id, "⚠️ Không tìm thấy module scheduler.")
        return

    parts = message.text.strip().split()
    if len(parts) >= 2:
        action = parts[1].lower()
        if action in ("on", "bat", "1", "true", "start"):
            set_autotrade_enabled(True)
            safe_send_message(
                chat_id,
                "🟢 *ĐÃ BẬT CHẾ ĐỘ AUTO-TRADING TOÀN DIỆN!*\n"
                "───────────────────\n"
                "• Trong phiên (09:15 - 14:45), hệ thống sẽ TỰ ĐỘNG MUA khi phát hiện cổ phiếu nổ Vol >= 1.8x MA20 & Giá tăng mạnh.\n"
                "• Tự động Cắt lỗ (-5%) và Chốt lời (+15%) theo chu kỳ T+2.5.\n"
                "• Tự động lưu mọi giao dịch vào Google Sheets trên Google Drive!",
                reply_markup=get_main_keyboard()
            )
            return
        elif action in ("off", "tat", "0", "false", "stop"):
            set_autotrade_enabled(False)
            safe_send_message(
                chat_id,
                "⏸️ *ĐÃ TẮT CHẾ ĐỘ TỰ ĐỘNG MUA!*\n"
                "───────────────────\n"
                "Bot sẽ chỉ gửi cảnh báo dòng tiền cá mập về Telegram để bạn tự quyết định đặt lệnh `/buy`.",
                reply_markup=get_main_keyboard()
            )
            return

    cfg = get_autotrade_config()
    st = "🟢 ĐANG BẬT (Tự động Mua & Bán)" if cfg.get("enabled") else "⏸️ ĐANG TẮT (Chỉ cảnh báo)"
    msg = (
        "🤖 *CẤU HÌNH AUTO-TRADING CHỨNG KHOÁN*\n"
        "───────────────────\n"
        f"• Trạng thái hiện tại: *{st}*\n"
        f"• Tỷ trọng tối đa mỗi mã: `{cfg.get('allocation_pct_per_stock', 0.2)*100:.0f}%` tài sản\n"
        f"• Tối đa số mã nắm giữ: `{cfg.get('max_stocks_in_portfolio', 5)}` cổ phiếu\n"
        f"• Ngưỡng Vol bùng nổ: `>= {cfg.get('min_vol_ratio', 1.8)}x` MA20\n\n"
        "📌 *Cách điều khiển:*\n"
        "• `/autotrade on` : Bật tự động mua khi có cá mập\n"
        "• `/autotrade off` : Tắt tự động mua, chỉ nhận tin báo"
    )
    send_chunked_message(chat_id, msg, reply_markup=get_main_keyboard())


@bot.message_handler(commands=["status"])
def handle_status(message):
    chat_id = message.chat.id
    import psutil
    proc = psutil.Process()
    rss_mb = proc.memory_info().rss / (1024 * 1024)
    cpu = psutil.cpu_percent(interval=0.2)
    uptime_sec = int(time.time() - BOT_START_TIME)
    h = uptime_sec // 3600
    m = (uptime_sec % 3600) // 60
    s = uptime_sec % 60
    try:
        bot_user = f"@{bot.get_me().username}"
    except Exception:
        bot_user = "@NinhstockTrading_bot"

    msg = (
        "🟢 *HỆ THỐNG AUTO-TRADING 24/7 ĐANG HOẠT ĐỘNG*\n"
        "───────────────────\n"
        f"• Máy chủ: `Cloud Render 24/7 Uptime`\n"
        f"• RAM tiến trình: `{rss_mb:.1f} MB / 512 MB` (Tối ưu siêu nhẹ)\n"
        f"• CPU sử dụng: `{cpu}%`\n"
        f"• Uptime: `{h}h {m}m {s}s`\n"
        f"• Telegram Bot: `{bot_user}`\n"
        f"• Lịch quét trong phiên: Mỗi 15 phút (09:15 - 14:45)\n"
        f"• Số lượng theo dõi: `{len(SUBSCRIBED_CHATS)}`\n"
        "───────────────────\n"
        "💡 *Lưu ý:* Bot đang chạy 100% trên Cloud Render. Bạn có thể TẮT MÁY TÍNH HOÀN TOÀN, bot vẫn hoạt động bình thường!"
    )
    safe_send_message(chat_id, msg)
    trim_memory()


@bot.message_handler(func=lambda msg: True)
def handle_text(message):
    """Xử lý tin nhắn văn bản thông thường (nút bấm hoặc gõ tên mã cổ phiếu)."""
    text = (message.text or "").strip()
    if not text:
        return
    chat_id = message.chat.id
    add_subscriber(chat_id)

    if text in ("🌊 Quét Dòng Tiền", "🔥 Top Cổ Phiếu"):
        handle_scan(message)
    elif text in ("💼 Xem Danh Mục",):
        handle_portfolio(message)
    elif text in ("📈 Google Sheet",):
        handle_sheet(message)
    elif text in ("🤖 Auto-Trading",):
        handle_autotrade(message)
    elif text in ("❓ Trợ Giúp",):
        handle_start(message)
    elif text.startswith("/analyze ") or text.startswith("/a "):
        parts = text.split()
        if len(parts) >= 2:
            ticker = parts[1].upper()
            _process_analyze(chat_id, ticker)
    elif len(text) in (3, 4) and text.isalpha():
        # Người dùng gõ trực tiếp tên mã cổ phiếu (ví dụ: HPG, FPT, VNM, SSI)
        ticker = text.upper()
        _process_analyze(chat_id, ticker)
    else:
        safe_send_message(
            chat_id,
            f"Tôi chưa hiểu lệnh `{text}`. Hãy gõ tên mã cổ phiếu (ví dụ: `HPG`, `FPT`) hoặc gõ `/help` để xem hướng dẫn.",
            reply_markup=get_main_keyboard()
        )


def _process_analyze(chat_id: int, ticker: str):
    """Phân tích nhanh mã cổ phiếu theo yêu cầu của người dùng."""
    bot.send_chat_action(chat_id, "typing")
    clean_ticker = ticker.replace(".VN", "").upper().strip()
    sym = f"{clean_ticker}.VN"

    safe_send_message(chat_id, f"🔍 Đang truy xuất dữ liệu kỹ thuật và tin tức cho mã *{clean_ticker}*...")

    try:
        t_obj = yf.Ticker(sym)
        hist = t_obj.history(period="1mo")
        if hist.empty:
            hist = t_obj.history(period="5d")
        hist = hist.dropna(subset=["Close", "Volume"])
        hist = hist[hist["Close"] > 0]
        if hist.empty:
            safe_send_message(chat_id, f"❌ Không tìm thấy dữ liệu cho mã `{clean_ticker}` trên sàn HOSE/HNX!")
            return

        cur_price = float(hist["Close"].iloc[-1])
        prev_price = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else cur_price
        pct = ((cur_price - prev_price) / prev_price) * 100.0 if prev_price > 0 else 0.0
        pct_sign = "+" if pct > 0 else ""

        vol = float(hist["Volume"].iloc[-1])
        vol_sma20 = float(hist["Volume"].rolling(20, min_periods=3).mean().iloc[-2]) if len(hist) >= 4 else float(hist["Volume"].mean())
        vol_ratio = vol / vol_sma20 if vol_sma20 > 0 else 1.0

        # Phân tích đường trung bình
        ema10 = float(hist["Close"].ewm(span=10, adjust=False).mean().iloc[-1])
        sma50 = float(hist["Close"].rolling(50, min_periods=5).mean().iloc[-1])
        trend = "Tăng ngắn hạn (Trên EMA10)" if cur_price > ema10 else "Điều chỉnh/Tích lũy (Dưới EMA10)"

        # Phân tích Hệ thống Ichimoku Kinko Hyo (Tenkan 9, Kijun 26, Senkou Span 52)
        h_series = hist["High"].dropna()
        l_series = hist["Low"].dropna()
        t_len = min(9, len(h_series))
        k_len = min(26, len(h_series))
        b_len = min(52, len(h_series))

        tenkan = float((h_series.iloc[-t_len:].max() + l_series.iloc[-t_len:].min()) / 2)
        kijun = float((h_series.iloc[-k_len:].max() + l_series.iloc[-k_len:].min()) / 2)
        span_a = (tenkan + kijun) / 2
        span_b = float((h_series.iloc[-b_len:].max() + l_series.iloc[-b_len:].min()) / 2)

        kumo_top = max(span_a, span_b)
        kumo_bot = min(span_a, span_b)

        if cur_price > kumo_top:
            ichi_pos = "Nằm TRÊN Mây Kumo ☁️ (Uptrend mạnh)"
        elif cur_price < kumo_bot:
            ichi_pos = "Nằm DƯỚI Mây Kumo 🔻 (Downtrend / Áp lực cản)"
        else:
            ichi_pos = "Nằm TRONG Mây Kumo ⏸️ (Vùng tích lũy giằng co)"

        tk_signal = "⚡ Tenkan cắt trên Kijun (Golden Cross - Tín hiệu MUA)" if tenkan >= kijun else "🔻 Tenkan nằm dưới Kijun"
        kumo_type = "Mây Xanh (Tăng)" if span_a >= span_b else "Mây Đỏ (Giảm)"

        # Lấy tin tức mới nhất từ ddgs an toàn
        news_snippet = ""
        try:
            try:
                from duckduckgo_search import DDGS
            except ImportError:
                from ddgs import DDGS
            news_items = list(DDGS().news(keywords=f"cổ phiếu {clean_ticker}", max_results=2))
            if news_items:
                news_snippet = "\n📰 *Tin tức mới nhất:*\n"
                for item in news_items:
                    t_str = str(item.get("title", "")).replace("*", "").replace("`", "").replace("_", " ")
                    s_str = str(item.get("source", "")).replace("*", "").replace("`", "").replace("_", " ")
                    news_snippet += f"• {t_str} ({s_str})\n"
        except Exception:
            pass

        # Đưa ra khuyến nghị hành động kết hợp Dòng tiền + Ichimoku + Quản trị rủi ro
        if cur_price > kumo_top and tenkan >= kijun and vol_ratio >= 1.3 and pct > 0:
            rec = "🔥 *MUA MẠNH (STRONG BUY)* - Dòng tiền cá mập bùng nổ + Chuẩn Ichimoku (Trên Mây Kumo & TK Golden Cross)!"
            sl = round(cur_price * 0.95, 0)
            tp = round(cur_price * 1.15, 0)
        elif cur_price > kumo_top:
            rec = "📈 *THEO DÕI MUA (ACCUMULATE)* - Nằm trên mây Kumo, canh mua ở các nhịp kiểm tra Kijun-sen."
            sl = round(cur_price * 0.95, 0)
            tp = round(cur_price * 1.12, 0)
        elif cur_price < kumo_bot:
            rec = "⚠️ *THẬN TRỌNG (BEARISH/AVOID)* - Giá nằm dưới mây Kumo, kháng cự mây dày đặc phía trên."
            sl = round(cur_price * 0.95, 0)
            tp = round(cur_price * 1.08, 0)
        else:
            rec = "⏸️ *QUAN SÁT (NEUTRAL/HOLD)* - Giá tích lũy trong mây Kumo, chờ tín hiệu bứt phá (Breakout)."
            sl = round(cur_price * 0.95, 0)
            tp = round(cur_price * 1.10, 0)

        msg = (
            f"📊 *PHÂN TÍCH TOÀN DIỆN: {clean_ticker}*\n"
            f"───────────────────\n"
            f"💵 *Giá hiện tại:* `{cur_price:,.0f} VND` ({pct_sign}{pct:.2f}%)\n"
            f"📊 *Thanh khoản:* `{vol:,.0f}` cp (*{vol_ratio:.2f}x* MA20)\n"
            f"📉 *Xu hướng MA:* {trend}\n"
            f"───────────────────\n"
            f"☁️ *HỆ THỐNG ICHIMOKU KINKO HYO:*\n"
            f"• *Tenkan-sen (9):* `{tenkan:,.0f} VND` | *Kijun-sen (26):* `{kijun:,.0f} VND`\n"
            f"• *Mây Kumo:* `{kumo_bot:,.0f} - {kumo_top:,.0f} VND` ({kumo_type})\n"
            f"• *Vị thế Giá:* {ichi_pos}\n"
            f"• *Tín hiệu TK:* {tk_signal}\n"
            f"{news_snippet}"
            f"───────────────────\n"
            f"🎯 *KHUYẾN NGHỊ HÀNH ĐỘNG:* {rec}\n"
            f"• Vùng mua gom: `{cur_price:,.0f} VND`\n"
            f"• Hỗ trợ Kijun-sen: `{kijun:,.0f} VND`\n"
            f"• Cắt lỗ kỷ luật (SL -5%): `{sl:,.0f} VND`\n"
            f"• Chốt lời mục tiêu (TP +15%): `{tp:,.0f} VND`\n"
            f"• Lưu ý chu kỳ: Tuân thủ quy tắc thanh toán T+2.5 sàn Việt Nam."
        )
        safe_send_message(chat_id, msg, reply_markup=get_main_keyboard())
    except Exception as e:
        logger.error(f"Lỗi khi phân tích mã {clean_ticker}: {e}", exc_info=True)
        safe_send_message(chat_id, f"❌ Lỗi khi phân tích mã {clean_ticker}: {str(e)[:200]}")
    finally:
        trim_memory()


def run_telegram_polling():
    """Vòng lặp lắng nghe tin nhắn Telegram liên tục (có cơ chế auto-reconnect)."""
    logger.info("Khởi động luồng lắng nghe tin nhắn Telegram (@NinhVNStock_bot)...")
    try:
        bot.delete_webhook(drop_pending_updates=True)
    except Exception as e:
        logger.warning(f"Lỗi khi xóa webhook Telegram: {e}")

    while True:
        try:
            bot.polling(non_stop=True, interval=1, timeout=10)
        except Exception as e:
            logger.error(f"Mất kết nối Telegram Polling, tự động kết nối lại sau 5s: {e}")
            time.sleep(5)


if __name__ == "__main__":
    print("Khởi động Telegram Trading Bot 24/7...")
    run_telegram_polling()
