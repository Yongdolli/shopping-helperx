"""최근 N일 가격 추세 — 선형회귀 기울기를 30일 변화율(%)로. 웹 lib/trend.ts 와 동일. suspect·품절 제외, 표본 4개 미만이면 None.
적합도 R² < MIN_R2 면 None: 평평하다 오늘 뚝 떨어진 '계단'(세일)은 추세가 아니다 — 그걸 추세로 보면 급락에 "더 떨어지는 중"이라 기다리라고 하게 된다."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional, Sequence

from .models import PriceSnapshot

MIN_R2 = 0.6   # 계단식 급락(8평+1저) ≈ 0.3~0.5, 완만한 하락 ≈ 0.9↑


def trend_pct(snapshots: Sequence[PriceSnapshot], days: int = 30, now: Optional[datetime] = None) -> Optional[float]:
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    pts = [((s.captured_at - cutoff).total_seconds() / 86400, s.price)
           for s in snapshots if s.in_stock and not s.suspect and s.captured_at >= cutoff]
    if len(pts) < 4:
        return None
    n = len(pts)
    mx = sum(x for x, _ in pts) / n
    my = sum(y for _, y in pts) / n
    sxx = sum((x - mx) ** 2 for x, _ in pts)
    if not sxx or not my:
        return None
    slope = sum((x - mx) * (y - my) for x, y in pts) / sxx     # 가격/일
    ss_tot = sum((y - my) ** 2 for _, y in pts)
    if ss_tot == 0:
        return 0.0                                              # 완전히 평평
    icpt = my - slope * mx
    r2 = 1 - sum((y - (icpt + slope * x)) ** 2 for x, y in pts) / ss_tot
    if r2 < MIN_R2:
        return None
    return round(slope * days / my * 100, 1)
