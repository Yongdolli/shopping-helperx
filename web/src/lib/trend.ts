/** 최근 N일 가격 추세 — 선형회귀 기울기를 30일 변화율(%)로. 워커 trend.py 와 동일. suspect·품절 제외, 표본 4개 미만이면 null.
 *  적합도 R² < MIN_R2 면 null: 평평하다 오늘 뚝 떨어진 계단(세일)은 추세가 아니다 — 추세로 보면 급락에 "더 떨어지는 중"이라 기다리라고 하게 된다. */
import type { Snapshot } from "../types";

const MIN_R2 = 0.6;   // 계단식 급락 ≈ 0.3~0.5, 완만한 하락 ≈ 0.9↑

export function trendPct(snaps: Snapshot[], days = 30, now = Date.now()): number | null {
  const cutoff = now - days * 86400_000;
  const pts = snaps.filter((s) => s.in_stock && !s.suspect && new Date(s.captured_at).getTime() >= cutoff)
    .map((s) => ({ x: (new Date(s.captured_at).getTime() - cutoff) / 86400_000, y: s.price }));
  if (pts.length < 4) return null;
  const n = pts.length, mx = pts.reduce((a, p) => a + p.x, 0) / n, my = pts.reduce((a, p) => a + p.y, 0) / n;
  const sxx = pts.reduce((a, p) => a + (p.x - mx) ** 2, 0);
  if (!sxx || !my) return null;
  const slope = pts.reduce((a, p) => a + (p.x - mx) * (p.y - my), 0) / sxx;   // 가격/일
  const ssTot = pts.reduce((a, p) => a + (p.y - my) ** 2, 0);
  if (!ssTot) return 0;                                                       // 완전히 평평
  const icpt = my - slope * mx;
  const r2 = 1 - pts.reduce((a, p) => a + (p.y - (icpt + slope * p.x)) ** 2, 0) / ssTot;
  if (r2 < MIN_R2) return null;
  return +((slope * days / my) * 100).toFixed(1);
}

export const trendLabel = (t: number | null) => (t == null ? null : t <= -5 ? `↘ 하락 추세 ${t}%` : t >= 5 ? `↗ 상승 추세 +${t}%` : null);
