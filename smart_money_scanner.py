# -*- coding: utf-8 -*-
"""
MODULE QUÉT DÒNG TIỀN LỚN (SMART MONEY SCANNER) - CHỨNG KHOÁN VIỆT NAM
Tự động quét toàn bộ rổ VN30 và Top 60 cổ phiếu dẫn dắt thị trường (HOSE/HNX).
Phát hiện các mã có dòng tiền cá mập / tổ chức gom hàng:
1. Khối lượng bùng nổ (Volume Surge >= 1.5x - 3.0x bình quân 20 phiên).
2. Giá tăng mạnh (> +1.5% đến kịch trần +7%).
3. Vượt các mốc cản kỹ thuật ngắn hạn (EMA10, Bollinger Upper Band).
4. Giá trị khớp lệnh lớn (tối thiểu trên 20-50 tỷ VNĐ).
"""

import sys
import os
from datetime import datetime, timedelta
from typing import List, Dict, Any
import pandas as pd
import yfinance as yf

# Đảm bảo UTF-8 cho console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Danh sách 60 mã cổ phiếu thanh khoản lớn và uy tín nhất TTCK Việt Nam
UNIVERSE_VN = [
    # Rổ VN30
    "HPG.VN", "FPT.VN", "VNM.VN", "SSI.VN", "TCB.VN", "MBB.VN", "MWG.VN", "VIC.VN", "VHM.VN", "VRE.VN",
    "VCB.VN", "CTG.VN", "BID.VN", "VPB.VN", "ACB.VN", "STB.VN", "TPB.VN", "HDB.VN", "SHB.VN", "LPB.VN",
    "GAS.VN", "PLX.VN", "POW.VN", "SAB.VN", "VJC.VN", "MSN.VN", "GVR.VN", "BCM.VN", "BVH.VN", "SSB.VN",
    # Nhóm Chứng khoán & Bất động sản & Thép Midcap
    "VCI.VN", "HCM.VN", "VND.VN", "KDH.VN", "NLG.VN", "DXG.VN", "DIG.VN", "PDR.VN", "KBC.VN",
    "HSG.VN", "NKG.VN", "CII.VN", "EIB.VN",
    # Nhóm Hóa chất, Dầu khí, Bán lẻ & Công nghệ
    "DGC.VN", "PVD.VN", "FRT.VN", "CTR.VN", "GEX.VN", "VGC.VN", "SZC.VN", "REE.VN", "PC1.VN",
    "DBC.VN", "HAX.VN", "DCM.VN", "DPM.VN", "VHC.VN", "ANV.VN"
]


