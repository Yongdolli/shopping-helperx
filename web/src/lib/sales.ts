/** 세일 캘린더(정적) + 구매 타이밍 판단. 데이터가 쌓이면 실제 하락폭 기반 점수로 승격. */
import type { Country, Snapshot } from "../types";

interface SaleEvent { name: string; scope: Array<Country | string>; date: (y: number) => Date; span?: number; strength: 1 | 2 | 3 }

const nthWeekday = (y: number, m: number, weekday: number, n: number) => {
  const d = new Date(y, m, 1); const offset = (weekday - d.getDay() + 7) % 7;
  return new Date(y, m, 1 + offset + (n - 1) * 7);
};

export const SALE_EVENTS: SaleEvent[] = [
  { name: "설 연휴 세일", scope: ["KR"], date: (y) => new Date(y, 0, 20), span: 14, strength: 1 },
  { name: "618 쇼핑 페스티벌", scope: ["CN"], date: (y) => new Date(y, 5, 18), span: 7, strength: 2 },
  { name: "프라임데이", scope: ["amazon"], date: (y) => new Date(y, 6, 12), span: 4, strength: 3 },
  { name: "추석 연휴 세일", scope: ["KR"], date: (y) => new Date(y, 8, 25), span: 14, strength: 1 },
  { name: "애플 신제품(9월)", scope: ["전자"], date: (y) => new Date(y, 8, 10), span: 10, strength: 1 },
  { name: "광군제 11·11", scope: ["CN", "aliexpress", "temu"], date: (y) => new Date(y, 10, 11), span: 3, strength: 3 },
  { name: "11절", scope: ["11st"], date: (y) => new Date(y, 10, 11), span: 3, strength: 2 },
  { name: "블랙프라이데이", scope: ["US", "KR"], date: (y) => new Date(nthWeekday(y, 10, 4, 4).getTime() + 86400_000), span: 4, strength: 3 },
  { name: "사이버먼데이", scope: ["US"], date: (y) => new Date(nthWeekday(y, 10, 4, 4).getTime() + 4 * 86400_000), span: 1, strength: 2 },
  { name: "12·12 세일", scope: ["CN"], date: (y) => new Date(y, 11, 12), span: 2, strength: 1 },
  { name: "연말 세일", scope: ["US", "KR"], date: (y) => new Date(y, 11, 20), span: 12, strength: 1 },
];

export interface Upcoming { name: string; daysUntil: number; strength: 1 | 2 | 3 }

export function upcomingSales(country: Country, site: string, category = "전자", now = new Date(), horizonDays = 45): Upcoming[] {
  const out: Upcoming[] = [];
  const y = now.getFullYear();
  for (const e of SALE_EVENTS) {
    if (!e.scope.some((s) => s === country || s === site || s === category)) continue;
    for (const year of [y, y + 1]) {
      const start = e.date(year); const end = new Date(start.getTime() + (e.span ?? 1) * 86400_000);
      const days = Math.ceil((start.getTime() - now.getTime()) / 86400_000);
      if (now >= start && now <= end) out.push({ name: e.name, daysUntil: 0, strength: e.strength });
      else if (days > 0 && days <= horizonDays) out.push({ name: e.name, daysUntil: days, strength: e.strength });
    }
  }
  return out.sort((a, b) => a.daysUntil - b.daysUntil || b.strength - a.strength).filter((v, i, a) => a.findIndex((x) => x.name === v.name) === i);
}

export type Timing = { verdict: "buy" | "wait" | "neutral"; label: string; detail?: string };

/** 급락 중이면 지금, 큰 세일이 30일 내면 기다림, 그 외 중립 */
export function buyTiming(dropNow: boolean, upcoming: Upcoming[]): Timing {
  if (dropNow) return { verdict: "buy", label: "지금 사도 됨", detail: upcoming[0] ? `${upcoming[0].name}까지 ${upcoming[0].daysUntil}일이지만 이미 급락 상태` : undefined };
  const big = upcoming.find((u) => u.strength >= 2 && u.daysUntil <= 30);
  if (big) return { verdict: "wait", label: big.daysUntil === 0 ? `${big.name} 진행 중` : `${big.daysUntil}일 뒤 ${big.name} — 기다려볼 만함` };
  const any = upcoming[0];
  if (any) return { verdict: "neutral", label: `${any.daysUntil}일 뒤 ${any.name}` };
  return { verdict: "neutral", label: "45일 내 큰 세일 없음" };
}

// ---------------------------------------------------------------- 실데이터 기반 통계

export interface EventStat { name: string; date: Date; dropPct: number; minPrice: number; before: number }

/** 이력 범위 안에 든 세일 이벤트마다: 이벤트 창(시작~span)의 최저가 vs 직전 30일 중앙값 → 실제 하락폭. */
export function eventStats(snaps: Snapshot[], country: Country, site: string, category = "전자"): EventStat[] {
  const ok = snaps.filter((s) => s.in_stock && !s.suspect);
  if (ok.length < 6) return [];
  const t0 = new Date(ok[0].captured_at).getTime(), t1 = new Date(ok[ok.length - 1].captured_at).getTime();
  const out: EventStat[] = [];
  for (const e of SALE_EVENTS) {
    if (!e.scope.some((s) => s === country || s === site || s === category)) continue;
    for (const y of new Set([new Date(t0).getFullYear(), new Date(t1).getFullYear()])) {
      const start = e.date(y).getTime(), end = start + (e.span ?? 1) * 86400_000;
      if (start < t0 || end > t1 + 86400_000) continue;
      const inWin = ok.filter((s) => { const t = new Date(s.captured_at).getTime(); return t >= start && t <= end; }).map((s) => s.price);
      const before = ok.filter((s) => { const t = new Date(s.captured_at).getTime(); return t >= start - 30 * 86400_000 && t < start; }).map((s) => s.price).sort((a, b) => a - b);
      if (inWin.length < 1 || before.length < 3) continue;
      const med = before[Math.floor(before.length / 2)];
      const min = Math.min(...inWin);
      out.push({ name: e.name, date: new Date(start), dropPct: +(((med - min) / med) * 100).toFixed(1), minPrice: min, before: med });
    }
  }
  return out.sort((a, b) => b.date.getTime() - a.date.getTime());
}

export interface PurchaseReport { minAfter: number | null; diffPct: number | null; grade: "great" | "ok" | "early"; label: string }

/** 구매 후 이력으로 성적표: 구매가 vs 구매 후 최저가 */
export function purchaseReport(snaps: Snapshot[], purchasedAt: string, purchasedPrice: number): PurchaseReport {
  const t = new Date(purchasedAt).getTime();
  const after = snaps.filter((s) => s.in_stock && !s.suspect && new Date(s.captured_at).getTime() > t).map((s) => s.price);
  if (!after.length) return { minAfter: null, diffPct: null, grade: "ok", label: "구매 후 데이터 수집 중" };
  const min = Math.min(...after);
  const diff = +(((min - purchasedPrice) / purchasedPrice) * 100).toFixed(1); // 양수 = 이후에 더 비쌌다(잘 삼)
  if (diff >= -2) return { minAfter: min, diffPct: diff, grade: "great", label: `잘 샀어요 — 이후 최저가가 ${diff >= 0 ? "+" : ""}${diff}%` };
  if (diff >= -8) return { minAfter: min, diffPct: diff, grade: "ok", label: `무난 — 이후 ${Math.abs(diff)}% 더 떨어진 적 있음` };
  return { minAfter: min, diffPct: diff, grade: "early", label: `조금 일렀어요 — 이후 ${Math.abs(diff)}% 더 떨어짐` };
}
