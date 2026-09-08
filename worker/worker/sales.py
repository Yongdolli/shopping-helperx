"""세일 캘린더(정적) + 구매 타이밍 — 웹 lib/sales.ts 와 동일 규칙. 주간 리포트·알림 note 의 '기다려볼 만함' 근거."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable, Optional, Sequence


@dataclass(frozen=True)
class SaleEvent:
    name: str
    scope: tuple[str, ...]          # 국가(KR/CN/US) | 사이트 | 카테고리
    start: Callable[[int], date]    # 연도 → 시작일
    span: int                       # 기간(일)
    strength: int                   # 1 약 · 2 보통 · 3 강


def _nth_weekday(y: int, month: int, weekday: int, n: int) -> date:
    """month 의 n번째 weekday (월=0 … 일=6)."""
    first = date(y, month, 1)
    return first + timedelta(days=(weekday - first.weekday()) % 7 + (n - 1) * 7)


def _black_friday(y: int) -> date:
    return _nth_weekday(y, 11, 3, 4) + timedelta(days=1)   # 11월 넷째 목요일(추수감사절) 다음 날


SALE_EVENTS: tuple[SaleEvent, ...] = (
    SaleEvent("설 연휴 세일", ("KR",), lambda y: date(y, 1, 20), 14, 1),
    SaleEvent("618 쇼핑 페스티벌", ("CN",), lambda y: date(y, 6, 18), 7, 2),
    SaleEvent("프라임데이", ("amazon",), lambda y: date(y, 7, 12), 4, 3),
    SaleEvent("추석 연휴 세일", ("KR",), lambda y: date(y, 9, 25), 14, 1),
    SaleEvent("애플 신제품(9월)", ("전자",), lambda y: date(y, 9, 10), 10, 1),
    SaleEvent("광군제 11·11", ("CN", "aliexpress", "temu"), lambda y: date(y, 11, 11), 3, 3),
    SaleEvent("11절", ("11st",), lambda y: date(y, 11, 11), 3, 2),
    SaleEvent("블랙프라이데이", ("US", "KR"), _black_friday, 4, 3),
    SaleEvent("사이버먼데이", ("US",), lambda y: _black_friday(y) + timedelta(days=3), 1, 2),
    SaleEvent("12·12 세일", ("CN",), lambda y: date(y, 12, 12), 2, 1),
    SaleEvent("연말 세일", ("US", "KR"), lambda y: date(y, 12, 20), 12, 1),
)


@dataclass(frozen=True)
class Upcoming:
    name: str
    days_until: int      # 0 = 진행 중
    strength: int


def upcoming_sales(country: str, site: str, category: str = "전자", today: Optional[date] = None,
                   horizon_days: int = 45) -> list[Upcoming]:
    """오늘 기준 horizon 안에 시작하거나 진행 중인 세일. 가까운 순, 같은 날이면 강한 순. 이름 중복 제거."""
    today = today or date.today()
    out: list[Upcoming] = []
    for e in SALE_EVENTS:
        if not any(s in (country, site, category) for s in e.scope):
            continue
        for y in (today.year, today.year + 1):
            start = e.start(y)
            end = start + timedelta(days=e.span)
            days = (start - today).days
            if start <= today <= end:
                out.append(Upcoming(e.name, 0, e.strength))
            elif 0 < days <= horizon_days:
                out.append(Upcoming(e.name, days, e.strength))
    out.sort(key=lambda u: (u.days_until, -u.strength))
    seen: set[str] = set()
    return [u for u in out if not (u.name in seen or seen.add(u.name))]


@dataclass(frozen=True)
class Timing:
    verdict: str          # buy | wait | neutral
    label: str
    detail: Optional[str] = None


def buy_timing(drop_now: bool, upcoming: Sequence[Upcoming]) -> Timing:
    """급락 중이면 지금, 강도 2↑ 세일이 30일 내면 기다림, 그 외 중립."""
    if drop_now:
        first = upcoming[0] if upcoming else None
        return Timing("buy", "지금 사도 됨", f"{first.name}까지 {first.days_until}일이지만 이미 급락 상태" if first else None)
    big = next((u for u in upcoming if u.strength >= 2 and u.days_until <= 30), None)
    if big:
        return Timing("wait", f"{big.name} 진행 중" if big.days_until == 0 else f"{big.days_until}일 뒤 {big.name} — 기다려볼 만함")
    if upcoming:
        return Timing("neutral", f"{upcoming[0].days_until}일 뒤 {upcoming[0].name}")
    return Timing("neutral", "45일 내 큰 세일 없음")
