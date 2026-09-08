from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Optional

import httpx

from ..config import settings
from ..models import Product, Quote


class AdapterError(Exception):
    pass


class BudgetExceeded(AdapterError):
    """이번 실행에서 이 어댑터의 호출 예산을 다 씀 — 오류가 아니라 '다음에'."""


class BaseAdapter(ABC):
    """사이트 하나 = 어댑터 하나. `available()` 가 False 면 registry 가 다음 후보로 넘어간다.

    min_interval_hours: 같은 상품을 다시 조회하기까지 최소 간격(호출 제한이 빡빡한 API 용).
    budget_per_run:     한 번의 워커 실행에서 허용하는 최대 호출 수(0 = 무제한).
    """

    site: str = "generic"
    priority: int = 100  # 낮을수록 우선
    min_interval_hours: float = 0
    budget_per_run: int = 0
    _used: int = 0

    def available(self) -> bool:
        return True

    @abstractmethod
    def matches(self, product: Product) -> bool: ...

    @abstractmethod
    def fetch(self, product: Product) -> Quote: ...

    # ---- 예산 관리 (run.py 가 호출)
    def reset_budget(self) -> None:
        self._used = 0

    def consume(self) -> None:
        if self.budget_per_run and self._used >= self.budget_per_run:
            raise BudgetExceeded(f"{self.site}: 이번 실행 호출 예산 {self.budget_per_run}회 소진")
        self._used += 1

    # ---- 공용 유틸
    def client(self, **kw) -> httpx.Client:
        headers = {"User-Agent": settings.user_agent, "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8"}
        return httpx.Client(headers=headers, timeout=20, follow_redirects=True, **kw)

    @staticmethod
    def parse_price(text: str | float | int | None) -> Optional[float]:
        if text is None:
            return None
        if isinstance(text, (int, float)):
            return float(text)
        m = re.search(r"[\d][\d,]*(?:\.\d+)?", str(text))
        return float(m.group(0).replace(",", "")) if m else None
