# -*- coding: utf-8 -*-
"""
CHƯƠNG TRÌNH PHÂN TÍCH ĐẦU TƯ CHỨNG KHOÁN VIỆT NAM (MULTI-AGENT AI)
Sử dụng TauricResearch/TradingAgents kết hợp mô hình Google Gemini 3.6 Flash.
Tự động áp dụng luật T+2.5, biên độ trần/sàn HOSE/HNX/UPCoM và quét tin tức báo chí VN.
"""

import os
import sys
import argparse
from datetime import datetime, timedelta

# Đảm bảo UTF-8 cho console Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Thêm thư viện TradingAgents vào sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
TA_DIR = os.path.join(BASE_DIR, "TradingAgents")
if TA_DIR not in sys.path:
    sys.path.insert(0, TA_DIR)

# Thiết lập biến môi trường mặc định
os.environ["TRADINGAGENTS_DEFAULT_MARKET"] = "VN"

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

# Nạp Gemini API Key từ keys_valid.txt nếu chưa có trong env
if not os.environ.get("GOOGLE_API_KEY") and not os.environ.get("GEMINI_API_KEY"):
    keys_file = os.path.join(PROJECT_ROOT, "keys_valid.txt")
    if os.path.exists(keys_file):
        with open(keys_file, "r", encoding="utf-8") as f:
            for line in f:
                k = line.strip()
                if k and not k.startswith("#"):
                    os.environ["GOOGLE_API_KEY"] = k
                    break

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph


