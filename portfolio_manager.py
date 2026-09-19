# -*- coding: utf-8 -*-
"""
MODULE QUẢN LÝ DANH MỤC & TỰ ĐỘNG GIAO DỊCH (PORTFOLIO MANAGER)
Tuân thủ 100% quy tắc Thị trường Chứng khoán Việt Nam:
1. Chu kỳ thanh toán T+2.5 (mua T+0 -> chiều T+2 mới được bán).
2. Phí giao dịch (0.15%) và Thuế thu nhập bán chứng khoán (0.1%).
3. Tự động chia 2 danh mục:
   - Ngắn hạn (Lướt sóng T+, Stoploss -5%, Target +12% đến +18%).
   - Dài hạn (Tích sản doanh nghiệp tốt, P/E thấp, tăng trưởng cao).
4. Tự động kiểm tra ngưỡng Cắt lỗ / Chốt lời theo thời gian thực.
"""

import os
import sys
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import yfinance as yf

# Đảm bảo UTF-8 cho console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

PORTFOLIO_FILE = os.path.join(os.path.dirname(__file__), "data", "portfolio.json")
FEE_RATE = 0.0015  # Phí giao dịch 0.15%
TAX_RATE = 0.0010  # Thuế bán 0.10%

try:
    from trading_sheet_sync import sheet_sync
except Exception:
    sheet_sync = None


def _get_settlement_date(trade_date: str) -> str:
    """Tính ngày cổ phiếu về tài khoản (T+2) theo lịch làm việc Việt Nam (bỏ qua T7, CN)."""
    dt = datetime.strptime(trade_date, "%Y-%m-%d")
    days_added = 0
    while days_added < 2:
        dt += timedelta(days=1)
        if dt.weekday() < 5:  # Thứ 2 đến Thứ 6
            days_added += 1
    return dt.strftime("%Y-%m-%d")


