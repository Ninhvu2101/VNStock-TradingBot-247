# -*- coding: utf-8 -*-
"""
GOOGLE SHEETS & GOOGLE DRIVE SYNC - VNSTOCK AUTO-TRADING
Đồng bộ dữ liệu giao dịch tự động lên Google Sheets và Google Drive:
1. Tab `Trading_Portfolio`: Danh mục cổ phiếu đang nắm giữ (Giá vốn, giá thị trường, % Lãi/Lỗ, ngày về T+2.5).
2. Tab `Trading_Orders`: Nhật ký toàn bộ lệnh mua/bán tự động (Lịch sử chốt lời, cắt lỗ, thuế phí).
3. Tab `Smart_Money_Scanner`: Danh sách các mã có dòng tiền cá mập vào mạnh trong phiên.
4. Tự động xuất file CSV lưu trữ và đồng bộ lên Google Drive.
"""

import os
import sys
import json
import csv
import io
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
import requests

# Đảm bảo UTF-8 cho console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

logger = logging.getLogger("TradingSheetSync")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

WEBAPP_URL = os.getenv("APPSHEET_WEBAPP_URL", "").strip()
SPREADSHEET_ID = os.getenv("APPSHEET_SPREADSHEET_ID", "1NZl2d8XaOD1COe6Qg1xb-7qn8SD9PKdGTTPJ7AUH2PE").strip()
SECRET_KEY = os.getenv("CLOUD_SCRIPT_SECRET", "MyAgentSecret_2026_KeyX").strip()

PORTFOLIO_COLUMNS = [
    "Mã CP", "Danh Mục", "Khối Lượng", "Giá Vốn (VND)", "Tổng Vốn (VND)",
    "Giá Hiện Tại (VND)", "Giá Trị TT (VND)", "Lãi/Lỗ (VND)", "% Lãi/Lỗ",
    "Ngưỡng Cắt Lỗ (-5%)", "Mục Tiêu Chốt Lời (+15%)", "Ngày Mua", "Ngày Hàng Về (T+2.5)", "Trạng Thái Hàng"
]

ORDERS_COLUMNS = [
    "Thời Gian", "Mã CP", "Lệnh", "Khối Lượng", "Giá Khớp (VND)",
    "Tổng Giá Trị (VND)", "Lãi/Lỗ (VND)", "% Lãi/Lỗ", "Danh Mục", "Lý Do Thực Hiện"
]

SCANNER_COLUMNS = [
    "Thời Gian Quét", "Mã CP", "Giá Hiện Tại (VND)", "% Biến Động",
    "Khối Lượng Khớp", "Đột Biến Vol (x MA20)", "Giá Trị (Tỷ VND)", "Tín Hiệu Xu Hướng"
]


