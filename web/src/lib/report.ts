/** 주간 요약 — 워커 report.py 와 같은 항목·규칙. 알림 탭 상단 카드에 표시 (워커는 같은 내용을 월요일 아침 텔레그램/이메일로). */
import type { Alert, ProductOverview } from "../types";
import { toKrw, type Rates } from "./fx";
import { upcomingSales } from "./sales";

export const TARGET_NEAR_PCT = 5;
export const SALE_HORIZON_DAYS = 30;

export interface WeeklySummary {
  start: Date;
  end: Date;
  tracked: number;
  alerts: Record<string, number>;
  total: number;
  buyNow: Array<{ p: ProductOverview; why: string }>;
  targetNear: Array<{ p: ProductOverview; gap: number }>;
  sales: Array<{ name: string; daysUntil: number; count: number }>;
  purchases: number;
  savedKrw: number;
  riskHigh: ProductOverview[];
  paused: ProductOverview[];
  empty: boolean;
}

export function weeklySummary(products: ProductOverview[], alerts: Alert[], rates: Rates, threshold: number, now = new Date()): WeeklySummary {
  const since = new Date(now.getTime() - 7 * 86400_000);
  const counts: Record<string, number> = {};
  for (const a of alerts) if (new Date(a.created_at) >= since) counts[a.kind] = (counts[a.kind] ?? 0) + 1;

  const buyNow: WeeklySummary["buyNow"] = [];
  const targetNear: WeeklySummary["targetNear"] = [];
  const riskHigh: ProductOverview[] = [];
  const paused: ProductOverview[] = [];
  const saleHits: Record<string, { daysUntil: number; count: number }> = {};
  let purchases = 0, savedKrw = 0;

  for (const p of products) {
    if (p.purchased_at) {
      if (new Date(p.purchased_at) >= since) {
        purchases++;
        savedKrw += Math.max(0, toKrw((p.baseline ?? p.purchased_price ?? 0) - (p.purchased_price ?? 0), p.currency, rates));
      }
      continue;
    }
    if (!p.active) { paused.push(p); continue; }
    if (p.last_price == null || !p.in_stock || p.pending_confirm) continue;   // 워커: 재고 있는 확정 스냅샷만
    const gap = p.target_price ? +(((p.last_price - p.target_price) / p.target_price) * 100).toFixed(1) : null;
    if (p.risk.level === "high") riskHigh.push(p);
    else if ((gap != null && gap <= 0) || (p.pct_vs_baseline != null && p.pct_vs_baseline >= threshold)) {
      buyNow.push({ p, why: gap != null && gap <= 0 ? "목표가 도달" : `평소보다 ${(p.pct_vs_baseline ?? 0).toFixed(0)}% 싸다` });
    } else if (gap != null && gap <= TARGET_NEAR_PCT) targetNear.push({ p, gap });
    for (const u of upcomingSales(p.country, p.site, p.category ?? "전자", now, SALE_HORIZON_DAYS)) {
      if (u.strength < 2) continue;
      saleHits[u.name] = { daysUntil: u.daysUntil, count: (saleHits[u.name]?.count ?? 0) + 1 };
    }
  }
  buyNow.sort((a, b) => (b.p.pct_vs_baseline ?? 0) - (a.p.pct_vs_baseline ?? 0));
  targetNear.sort((a, b) => a.gap - b.gap);
  const sales = Object.entries(saleHits).map(([name, v]) => ({ name, ...v })).sort((a, b) => a.daysUntil - b.daysUntil);
  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  const empty = !total && !buyNow.length && !targetNear.length && !purchases && !riskHigh.length && !paused.length;
  return {
    start: since, end: now, tracked: products.filter((p) => p.active && !p.purchased_at).length,
    alerts: counts, total, buyNow, targetNear, sales, purchases, savedKrw, riskHigh, paused, empty,
  };
}

export const dday = (d: number) => (d === 0 ? "진행 중" : `D-${d}`);
