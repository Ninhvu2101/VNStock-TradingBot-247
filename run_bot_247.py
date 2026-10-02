# -*- coding: utf-8 -*-
"""
HỆ THỐNG AUTO-TRADING 24/7 CHỨNG KHOÁN VIỆT NAM (MASTER RUNNER)
Telegram Bot: @NinhVNStock_bot
Tác giả: MyAgent Multi-Agent Trading System

Chức năng:
1. Chạy song song luồng lắng nghe tin nhắn Telegram 2 chiều (bàn phím tương tác, lệnh /scan, /buy, /sell, /portfolio).
2. Chạy luồng Scheduler giám sát thị trường theo chu kỳ thời gian thực (quét dòng tiền cá mập, kiểm tra cắt lỗ/chốt lời).
3. Cơ chế Watchdog giám sát lỗi, tự động kết nối lại khi mất mạng hoặc gặp ngoại lệ.
"""

import os
import sys
import time
import signal
import logging
import threading
from datetime import datetime

# Đảm bảo UTF-8 cho console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from logging.handlers import RotatingFileHandler
import gc
import ctypes
import psutil

os.makedirs(os.path.join(os.path.dirname(__file__), "data"), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        RotatingFileHandler(os.path.join(os.path.dirname(__file__), "data", "bot_247.log"), maxBytes=2*1024*1024, backupCount=1, encoding="utf-8")
    ]
)
logger = logging.getLogger("MasterRunner")


def trim_memory():
    """Dọn dẹp triệt để RAM không dùng để bot luôn duy trì dưới 150MB trên Render 512MB."""
    gc.collect()
    try:
        if sys.platform != "win32":
            ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
TA_DIR = os.path.join(BASE_DIR, "TradingAgents")
if TA_DIR not in sys.path:
    sys.path.insert(0, TA_DIR)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from telegram_trading_bot import bot, run_telegram_polling, broadcast_message, portfolio, get_main_keyboard
from trading_scheduler import run_scheduler_loop

# Cờ dừng hệ thống
STOP_FLAG = threading.Event()


def handle_exit(signum, frame):
    logger.info("Nhận tín hiệu dừng chương trình (Ctrl+C)... Đang tắt các tiến trình...")
    STOP_FLAG.set()
    try:
        bot.stop_polling()
    except Exception:
        pass
    sys.exit(0)


import json
import socketserver
from http.server import HTTPServer, BaseHTTPRequestHandler

IS_CLOUD = sys.platform != "win32" or os.environ.get("IS_CLOUD", "").lower() in ("true", "1") or "RENDER" in os.environ or "PORT" in os.environ
RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://vnstock-trading-bot-247.onrender.com").rstrip("/")


class ThreadedHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True


class WebhookAndHealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/api/debug"):
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            proc = psutil.Process()
            rss_mb = round(proc.memory_info().rss / (1024 * 1024), 2)
            bot_info = {}
            try:
                me = bot.get_me()
                bot_info = {
                    "id": me.id,
                    "username": me.username,
                    "first_name": me.first_name,
                }
            except Exception as e:
                bot_info = {"error": str(e)}

            wh_info = {}
            try:
                wh = bot.get_webhook_info()
                wh_info = {
                    "url": wh.url,
                    "pending_update_count": wh.pending_update_count,
                    "last_error_message": wh.last_error_message
                }
            except Exception as e:
                wh_info = {"error": str(e)}

            debug_info = {
                "platform": sys.platform,
                "is_cloud": IS_CLOUD,
                "memory_rss_mb": rss_mb,
                "memory_limit_mb": 512,
                "memory_safe": rss_mb < 250,
                "threads": [t.name for t in threading.enumerate()],
                "bot": bot_info,
                "webhook": wh_info,
                "time": datetime.now().isoformat()
            }
            self.wfile.write(json.dumps(debug_info, indent=2).encode("utf-8"))
            return

        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        proc = psutil.Process()
        rss_mb = round(proc.memory_info().rss / (1024 * 1024), 1)
        bot_user = "@NinhstockTrading_bot"
        try:
            bot_user = f"@{bot.get_me().username}"
        except Exception:
            pass

        html = f"""
        <html>
        <head><title>VNStock Trading Bot 24/7</title></head>
        <body style="font-family: Arial, sans-serif; background: #0f172a; color: #f8fafc; padding: 40px; text-align: center;">
            <h1>🤖 VNStock Trading Bot 24/7</h1>
            <p style="color: #4ade80; font-size: 1.2rem; font-weight: bold;">● Hệ Thống Đang Vận Hành 24/7 Trên Cloud Render</p>
            <p>Telegram Bot: <b>{bot_user}</b></p>
            <p>RAM Tiến Trình: <b style="color: #38bdf8;">{rss_mb} MB / 512 MB</b> (Siêu nhẹ & An toàn tuyệt đối)</p>
            <p>Google Sheet: <a style="color: #38bdf8;" href="https://docs.google.com/spreadsheets/d/1mjYsI-sXYgqAaebNXJb8BA4hwLZWxh-Cqji8p_F-dwo/edit" target="_blank">Xem Bảng Tính Danh Mục</a></p>
            <p style="color: #94a3b8; font-size: 0.9rem; margin-top: 30px;">Tự động quét dòng tiền mỗi 15 phút & Khớp lệnh SL/TP kỷ luật.</p>
        </body>
        </html>
        """
        self.wfile.write(html.encode("utf-8"))

    def do_POST(self):
        """Tiếp nhận Webhook Update từ Telegram gửi về."""
        if self.path.startswith("/webhook"):
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else ""

                if body:
                    try:
                        update_dict = json.loads(body)
                        update = telebot.types.Update.de_json(update_dict)
                        if update:
                            threading.Thread(target=bot.process_new_updates, args=([update],), daemon=True).start()
                    except Exception as parse_err:
                        logger.warning(f"[Webhook] Lỗi parse payload: {parse_err}")

                self.send_response(200)
                self.send_header("Content-type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"OK")
            except Exception as e:
                logger.error(f"[Webhook Error] {e}")
                try:
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"OK")
                except Exception:
                    pass
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Tắt log spam HTTP request