class TradingSheetSync:
    def __init__(self, webapp_url: Optional[str] = None, spreadsheet_id: Optional[str] = None):
        self.webapp_url = webapp_url or WEBAPP_URL
        self.spreadsheet_id = spreadsheet_id or SPREADSHEET_ID
        self.secret_key = SECRET_KEY
        self.sheet_url = f"https://docs.google.com/spreadsheets/d/{self.spreadsheet_id}/edit"
        self.data_dir = os.path.join(BASE_DIR, "data")
        os.makedirs(self.data_dir, exist_ok=True)

    def get_sheet_link(self) -> str:
        """Trả về đường link trực tiếp tới Google Sheet trên Google Drive."""
        return self.sheet_url

    def sync_portfolio_to_sheet(self, portfolio_data: Dict[str, Any], current_prices: Optional[Dict[str, float]] = None) -> bool:
        """Đồng bộ danh mục đang nắm giữ lên Google Sheets và xuất CSV lưu Google Drive."""
        current_prices = current_prices or {}
        today_str = datetime.now().strftime("%Y-%m-%d")
        rows = []

        # 1. Danh mục Ngắn hạn
        for ticker, pos in portfolio_data.get("short_term_positions", {}).items():
            cur_p = current_prices.get(ticker) or pos["avg_price"]
            cost_val = pos["avg_price"] * pos["shares"]
            market_val = cur_p * pos["shares"]
            pnl = market_val - cost_val
            pnl_pct = (pnl / cost_val) * 100.0 if cost_val > 0 else 0.0
            status_t = "✅ Sẵn sàng bán" if today_str >= pos.get("available_date", "") else f"⏳ Đang về ({pos.get('available_date')})"

            rows.append([
                ticker, "Ngắn hạn (T+2.5)", pos["shares"], round(pos["avg_price"], 0),
                round(cost_val, 0), round(cur_p, 0), round(market_val, 0),
                round(pnl, 0), round(pnl_pct, 2),
                round(pos.get("stop_loss", pos["avg_price"] * 0.95), 0),
                round(pos.get("take_profit", pos["avg_price"] * 1.15), 0),
                pos.get("buy_date", ""), pos.get("available_date", ""), status_t
            ])

        # 2. Danh mục Dài hạn
        for ticker, pos in portfolio_data.get("long_term_positions", {}).items():
            cur_p = current_prices.get(ticker) or pos["avg_price"]
            cost_val = pos["avg_price"] * pos["shares"]
            market_val = cur_p * pos["shares"]
            pnl = market_val - cost_val
            pnl_pct = (pnl / cost_val) * 100.0 if cost_val > 0 else 0.0

            rows.append([
                ticker, "Dài hạn (Tích sản)", pos["shares"], round(pos["avg_price"], 0),
                round(cost_val, 0), round(cur_p, 0), round(market_val, 0),
                round(pnl, 0), round(pnl_pct, 2),
                "-", round(pos.get("target_price", pos["avg_price"] * 1.3), 0),
                pos.get("buy_date", ""), pos.get("available_date", ""), "✅ Nắm giữ"
            ])

        # Lưu file CSV cục bộ
        csv_path = os.path.join(self.data_dir, "Trading_Portfolio.csv")
        try:
            with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(PORTFOLIO_COLUMNS)
                writer.writerows(rows)
        except Exception as e:
            logger.warning(f"Lỗi lưu file CSV danh mục: {e}")

        # Gửi lên Google Apps Script WebApp
        if self.webapp_url:
            try:
                payload = {
                    "action": "sync_sheet",
                    "sheet_name": "Trading_Portfolio",
                    "columns": PORTFOLIO_COLUMNS,
                    "rows": rows,
                    "secret": self.secret_key
                }
                res = requests.post(self.webapp_url, json=payload, timeout=15)
                if res.status_code == 200:
                    logger.info(f"Đã đồng bộ {len(rows)} vị thế lên Google Sheet [Trading_Portfolio]")
                    return True
            except Exception as e:
                logger.error(f"Lỗi gửi dữ liệu lên Google Sheets: {e}")

        return False

    def log_order_to_sheet(self, order_data: Dict[str, Any]) -> bool:
        """Ghi nhận một lệnh Mua/Bán mới vào nhật ký Google Sheets và CSV."""
        now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        row = [
            now_str,
            order_data.get("ticker", ""),
            order_data.get("action", "MUA"),
            order_data.get("shares", 0),
            round(order_data.get("price", 0), 0),
            round(order_data.get("total_value", 0), 0),
            round(order_data.get("pnl", 0), 0),
            round(order_data.get("pnl_pct", 0), 2),
            order_data.get("portfolio_type", "Ngắn hạn"),
            order_data.get("rationale", "")
        ]

        # Ghi vào CSV cục bộ
        csv_path = os.path.join(self.data_dir, "Trading_Orders.csv")
        file_exists = os.path.exists(csv_path)
        try:
            with open(csv_path, "a", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(ORDERS_COLUMNS)
                writer.writerow(row)
        except Exception as e:
            logger.warning(f"Lỗi ghi CSV đơn hàng: {e}")

        # Gửi lên Google Apps Script WebApp
        if self.webapp_url:
            try:
                payload = {
                    "action": "append_row",
                    "sheet_name": "Trading_Orders",
                    "columns": ORDERS_COLUMNS,
                    "row": row,
                    "secret": self.secret_key
                }
                res = requests.post(self.webapp_url, json=payload, timeout=15)
                if res.status_code == 200:
                    logger.info(f"Đã ghi lệnh {order_data.get('action')} {order_data.get('ticker')} lên Google Sheet [Trading_Orders]")
                    return True
            except Exception as e:
                logger.error(f"Lỗi ghi lệnh lên Google Sheets: {e}")

        return False

    def log_scanner_to_sheet(self, hot_stocks: List[Dict[str, Any]]) -> bool:
        """Ghi nhận danh sách cổ phiếu bùng nổ dòng tiền vào Google Sheets."""
        if not hot_stocks:
            return False

        now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        rows = []
        for s in hot_stocks:
            rows.append([
                now_str,
                s.get("ticker", ""),
                round(s.get("price", 0), 0),
                round(s.get("price_change_pct", 0), 2),
                round(s.get("volume", 0), 0),
                round(s.get("vol_ratio", 0), 2),
                round(s.get("turnover_billion", 0), 1),
                s.get("trend_signal", "")
            ])

        if self.webapp_url:
            try:
                payload = {
                    "action": "sync_sheet",
                    "sheet_name": "Smart_Money_Alerts",
                    "columns": SCANNER_COLUMNS,
                    "rows": rows,
                    "secret": self.secret_key
                }
                res = requests.post(self.webapp_url, json=payload, timeout=15)
                if res.status_code == 200:
                    logger.info(f"Đã đồng bộ {len(rows)} mã bùng nổ lên Google Sheet [Smart_Money_Alerts]")
                    return True
            except Exception as e:
                logger.error(f"Lỗi đồng bộ scanner lên Google Sheets: {e}")

        return False


# Tạo instance dùng chung
sheet_sync = TradingSheetSync()

if __name__ == "__main__":
    print(f"TradingSheetSync Initialized!")
    print(f"Spreadsheet URL: {sheet_sync.get_sheet_link()}")
    # Test sync sample
    sample_portfolio = {
        "short_term_positions": {
            "HPG": {
                "shares": 1000, "avg_price": 28500, "buy_date": "2026-09-18",
                "available_date": "2026-09-22", "stop_loss": 27000, "take_profit": 32500
            }
        },
        "long_term_positions": {}
    }
    sheet_sync.sync_portfolio_to_sheet(sample_portfolio, {"HPG": 29100})
