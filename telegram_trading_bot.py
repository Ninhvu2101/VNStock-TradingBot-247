# -*- coding: utf-8 -*-
"""
TELEGRAM TRADING BOT 24/7 - CHỨNG KHOÁN VIỆT NAM (@NinhVNStock_bot)
Tích hợp:
1. Quét dòng tiền lớn (Smart Money Scanner) real-time trong phiên.
2. Tự động quản lý danh mục Đầu tư Ngắn hạn (Lướt sóng T+) và Dài hạn (Tích sản).
3. Phân tích cổ phiếu theo yêu cầu người dùng (Fast AI / TradingAgents).
4. Tương tác 2 chiều 24/7 qua tin nhắn Telegram.
"""

import os
import sys
import time
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
from smart_money_scanner import scan_smart_money, format_scan_report
from portfolio_manager import PortfolioManager

# Cấu hình Token & Chat ID
BOT_TOKEN = os.getenv("TELEGRAM_TRADING_BOT_TOKEN", "8751866432:AAGYb-FoT9-bo43xm-WcwmFODWA1VvCKbpk")
DEFAULT_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "6383178389")

import json

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")
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


def send_chunked_message(chat_id: int, text: str, reply_markup=None):
    """Gửi tin nhắn an toàn, tự động chia nhỏ nếu vượt quá 4000 ký tự."""
    max_len = 4000
    if len(text) <= max_len:
        try:
            bot.send_message(chat_id, text, reply_markup=reply_markup)
        except Exception:
            # Thử gửi dạng text thuần nếu lỗi định dạng Markdown
            bot.send_message(chat_id, text.replace("*", "").replace("`", ""), reply_markup=reply_markup)
        return

    # Chia thành các đoạn nhỏ
    parts = []
    while len(text) > max_len:
        split_idx = text.rfind("\n\n", 0, max_len)
        if split_idx == -1:
            split_idx = text.rfind("\n", 0, max_len)
        if split_idx == -1:
            split_idx = max_len
        parts.append(text[:split_idx])
        text = text[split_idx:].lstrip()
    if text:
        parts.append(text)

    for i, p in enumerate(parts):
        markup = reply_markup if i == len(parts) - 1 else None
        try:
            bot.send_message(chat_id, p, reply_markup=markup)
        except Exception:
            bot.send_message(chat_id, p.replace("*", "").replace("`", ""), reply_markup=markup)


def broadcast_message(text: str, reply_markup=None):
    """Gửi thông báo tới toàn bộ người dùng đã đăng ký."""
    subscribers = get_subscribers()
    for cid in subscribers:
        try:
            send_chunked_message(cid, text, reply_markup=reply_markup)
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
    bot.send_message(chat_id, "⏳ Đang quét dữ liệu toàn bộ 60 cổ phiếu hàng đầu thị trường...")

    results = scan_smart_money(min_vol_ratio=1.3, min_price_change=0.5, top_n=8)
    report = format_scan_report(results)
    send_chunked_message(chat_id, report, reply_markup=get_main_keyboard())


@bot.message_handler(commands=["portfolio", "p"])
def handle_portfolio(message):
    chat_id = message.chat.id
    add_subscriber(chat_id)
    bot.send_chat_action(chat_id, "typing")
    summary = portfolio.get_summary()
    send_chunked_message(chat_id, summary, reply_markup=get_main_keyboard())


@bot.message_handler(commands=["buy"])
def handle_buy(message):
    chat_id = message.chat.id
    add_subscriber(chat_id)
    # Cú pháp: /buy <MÃ> <KHỐI_LƯỢNG> [ngan/dai]
    parts = message.text.strip().split()
    if len(parts) < 3:
        bot.send_message(chat_id, "⚠️ Cú pháp: `/buy <MÃ> <SỐ_LƯỢNG> [ngan/dai]`\nVí dụ: `/buy HPG 2000 ngan`")
        return

    ticker = parts[1].upper()
    try:
        shares = int(parts[2])
    except ValueError:
        bot.send_message(chat_id, "⚠️ Số lượng cổ phiếu phải là số nguyên!")
        return

    p_type = "short_term"
    if len(parts) >= 4 and parts[3].lower() in ("dai", "long", "tich_san"):
        p_type = "long_term"

    # Lấy giá thị trường gần nhất
    bot.send_chat_action(chat_id, "typing")
    sym = f"{ticker}.VN" if not ticker.endswith(".VN") else ticker
    try:
        t_obj = yf.Ticker(sym)
        hist = t_obj.history(period="2d")
        if hist.empty:
            bot.send_message(chat_id, f"❌ Không tìm thấy mã cổ phiếu {ticker} trên sàn!")
            return
        cur_price = float(hist["Close"].iloc[-1])
    except Exception as e:
        bot.send_message(chat_id, f"❌ Lỗi lấy giá cổ phiếu: {e}")
        return

    res = portfolio.buy(ticker, cur_price, shares, portfolio_type=p_type, rationale="Lệnh đặt qua Telegram")
    bot.send_message(chat_id, res["message"])