def start_health_server():
    """Khởi động máy chủ Web đa luồng phục vụ Webhook và Health Check trên Render."""
    port = int(os.environ.get("PORT", 10000))
    if IS_CLOUD:
        def _run():
            try:
                server = ThreadedHTTPServer(("0.0.0.0", port), WebhookAndHealthHandler)
                logger.info(f"[Web Service] Webhook & Health server đang chạy trên cổng {port}...")
                server.serve_forever()
            except Exception as e:
                logger.warning(f"Không thể khởi động web health server: {e}")
        t = threading.Thread(target=_run, name="HealthServerThread", daemon=True)
        t.start()
        return t
    return None


def start_memory_watchdog_thread() -> threading.Thread:
    """Luồng giám sát RAM liên tục, tự động giải phóng khi bộ nhớ vượt quá ngưỡng an toàn."""
    def _worker():
        logger.info("[Luồng 3] Memory Watchdog khởi động (Đảm bảo RAM < 200MB / 512MB)...")
        while not STOP_FLAG.is_set():
            try:
                proc = psutil.Process()
                rss_mb = proc.memory_info().rss / (1024 * 1024)
                if rss_mb > 200:
                    logger.warning(f"⚠️ Bộ nhớ RAM ({rss_mb:.1f} MB) vượt 200MB. Kích hoạt thu hồi malloc_trim...")
                    trim_memory()
                    rss_after = proc.memory_info().rss / (1024 * 1024)
                    logger.info(f"✅ Đã dọn RAM: từ {rss_mb:.1f} MB xuống {rss_after:.1f} MB.")
                else:
                    trim_memory()
            except Exception as e:
                logger.warning(f"Lỗi memory watchdog: {e}")
            time.sleep(30)

    t = threading.Thread(target=_worker, name="MemoryWatchdogThread", daemon=True)
    t.start()
    return t


def start_telegram_thread() -> threading.Thread:
    """Khởi chạy Telegram Bot Polling 24/7 với cơ chế tự phục hồi."""
    def _worker():
        logger.info("[Luồng 1] Khởi động Telegram Bot Polling 24/7...")
        # Đảm bảo xóa sạch Webhook cũ để Polling nhận 100% tin nhắn
        try:
            bot.delete_webhook(drop_pending_updates=True)
            logger.info("[Luồng 1] Đã dọn dẹp Webhook cũ, sẵn sàng Polling trực tiếp từ Telegram.")
        except Exception as e:
            logger.warning(f"[Luồng 1] Xóa webhook: {e}")

        while not STOP_FLAG.is_set():
            try:
                try:
                    bot._TeleBot__stop_polling.clear()
                except Exception:
                    pass
                bot.infinity_polling(timeout=10, long_polling_timeout=5, logger_level=logging.ERROR)
            except Exception as e:
                logger.error(f"[Luồng 1] Telegram polling gặp lỗi: {e}. Thử kết nối lại sau 5 giây...")
                time.sleep(5)

    t = threading.Thread(target=_worker, name="TelegramPollingThread", daemon=True)
    t.start()
    return t


def start_scheduler_thread() -> threading.Thread:
    """Khởi chạy luồng Scheduler giám sát thị trường và danh mục."""
    def _worker():
        logger.info("[Luồng 2] Trading Scheduler 24/7 khởi động...")
        while not STOP_FLAG.is_set():
            try:
                run_scheduler_loop(interval_seconds=30)
            except Exception as e:
                logger.error(f"[Luồng 2] Scheduler gặp lỗi: {e}. Tự khởi động lại sau 10 giây...")
                time.sleep(10)

    t = threading.Thread(target=_worker, name="SchedulerThread", daemon=True)
    t.start()
    return t


