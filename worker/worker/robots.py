"""robots.txt 준수. 호스트별로 한 번만 받아 캐시. 스크래핑 어댑터는 fetch 전에 allowed() 를 확인한다."""
from __future__ import annotations

import logging
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from .config import settings

log = logging.getLogger(__name__)
_cache: dict[str, RobotFileParser | None] = {}


def _load(host: str) -> RobotFileParser | None:
    if host in _cache:
        return _cache[host]
    rp = RobotFileParser()
    try:
        r = httpx.get(f"https://{host}/robots.txt", headers={"User-Agent": settings.user_agent}, timeout=10, follow_redirects=True)
        if r.status_code == 200:
            rp.parse(r.text.splitlines())
        elif r.status_code in (401, 403):
            rp.disallow_all = True      # 접근 자체를 막는 사이트
        else:
            rp.allow_all = True         # robots.txt 없음 → 허용
    except Exception as e:  # noqa: BLE001
        log.debug("robots.txt %s 실패 %s → 허용으로 간주", host, e)
        rp.allow_all = True
    _cache[host] = rp
    return rp


def allowed(url: str, agent: str = "*") -> bool:
    host = urlparse(url).hostname or ""
    rp = _load(host)
    return True if rp is None else rp.can_fetch(agent, url)


def reset_cache() -> None:
    _cache.clear()