def scan_smart_money(
    min_vol_ratio: float = 1.3,
    min_price_change: float = 0.5,
    min_turnover_billion: float = 10.0,
    top_n: int = 10
) -> List[Dict[str, Any]]:
    """
    Quét danh mục cổ phiếu và xếp hạng các mã có dòng tiền lớn vào mạnh nhất.
    
    Args:
        min_vol_ratio: Tỷ lệ Volume hôm nay / SMA20 Volume tối thiểu (mặc định 1.3x)
        min_price_change: Mức tăng giá tối thiểu % (mặc định +0.5%)
        min_turnover_billion: Giá trị giao dịch tối thiểu tính bằng tỷ VNĐ (mặc định 10 tỷ)
        top_n: Số lượng cổ phiếu tối đa trả về
    """
    print(f"[*] Đang tải dữ liệu {len(UNIVERSE_VN)} cổ phiếu hàng đầu Việt Nam...")
    try:
        # Tải dữ liệu 3 tháng gần nhất để tính chuẩn MA20, EMA10 và hệ thống Ichimoku Kinko Hyo
        data = yf.download(UNIVERSE_VN, period="3mo", progress=False)
        if data.empty or "Close" not in data or "Volume" not in data:
            print("[Lỗi] Không nhận được dữ liệu từ sàn!")
            return []

        close_df = data["Close"]
        vol_df = data["Volume"]
        high_df = data.get("High", close_df)
        low_df = data.get("Low", close_df)

        results = []
        latest_date_str = close_df.index[-1].strftime("%Y-%m-%d")

        for symbol in UNIVERSE_VN:
            if symbol not in close_df or symbol not in vol_df:
                continue

            c_series = close_df[symbol].dropna()
            v_series = vol_df[symbol].dropna()
            h_series = high_df[symbol].dropna() if symbol in high_df else c_series
            l_series = low_df[symbol].dropna() if symbol in low_df else c_series

            if len(c_series) < 5 or len(v_series) < 5:
                continue

            current_price = float(c_series.iloc[-1])
            prev_price = float(c_series.iloc[-2]) if len(c_series) >= 2 else current_price

            if prev_price <= 0:
                continue

            price_change_pct = ((current_price - prev_price) / prev_price) * 100.0
            current_vol = float(v_series.iloc[-1])

            # Tính trung bình Volume 20 phiên (hoặc số phiên tối đa đang có)
            lookback = min(20, len(v_series) - 1)
            if lookback >= 3:
                vol_sma = float(v_series.iloc[-lookback-1 : -1].mean())
            else:
                vol_sma = float(v_series.mean())

            vol_ratio = (current_vol / vol_sma) if vol_sma > 0 else 1.0
            turnover_billion = (current_price * current_vol) / 1_000_000_000.0

            # Tính EMA10 và Hệ thống Ichimoku Kinko Hyo (Tenkan 9, Kijun 26, Senkou Span 52)
            ema10 = float(c_series.ewm(span=10, adjust=False).mean().iloc[-1])
            is_above_ema10 = current_price > ema10

            t_len = min(9, len(h_series))
            k_len = min(26, len(h_series))
            b_len = min(52, len(h_series))

            tenkan = float((h_series.iloc[-t_len:].max() + l_series.iloc[-t_len:].min()) / 2)
            kijun = float((h_series.iloc[-k_len:].max() + l_series.iloc[-k_len:].min()) / 2)
            span_a = (tenkan + kijun) / 2
            span_b = float((h_series.iloc[-b_len:].max() + l_series.iloc[-b_len:].min()) / 2)

            kumo_top = max(span_a, span_b)
            kumo_bot = min(span_a, span_b)

            is_above_kumo = current_price >= kumo_top
            is_tk_cross = tenkan >= kijun

            if is_above_kumo and is_tk_cross:
                ichi_signal = "Trên Mây + TK Golden Cross ⚡"
                ichi_bonus = 15.0
            elif is_above_kumo:
                ichi_signal = "Trên Mây Kumo ☁️"
                ichi_bonus = 10.0
            elif current_price < kumo_bot:
                ichi_signal = "Dưới Mây Kumo 🔻"
                ichi_bonus = -5.0
            else:
                ichi_signal = "Trong Mây Kumo ⏸️"
                ichi_bonus = 0.0

            # Lọc các tiêu chí dòng tiền lớn
            # Điểm dòng tiền (Money Flow Score): kết hợp Tỷ lệ Vol + % Tăng giá + Quy mô tiền + Ichimoku
            if vol_ratio >= min_vol_ratio and price_change_pct >= min_price_change and turnover_billion >= min_turnover_billion:
                # Tính điểm sức mạnh dòng tiền
                score = (vol_ratio * 30.0) + (price_change_pct * 15.0) + min(turnover_billion / 20.0, 25.0)
                if is_above_ema10:
                    score += 15.0
                score += ichi_bonus

                clean_ticker = symbol.replace(".VN", "")
                
                # Xác định nhãn tín hiệu
                if vol_ratio >= 2.0 and price_change_pct >= 3.0:
                    signal = "🔥 DÒNG TIỀN BÙNG NỔ (CÁ MẬP VÀO)"
                elif vol_ratio >= 1.5 and price_change_pct >= 1.5:
                    signal = "⚡ DÒNG TIỀN VÀO MẠNH (BREAKOUT)"
                else:
                    signal = "📈 DÒNG TIỀN TÍCH CỰC"

                results.append({
                    "ticker": clean_ticker,
                    "symbol": symbol,
                    "date": latest_date_str,
                    "price": current_price,
                    "price_change_pct": round(price_change_pct, 2),
                    "volume": int(current_vol),
                    "vol_ratio": round(vol_ratio, 2),
                    "turnover_billion": round(turnover_billion, 1),
                    "is_above_ema10": is_above_ema10,
                    "tenkan": round(tenkan, 0),
                    "kijun": round(kijun, 0),
                    "kumo_range": f"{kumo_bot:,.0f} - {kumo_top:,.0f}",
                    "ichi_signal": ichi_signal,
                    "score": round(score, 1),
                    "signal": signal
                })

        # Sắp xếp theo điểm dòng tiền giảm dần
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_n]

    except Exception as e:
        print(f"[Lỗi trong quá trình quét dòng tiền]: {e}")
        import traceback
        traceback.print_exc()
        return []


def format_scan_report(results: List[Dict[str, Any]]) -> str:
    """Định dạng kết quả quét thành thông điệp gửi Telegram hoặc hiển thị terminal."""
    if not results:
        return "⚠️ Không phát hiện cổ phiếu nào có đột biến dòng tiền trong phiên!"

    date_str = results[0]["date"]
    msg = f"🌊 *TOP CỔ PHIẾU CÓ DÒNG TIỀN LỚN ĐỘT BIẾN*\n"
    msg += f"📅 *Ngày giao dịch:* `{date_str}`\n"
    msg += f"🎯 *Rổ theo dõi:* VN30 + Top Midcaps thanh khoản lớn\n"
    msg += "───────────────────\n\n"

    for i, item in enumerate(results, 1):
        t = item["ticker"]
        p = item["price"]
        pct = item["price_change_pct"]
        pct_sign = "+" if pct > 0 else ""
        vr = item["vol_ratio"]
        tb = item["turnover_billion"]
        sig = item["signal"]

        msg += f"*{i}. {t}* | `{p:,.0f} VND` ({pct_sign}{pct}%)\n"
        msg += f"   • {sig}\n"
        if item.get("ichi_signal"):
            msg += f"   • Ichimoku: *{item['ichi_signal']}* (Mây `{item.get('kumo_range')}`)\n"
        msg += f"   • Thanh khoản: *{vr}x* MA20 (`{item['volume']:,}` cp)\n"
        msg += f"   • Giá trị GD: *{tb:,.1f} tỷ VNĐ*\n"
        msg += f"   • Lệnh xem AI: `/analyze {t}`\n\n"

    msg += "───────────────────\n"
    msg += "💡 *Chiến lược:* Canh mua gia tăng ở các nhịp rung lắc, tuân thủ T+2.5 và Stoploss -5%."
    return msg


if __name__ == "__main__":
    print("=" * 65)
    print("   BỘ QUÉT DÒNG TIỀN LỚN (SMART MONEY SCANNER) - TTCK VIỆT NAM")
    print("=" * 65)
    items = scan_smart_money(min_vol_ratio=1.3, min_price_change=0.5, top_n=8)
    report = format_scan_report(items)
    print(report)