@bot.message_handler(commands=["sell"])
def handle_sell(message):
    chat_id = message.chat.id
    add_subscriber(chat_id)
    # Cú pháp: /sell <MÃ> [KHỐI_LƯỢNG]
    parts = message.text.strip().split()
    if len(parts) < 2:
        bot.send_message(chat_id, "⚠️ Cú pháp: `/sell <MÃ> [SỐ_LƯỢNG]`\nVí dụ: `/sell HPG 1000` (bỏ trống số lượng sẽ bán hết)")
        return

    ticker = parts[1].upper()
    shares = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else None

    # Lấy giá thị trường gần nhất
    bot.send_chat_action(chat_id, "typing")
    sym = f"{ticker}.VN" if not ticker.endswith(".VN") else ticker
    try:
        t_obj = yf.Ticker(sym)
        hist = t_obj.history(period="2d")
        if hist.empty:
            bot.send_message(chat_id, f"❌ Không tìm thấy mã cổ phiếu {ticker} trên sàn!")
            return
        cur_price = float(hist["Close"].iloc[-1])
    except Exception as e:
        bot.send_message(chat_id, f"❌ Lỗi lấy giá cổ phiếu: {e}")
        return

    res = portfolio.sell(ticker, cur_price, shares=shares, rationale="Lệnh bán chủ động qua Telegram")
    bot.send_message(chat_id, res["message"])


