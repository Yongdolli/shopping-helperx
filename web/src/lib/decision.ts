/** 구매 결정 한 줄 — 워커 decision.py 와 규칙 동일. 모든 신호를 verdict + headline + reasons 로 합친다. */
export type Verdict = "buy" | "wait" | "avoid" | "neutral";
export interface Decision { verdict: Verdict; headline: string; reasons: string[] }

export function decide(o: {
  pctVsBaseline: number | null; threshold: number; risk: "low" | "medium" | "high"; fake: boolean;
  targetHit: boolean | null; landedRank?: [number, number] | null; waitLabel?: string | null; trendPct?: number | null;
}): Decision {
  const r: string[] = [];
  if (o.pctVsBaseline != null) r.push(`평소보다 ${Math.abs(o.pctVsBaseline).toFixed(0)}% ${o.pctVsBaseline >= 0 ? "싸다" : "비싸다"}`);
  if (o.targetHit) r.push("목표가 도달");
  if (o.fake) r.push("표시 할인은 가짜");
  if (o.risk === "high") r.push("정품 리스크 높음");
  else if (o.risk === "medium") r.push("정품 리스크 보통");
  if (o.landedRank && o.landedRank[1] > 1) r.push(`최종가 ${o.landedRank[1]}곳 중 ${o.landedRank[0]}위`);
  if (o.trendPct != null && Math.abs(o.trendPct) >= 5) r.push(`30일 ${o.trendPct < 0 ? "하락" : "상승"} 추세`);
  if (o.waitLabel) r.push(o.waitLabel);

  const cheap = o.pctVsBaseline != null && o.pctVsBaseline >= o.threshold;
  if (o.risk === "high") return { verdict: "avoid", headline: "⛔ 이 판매처는 피하세요", reasons: r };
  if (o.targetHit || (cheap && !o.fake)) {
    if (o.trendPct != null && o.trendPct <= -8 && !o.targetHit) return { verdict: "wait", headline: "⏳ 더 떨어지는 중 — 조금만 더", reasons: r };
    return { verdict: "buy", headline: "✅ 지금 사도 됨", reasons: r };
  }
  if (o.waitLabel) return { verdict: "wait", headline: "⏳ 기다려볼 만함", reasons: r };
  if (o.fake) return { verdict: "neutral", headline: "😐 할인 아님 — 평소 가격", reasons: r };
  return { verdict: "neutral", headline: "😐 특별한 신호 없음", reasons: r };
}

export const VERDICT_CLS: Record<Verdict, string> = {
  buy: "bg-emerald-50 text-emerald-900 dark:bg-emerald-900/40 dark:text-emerald-100 ring-emerald-200 dark:ring-emerald-800",
  wait: "bg-indigo-50 text-indigo-900 dark:bg-indigo-900/40 dark:text-indigo-100 ring-indigo-200 dark:ring-indigo-800",
  avoid: "bg-rose-50 text-rose-900 dark:bg-rose-900/40 dark:text-rose-100 ring-rose-200 dark:ring-rose-800",
  neutral: "bg-slate-50 text-slate-700 dark:bg-slate-800/60 dark:text-slate-200 ring-slate-200 dark:ring-slate-700",
};
