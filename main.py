#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cloud_sentinel/main.py

BAN 9: APEX LIVE PORTFOLIO SENTINEL 24/7 CLOUD SERVICE ("VICTOR")
Designed for 24/7 Cloud Deployment (Hugging Face Spaces, Render, Koyeb, Railway, VPS, Docker)

Features:
- Built-in FastAPI web server for uptime health checks and live web dashboard.
- Background continuous daemon scanning active positions every 60 seconds.
- Instant Telegram alert dispatcher directly to Phước Trần's phone when anomalies occur.
- Anti-spam cooldown (won't flood Telegram repeatedly for the same alert within 30 mins).
- Manual trigger endpoints (/api/scan, /api/drill/{symbol}).
"""

import os
import sys
import json
import time
import threading
import datetime
import warnings
from pathlib import Path
from typing import Dict, List, Any, Optional
import urllib.request
import urllib.parse

warnings.filterwarnings("ignore")

try:
    import yfinance as yf
except ImportError:
    yf = None

from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse

app = FastAPI(title="Victor Sentinel 24/7 Cloud Engine", version="1.0.0")

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "sentinel_config.json"
PORTFOLIO_PATH = BASE_DIR / "portfolio_data.json"

# Global in-memory state
STATE = {
    "started_at": datetime.datetime.now().isoformat(),
    "last_scan_at": None,
    "scan_count": 0,
    "status": "INITIALIZING",
    "active_alerts_count": 0,
    "positions_cache": [],
    "recent_alert_history": {},  # {symbol: timestamp}
    "is_running": True
}


def load_config() -> Dict[str, Any]:
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "poll_interval_seconds": 60,
        "alert_thresholds": {
            "price_drop_warning_pct": -2.0,
            "price_drop_critical_pct": -3.5,
            "stop_loss_proximity_pct": 1.5,
            "volume_surge_multiplier": 2.5,
            "circuit_breaker_threat_pct_vn": -6.5,
            "circuit_breaker_threat_pct_us": -7.0
        },
        "notification_channels": {
            "telegram": {
                "enabled": True,
                "bot_token": "9113394586:AAEV3JfSShG3Sl6YEIeqwIky7cTT0XYYccw",
                "chat_id": "8332675283"
            }
        },
        "hedging_parameters": {
            "vn30f_multiplier": 100000,
            "vn30f_current_index_estimate": 1320.0
        }
    }


def load_portfolio() -> List[Dict[str, Any]]:
    if PORTFOLIO_PATH.exists():
        try:
            with open(PORTFOLIO_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def send_telegram(text: str) -> bool:
    config = load_config()
    tg = config.get("notification_channels", {}).get("telegram", {})
    if not tg.get("enabled", False):
        return False
    bot_token = tg.get("bot_token", "").strip()
    chat_id = tg.get("chat_id", "").strip()
    if not bot_token or not chat_id:
        return False

    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"[!] Error sending Telegram: {e}")
        return False


def fetch_live_quote(symbol: str, market: str, fallback_price: float) -> Dict[str, Any]:
    res = {
        "symbol": symbol,
        "market": market,
        "price": fallback_price,
        "prev_close": fallback_price,
        "change_pct": 0.0,
        "volume": 0,
        "avg_volume": 1000000,
        "volume_surge_ratio": 1.0,
        "vwap_est": fallback_price,
        "timestamp": datetime.datetime.now().isoformat()
    }
    if not yf:
        return res

    yf_ticker = symbol if market == "US_GLOBAL" else f"{symbol}.VN"
    try:
        t = yf.Ticker(yf_ticker)
        info = getattr(t, "fast_info", None)
        if info:
            last = getattr(info, "last_price", None) or getattr(info, "regular_market_previous_close", None)
            prev = getattr(info, "previous_close", None) or getattr(info, "regular_market_previous_close", None)
            vol = getattr(info, "last_volume", None) or 0
            avg_vol = getattr(info, "three_month_average_volume", None) or 1000000
            if last and last > 0:
                res["price"] = float(last)
                res["prev_close"] = float(prev) if prev else float(last)
                if res["prev_close"] > 0:
                    res["change_pct"] = round(((res["price"] - res["prev_close"]) / res["prev_close"]) * 100.0, 2)
                res["volume"] = int(vol)
                res["avg_volume"] = int(avg_vol)
                if res["avg_volume"] > 0 and res["volume"] > 0:
                    res["volume_surge_ratio"] = round(res["volume"] / res["avg_volume"], 2)
                res["vwap_est"] = res["price"]
                return res

        hist = t.history(period="5d", interval="1d")
        if not hist.empty:
            last_row = hist.iloc[-1]
            prev_row = hist.iloc[-2] if len(hist) > 1 else last_row
            last_p = float(last_row["Close"])
            prev_p = float(prev_row["Close"])
            res["price"] = last_p
            res["prev_close"] = prev_p
            if prev_p > 0:
                res["change_pct"] = round(((last_p - prev_p) / prev_p) * 100.0, 2)
            res["volume"] = int(last_row["Volume"])
            res["avg_volume"] = int(hist["Volume"].mean())
            if res["avg_volume"] > 0:
                res["volume_surge_ratio"] = round(res["volume"] / res["avg_volume"], 2)
            res["vwap_est"] = last_p
    except Exception:
        pass
    return res


def scan_portfolio(drill_symbol: Optional[str] = None, drill_drop: float = -5.8) -> List[Dict[str, Any]]:
    config = load_config()
    positions = load_portfolio()
    results = []
    alerts = []

    thresh = config.get("alert_thresholds", {})
    p_warn = thresh.get("price_drop_warning_pct", -2.0)
    p_crit = thresh.get("price_drop_critical_pct", -3.5)
    stop_prox_thresh = thresh.get("stop_loss_proximity_pct", 1.5)
    floor_thresh = thresh.get("circuit_breaker_threat_pct_vn", -6.5)

    now_ts = time.time()

    for pos in positions:
        sym = pos["symbol"]
        market = pos["market"]
        base_p = pos.get("current_price", 100.0)

        if drill_symbol and sym.upper() == drill_symbol.upper():
            quote = {
                "symbol": sym,
                "market": market,
                "price": round(base_p * (1.0 + drill_drop / 100.0), 2),
                "prev_close": base_p,
                "change_pct": drill_drop,
                "volume": 3500000,
                "avg_volume": 1000000,
                "volume_surge_ratio": 3.5,
                "vwap_est": base_p,
                "timestamp": datetime.datetime.now().isoformat()
            }
        else:
            quote = fetch_live_quote(sym, market, base_p)

        price = quote["price"]
        change = quote["change_pct"]
        stop = pos.get("stop_loss_2atr", 0.0)
        curr = pos.get("currency", "USD" if market == "US_GLOBAL" else "VND")

        stop_dist = 999.0
        if price > 0 and stop > 0:
            stop_dist = round(((price - stop) / price) * 100.0, 2)

        vol_ratio = quote.get("volume_surge_ratio", 1.0)
        triggers = []
        severity = "NORMAL"

        if change <= floor_thresh:
            triggers.append(f"Nguy cơ kẹt sàn / Trắng bên mua ({change:.2f}% <= {floor_thresh}%)")
            severity = "EMERGENCY"
        if stop > 0 and stop_dist <= stop_prox_thresh:
            triggers.append(f"Cận kề Stop Loss 2xATR (cách {stop_dist:.2f}% <= {stop_prox_thresh}%)")
            if severity != "EMERGENCY":
                severity = "CRITICAL"
        if change <= p_crit:
            triggers.append(f"Biến động sụt giảm cực mạnh ({change:.2f}% <= {p_crit}%)")
            if severity not in ["EMERGENCY", "CRITICAL"]:
                severity = "CRITICAL"
        elif change <= p_warn:
            triggers.append(f"Sụt giảm cần quan sát ({change:.2f}% <= {p_warn}%)")
            if severity == "NORMAL":
                severity = "WARNING"
        if change < -1.0 and vol_ratio >= thresh.get("volume_surge_multiplier", 2.5):
            triggers.append(f"Khối lượng xả hàng dồn dập ({vol_ratio:.1f}x)")
            if severity != "EMERGENCY":
                severity = "CRITICAL"

        # Hedging recommendation
        hedge_rec = ""
        if market == "VIETNAM":
            vn30f_idx = config.get("hedging_parameters", {}).get("vn30f_current_index_estimate", 1320.0)
            contract_val = vn30f_idx * 100000.0
            allocated_vnd = pos.get("allocated_capital", price * pos.get("shares", 1000))
            contracts = max(1, round(allocated_vnd / contract_val)) if contract_val > 0 else 1
            hedge_rec = f"SHORT {contracts} HĐ VN30F1M (Khóa lỗ T+2.5)"
        else:
            hedge_rec = f"BUY SPY/QQQ Put Options At-The-Money"

        item = {
            "symbol": sym,
            "market": market,
            "name": pos.get("name", sym),
            "current_price": price,
            "change_pct": change,
            "stop_loss_2atr": stop,
            "stop_dist_pct": stop_dist,
            "volume_surge_ratio": vol_ratio,
            "currency": curr,
            "severity": severity,
            "triggers": triggers,
            "hedge_rec": hedge_rec
        }
        results.append(item)

        if severity in ["EMERGENCY", "CRITICAL"]:
            alerts.append(item)
            # Check cooldown: only send Telegram if at least 1800s (30m) passed, or in drill mode
            last_alert_time = STATE["recent_alert_history"].get(sym, 0)
            if drill_symbol or (now_ts - last_alert_time > 1800):
                STATE["recent_alert_history"][sym] = now_ts
                msg = (
                    f"🚨 *[VICTOR SENTINEL 24/7 BÁO ĐỘNG]*\n"
                    f"Mã CP: *{sym}* ({market})\n"
                    f"Giá hiện tại: *{price:,.2f} {curr}* ({change:+.2f}%)\n"
                    f"Khoảng cách đến Stop 2xATR: *{stop_dist:+.2f}%* (Ngưỡng cắt lỗ: {stop:,.2f})\n"
                    f"Mức độ: *{severity}*\n"
                    f"⚠️ Dị thường: {', '.join(triggers)}\n"
                    f"👉 *Phương án khắc phục tức thời*: {hedge_rec}\n"
                    f"Hệ thống Victor 24/7 đang bảo vệ danh mục của Anh Phước Trần!"
                )
                send_telegram(msg)

    STATE["positions_cache"] = results
    STATE["active_alerts_count"] = len(alerts)
    STATE["last_scan_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    STATE["scan_count"] += 1
    STATE["status"] = "ALERT_ACTIVE" if alerts else "MONITORING_NORMAL"

    return results


def background_daemon_loop():
    print("[*] Victor 24/7 Cloud Daemon started successfully!")
    while STATE["is_running"]:
        try:
            config = load_config()
            interval = config.get("poll_interval_seconds", 60)
            scan_portfolio()
        except Exception as e:
            print(f"[!] Daemon scan error: {e}")
        time.sleep(interval)


# Start daemon on startup in separate thread
daemon_thread = threading.Thread(target=background_daemon_loop, daemon=True)
daemon_thread.start()


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "Victor Live Sentinel 24/7",
        "uptime_scans": STATE["scan_count"],
        "last_scan": STATE["last_scan_at"],
        "active_alerts": STATE["active_alerts_count"]
    }


@app.get("/api/status")
def get_status():
    return {
        "state": STATE,
        "positions": STATE["positions_cache"]
    }


@app.get("/api/drill/{symbol}")
def trigger_drill(symbol: str, drop: float = -5.8, background_tasks: BackgroundTasks = None):
    res = scan_portfolio(drill_symbol=symbol, drill_drop=drop)
    return {"message": f"Drill triggered for {symbol} with drop {drop}%! Telegram alert sent to Phước Trần.", "symbol": symbol}


@app.get("/", response_class=HTMLResponse)
def dashboard_html():
    positions = STATE.get("positions_cache", [])
    last_scan = STATE.get("last_scan_at", "Chưa quét")
    status_label = "✅ TOÀN BỘ ỔN ĐỊNH" if STATE.get("active_alerts_count", 0) == 0 else "🚨 CÓ BIẾN ĐỘNG KHẨN CẤP"
    status_color = "#10b981" if STATE.get("active_alerts_count", 0) == 0 else "#ef4444"

    rows_html = ""
    for r in positions:
        sev = r["severity"]
        badge = '<span style="background:#10b98122;color:#10b981;padding:4px 8px;border-radius:6px;font-size:12px;">Bình thường</span>'
        if sev == "EMERGENCY":
            badge = '<span style="background:#ef444433;color:#ef4444;padding:4px 8px;border-radius:6px;font-size:12px;font-weight:bold;">🔥 Kẹt Sàn</span>'
        elif sev == "CRITICAL":
            badge = '<span style="background:#ef444422;color:#ef4444;padding:4px 8px;border-radius:6px;font-size:12px;font-weight:bold;">🚨 Báo Động Đỏ</span>'
        elif sev == "WARNING":
            badge = '<span style="background:#f59e0b22;color:#f59e0b;padding:4px 8px;border-radius:6px;font-size:12px;">⚠️ Cảnh giác</span>'

        change_color = "#10b981" if r["change_pct"] >= 0 else "#ef4444"
        rows_html += f"""
        <tr>
            <td style="font-weight:bold;font-family:monospace;font-size:14px;">{r['symbol']}</td>
            <td style="color:#94a3b8;font-size:12px;">{r['market']}</td>
            <td style="font-weight:600;">{r['current_price']:,.2f} {r['currency']}</td>
            <td style="color:{change_color};font-weight:bold;">{r['change_pct']:+.2f}%</td>
            <td style="color:#94a3b8;">{r['stop_loss_2atr']:,.2f}</td>
            <td style="font-weight:600;">{r['stop_dist_pct']:+.2f}%</td>
            <td style="color:#94a3b8;">{r['volume_surge_ratio']:.1f}x</td>
            <td>{badge}</td>
        </tr>
        """

    html = f"""
    <!DOCTYPE html>
    <html lang="vi">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Victor 24/7 Cloud Sentinel Dashboard</title>
        <meta http-equiv="refresh" content="30">
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 24px; }}
            .container {{ max-width: 1100px; margin: 0 auto; }}
            .header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #1e293b; padding-bottom: 16px; margin-bottom: 24px; }}
            .card {{ background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 20px; margin-bottom: 24px; }}
            .badge-status {{ display: inline-block; padding: 6px 14px; border-radius: 20px; font-weight: bold; background: {status_color}22; color: {status_color}; border: 1px solid {status_color}; }}
            table {{ width: 100%; border-collapse: collapse; text-align: left; }}
            th {{ background: #0f172a; color: #94a3b8; padding: 12px; font-size: 13px; text-transform: uppercase; border-bottom: 1px solid #334155; }}
            td {{ padding: 12px; border-bottom: 1px solid #334155; }}
            .btn {{ background: #3b82f6; color: white; padding: 8px 16px; border-radius: 8px; text-decoration: none; font-size: 13px; font-weight: 600; display: inline-block; border: none; cursor: pointer; }}
            .btn-danger {{ background: #ef4444; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div>
                    <h1 style="margin:0 0 6px 0;font-size:22px;">🛡️ Victor Sentinel 24/7 Cloud Engine</h1>
                    <p style="margin:0;color:#94a3b8;font-size:14px;">Ban Giám Sát Danh Mục Thời Gian Thực & Ứng Phó Biến Động Khẩn Cấp • Trực chiến liên tục 24/7</p>
                </div>
                <div>
                    <span class="badge-status">{status_label}</span>
                </div>
            </div>

            <div class="card" style="display:flex;justify-content:space-between;align-items:center;">
                <div>
                    <div style="color:#94a3b8;font-size:13px;">Kênh Telegram Đã Kết Nối:</div>
                    <div style="font-weight:bold;font-size:16px;color:#38bdf8;">@Chuyenvienvictor_bot ➔ Anh Phước Trần</div>
                    <div style="color:#64748b;font-size:12px;margin-top:4px;">Lần quét gần nhất: {last_scan} • Tổng số lần quét: {STATE.get('scan_count', 0)}</div>
                </div>
                <div>
                    <a href="/api/drill/VHM?drop=-5.8" target="_blank" class="btn btn-danger">🚨 Bấm Nút Diễn Tập Telegram (VHM -5.8%)</a>
                </div>
            </div>

            <div class="card" style="padding:0;overflow:hidden;">
                <table>
                    <thead>
                        <tr>
                            <th>Mã CP</th>
                            <th>Thị Trường</th>
                            <th>Giá Hiện Tại</th>
                            <th>Thay Đổi</th>
                            <th>Stop 2xATR</th>
                            <th>Cách Stop</th>
                            <th>Vol Surge</th>
                            <th>Trạng Thái</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows_html if rows_html else '<tr><td colspan="8" style="text-align:center;padding:24px;color:#94a3b8;">Đang tải dữ liệu quét ban đầu... Vui lòng chờ 30 giây.</td></tr>'}
                    </tbody>
                </table>
            </div>
        </div>
    </body>
    </html>
    """
    return html


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 7860))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
