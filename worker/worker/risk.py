"""정품 리스크 점수 — 확정 판정이 아니라 '의심 신호의 합'. 순수 함수만, 웹 lib/risk.ts 의 assessRisk 와 규칙을 같게 유지.

점수 → 등급: 60↑ high / 30↑ medium / 그 외 low. 사용자가 '정품 확인됨'(verified) 으로 표시하면 항상 low.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional, Sequence

# 강한 키워드: 상품 자체가 정품이 아님을 사실상 인정
STRONG_WORDS = ["레플", "레플리카", "replica", "미러급", "s급", "sa급", "1:1", "고퀄", "최고급퀄", "이미테이션", "짝퉁", "가품", "custom made", "리얼리티"]
# 약한 키워드: 정품이어도 붙을 수 있지만 브랜드 신품이 아님
WEAK_WORDS = ["호환", "compatible", "벌크", "bulk", "리퍼", "refurb", "병행", "병행수입", "중고", "used", "비품", "비정품", "unbranded", "generic", "oem"]
OFFICIAL_WORDS = ["공식", "브랜드스토어", "브랜드 스토어", "로켓", "직영", "official", "flagship", "authorized", "정품판매"]
OFFICIAL_SITES = {"bestbuy", "walmart", "target"}                 # 직영 리테일러
OVERSEAS_MARKET_SITES = {"aliexpress", "temu", "shein", "taobao", "tmall", "1688", "jd"}

PRICE_SELF_HIGH = 50.0    # 자체 기준선 대비 -50% 이상
PRICE_SELF_MID = 35.0
PRICE_CROSS_HIGH = 40.0   # 동일 모델 다른 상품 중앙값 대비 -40% 이상
PRICE_CROSS_MID = 25.0
SELLER_CHURN_HIGH = 5     # 90일 내 판매자 변경 5회↑ → +25
SELLER_CHURN_MID = 3      # 3회↑ → +15


@dataclass
class RiskResult:
    level: str                  # low | medium | high
    score: int
    reasons: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return " · ".join(self.reasons)


def _has(text: str, words: Sequence[str]) -> Optional[str]:
    t = text.lower()
    for w in words:
        if w.lower() in t:
            return w
    return None


def is_official_seller(seller: Optional[str], site: str) -> bool:
    if site in OFFICIAL_SITES:
        return True
    return bool(seller and _has(seller, OFFICIAL_WORDS))


def assess_risk(
    title: str,
    site: str,
    price: float,
    seller: Optional[str] = None,
    baseline: Optional[float] = None,
    cross_baseline: Optional[float] = None,   # 같은 model_no 를 가진 '다른' 상품들의 최신가 중앙값 (같은 통화)
    model_no: Optional[str] = None,
    usual_seller: Optional[str] = None,       # 이력상 최빈 판매자
    verified: bool = False,
    seller_changes: int = 0,                  # 최근 90일 판매자 변경 횟수 (baseline.seller_changes)
) -> RiskResult:
    if verified:
        return RiskResult("low", 0, ["사용자가 정품 확인함"])

    score = 0
    reasons: list[str] = []

    # 1) 제목 키워드
    w = _has(title, STRONG_WORDS)
    if w:
        score += 60; reasons.append(f"제목에 '{w}'")
    else:
        w = _has(title, WEAK_WORDS)
        if w:
            score += 15; reasons.append(f"제목에 '{w}'")

    # 2) 가격 이상치 — 자체 기준선
    if baseline and baseline > 0:
        pct = (baseline - price) / baseline * 100
        if pct >= 65:
            score += 60; reasons.append(f"평소 가격 대비 -{pct:.0f}%")
        elif pct >= PRICE_SELF_HIGH:
            score += 40; reasons.append(f"평소 가격 대비 -{pct:.0f}%")
        elif pct >= PRICE_SELF_MID:
            score += 20; reasons.append(f"평소 가격 대비 -{pct:.0f}%")

    # 3) 가격 이상치 — 동일 모델 교차 비교
    if cross_baseline and cross_baseline > 0:
        pct = (cross_baseline - price) / cross_baseline * 100
        if pct >= 60:
            score += 60; reasons.append(f"같은 모델 다른 판매처 대비 -{pct:.0f}%")
        elif pct >= PRICE_CROSS_HIGH:
            score += 40; reasons.append(f"같은 모델 다른 판매처 대비 -{pct:.0f}%")
        elif pct >= PRICE_CROSS_MID:
            score += 20; reasons.append(f"같은 모델 다른 판매처 대비 -{pct:.0f}%")

    # 4) 판매자
    official = is_official_seller(seller, site)
    if official:
        score -= 20
    elif usual_seller and is_official_seller(usual_seller, site) and seller and seller != usual_seller:
        score += 30; reasons.append(f"공식 판매자({usual_seller})에서 제3자({seller})로 바뀜")
    elif seller and seller not in ("직접 기록", "demo", "mock-seller"):
        score += 10; reasons.append("공식 판매자 아님")

    # 4b) 판매자 이력 — 자주 바뀌면 최저가 경쟁 셀러가 돌아가며 붙는 상품 (공식 판매자면 무시)
    if not official and seller_changes >= SELLER_CHURN_HIGH:
        score += 25; reasons.append(f"판매자가 자주 바뀜 (90일 {seller_changes}회)")
    elif not official and seller_changes >= SELLER_CHURN_MID:
        score += 15; reasons.append(f"판매자가 자주 바뀜 (90일 {seller_changes}회)")

    # 5) 해외 오픈마켓
    if site in OVERSEAS_MARKET_SITES:
        score += 15; reasons.append("해외 오픈마켓 (판매자 검증 약함)")

    # 6) 모델명 불일치
    if model_no and title and model_no.lower().replace("-", "") not in title.lower().replace("-", "").replace(" ", ""):
        score += 10; reasons.append(f"제목에 모델명 {model_no} 없음")

    score = max(0, score)
    level = "high" if score >= 60 else "medium" if score >= 30 else "low"
    if not reasons and level == "low":
        reasons.append("특이 신호 없음")
    return RiskResult(level, score, reasons)


MODEL_TOKEN_RE = re.compile(r"\b[A-Z]{1,4}-?\d{2,5}[A-Z]{0,3}\d{0,2}\b")


def guess_model_no(title: str) -> Optional[str]:
    """제목에서 모델명처럼 보이는 토큰 하나 (예: WH-1000XM6, OLED65C5, MX Master → 없음)."""
    m = MODEL_TOKEN_RE.search(title.upper())
    return m.group(0) if m else None