import socket

SINGLETON_LOCK_SOCKET = None

def acquire_singleton_lock(port: int = 58999):
    """Đảm bảo chỉ duy nhất một phiên bản Bot 24/7 chạy để tránh xung đột Telegram getUpdates."""
    global SINGLETON_LOCK_SOCKET
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
        s.listen(1)
        SINGLETON_LOCK_SOCKET = s
        return True
    except socket.error:
        logger.warning(f"⚠️ Đã có một phiên bản Bot 24/7 khác đang chạy (Port {port} đã được dùng). Dừng phiên bản trùng lặp này.")
        sys.exit(0)


def main():
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    if not IS_CLOUD and "--force-local" not in sys.argv:
        try:
            import requests
            r = requests.get("https://vnstock-trading-bot-247.onrender.com", timeout=3)
            if r.status_code == 200:
                print("\n" + "=" * 65)
                print("   🤖 MYAGENT AUTO-TRADING 24/7 - CHỨNG KHOÁN VIỆT NAM 🇻🇳")
                print("   Telegram Bot : @NinhstockTrading_bot")
                print("=" * 65)
                print("   ✅ CLOUD RENDER ĐANG VẬN HÀNH BOT 24/7 TRÊN MẠNG!")
                print("   Bạn KHÔNG CẦN bật chương trình này trên PC.")
                print("   Bạn có thể TẮT MÁY TÍNH HOÀN TOÀN, bot vẫn trả lời 24/7 trên Telegram.")
                print("   (Nếu muốn chạy trên PC để debug thử nghiệm, gõ: python run_bot_247.py --force-local)")
                print("=" * 65 + "\n")
                sys.exit(0)
        except Exception:
            pass

    acquire_singleton_lock()

    print("=" * 65)
    print("   🤖 MYAGENT AUTO-TRADING 24/7 - CHỨNG KHOÁN VIỆT NAM 🇻🇳")
    print("   Telegram Bot : @NinhstockTrading_bot")
    print("   AI Engine    : Multi-Agent x Google Gemini 3.5 Flash")
    print("   Khởi động lúc: " + datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
    print("=" * 65)

    os.makedirs(os.path.join(BASE_DIR, "data"), exist_ok=True)

    # Gửi thông báo khởi động tới người dùng qua Telegram
    try:
        startup_msg = (
            "🚀 *[MYAGENT AUTO-TRADING 24/7 ĐÃ KHỞI ĐỘNG]* 🚀\n"
            f"⏰ *Thời gian:* `{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}`\n"
            "───────────────────\n"
            "• Hệ thống Multi-Agent AI giám sát thị trường 24/7 đã sẵn sàng.\n"
            "• Quét dòng tiền cá mập: *Mỗi 15 phút trong phiên (09:15 - 14:45)*\n"
            "• Quản lý danh mục: Tự động Stop Loss (-5%) & Take Profit (+15%)\n"
            "• Báo cáo tổng kết ngày: *15:15*\n"
            "• Chiến lược phiên mai: *20:00*\n\n"
            "👉 Gõ `/help` hoặc bấm các nút menu bên dưới để ra lệnh!"
        )
        broadcast_message(startup_msg, reply_markup=get_main_keyboard())
        logger.info("Đã gửi thông báo khởi động tới Telegram.")
    except Exception as e:
        logger.warning(f"Chưa thể gửi thông báo khởi động qua Telegram: {e}")

    # Khởi chạy các luồng công việc chính
    start_health_server()
    t_mem = start_memory_watchdog_thread()
    t_tele = start_telegram_thread()
    t_sched = start_scheduler_thread()

    # Vòng lặp Watchdog của luồng chính
    logger.info("Tất cả các luồng đã hoạt động. Hệ thống đang vận hành 24/7...")
    try:
        while not STOP_FLAG.is_set():
            time.sleep(10)
            # Kiểm tra trạng thái nếu có luồng bị chết bất thường thì hồi sinh
            if not t_tele.is_alive():
                logger.warning("Phát hiện luồng Telegram bị tắt! Đang hồi sinh luồng mới...")
                t_tele = start_telegram_thread()

            if not t_sched.is_alive():
                logger.warning("Phát hiện luồng Scheduler bị tắt! Đang hồi sinh luồng mới...")
                t_sched = start_scheduler_thread()

            if not t_mem.is_alive():
                logger.warning("Phát hiện luồng Memory Watchdog bị tắt! Đang hồi sinh luồng mới...")
                t_mem = start_memory_watchdog_thread()

    except (KeyboardInterrupt, SystemExit):
        handle_exit(None, None)


if __name__ == "__main__":
    main()
