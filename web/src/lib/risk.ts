/** 정품 리스크 — 워커 risk.py 와 같은 규칙. 확정 판정이 아니라 '의심 신호의 합'. */
import type { Snapshot } from "../types";
export type RiskLevel = "low" | "medium" | "high";
export interface RiskResult { level: RiskLevel; score: number; reasons: string[] }

const STRONG = ["레플", "레플리카", "replica", "미러급", "s급", "sa급", "1:1", "고퀄", "최고급퀄", "이미테이션", "짝퉁", "가품", "custom made", "리얼리티"];
const WEAK = ["호환", "compatible", "벌크", "bulk", "리퍼", "refurb", "병행", "병행수입", "중고", "used", "비품", "비정품", "unbranded", "generic", "oem"];
const OFFICIAL = ["공식", "브랜드스토어", "브랜드 스토어", "로켓", "직영", "official", "flagship", "authorized", "정품판매"];
const OFFICIAL_SITES = new Set(["bestbuy", "walmart", "target"]);
const OVERSEAS = new Set(["aliexpress", "temu", "shein", "taobao", "tmall", "1688", "jd"]);
const NEUTRAL_SELLERS = new Set(["직접 기록", "demo", "mock-seller"]);
const SELLER_CHURN_HIGH = 5, SELLER_CHURN_MID = 3;   // 90일 내 판매자 변경 횟수 → +25 / +15

const has = (text: string, words: string[]) => { const t = text.toLowerCase(); return words.find((w) => t.includes(w.toLowerCase())) ?? null; };
export const isOfficialSeller = (seller: string | null | undefined, site: string) => OFFICIAL_SITES.has(site) || !!(seller && has(seller, OFFICIAL));

export function assessRisk(o: {
  title: string; site: string; price: number | null; seller?: string | null; baseline?: number | null;
  crossBaseline?: number | null; modelNo?: string | null; usualSeller?: string | null; verified?: boolean;
  sellerChanges?: number;   // countSellerChanges() — 최근 window 내 판매자 변경 횟수
}): RiskResult {
  if (o.verified) return { level: "low", score: 0, reasons: ["사용자가 정품 확인함"] };
  let score = 0; const reasons: string[] = [];
  const sw = has(o.title, STRONG);
  if (sw) { score += 60; reasons.push(`제목에 '${sw}'`); }
  else { const ww = has(o.title, WEAK); if (ww) { score += 15; reasons.push(`제목에 '${ww}'`); } }

  if (o.price != null && o.baseline && o.baseline > 0) {
    const pct = ((o.baseline - o.price) / o.baseline) * 100;
    if (pct >= 65) { score += 60; reasons.push(`평소 가격 대비 -${pct.toFixed(0)}%`); }
    else if (pct >= 50) { score += 40; reasons.push(`평소 가격 대비 -${pct.toFixed(0)}%`); }
    else if (pct >= 35) { score += 20; reasons.push(`평소 가격 대비 -${pct.toFixed(0)}%`); }
  }
  if (o.price != null && o.crossBaseline && o.crossBaseline > 0) {
    const pct = ((o.crossBaseline - o.price) / o.crossBaseline) * 100;
    if (pct >= 60) { score += 60; reasons.push(`같은 모델 다른 판매처 대비 -${pct.toFixed(0)}%`); }
    else if (pct >= 40) { score += 40; reasons.push(`같은 모델 다른 판매처 대비 -${pct.toFixed(0)}%`); }
    else if (pct >= 25) { score += 20; reasons.push(`같은 모델 다른 판매처 대비 -${pct.toFixed(0)}%`); }
  }
  const official = isOfficialSeller(o.seller, o.site);
  if (official) score -= 20;
  else if (o.usualSeller && isOfficialSeller(o.usualSeller, o.site) && o.seller && o.seller !== o.usualSeller) { score += 30; reasons.push(`공식 판매자(${o.usualSeller})에서 제3자(${o.seller})로 바뀜`); }
  else if (o.seller && !NEUTRAL_SELLERS.has(o.seller)) { score += 10; reasons.push("공식 판매자 아님"); }
  const churn = o.sellerChanges ?? 0;
  if (!official && churn >= SELLER_CHURN_HIGH) { score += 25; reasons.push(`판매자가 자주 바뀜 (90일 ${churn}회)`); }
  else if (!official && churn >= SELLER_CHURN_MID) { score += 15; reasons.push(`판매자가 자주 바뀜 (90일 ${churn}회)`); }
  if (OVERSEAS.has(o.site)) { score += 15; reasons.push("해외 오픈마켓 (판매자 검증 약함)"); }
  if (o.modelNo && o.title) {
    const norm = (s: string) => s.toLowerCase().replace(/-/g, "").replace(/\s/g, "");
    if (!norm(o.title).includes(norm(o.modelNo))) { score += 10; reasons.push(`제목에 모델명 ${o.modelNo} 없음`); }
  }
  score = Math.max(0, score);
  const level: RiskLevel = score >= 60 ? "high" : score >= 30 ? "medium" : "low";
  if (!reasons.length) reasons.push("특이 신호 없음");
  return { level, score, reasons };
}

/** 최근 days 안에서 판매자가 바뀐 횟수 (연속 스냅샷의 판매자가 다르면 1회). 워커 baseline.seller_changes 와 동일. */
export function countSellerChanges(snaps: Snapshot[], days = 90, now = Date.now()): number {
  const cutoff = now - days * 86400_000;
  const sellers = snaps.filter((s) => s.seller && new Date(s.captured_at).getTime() >= cutoff).map((s) => s.seller as string);
  let n = 0;
  for (let i = 1; i < sellers.length; i++) if (sellers[i] !== sellers[i - 1]) n++;
  return n;
}

export function guessModelNo(title: string): string | null {
  const m = title.toUpperCase().match(/\b[A-Z]{1,4}-?\d{2,5}[A-Z]{0,3}\d{0,2}\b/);
  return m ? m[0] : null;
}

export const RISK_LABEL: Record<RiskLevel, string> = { low: "정품 리스크 낮음", medium: "정품 리스크 보통", high: "정품 리스크 높음" };
export const RISK_CLS: Record<RiskLevel, string> = {
  low: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
  medium: "bg-orange-100 text-orange-800 dark:bg-orange-900/50 dark:text-orange-200",
  high: "bg-rose-100 text-rose-800 dark:bg-rose-900/50 dark:text-rose-200",
};
