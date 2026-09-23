"""CLI: python -m worker <run|demo|add|list|vapid|doctor|report|digest|deals|user>"""
from __future__ import annotations

import argparse
import logging
import random
import sys
from datetime import datetime, timedelta, timezone

from .models import Alert, PriceSnapshot, Product, detect_site, parse_variant
from .run import run_once
from .storage import get_storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

# (url, title, site, country, currency, base, variant)
DEMO = [
    ("mock://coupang/sony-wh1000xm6?base=449000&vendorItemId=1001", "소니 WH-1000XM6 노이즈캔슬링 헤드폰", "coupang", "KR", "KRW", 449_000, "vendorItemId=1001"),
    ("mock://coupang/sony-wh1000xm6?base=469000&vendorItemId=1002", "소니 WH-1000XM6 노이즈캔슬링 헤드폰", "coupang", "KR", "KRW", 469_000, "vendorItemId=1002"),
    ("mock://11st/sony-xm6-sgrade?base=89000&seller=해외셀러", "소니 WH-1000XM6 S급 미러급 헤드폰 해외직구", "11st", "KR", "KRW", 89_000, None),
    ("mock://11st/lg-oled-c5-65?base=2890000", "LG 올레드 evo C5 65인치 OLED65C5", "11st", "KR", "KRW", 2_890_000, None),
    ("mock://aliexpress/anker-737?base=89.99", "Anker 737 Power Bank 24000mAh 140W", "aliexpress", "CN", "USD", 89.99, None),
    ("mock://amazon/kindle-paperwhite?base=159.99", "Kindle Paperwhite 16GB (2024)", "amazon", "US", "USD", 159.99, None),
    ("mock://bestbuy/ipad-air-m3?base=599&list=799", "Apple iPad Air 11\" M3 128GB", "bestbuy", "US", "USD", 599.0, None),
    ("mock://ebay/logitech-mx-master-4?base=119.99", "Logitech MX Master 4 Wireless Mouse", "ebay", "US", "USD", 119.99, None),
]


def cmd_demo(store) -> None:
    rnd = random.Random(42)
    now = datetime.now(timezone.utc)
    for url, title, site, country, cur, base, variant in DEMO:
        from .risk import guess_model_no
        p = store.add_product(Product("", title, url, site, country, cur, variant=variant, model_no=guess_model_no(title)))
        if store.history(p.id, 365):
            continue
        price = base
        list_price = 799.0 if "list=" in url else None
        for d in range(90, 0, -1):
            price = max(base * 0.7, min(base * 1.15, price * (1 + rnd.uniform(-0.03, 0.03))))
            if d in (61, 60, 59):       # 두 달 전 반짝 세일
                price = base * 0.86
            if list_price:              # 가짜 할인 데모: 가격은 거의 그대로
                price = base * (1 + rnd.uniform(-0.01, 0.01))
            rounded = round(price, 2) if cur != "KRW" else round(price, -2)
            seller = "해외셀러" if "seller=" in url else "mock-seller"
            store.add_snapshot(PriceSnapshot(p.id, rounded, cur, seller, rnd.random() > 0.02,
                                             now - timedelta(days=d), list_price))
        if "mx-master-4" in url:       # 지금 급락 상태 + 알림
            store.add_snapshot(PriceSnapshot(p.id, round(base * 0.82, 2), cur, "mock-seller", True, now))
            store.add_alert(Alert(p.id, "drop", round(base * 0.82, 2), base, 18.0, None, now))
        if list_price:                 # 가짜 할인 알림
            store.add_alert(Alert(p.id, "fake", base, base, 0.0, None, now, note="표시 할인 25% 지만 평소 가격과 차이 0.0%"))
    print(f"데모 상품 {len(DEMO)}개 시드 완료.")


def cmd_add(store, url: str, title: str | None) -> None:
    site, country, cur = detect_site(url)
    variant = parse_variant(url, site)
    if site == "coupang" and not title:
        print("쿠팡은 상품명이 필요합니다: --title \"상품명\"")
        return
    p = store.add_product(Product("", title or url, url, site, country, cur, variant=variant))
    print(f"추가됨: [{site}/{country}] {p.title}{' · ' + variant if variant else ''} ({p.id})")


