# -*- coding: utf-8 -*-
"""
TRADING SCHEDULER 24/7 - CHỨNG KHOÁN VIỆT NAM
Tự động lập lịch giám sát thị trường và danh mục đầu tư theo thời gian thực:
1. TRONG PHIÊN (T2-T6: 09:15 - 11:30 & 13:00 - 14:45):
   - Mỗi 15 phút quét toàn bộ 60 cổ phiếu hàng đầu.
   - Bắn cảnh báo Telegram tức thì khi phát hiện Vol bùng nổ (>= 1.5x MA20) & Giá tăng mạnh.
   - Kiểm tra ngưỡng Stop Loss (-5%) và Take Profit (+15%) của danh mục, tự động khớp lệnh.
2. SAU PHIÊN (T2-T6 lúc 15:15):
   - Tổng kết thị trường và báo cáo biến động danh mục trong ngày.
3. BUỔI TỐI (T2-T6 lúc 20:00):
   - Tự động phân tích sâu cổ phiếu dẫn dắt dòng tiền số 1 thị trường, gửi kế hoạch hành động phiên sáng hôm sau.
"""

import os
import sys
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, Any

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
logger = logging.getLogger("TradingScheduler")

# Import các module liên quan
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
TA_DIR = os.path.join(BASE_DIR, "TradingAgents")
if TA_DIR not in sys.path:
    sys.path.insert(0, TA_DIR)

from smart_money_scanner import scan_smart_money, UNIVERSE_VN
from portfolio_manager import PortfolioManager
import yfinance as yf

# Import broadcast_message từ telegram bot
try:
    from telegram_trading_bot import broadcast_message, portfolio
except ImportError:
    portfolio = PortfolioManager()
    def broadcast_message(text: str, reply_markup=None):
        logger.info(f"[BROADCAST PREVIEW]\n{text}")


# Cấu hình Tự động Giao dịch (Auto-Trading: Tự Mua & Tự Bán)
AUTOTRADE_FILE = os.path.join(BASE_DIR, "data", "autotrade_config.json")

def get_autotrade_config() -> dict:
    default_cfg = {
        "enabled": True,
        "max_stocks_in_portfolio": 5,
        "allocation_pct_per_stock": 0.20,
        "max_capital_per_order": 100_000_000,
        "min_vol_ratio": 1.8,
        "min_price_change": 1.5,
        "min_turnover_billion": 15.0
    }
    if os.path.exists(AUTOTRADE_FILE):
        try:
            with open(AUTOTRADE_FILE, "r", encoding="utf-8") as f:
                return {**default_cfg, **json.load(f)}
        except Exception:
            pass
    return default_cfg