@bot.message_handler(commands=["sheet"])
def handle_sheet(message):
    chat_id = message.chat.id
    add_subscriber(chat_id)
    try:
        from trading_sheet_sync import sheet_sync
        link = sheet_sync.get_sheet_link()
    except Exception:
        link = "https://docs.google.com/spreadsheets/d/1NZl2d8XaOD1COe6Qg1xb-7qn8SD9PKdGTTPJ7AUH2PE/edit"

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
        bot.send_message(chat_id, "⚠️ Không tìm thấy module scheduler.")
        return

    parts = message.text.strip().split()
    if len(parts) >= 2:
        action = parts[1].lower()
        if action in ("on", "bat", "1", "true", "start"):
            set_autotrade_enabled(True)
            bot.send_message(
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
            bot.send_message(
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
    cpu = psutil.cpu_percent(interval=0.5)
    ram = psutil.virtual_memory().percent
    msg = (
        "🟢 *HỆ THỐNG AUTO-TRADING 24/7 ĐANG HOẠT ĐỘNG*\n"
        "───────────────────\n"
        f"• CPU sử dụng: `{cpu}%`\n"
        f"• RAM sử dụng: `{ram}%`\n"
        f"• Telegram Bot: `@NinhVNStock_bot`\n"
        f"• Mô hình AI: Google Gemini 3.5 Flash (Xoay tua 10 Keys)\n"
        f"• Lịch quét trong phiên: Mỗi 15 phút từ 09:15 đến 14:45\n"
        f"• Số lượng người theo dõi: `{len(SUBSCRIBED_CHATS)}`"
    )
    bot.send_message(chat_id, msg)


@bot.message_handler(func=lambda msg: True)
def handle_text(message):
    """Xử lý tin nhắn văn bản thông thường (nút bấm hoặc gõ tên mã cổ phiếu)."""
    text = message.text.strip()
    chat_id = message.chat.id
    add_subscriber(chat_id)

    if text == "🌊 Quét Dòng Tiền" or text == "🔥 Top Cổ Phiếu":
        handle_scan(message)
    elif text == "💼 Xem Danh Mục":
        handle_portfolio(message)
    elif text == "📈 Google Sheet":
        handle_sheet(message)
    elif text == "🤖 Auto-Trading":
        handle_autotrade(message)
    elif text == "❓ Trợ Giúp":
        handle_start(message)
    elif text.startswith("/analyze ") or text.startswith("/a "):
        ticker = text.split()[1].upper()
        _process_analyze(chat_id, ticker)
    elif len(text) in (3, 4) and text.isalpha():
        # Người dùng gõ trực tiếp tên mã cổ phiếu (ví dụ: HPG, FPT, VNM, SSI)
        ticker = text.upper()
        _process_analyze(chat_id, ticker)
    else:
        bot.send_message(
            chat_id,
            f"Tôi chưa hiểu lệnh `{text}`. Hãy gõ tên mã cổ phiếu (ví dụ: `HPG`, `FPT`) hoặc gõ `/help` để xem hướng dẫn.",
            reply_markup=get_main_keyboard()
        )


def _process_analyze(chat_id: int, ticker: str):
    """Phân tích nhanh mã cổ phiếu theo yêu cầu của người dùng."""
    bot.send_chat_action(chat_id, "typing")
    clean_ticker = ticker.replace(".VN", "").upper()
    sym = f"{clean_ticker}.VN"

    bot.send_message(chat_id, f"🔍 Đang truy xuất dữ liệu kỹ thuật và tin tức cho mã *{clean_ticker}*...")

    try:
        t_obj = yf.Ticker(sym)
        hist = t_obj.history(period="1mo")
        if hist.empty:
            bot.send_message(chat_id, f"❌ Không tìm thấy dữ liệu cho mã `{clean_ticker}`!")
            return

        cur_price = float(hist["Close"].iloc[-1])
        prev_price = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else cur_price
        pct = ((cur_price - prev_price) / prev_price) * 100.0
        pct_sign = "+" if pct > 0 else ""

        vol = float(hist["Volume"].iloc[-1])
        vol_sma20 = float(hist["Volume"].rolling(20).mean().iloc[-2]) if len(hist) >= 20 else float(hist["Volume"].mean())
        vol_ratio = vol / vol_sma20 if vol_sma20 > 0 else 1.0

        # Phân tích nhanh chỉ báo
        ema10 = float(hist["Close"].ewm(span=10, adjust=False).mean().iloc[-1])
        sma50 = float(hist["Close"].rolling(50, min_periods=10).mean().iloc[-1])
        trend = "Tăng ngắn hạn (Trên EMA10)" if cur_price > ema10 else "Điều chỉnh/Tích lũy (Dưới EMA10)"

        info = t_obj.info or {}
        company_name = info.get("shortName") or info.get("longName") or clean_ticker
        pe = info.get("trailingPE")
        pb = info.get("priceToBook")
        pe_str = f"{pe:.1f}" if pe else "N/A"
        pb_str = f"{pb:.2f}" if pb else "N/A"

        # Lấy tin tức mới nhất từ ddgs
        news_snippet = ""
        try:
            from ddgs import DDGS
            news_items = list(DDGS().news(query=f"cổ phiếu {clean_ticker}", max_results=2))
            if news_items:
                news_snippet = "\n📰 *Tin tức mới nhất:*\n"
                for item in news_items:
                    news_snippet += f"• {item.get('title')} ({item.get('source')})\n"
        except Exception:
            pass

        # Đưa ra khuyến nghị
        if cur_price > ema10 and vol_ratio >= 1.5 and pct > 0:
            rec = "🔥 *MUA (BUY)* - Dòng tiền xác nhận bùng nổ, giá vượt EMA10."
            sl = round(cur_price * 0.95, 0)
            tp = round(cur_price * 1.15, 0)
        elif cur_price > ema10:
            rec = "📈 *THEO DÕI MUA (ACCUMULATE)* - Xu hướng tích cực, chờ điểm mua tối ưu."
            sl = round(cur_price * 0.95, 0)
            tp = round(cur_price * 1.12, 0)
        else:
            rec = "⏸️ *QUAN SÁT (NEUTRAL/HOLD)* - Giá đang tích lũy dưới cản ngắn hạn."
            sl = round(cur_price * 0.95, 0)
            tp = round(cur_price * 1.10, 0)

        msg = (
            f"📊 *PHÂN TÍCH NHANH: {clean_ticker} - {company_name}*\n"
            f"───────────────────\n"
            f"💵 *Giá hiện tại:* `{cur_price:,.0f} VND` ({pct_sign}{pct:.2f}%)\n"
            f"📊 *Thanh khoản:* `{vol:,.0f}` cp (*{vol_ratio:.2f}x* MA20)\n"
            f"📈 *Định giá:* P/E = `{pe_str}` | P/B = `{pb_str}`\n"
            f"📉 *Xu hướng:* {trend}\n"
            f"{news_snippet}\n"
            f"───────────────────\n"
            f"🎯 *KHUYẾN NGHỊ:* {rec}\n"
            f"• Vùng mua gom: `{cur_price:,.0f} VND`\n"
            f"• Cắt lỗ (Stoploss): `{sl:,.0f} VND` (-5%)\n"
            f"• Chốt lời (Target): `{tp:,.0f} VND` (+10% đến +15%)\n"
            f"• Lưu ý: Tuân thủ chu kỳ thanh toán T+2.5 sàn Việt Nam."
        )
        send_chunked_message(chat_id, msg, reply_markup=get_main_keyboard())

    except Exception as e:
        bot.send_message(chat_id, f"❌ Lỗi khi phân tích mã {clean_ticker}: {e}")


def run_telegram_polling():
    """Vòng lặp lắng nghe tin nhắn Telegram liên tục (có cơ chế auto-reconnect)."""
    logger.info("Khởi động luồng lắng nghe tin nhắn Telegram (@NinhVNStock_bot)...")
    try:
        bot.delete_webhook(drop_pending_updates=True)
    except Exception as e:
        logger.warning(f"Lỗi khi xóa webhook Telegram: {e}")

    while True:
        try:
            bot.infinity_polling(timeout=20, long_polling_timeout=15)
        except Exception as e:
            logger.error(f"Mất kết nối Telegram Polling, tự động kết nối lại sau 5s: {e}")
            time.sleep(5)


if __name__ == "__main__":
    print("Khởi động Telegram Trading Bot 24/7...")
    run_telegram_polling()