def cmd_list(store) -> None:
    for p in store.list_products(active_only=False):
        h = store.history(p.id, 90)
        last = f"{h[-1].price:,.0f} {h[-1].currency}" if h else "-"
        flag = "" if p.active else " (중단)"
        err = f"  ✗{p.fail_count} {p.last_error[:40]}" if p.fail_count else ""
        print(f"{p.id[:8]}  {p.site:<10} {last:>16}  {p.title[:40]}{' · ' + p.variant if p.variant else ''}{flag}{err}")


def cmd_user(email: str, password: str) -> None:
    """자동 로그인용 계정 생성/비밀번호 갱신 (Supabase Auth admin API, 이메일 확인 완료 상태). 웹 .env.local 의 VITE_LOGIN_EMAIL/PASSWORD 와 짝."""
    from .config import settings
    if not settings.use_supabase:
        print("SUPABASE_URL / SUPABASE_SERVICE_KEY 가 필요합니다 (worker/.env)")
        return
    from supabase import create_client
    admin = create_client(settings.supabase_url, settings.supabase_key).auth.admin
    existing = next((u for u in admin.list_users() if (u.email or "").lower() == email.lower()), None)
    if existing:
        admin.update_user_by_id(existing.id, {"password": password, "email_confirm": True})
        print(f"갱신됨: {email} ({existing.id})")
    else:
        u = admin.create_user({"email": email, "password": password, "email_confirm": True})
        print(f"생성됨: {email} ({u.user.id})")
    from urllib.parse import quote
    print("로컬 개발: web/.env.local 의 VITE_LOGIN_PASSWORD 를 같은 값으로.")
    print("기기별 로그인 링크 (폰·PC 에서 한 번 열기, 남에게 공유 금지):\n  https://shopping-helperx.vercel.app/#login=" + quote(password, safe=""))


def cmd_vapid() -> None:
    from .push import generate_vapid_keys

    pub, priv = generate_vapid_keys()
    print("# web/.env.local\nVITE_VAPID_PUBLIC_KEY=" + pub)
    print("\n# worker/.env\nVAPID_PUBLIC_KEY=" + pub + "\nVAPID_PRIVATE_KEY=" + priv + "\nVAPID_SUBJECT=mailto:you@example.com")


def main() -> None:
    for stream in (sys.stdout, sys.stderr):   # Windows 콘솔(cp949)에서도 한글·이모지 출력
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(prog="worker")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run", help="1회 수집·판정·알림")
    sub.add_parser("demo", help="데모 상품과 90일 이력 시드")
    a = sub.add_parser("add", help="추적 상품 추가")
    a.add_argument("url")
    a.add_argument("--title")
    sub.add_parser("list", help="추적 상품 목록")
    sub.add_parser("vapid", help="웹푸시용 VAPID 키 생성")
    sub.add_parser("doctor", help="키·연결·어댑터 상태 점검")
    r = sub.add_parser("report", help="주간 요약 리포트 발송 (텔레그램·이메일·푸시)")
    r.add_argument("--dry-run", action="store_true", help="발송하지 않고 출력만")
    d = sub.add_parser("digest", help="대기 중 알림을 모아 발송 (아침·점심·저녁 크론)")
    d.add_argument("--dry-run", action="store_true", help="발송·처리하지 않고 출력만")
    sub.add_parser("deals", help="핫딜 커뮤니티에서 딜 수집 (매시 크론)")
    u = sub.add_parser("user", help="자동 로그인용 계정 생성/비밀번호 갱신 (Supabase)")
    u.add_argument("email")
    u.add_argument("password")
    args = ap.parse_args()

    if args.cmd == "vapid":
        cmd_vapid()
        return
    if args.cmd == "doctor":
        from .doctor import run_doctor
        raise SystemExit(run_doctor())
    if args.cmd == "user":
        cmd_user(args.email, args.password)
        return
    store = get_storage()
    if args.cmd == "run":
        run_once(store)
    elif args.cmd == "demo":
        cmd_demo(store)
    elif args.cmd == "add":
        cmd_add(store, args.url, args.title)
    elif args.cmd == "list":
        cmd_list(store)
    elif args.cmd == "report":
        from .report import run_weekly
        run_weekly(store, dry_run=args.dry_run)
    elif args.cmd == "digest":
        from .digest import run_digest
        run_digest(store, dry_run=args.dry_run)
    elif args.cmd == "deals":
        from .deals import run_deals
        run_deals(store)


if __name__ == "__main__":
    main()