def set_autotrade_enabled(enabled: bool):
    cfg = get_autotrade_config()
    cfg["enabled"] = enabled
    os.makedirs(os.path.dirname(AUTOTRADE_FILE), exist_ok=True)
    with open(AUTOTRADE_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

# Bộ đệm để chống spam thông báo cho cùng một mã cổ phiếu (chỉ báo lại sau 90 phút)
LAST_ALERTED_TIME: Dict[str, datetime] = {}
THROTTLE_MINUTES = 90

# Biến cờ theo dõi việc gửi báo cáo định kỳ mỗi ngày
LAST_EOD_SENT_DATE: str = ""
LAST_EVENING_SENT_DATE: str = ""


def is_trading_day() -> bool:
    """Kiểm tra hôm nay có phải ngày giao dịch (Thứ 2 đến Thứ 6) hay không."""
    return datetime.now().weekday() < 5


def is_in_trading_session() -> bool:
    """
    Kiểm tra hiện tại có đang trong phiên giao dịch của sàn HOSE/HNX hay không.
    Phiên sáng: 09:15 - 11:30
    Phiên chiều: 13:00 - 14:45
    """
    if not is_trading_day():
        return False

    now = datetime.now().time()
    t_0915 = datetime.strptime("09:15", "%H:%M").time()
    t_1130 = datetime.strptime("11:30", "%H:%M").time()
    t_1300 = datetime.strptime("13:00", "%H:%M").time()
    t_1445 = datetime.strptime("14:45", "%H:%M").time()

    morning_session = t_0915 <= now <= t_1130
    afternoon_session = t_1300 <= now <= t_1445

    return morning_session or afternoon_session


def run_session_scan_and_alert():
    """
    Quét dòng tiền lớn trong phiên và gửi cảnh báo khẩn cấp tới Telegram.
    Đồng thời kiểm tra ngưỡng cắt lỗ / chốt lời danh mục.
    """
    now = datetime.now()
    time_str = now.strftime("%H:%M:%S")
    logger.info(f"[{time_str}] Bắt đầu chu kỳ quét dòng tiền trong phiên...")

    try:
        # 1. Quét dòng tiền lớn
        hot_stocks = scan_smart_money(
            min_vol_ratio=1.5,
            min_price_change=1.0,
            min_turnover_billion=10.0,
            top_n=5
        )

        alert_items = []
        for stock in hot_stocks:
            ticker = stock["ticker"]
            last_alert = LAST_ALERTED_TIME.get(ticker)
            if last_alert and (now - last_alert).total_seconds() < THROTTLE_MINUTES * 60:
                continue  # Bỏ qua nếu đã thông báo gần đây

            LAST_ALERTED_TIME[ticker] = now
            alert_items.append(stock)

        # Nếu có mã bùng nổ mới -> Gửi cảnh báo khẩn Telegram
        if alert_items:
            msg = (
                f"🚨 *[CẢNH BÁO DÒNG TIỀN CÁ MẬP VÀO PHIÊN]* 🚨\n"
                f"⏰ *Thời gian:* `{time_str}` (Ngày {now.strftime('%d/%m/%Y')})\n"
                f"───────────────────\n"
                f"Phát hiện *{len(alert_items)} mã* bùng nổ thanh khoản và giá tăng mạnh:\n\n"
            )

            for i, item in enumerate(alert_items, 1):
                msg += (
                    f"*{i}. {item['ticker']}*: `{item['price']:,.0f} VND` (*+{item['price_change_pct']:.2f}%*)\n"
                    f"   • Khối lượng: `{item['volume']:,.0f}` cp (*{item['vol_ratio']:.2f}x* MA20)\n"
                    f"   • Giá trị: `{item['turnover_billion']:,.1f} tỷ VND`\n"
                    f"   • Tín hiệu: *{item['trend_signal']}*\n"
                    f"   👉 *Lệnh nhanh:* `/buy {item['ticker']} 1000 ngan` | Gõ `{item['ticker']}` xem AI\n\n"
                )

            msg += "───────────────────\n💡 *Khuyến nghị:* Mua đón sóng dòng tiền, tuân thủ T+2.5 và SL -5%."
            broadcast_message(msg)
            logger.info(f"Đã phát cảnh báo dòng tiền cho {len(alert_items)} mã: {[x['ticker'] for x in alert_items]}")

        # Đồng bộ lịch sử quét bùng nổ dòng tiền lên Google Sheets
        try:
            from trading_sheet_sync import sheet_sync
            if hot_stocks:
                sheet_sync.log_scanner_to_sheet(hot_stocks)
        except Exception:
            pass

        # 1.1 TỰ ĐỘNG GIẢI NGÂN MUA (AUTO-BUY) NẾU BẬT CHẾ ĐỘ AUTO-TRADING
        cfg = get_autotrade_config()
        if cfg.get("enabled") and alert_items:
            current_holdings = set(portfolio.data.get("short_term_positions", {}).keys()) | set(portfolio.data.get("long_term_positions", {}).keys())
            max_stocks = cfg.get("max_stocks_in_portfolio", 5)

            for stock in alert_items:
                ticker = stock["ticker"]
                if ticker in current_holdings:
                    continue
                if len(current_holdings) >= max_stocks:
                    break

                # Điều kiện lọc cổ phiếu có dòng tiền bùng nổ thực sự
                if stock["vol_ratio"] >= cfg.get("min_vol_ratio", 1.8) and stock["price_change_pct"] >= cfg.get("min_price_change", 1.5):
                    available_cash = portfolio.data.get("cash", 0)
                    if available_cash < 15_000_000:
                        break

                    target_invest = min(
                        available_cash * cfg.get("allocation_pct_per_stock", 0.20),
                        cfg.get("max_capital_per_order", 100_000_000)
                    )
                    price = stock["price"]
                    if price <= 0:
                        continue

                    # Làm tròn số lượng cổ phiếu theo lô 100 chuẩn HOSE/HNX
                    raw_shares = int(target_invest // (price * 1.0015))
                    shares = (raw_shares // 100) * 100

                    if shares >= 100:
                        res = portfolio.buy(
                            ticker=ticker,
                            price=price,
                            shares=shares,
                            portfolio_type="short_term",
                            rationale=f"Auto-Trading: Dòng tiền nổ {stock['vol_ratio']:.1f}x MA20, Giá +{stock['price_change_pct']:.1f}%"
                        )
                        if res.get("success"):
                            current_holdings.add(ticker)
                            auto_buy_msg = (
                                f"🤖 *[AUTO-TRADING: TỰ ĐỘNG KHỚP LỆNH MUA]* 🤖\n"
                                f"───────────────────\n"
                                f"Hệ thống đã tự động mua gom theo dòng tiền cá mập:\n"
                                f"• *Mã cổ phiếu:* `{ticker}`\n"
                                f"• *Khối lượng:* `{shares:,} cp` (Lô 100)\n"
                                f"• *Giá khớp:* `{price:,.0f} VND`\n"
                                f"• *Tổng vốn:* `{(price * shares * 1.0015):,.0f} VND`\n"
                                f"• *Kỷ luật:* Cắt lỗ -5% | Chốt lời +15% | Hàng về T+2.5\n"
                                f"• *Google Sheets:* Đã lưu vào Sheet & Drive trực tiếp!\n"
                                f"👉 Xem bảng tính online: gõ `/sheet`"
                            )
                            broadcast_message(auto_buy_msg)
                            logger.info(f"Auto-Buy thành công: {ticker} {shares} cp")

        # 2. Kiểm tra Cắt lỗ (-5%) và Chốt lời (+15%) cho danh mục
        positions = list(portfolio.data.get("short_term_positions", {}).keys()) + list(portfolio.data.get("long_term_positions", {}).keys())
        if positions:
            yf_symbols = [f"{t}.VN" for t in positions]
            try:
                df = yf.download(yf_symbols, period="2d", progress=False)["Close"]
                price_map = {}
                for t in positions:
                    sym = f"{t}.VN"
                    if sym in df:
                        s = df[sym].dropna()
                        if not s.empty:
                            price_map[t] = float(s.iloc[-1])

                sl_tp_alerts = portfolio.check_sl_tp(price_map)
                for alert in sl_tp_alerts:
                    broadcast_message(alert["message"])
                    logger.info(f"Kích hoạt SL/TP: {alert['message']}")
            except Exception as e:
                logger.error(f"Lỗi kiểm tra SL/TP danh mục: {e}")

    except Exception as e:
        logger.error(f"Lỗi trong chu kỳ quét phiên: {e}", exc_info=True)


def check_and_run_eod_summary():
    """Gửi tổng kết thị trường và tình trạng danh mục cuối ngày lúc 15:15."""
    global LAST_EOD_SENT_DATE
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")

    if not is_trading_day() or LAST_EOD_SENT_DATE == today_str:
        return

    # Kiểm tra thời gian từ 15:15 đến 16:30
    t_1515 = datetime.strptime("15:15", "%H:%M").time()
    t_1630 = datetime.strptime("16:30", "%H:%M").time()

    if t_1515 <= now.time() <= t_1630:
        logger.info("Bắt đầu tạo bản tin tổng kết kết phiên 15:15...")
        try:
            summary = portfolio.get_summary()
            eod_msg = (
                "🏁 *[TỔNG KẾT PHIÊN GIAO DỊCH HÔM NAY]* 🏁\n"
                f"📅 *Ngày:* `{now.strftime('%d/%m/%Y')}`\n"
                "───────────────────\n\n"
                f"{summary}\n\n"
                "📌 *Kế hoạch phiên tiếp theo:* AI sẽ rà soát cơ hội gom hàng lúc 20:00 tối nay."
            )
            broadcast_message(eod_msg)
            LAST_EOD_SENT_DATE = today_str
            logger.info("Đã gửi thành công tổng kết phiên 15:15.")
        except Exception as e:
            logger.error(f"Lỗi gửi tổng kết phiên: {e}")


def check_and_run_evening_strategy():
    """Phân tích sâu mã dòng tiền số 1 thị trường lúc 20:00 tối để chuẩn bị cho phiên mai."""
    global LAST_EVENING_SENT_DATE
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")

    if not is_trading_day() or LAST_EVENING_SENT_DATE == today_str:
        return

    # Kiểm tra thời gian từ 20:00 đến 21:00
    t_2000 = datetime.strptime("20:00", "%H:%M").time()
    t_2100 = datetime.strptime("21:00", "%H:%M").time()

    if t_2000 <= now.time() <= t_2100:
        logger.info("Bắt đầu tạo bản tin chiến lược buổi tối 20:00...")
        try:
            # Quét tìm mã dẫn đầu dòng tiền hôm nay
            top_stocks = scan_smart_money(min_vol_ratio=1.2, min_price_change=0.5, top_n=3)
            if top_stocks:
                best_stock = top_stocks[0]
                ticker = best_stock["ticker"]

                strategy_msg = (
                    f"🌙 *[BẢN TIN CHIẾN LƯỢC TỐI & KẾ HOẠCH PHIÊN MAI]* 🌙\n"
                    f"📅 *Ngày chuẩn bị:* `{now.strftime('%d/%m/%Y')}`\n"
                    f"───────────────────\n"
                    f"🔥 *Cổ phiếu Tiêu điểm Dòng tiền:* *{ticker}*\n"
                    f"• Giá đóng cửa: `{best_stock['price']:,.0f} VND` (+{best_stock['price_change_pct']:.2f}%)\n"
                    f"• Khối lượng bùng nổ: `{best_stock['vol_ratio']:.2f}x` bình quân 20 phiên\n"
                    f"• Giá trị dòng tiền lớn: `{best_stock['turnover_billion']:,.1f} tỷ VND`\n"
                    f"• Tín hiệu kỹ thuật: *{best_stock['trend_signal']}*\n"
                    f"───────────────────\n"
                    f"🎯 *Kế hoạch giải ngân phiên mai:*\n"
                    f"• Vùng giá canh mua: `{best_stock['price'] * 0.99:,.0f} - {best_stock['price'] * 1.01:,.0f} VND`\n"
                    f"• Mục tiêu chốt lời (TP): `{best_stock['price'] * 1.15:,.0f} VND` (+15%)\n"
                    f"• Cắt lỗ dứt khoát (SL): `{best_stock['price'] * 0.95:,.0f} VND` (-5%)\n"
                    f"• Tỷ trọng khuyến nghị: Tối đa 20-30% tổng tài sản lướt sóng T+2.5.\n\n"
                    f"👉 *Để xem phân tích chi tiết cơ bản & tin tức, hãy gửi tin nhắn `{ticker}` cho bot!*"
                )
                broadcast_message(strategy_msg)
                LAST_EVENING_SENT_DATE = today_str
                logger.info(f"Đã gửi thành công chiến lược tối cho mã {ticker}.")
        except Exception as e:
            logger.error(f"Lỗi tạo chiến lược tối: {e}")


def run_scheduler_loop(interval_seconds: int = 60):
    """Vòng lặp chính của trình lập lịch chạy nền 24/7."""
    logger.info("=== TRADING SCHEDULER 24/7 ĐÃ ĐƯỢC KHỞI TẠO ===")
    logger.info("• Theo dõi phiên giao dịch (T2-T6: 09:15-11:30 & 13:00-14:45)")
    logger.info("• Báo cáo tổng kết phiên lúc 15:15")
    logger.info("• Bản tin chiến lược sáng mai lúc 20:00")

    last_session_scan = datetime.min

    while True:
        try:
            now = datetime.now()

            # 1. Kiểm tra nếu đang trong phiên giao dịch
            if is_in_trading_session():
                # Quét mỗi 15 phút một lần
                if (now - last_session_scan).total_seconds() >= 15 * 60:
                    run_session_scan_and_alert()
                    last_session_scan = now

            # 2. Kiểm tra báo cáo kết phiên 15:15
            check_and_run_eod_summary()

            # 3. Kiểm tra bản tin chiến lược tối 20:00
            check_and_run_evening_strategy()

        except Exception as e:
            logger.error(f"Lỗi trong vòng lặp scheduler: {e}", exc_info=True)

        time.sleep(interval_seconds)


if __name__ == "__main__":
    run_scheduler_loop(interval_seconds=30)
