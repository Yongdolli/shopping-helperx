"""구매 결정 한 줄 — 신호(급락·가짜할인·정품리스크·최종가·목표가)를 합쳐 verdict + 문장. 웹 lib/decision.ts 와 규칙 동일.

verdict: buy(지금 사도 됨) | wait(기다리기) | avoid(피하기) | neutral(특별한 신호 없음)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Decision:
    verdict: str
    headline: str
    reasons: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return f"{self.headline} — " + " · ".join(self.reasons) if self.reasons else self.headline


def decide(
    pct_vs_baseline: Optional[float],   # 양수 = 평소보다 싸다
    threshold_pct: float,
    risk_level: str = "low",
    fake: bool = False,
    target_hit: Optional[bool] = None,  # 목표가 이하인가 (목표가 없으면 None)
    landed_rank: Optional[tuple[int, int]] = None,  # (순위, 비교 대상 수) — 같은 모델 최종가 비교
    wait_label: Optional[str] = None,   # "23일 뒤 블랙프라이데이" 등 (큰 세일이 30일 내일 때만)
    trend_pct: Optional[float] = None,  # 최근 30일 추세(%). 음수 = 하락 중
) -> Decision:
    r: list[str] = []
    if pct_vs_baseline is not None:
        r.append(f"평소보다 {abs(pct_vs_baseline):.0f}% {'싸다' if pct_vs_baseline >= 0 else '비싸다'}")
    if target_hit is True:
        r.append("목표가 도달")
    if fake:
        r.append("표시 할인은 가짜")
    if risk_level == "high":
        r.append("정품 리스크 높음")
    elif risk_level == "medium":
        r.append("정품 리스크 보통")
    if landed_rank and landed_rank[1] > 1:
        r.append(f"최종가 {landed_rank[1]}곳 중 {landed_rank[0]}위")
    if trend_pct is not None and abs(trend_pct) >= 5:
        r.append(f"30일 {'하락' if trend_pct < 0 else '상승'} 추세")
    if wait_label:
        r.append(wait_label)

    cheap = pct_vs_baseline is not None and pct_vs_baseline >= threshold_pct
    if risk_level == "high":
        return Decision("avoid", "⛔ 이 판매처는 피하세요", r)
    if target_hit or (cheap and not fake):
        if trend_pct is not None and trend_pct <= -8 and not target_hit:
            return Decision("wait", "⏳ 더 떨어지는 중 — 조금만 더", r)
        return Decision("buy", "✅ 지금 사도 됨", r)
    if wait_label:
        return Decision("wait", "⏳ 기다려볼 만함", r)
    if fake:
        return Decision("neutral", "😐 할인 아님 — 평소 가격", r)
    return Decision("neutral", "😐 특별한 신호 없음", r)