def send_telegram_alert(message: str) -> bool:
    """Gửi tóm tắt phân tích tới Telegram của người dùng."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False

    try:
        import requests
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        # Cắt ngắn nếu vượt quá giới hạn 4096 ký tự của Telegram
        if len(message) > 4000:
            message = message[:3950] + "\n\n...(Báo cáo chi tiết xem tại thư mục output/stock_reports)"
        
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }
        res = requests.post(url, json=payload, timeout=10)
        return res.status_code == 200
    except Exception as e:
        print(f"[Cảnh báo] Không thể gửi tin nhắn Telegram: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Phân tích cổ phiếu Việt Nam bằng AI Multi-Agent")
    parser.add_argument("ticker", nargs="?", default=None, help="Mã cổ phiếu (ví dụ: HPG, FPT, VNM, SSI)")
    parser.add_argument("--date", default=None, help="Ngày phân tích (YYYY-MM-DD), mặc định là ngày hôm nay")
    parser.add_argument("--rounds", type=int, default=1, help="Số vòng tranh biện Bull vs Bear (mặc định: 1)")
    args = parser.parse_args()

    # Nhập mã cổ phiếu nếu chưa truyền qua command line
    ticker = args.ticker
    if not ticker:
        print("=" * 65)
        print("   HỆ THỐNG PHÂN TÍCH CHỨNG KHOÁN VIỆT NAM - MULTI-AGENT AI")
        print("=" * 65)
        ticker = input("Nhập mã cổ phiếu cần phân tích (ví dụ: HPG, FPT, VNM): ").strip().upper()

    if not ticker:
        print("Lỗi: Mã cổ phiếu không được để trống!")
        sys.exit(1)

    ticker = ticker.upper().strip()
    if not ticker.endswith(".VN") and not ticker.startswith("^"):
        ticker = f"{ticker}.VN"

    if args.date:
        curr_date = args.date
    else:
        now = datetime.now()
        if now.weekday() == 5:
            curr_date = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        elif now.weekday() == 6:
            curr_date = (now - timedelta(days=2)).strftime("%Y-%m-%d")
        else:
            curr_date = now.strftime("%Y-%m-%d")

    output_dir = os.path.join(PROJECT_ROOT, "output", "stock_reports")
    os.makedirs(output_dir, exist_ok=True)

    print(f"\n[*] Đang khởi tạo hệ thống phân tích...")
    print(f"[*] Mã cổ phiếu: {ticker}")
    print(f"[*] Ngày phân tích (phiên giao dịch gần nhất): {curr_date}")
    print(f"[*] Mô hình AI: Google Gemini 3.5 Flash (Ngôn ngữ: Tiếng Việt)")
    print(f"[*] Ràng buộc thị trường: Chu kỳ T+2.5, Không bán khống cơ sở, Biên độ trần/sàn")
    print("-" * 65)

    # Cấu hình TradingAgents
    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = "google"
    config["deep_think_llm"] = "gemini-3.5-flash"
    config["quick_think_llm"] = "gemini-3.5-flash"
    config["output_language"] = "Vietnamese"
    config["max_debate_rounds"] = args.rounds
    config["max_risk_discuss_rounds"] = args.rounds
    config["results_dir"] = output_dir

    try:
        # Bỏ qua social analyst (Reddit/StockTwits chỉ áp dụng cho mã chứng khoán Mỹ)
        ta = TradingAgentsGraph(
            selected_analysts=("market", "news", "fundamentals"),
            debug=True,
            config=config,
        )
        print("[*] Đang kích hoạt 5 tầng Agent (Analyst -> Research Debate -> Trader -> Risk -> Portfolio)...")
        print("[*] Vui lòng đợi trong giây lát...\n")

        state, decision = ta.propagate(ticker, curr_date)

        clean_symbol = ticker.replace(".VN", "")
        report_file = os.path.join(output_dir, f"{clean_symbol}_{curr_date}.md")
        
        report_content = f"# BÁO CÁO PHÂN TÍCH ĐẦU TƯ: {clean_symbol}\n"
        report_content += f"- **Ngày phân tích:** {curr_date}\n"
        report_content += f"- **Thị trường:** Chứng khoán Việt Nam (HOSE/HNX)\n"
        report_content += f"- **Công nghệ:** TauricResearch Multi-Agent (LangGraph x Gemini)\n\n"
        report_content += "---\n\n"
        report_content += f"## QUYẾT ĐỊNH & KHUYẾN NGHỊ CUỐI CÙNG:\n\n{decision}\n\n"

        # Bổ sung các báo cáo chi tiết của Analyst và Debate nếu có trong state
        if isinstance(state, dict):
            if state.get("market_report"):
                report_content += f"\n---\n## 1. Báo cáo Phân tích Kỹ thuật & Thị trường:\n{state['market_report']}\n"
            if state.get("fundamentals_report"):
                report_content += f"\n---\n## 2. Báo cáo Phân tích Cơ bản:\n{state['fundamentals_report']}\n"
            if state.get("news_report"):
                report_content += f"\n---\n## 3. Báo cáo Tin tức & Sự kiện:\n{state['news_report']}\n"
            if state.get("sentiment_report"):
                report_content += f"\n---\n## 4. Báo cáo Tâm lý & Dòng tiền:\n{state['sentiment_report']}\n"
            if state.get("investment_plan"):
                report_content += f"\n---\n## 5. Kế hoạch Tranh biện Bull/Bear:\n{state['investment_plan']}\n"

        with open(report_file, "w", encoding="utf-8") as f:
            f.write(report_content)

        print("\n" + "=" * 65)
        print(f"   KẾT QUẢ KHUYẾN NGHỊ CHO {clean_symbol} (NGÀY {curr_date}):")
        print("=" * 65)
        print(decision)
        print("-" * 65)
        print(f"[OK] Báo cáo đầy đủ đã được lưu tại:")
        print(f"     {report_file}")

        # Gửi tóm tắt về Telegram
        tele_msg = (
            f"📊 *TÍN HIỆU ĐẦU TƯ CỔ PHIẾU: {clean_symbol}*\n"
            f"📅 *Ngày:* {curr_date}\n"
            f"🤖 *Hệ thống:* TradingAgents VN (Multi-Agent AI)\n\n"
            f"📌 *Khuyến nghị:*\n{decision[:1200]}\n\n"
            f"📁 *Báo cáo file:* `output/stock_reports/{clean_symbol}_{curr_date}.md`"
        )
        if send_telegram_alert(tele_msg):
            print(f"[OK] Đã gửi thông báo khuyến nghị tới Telegram thành công!")

    except Exception as e:
        print(f"\n[Lỗi trong quá trình chạy phân tích]: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
