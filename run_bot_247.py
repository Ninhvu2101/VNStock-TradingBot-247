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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(os.path.dirname(__file__), "data", "bot_247.log"), encoding="utf-8")
    ]
)
logger = logging.getLogger("MasterRunner")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
TA_DIR = os.path.join(BASE_DIR, "TradingAgents")
if TA_DIR not in sys.path:
    sys.path.insert(0, TA_DIR)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from telegram_trading_bot import bot, run_telegram_polling, broadcast_message, portfolio
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


def start_telegram_thread() -> threading.Thread:
    """Khởi chạy luồng Telegram Bot với cơ chế tự phục hồi."""
    def _worker():
        logger.info("[Luồng 1] Telegram Bot polling khởi động...")
        try:
            bot.delete_webhook(drop_pending_updates=True)
        except Exception:
            pass
        while not STOP_FLAG.is_set():
            try:
                bot.infinity_polling(timeout=20, long_polling_timeout=15)
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

    acquire_singleton_lock()

    print("=" * 65)
    print("   🤖 MYAGENT AUTO-TRADING 24/7 - CHỨNG KHOÁN VIỆT NAM 🇻🇳")
    print("   Telegram Bot : @NinhVNStock_bot")
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
        broadcast_message(startup_msg)
        logger.info("Đã gửi thông báo khởi động tới Telegram.")
    except Exception as e:
        logger.warning(f"Chưa thể gửi thông báo khởi động qua Telegram: {e}")

    # Khởi chạy 2 luồng công việc chính
    t_tele = start_telegram_thread()
    t_sched = start_scheduler_thread()

    # Vòng lặp Watchdog của luồng chính
    logger.info("Cả 2 luồng đã hoạt động. Hệ thống đang vận hành 24/7...")
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

    except (KeyboardInterrupt, SystemExit):
        handle_exit(None, None)


if __name__ == "__main__":
    main()
