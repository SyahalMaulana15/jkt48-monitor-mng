#!/usr/bin/env python3
"""JKT48 Ticket Monitor — Notif Quota Berkurang"""

import requests, os, time
from datetime import datetime, timezone, timedelta

API_URL        = "https://jkt48.com/api/v1/exclusives/EXE588/bonus?lang=id"
EXCLUSIVE_CODE = "EXE588"
BOT_TOKEN      = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID        = os.environ.get("TELEGRAM_CHAT_ID", "")
INTERVAL       = 30
HEARTBEAT_H    = 6
MAX_FAIL       = 5
WATCH_MEMBERS  = []

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "id-ID,id;q=0.9",
    "Referer": "https://jkt48.com/",
    "Origin": "https://jkt48.com",
}

def wib(): return datetime.now(timezone(timedelta(hours=7)))
def wib_str(): return wib().strftime("%Y-%m-%d %H:%M:%S WIB")

def telegram(msg):
    if not BOT_TOKEN or not CHAT_ID:
        return print("❌ Token/Chat ID belum diset!")
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=10
        )
        r.raise_for_status()
        print("  ✅ Telegram terkirim")
    except Exception as e:
        print(f"  ❌ Gagal kirim Telegram: {e}")

def fetch(retries=3):
    for i in range(1, retries + 1):
        try:
            r = requests.get(API_URL, headers=HEADERS, timeout=20)
            r.raise_for_status()
            text = r.content.decode("utf-8", errors="replace").strip()
            if not text or not (text.startswith("{") or text.startswith("[")):
                raise ValueError(f"Respons tidak valid: {text[:80]!r}")
            data = r.json()
            if data.get("status") and "data" in data:
                return data["data"]
            print(f"  ⚠ Pesan API: {data.get('message')}")
        except Exception as e:
            if i < retries:
                print(f"  ⚠ Attempt {i}/{retries} gagal, retry {i*15}s — {e}")
                time.sleep(i * 15)
            else:
                print(f"  ❌ Fetch gagal {retries}x: {e}")
    return None

def extract_quota(sessions):
    return {
        str(m.get("session_detail_id", "")): m.get("quota", 0)
        for s in sessions for m in s.get("session_members", [])
    }

def heartbeat(sessions, run_count, last_hb):
    if last_hb and (wib() - last_hb).total_seconds() < HEARTBEAT_H * 3600:
        return last_hb
    now = wib()
    total = sum(len(s.get("session_members", [])) for s in sessions)
    avail = sum(1 for s in sessions for m in s.get("session_members", []) if m.get("quota", 0) > 0)
    telegram(
        f" <b>Laporan Berkala</b>\n\n"
        f" {now.strftime('%Y-%m-%d %H:%M WIB')} | ⚡ Interval: {INTERVAL}s\n"
        f" Total: {total} | Tersedia: {avail} | Sold out: {total - avail}\n"
        f" Berikutnya: {(now + timedelta(hours=HEARTBEAT_H)).strftime('%H:%M WIB')} | 📈 Cek: {run_count:,}x"
    )
    print("   Heartbeat terkirim")
    return now

def main():
    print(f"{'='*50}\nJKT48 Monitor | Interval: {INTERVAL}s | Heartbeat: {HEARTBEAT_H}h\n{'='*50}")

    while not (sessions := fetch()):
        print("  ⚠ API belum merespons, retry 15s...")
        time.sleep(15)

    prev_quota = extract_quota(sessions)
    print(f"   Data awal: {len(prev_quota)} slot | {sum(1 for v in prev_quota.values() if v > 0)} tersedia")

    telegram(
        f" <b>JKT48 Monitor aktif!</b>\n"
        f" Notif saat tiket <b>berkurang</b> (ada pembelian)\n"
        f" Cek setiap <b>{INTERVAL} detik</b> | 🕐 {wib_str()}"
    )

    run_count, fail_count, last_hb = 0, 0, wib()
    purchase_url = f"https://jkt48.com/purchase/exclusive?code={EXCLUSIVE_CODE}"

    while True:
        time.sleep(INTERVAL)
        run_count += 1
        print(f"[{wib().strftime('%H:%M:%S')}] Cek #{run_count}...", end=" ", flush=True)

        if not (sessions := fetch()):
            fail_count += 1
            print(f"gagal ({fail_count}x)")
            if fail_count == MAX_FAIL:
                telegram(f"⚠️ <b>API Bermasalah</b> — Gagal {MAX_FAIL}x berturut-turut\n🕐 {wib_str()}")
            continue

        fail_count = 0
        new_quota  = extract_quota(sessions)
        notif_count = 0

        for s in sessions:
            label, stime = s.get("label", "?"), s.get("start_time", "")[:5]
            for m in s.get("session_members", []):
                name, jalur   = m.get("member_name", ""), m.get("label", "")
                quota, price  = m.get("quota", 0), m.get("price", 0)
                did           = str(m.get("session_detail_id", ""))

                if WATCH_MEMBERS and name not in WATCH_MEMBERS:
                    continue

                prev, selisih = prev_quota.get(did, 0), prev_quota.get(did, 0) - quota

                if selisih > 0:
                    icon = "🔴" if quota == 0 else ("🟡" if quota / (quota + selisih) < 0.3 else "🟢")
                    print(f"\n  🛒 TERBELI: {name} | {label} ({stime}) | {jalur} | -{selisih} → sisa {quota}")
                    telegram(
                        f"🛒 <b>TIKET TERBELI!</b>\n\n"
                        f"👤 <b>{name}</b> | 📋 {label} ({stime} WIB)\n"
                        f"🚪 {jalur} | 💰 Rp{price:,}\n"
                        f"📉 {prev} → {quota} <i>(-{selisih})</i> | {icon} Sisa: {quota}"
                        + (" <i>(SOLD OUT!)</i>" if quota == 0 else "") +
                        f"\n🕐 {wib_str()}\n🔗 <a href='{purchase_url}'>Lihat tiket →</a>"
                    )
                    notif_count += 1
                elif quota > prev:
                    print(f"\n  ♻️  Restock: {name} | {label} | {jalur} | +{quota - prev} → {quota}")

        prev_quota = new_quota
        last_hb    = heartbeat(sessions, run_count, last_hb)

        print(f"  📨 {notif_count} notif" if notif_count else ("OK" if run_count % 10 else f"OK ({run_count}x)"))

if __name__ == "__main__":
    main()
