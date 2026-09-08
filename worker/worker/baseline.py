"""기준선 계산과 알림 판정. 순수 함수만 — 테스트 대상."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Optional, Sequence

from .models import PriceSnapshot

MIN_SAMPLES = 3            # 이보다 적으면 기준선 없음 (등록 직후 오탐 방지)
CONFIRM_PCT = 40.0         # 기준선 대비 이만큼 이상 싸면 '극단값' — 다음 수집에서 한 번 더 확인된 뒤에만 알림
FAKE_CLAIM_MIN_PCT = 20.0  # 사이트 표시 할인율이 이 이상인데
FAKE_REAL_MAX_PCT = 3.0    # 실제(기준선 대비) 할인은 이 이하면 '가짜 할인' 의심


def compute_baseline(
    snapshots: Sequence[PriceSnapshot],
    window_days: int = 90,
    now: Optional[datetime] = None,
) -> Optional[float]:
    """최근 window_days 안의 스냅샷 가격 중앙값. 재고 없는 스냅샷은 제외."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=window_days)
    prices = [s.price for s in snapshots if s.in_stock and not s.suspect and s.captured_at >= cutoff]
    if len(prices) < MIN_SAMPLES:
        return None
    return float(median(prices))


def all_time_low(snapshots: Sequence[PriceSnapshot]) -> Optional[float]:
    prices = [s.price for s in snapshots if s.in_stock and not s.suspect]
    return min(prices) if prices else None


def is_extreme(price: float, baseline: Optional[float]) -> bool:
    """기준선 대비 CONFIRM_PCT 이상 싼 값 = 파싱 오류일 가능성이 있어 확인이 필요."""
    return bool(baseline) and price <= baseline * (1 - CONFIRM_PCT / 100)


def needs_confirmation(current: PriceSnapshot, history: Sequence[PriceSnapshot], baseline: Optional[float]) -> bool:
    """극단값이고, 직전 스냅샷이 같은 수준(±5%)의 극단값이 아니면 → 이번엔 '확인 대기'.
    직전이 이미 suspect 이고 이번 값이 그와 비슷하면 확인된 것으로 본다."""
    if not is_extreme(current.price, baseline):
        return False
    prev = history[-1] if history else None
    if prev and prev.suspect and abs(prev.price - current.price) / max(prev.price, 1e-9) <= 0.05:
        return False
    return True


def confirms_suspect(current: PriceSnapshot, history: Sequence[PriceSnapshot]) -> bool:
    """직전 스냅샷이 suspect 이고 이번 값이 그와 같은 수준(±5%)이면 → 승격(진짜 가격). 이번 값이 정상으로 돌아왔으면 승격하지 않는다
    (파싱 오류로 읽힌 1/10 가격이 역대 최저·기준선에 남지 않도록)."""
    prev = history[-1] if history else None
    return bool(prev and prev.suspect and abs(prev.price - current.price) / max(prev.price, 1e-9) <= 0.05)


def dominant_seller(snapshots: Sequence[PriceSnapshot]) -> Optional[str]:
    sellers = [s.seller for s in snapshots if s.seller]
    return Counter(sellers).most_common(1)[0][0] if sellers else None


def seller_changes(snapshots: Sequence[PriceSnapshot], days: int = 90, now: Optional[datetime] = None) -> int:
    """최근 days 안에서 판매자가 '바뀐' 횟수 (연속 스냅샷의 판매자가 다르면 1회). 판매자 없는 스냅샷은 무시.
    자주 바뀌면 오픈마켓 최저가 경쟁 셀러가 돌아가며 붙는 상품 — 정품 리스크 신호."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    sellers = [s.seller for s in snapshots if s.seller and s.captured_at >= cutoff]
    return sum(1 for a, b in zip(sellers, sellers[1:]) if a != b)


def claimed_discount_pct(price: float, list_price: Optional[float]) -> Optional[float]:
    """사이트가 주장하는 할인율(정가 대비)."""
    if not list_price or list_price <= price:
        return None
    return round((list_price - price) / list_price * 100, 2)


def is_fake_discount(price: float, list_price: Optional[float], baseline: Optional[float]) -> bool:
    """'정가 대비 20% 할인'이라 표시하지만 평소 가격(중앙값)과 거의 같으면 가짜 할인."""
    claimed = claimed_discount_pct(price, list_price)
    if claimed is None or baseline is None or claimed < FAKE_CLAIM_MIN_PCT:
        return False
    real = (baseline - price) / baseline * 100
    return real <= FAKE_REAL_MAX_PCT


@dataclass
class Verdict:
    kind: Optional[str]          # drop | low | restock | fake | None
    baseline: Optional[float]
    pct: Optional[float]         # 기준선 대비 하락률(%) 양수
    seller_changed: Optional[str] = None  # '판매자 변경: A → B'
    claimed_pct: Optional[float] = None   # 사이트 표시 할인율
    fake: bool = False

    @property
    def triggered(self) -> bool:
        return self.kind is not None


def judge(
    current: PriceSnapshot,
    history: Sequence[PriceSnapshot],
    threshold_pct: float = 10.0,
    window_days: int = 90,
    target_price: Optional[float] = None,
) -> Verdict:
    """현재 스냅샷을 과거 이력(현재 제외)과 비교해 알림 종류를 결정.

    우선순위: target(목표가 이하) > drop(기준선 대비 -threshold 이상) > low(역대 최저 갱신) > restock > fake(가짜 할인).
    판매자가 평소와 다르면 seller_changed 에 표시(알림은 그대로 나가되 사용자에게 주의를 줌).
    """
    baseline = compute_baseline(history, window_days, now=current.captured_at)
    pct = round((baseline - current.price) / baseline * 100, 2) if baseline else None
    claimed = claimed_discount_pct(current.price, current.list_price)
    fake = is_fake_discount(current.price, current.list_price, baseline)

    seller_changed = None
    usual = dominant_seller(history)
    if usual and current.seller and current.seller != usual:
        seller_changed = f"판매자 변경: {usual} → {current.seller}"

    v = Verdict(None, baseline, pct, seller_changed, claimed, fake)
    if not current.in_stock:
        return v

    if target_price and current.price <= target_price:
        v.kind = "target"
        return v

    if baseline and current.price <= baseline * (1 - threshold_pct / 100):
        v.kind = "drop"
        return v

    low = all_time_low(history)
    if low is not None and len(history) >= MIN_SAMPLES and current.price < low:
        v.kind = "low"
        return v

    if history and not history[-1].in_stock:
        v.kind = "restock"
        return v

    if fake:
        v.kind = "fake"
    return v