class PortfolioManager:
    def __init__(self, storage_path: str = PORTFOLIO_FILE):
        self.storage_path = storage_path
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        self.data = self._load()

    def _load(self) -> Dict[str, Any]:
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[Cảnh báo] Lỗi đọc file portfolio, khởi tạo mới: {e}")

        # Khởi tạo mặc định: Vốn ban đầu 500,000,000 VNĐ
        return {
            "initial_capital": 500_000_000,
            "cash": 500_000_000,
            "short_term_positions": {},  # {ticker: {shares, avg_price, buy_date, available_date, stop_loss, take_profit}}
            "long_term_positions": {},   # {ticker: {shares, avg_price, buy_date, target_price}}
            "history": []                # Danh sách các lệnh đã đóng
        }

    def _save(self) -> None:
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def buy(
        self,
        ticker: str,
        price: float,
        shares: int,
        portfolio_type: str = "short_term",
        stop_loss_pct: float = 5.0,
        take_profit_pct: float = 15.0,
        rationale: str = ""
    ) -> Dict[str, Any]:
        """Thực hiện mở vị thế Mua (Long) cổ phiếu."""
        clean_ticker = ticker.upper().replace(".VN", "").strip()
        trade_date = datetime.now().strftime("%Y-%m-%d")
        total_cost = (price * shares) * (1.0 + FEE_RATE)

        if total_cost > self.data["cash"]:
            return {
                "success": False,
                "message": f"Số dư tiền mặt không đủ! Cần {total_cost:,.0f} VND nhưng chỉ còn {self.data['cash']:,.0f} VND."
            }

        # Trừ tiền mặt
        self.data["cash"] -= total_cost
        available_date = _get_settlement_date(trade_date)
        stop_loss_price = round(price * (1.0 - stop_loss_pct / 100.0), 0)
        take_profit_price = round(price * (1.0 + take_profit_pct / 100.0), 0)

        pos_dict = self.data["short_term_positions"] if portfolio_type == "short_term" else self.data["long_term_positions"]

        if clean_ticker in pos_dict:
            # Trung bình giá
            old = pos_dict[clean_ticker]
            new_shares = old["shares"] + shares
            new_avg_price = round(((old["avg_price"] * old["shares"]) + (price * shares)) / new_shares, 0)
            old["shares"] = new_shares
            old["avg_price"] = new_avg_price
            old["buy_date"] = trade_date
            old["available_date"] = available_date
        else:
            pos_dict[clean_ticker] = {
                "shares": shares,
                "avg_price": price,
                "buy_date": trade_date,
                "available_date": available_date,
                "stop_loss": stop_loss_price,
                "take_profit": take_profit_price,
                "rationale": rationale
            }

        self._save()

        # Đồng bộ Google Sheets và Google Drive
        if sheet_sync:
            try:
                sheet_sync.log_order_to_sheet({
                    "ticker": clean_ticker,
                    "action": "MUA",
                    "shares": shares,
                    "price": price,
                    "total_value": total_cost,
                    "pnl": 0,
                    "pnl_pct": 0,
                    "portfolio_type": "Ngắn hạn" if portfolio_type == "short_term" else "Dài hạn",
                    "rationale": rationale or "Mở vị thế mua"
                })
                sheet_sync.sync_portfolio_to_sheet(self.data, {clean_ticker: price})
            except Exception:
                pass

        return {
            "success": True,
            "message": f"✅ Đã MUA thành công {shares:,} cổ phiếu {clean_ticker} giá {price:,.0f} VND!\n"
                       f"• Tổng tiền: {total_cost:,.0f} VND (đã gồm phí 0.15%)\n"
                       f"• Danh mục: {'Ngắn hạn (Lướt sóng)' if portfolio_type == 'short_term' else 'Dài hạn (Tích sản)'}\n"
                       f"• Cắt lỗ: {stop_loss_price:,.0f} VND (-{stop_loss_pct}%)\n"
                       f"• Chốt lời: {take_profit_price:,.0f} VND (+{take_profit_pct}%)\n"
                       f"• Cổ phiếu về tài khoản (T+2.5): Chiều ngày {available_date}."
        }

    def sell(
        self,
        ticker: str,
        price: float,
        shares: Optional[int] = None,
        rationale: str = ""
    ) -> Dict[str, Any]:
        """Thực hiện Bán chốt lời / cắt lỗ cổ phiếu (kiểm tra T+2.5)."""
        clean_ticker = ticker.upper().replace(".VN", "").strip()
        trade_date = datetime.now().strftime("%Y-%m-%d")

        # Tìm trong danh mục ngắn hạn trước, sau đó đến dài hạn
        pos_dict = None
        p_type = "short_term"
        if clean_ticker in self.data["short_term_positions"]:
            pos_dict = self.data["short_term_positions"]
            p_type = "short_term"
        elif clean_ticker in self.data["long_term_positions"]:
            pos_dict = self.data["long_term_positions"]
            p_type = "long_term"

        if not pos_dict:
            return {"success": False, "message": f"Không tìm thấy cổ phiếu {clean_ticker} trong bất kỳ danh mục nào!"}

        pos = pos_dict[clean_ticker]

        # Kiểm tra chu kỳ T+2.5
        if trade_date < pos["available_date"]:
            return {
                "success": False,
                "message": f"⚠️ Vi phạm quy định T+2.5! Cổ phiếu {clean_ticker} mua ngày {pos['buy_date']}, "
                           f"đến chiều ngày {pos['available_date']} mới về tài khoản để bán."
            }

        sell_shares = shares if shares and shares <= pos["shares"] else pos["shares"]
        gross_value = price * sell_shares
        net_proceeds = gross_value * (1.0 - FEE_RATE - TAX_RATE)  # Trừ phí 0.15% và thuế 0.1%

        # Tính lãi/lỗ
        cost_basis = pos["avg_price"] * sell_shares
        pnl = net_proceeds - cost_basis
        pnl_pct = (pnl / cost_basis) * 100.0

        # Cộng tiền mặt
        self.data["cash"] += net_proceeds

        # Lưu lịch sử
        self.data["history"].append({
            "ticker": clean_ticker,
            "shares": sell_shares,
            "buy_price": pos["avg_price"],
            "sell_price": price,
            "buy_date": pos["buy_date"],
            "sell_date": trade_date,
            "net_proceeds": round(net_proceeds, 0),
            "pnl": round(pnl, 0),
            "pnl_pct": round(pnl_pct, 2),
            "type": p_type,
            "rationale": rationale
        })

        if sell_shares >= pos["shares"]:
            del pos_dict[clean_ticker]
        else:
            pos["shares"] -= sell_shares

        self._save()

        # Đồng bộ Google Sheets và Google Drive
        if sheet_sync:
            try:
                sheet_sync.log_order_to_sheet({
                    "ticker": clean_ticker,
                    "action": "BÁN",
                    "shares": sell_shares,
                    "price": price,
                    "total_value": net_proceeds,
                    "pnl": pnl,
                    "pnl_pct": pnl_pct,
                    "portfolio_type": "Ngắn hạn" if p_type == "short_term" else "Dài hạn",
                    "rationale": rationale or "Tất toán vị thế"
                })
                sheet_sync.sync_portfolio_to_sheet(self.data, {clean_ticker: price})
            except Exception:
                pass

        pnl_sign = "+" if pnl > 0 else ""
        icon = "🎉 CHỐT LỜI" if pnl > 0 else "🛑 CẮT LỖ"

        return {
            "success": True,
            "message": f"{icon}: Đã BÁN {sell_shares:,} cổ phiếu {clean_ticker} giá {price:,.0f} VND!\n"
                       f"• Tiền thu về: {net_proceeds:,.0f} VND (đã trừ thuế phí)\n"
                       f"• Lãi/Lỗ: {pnl_sign}{pnl:,.0f} VND ({pnl_sign}{pnl_pct:.2f}%)\n"
                       f"• Lý do: {rationale or 'Chủ động tất toán'}"
        }

    def check_sl_tp(self, price_map: Dict[str, float]) -> List[Dict[str, Any]]:
        """Kiểm tra toàn bộ danh mục ngắn hạn để tự động kích hoạt Cắt lỗ (-5%) hoặc Chốt lời (+15%)."""
        today_str = datetime.now().strftime("%Y-%m-%d")
        alerts = []

        for ticker, pos in list(self.data["short_term_positions"].items()):
            cur_price = price_map.get(ticker) or price_map.get(f"{ticker}.VN")
            if not cur_price:
                continue

            # Kiểm tra Stop Loss
            if cur_price <= pos["stop_loss"]:
                if today_str >= pos["available_date"]:
                    res = self.sell(ticker, cur_price, pos["shares"], rationale="Chạm ngưỡng CẮT LỖ (-5%)")
                    alerts.append(res)
                else:
                    alerts.append({
                        "success": False,
                        "message": f"🚨 CẢNH BÁO: {ticker} đã thủng ngưỡng cắt lỗ ({cur_price:,.0f} <= {pos['stop_loss']:,.0f}) "
                                   f"nhưng cổ phiếu đang kẹt T+2.5 (sẽ về ngày {pos['available_date']})."
                    })

            # Kiểm tra Take Profit
            elif cur_price >= pos["take_profit"]:
                if today_str >= pos["available_date"]:
                    res = self.sell(ticker, cur_price, pos["shares"], rationale="Đạt mục tiêu CHỐT LỜI (+15%)")
                    alerts.append(res)
                else:
                    alerts.append({
                        "success": False,
                        "message": f"🎯 CẢNH BÁO: {ticker} đã đạt mục tiêu chốt lời ({cur_price:,.0f} >= {pos['take_profit']:,.0f})! "
                                   f"Cổ phiếu sẽ về vào ngày {pos['available_date']} để bán."
                    })

        return alerts

    def get_summary(self) -> str:
        """Tạo báo cáo tổng kết tình trạng danh mục đầu tư gửi qua Telegram."""
        # Lấy giá thị trường hiện tại của các mã đang nắm giữ
        all_tickers = list(self.data["short_term_positions"].keys()) + list(self.data["long_term_positions"].keys())
        price_map = {}
        if all_tickers:
            yf_symbols = [f"{t}.VN" for t in all_tickers]
            try:
                df = yf.download(yf_symbols, period="5d", progress=False)["Close"]
                for t in all_tickers:
                    sym = f"{t}.VN"
                    if sym in df:
                        s = df[sym].dropna()
                        if not s.empty:
                            price_map[t] = float(s.iloc[-1])
            except Exception:
                pass

        total_stock_value = 0.0
        msg = "💼 *BÁO CÁO DANH MỤC ĐẦU TƯ TỰ ĐỘNG*\n"
        msg += f"📅 *Cập nhật:* `{datetime.now().strftime('%d/%m/%Y %H:%M')}`\n"
        msg += "───────────────────\n"

        # 1. Danh mục Ngắn hạn (Lướt sóng)
        msg += "🏄 *1. DANH MỤC NGẮN HẠN (LƯỚT SÓNG T+):*\n"
        if not self.data["short_term_positions"]:
            msg += "   _(Chưa có vị thế mở)_\n"
        else:
            for t, p in self.data["short_term_positions"].items():
                cur = price_map.get(t, p["avg_price"])
                val = cur * p["shares"]
                total_stock_value += val
                pnl = (cur - p["avg_price"]) * p["shares"]
                pct = ((cur - p["avg_price"]) / p["avg_price"]) * 100.0
                sign = "+" if pnl > 0 else ""
                msg += f"• *{t}*: {p['shares']:,} cp | Vốn: `{p['avg_price']:,.0f}` ➔ Hiện tại: `{cur:,.0f}`\n"
                msg += f"   Lãi/Lỗ: *{sign}{pnl:,.0f} VND* ({sign}{pct:.2f}%) | Hàng về: `{p['available_date']}`\n"

        # 2. Danh mục Dài hạn (Tích sản)
        msg += "\n💎 *2. DANH MỤC DÀI HẠN (TÍCH SẢN):*\n"
        if not self.data["long_term_positions"]:
            msg += "   _(Chưa có vị thế mở)_\n"
        else:
            for t, p in self.data["long_term_positions"].items():
                cur = price_map.get(t, p["avg_price"])
                val = cur * p["shares"]
                total_stock_value += val
                pnl = (cur - p["avg_price"]) * p["shares"]
                pct = ((cur - p["avg_price"]) / p["avg_price"]) * 100.0
                sign = "+" if pnl > 0 else ""
                msg += f"• *{t}*: {p['shares']:,} cp | Vốn: `{p['avg_price']:,.0f}` ➔ Hiện tại: `{cur:,.0f}`\n"
                msg += f"   Lãi/Lỗ: *{sign}{pnl:,.0f} VND* ({sign}{pct:.2f}%)\n"

        # Tổng tài sản
        nav = self.data["cash"] + total_stock_value
        initial = self.data["initial_capital"]
        total_pnl = nav - initial
        total_pct = (total_pnl / initial) * 100.0
        pnl_sign = "+" if total_pnl > 0 else ""

        msg += "\n───────────────────\n"
        msg += f"💵 *Tiền mặt khả dụng:* `{self.data['cash']:,.0f} VND`\n"
        msg += f"📈 *Giá trị cổ phiếu:* `{total_stock_value:,.0f} VND`\n"
        msg += f"🏆 *TỔNG TÀI SẢN (NAV):* `{nav:,.0f} VND`\n"
        msg += f"📊 *Hiệu suất tổng thể:* *{pnl_sign}{total_pnl:,.0f} VND* ({pnl_sign}{total_pct:.2f}%)\n"
        return msg


if __name__ == "__main__":
    pm = PortfolioManager()
    print(pm.get_summary())
