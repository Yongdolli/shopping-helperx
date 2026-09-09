import { Link } from "react-router-dom";
import type { ProductOverview } from "../types";
import { COUNTRY_FLAG, SITE_LABEL, fmtPct, fmtPrice, isManualOnly, timeAgo } from "../lib/format";
import { RISK_CLS, RISK_LABEL } from "../lib/risk";
import { VERDICT_CLS } from "../lib/decision";
import { trendLabel } from "../lib/trend";

const SITE_COLOR: Record<string, string> = {
  coupang: "bg-rose-500", "11st": "bg-red-500", gmarket: "bg-lime-500", naver: "bg-green-500", danawa: "bg-sky-500",
  aliexpress: "bg-orange-500", temu: "bg-orange-600", taobao: "bg-orange-400", jd: "bg-red-600",
  amazon: "bg-amber-500", ebay: "bg-blue-600", walmart: "bg-blue-500", bestbuy: "bg-yellow-500", target: "bg-red-500",
};

/** 배지는 우선순위대로 최대 2개만. 나머지는 상세에서. */
function badges(p: ProductOverview, threshold: number): Array<[string, string]> {
  const out: Array<[string, string]> = [];
  const drop = p.pct_vs_baseline != null && p.pct_vs_baseline >= threshold;
  if (!p.active && p.purchased_at) out.push(["구매함 ✓", "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/50 dark:text-emerald-200"]);
  else if (!p.active) out.push(["중단됨", "bg-slate-200 text-slate-600 dark:bg-slate-700 dark:text-slate-300"]);
  if (p.risk.level !== "low") out.push([RISK_LABEL[p.risk.level], RISK_CLS[p.risk.level]]);
  if (p.target_hit) out.push(["목표가 도달 🎯", "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/50 dark:text-emerald-200"]);
  if (p.pending_confirm) out.push(["확인 대기", "bg-violet-100 text-violet-800 dark:bg-violet-900/50 dark:text-violet-200"]);
  if (p.fake) out.push(["가짜 할인 의심", "bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-200"]);
  if (drop) out.push([`급락 ▼${threshold}%↑`, "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/50 dark:text-emerald-200"]);
  if (p.last_price != null && p.all_time_low != null && p.last_price <= p.all_time_low) out.push(["역대 최저", "bg-sky-100 text-sky-800 dark:bg-sky-900/50 dark:text-sky-200"]);
  const t = trendLabel(p.trend_pct);
  if (t) out.push([t, "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300"]);
  if (isManualOnly(p.last_error)) out.push(["📌 직접 기록", "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300"]);
  else if ((p.fail_count ?? 0) >= 3) out.push([`수집 실패 ${p.fail_count}회`, "bg-rose-100 text-rose-700 dark:bg-rose-900/50 dark:text-rose-200"]);
  return out.slice(0, 2);
}

/** to=null 이면 링크 없는 읽기 전용 카드 (공유 보기) */
export default function ProductCard({ p, threshold, to }: { p: ProductOverview; threshold: number; to?: string | null }) {
  const ring = p.decision.verdict === "avoid" ? "ring-2 ring-rose-400/70" : p.decision.verdict === "buy" ? "ring-2 ring-emerald-400/70" : "";
  const cls = `card block p-4 transition ${to === null ? "" : "hover:ring-sky-400"} ${ring} ${!p.active ? "opacity-70" : ""}`;
  const inner = (
      <div className="flex gap-3">
        <div className="h-16 w-16 shrink-0 overflow-hidden rounded-xl bg-slate-100 dark:bg-slate-800 flex items-center justify-center">
          {p.image_url
            ? <img src={p.image_url} alt="" className="h-full w-full object-cover" />
            : <div className={`h-9 w-9 rounded-lg ${SITE_COLOR[p.site] ?? "bg-slate-400"} text-white text-[11px] font-bold flex items-center justify-center`}>{(SITE_LABEL[p.site] ?? p.site).slice(0, 2)}</div>}
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-[11px] text-slate-500 truncate">
            {COUNTRY_FLAG[p.country]} {SITE_LABEL[p.site] ?? p.site}{p.last_seller ? ` · ${p.last_seller}` : ""} · {timeAgo(p.last_captured_at)}
            {p.tags?.length ? <> · {p.tags.map((t) => `#${t}`).join(" ")}</> : null}
          </div>
          <div className="truncate font-semibold leading-snug">{p.title}</div>
          <div className="mt-1 flex items-baseline gap-2 flex-wrap">
            <span className="text-lg font-bold tabular-nums">{fmtPrice(p.last_price, p.currency)}</span>
            {p.pct_vs_baseline != null && (
              <span className={`text-sm font-semibold tabular-nums ${p.pct_vs_baseline >= 0 ? "text-emerald-600" : "text-rose-500"}`}>{fmtPct(p.pct_vs_baseline)}</span>
            )}
            {p.currency !== "KRW" && p.landed_krw != null && <span className="text-xs text-slate-500 tabular-nums">≈ {fmtPrice(p.landed_krw, "KRW")}</span>}
            {!p.in_stock && <span className="text-[11px] rounded bg-slate-200 dark:bg-slate-700 px-1.5">품절</span>}
          </div>
          {p.active && p.decision.headline && (
            <div className={`mt-1.5 inline-block rounded-lg px-2 py-0.5 text-xs font-medium ring-1 ${VERDICT_CLS[p.decision.verdict]}`}>{p.decision.headline}</div>
          )}
          <div className="mt-1.5 flex gap-1.5 flex-wrap text-[11px]">
            {badges(p, threshold).map(([label, cls]) => <span key={label} className={`rounded-full px-2 py-0.5 ${cls}`}>{label}</span>)}
            {p.baseline == null && <span className="text-slate-400">데이터 수집 중 (3회 이상 필요)</span>}
          </div>
        </div>
      </div>
  );
  return to === null ? <div className={cls}>{inner}</div> : <Link to={to ?? `/p/${p.id}`} className={cls}>{inner}</Link>;
}
