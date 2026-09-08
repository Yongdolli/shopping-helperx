import { Link } from "react-router-dom";
import { useStore } from "../store";
import { ALERT_LABEL, fmtPrice, timeAgo } from "../lib/format";
import { dday, weeklySummary } from "../lib/report";
import type { ProductOverview } from "../types";

const CLS: Record<string, string> = {
  target: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/50 dark:text-emerald-200",
  drop: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/50 dark:text-emerald-200",
  low: "bg-sky-100 text-sky-800 dark:bg-sky-900/50 dark:text-sky-200",
  restock: "bg-violet-100 text-violet-800 dark:bg-violet-900/50 dark:text-violet-200",
  fake: "bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-200",
  paused: "bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200",
};

export default function Alerts() {
  const { alerts, products, markRead, markAllRead, rates, settings } = useStore();
  const byId = Object.fromEntries(products.map((p) => [p.id, p]));
  const unread = alerts.filter((a) => !a.read).length;
  const week = weeklySummary(products, alerts, rates, settings?.threshold_pct ?? 10);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">알림 {unread > 0 && <span className="text-sm font-normal text-slate-500">안 읽음 {unread}</span>}</h1>
        {unread > 0 && <button className="btn-ghost text-xs py-1.5" onClick={markAllRead}>모두 읽음</button>}
      </div>
      {products.length > 0 && <WeeklyCard w={week} />}
      {!alerts.length && <div className="card p-8 text-center text-sm text-slate-500">아직 알림이 없습니다. 워커가 급락을 감지하면 여기에 쌓입니다.</div>}
      <ul className="space-y-2">
        {alerts.map((a) => {
          const p = byId[a.product_id];
          return (
            <li key={a.id}>
              <Link to={p ? `/p/${p.id}` : "#"} onClick={() => !a.read && markRead(a.id)}
                className={`card block p-4 ${a.read ? "opacity-70" : "ring-2 ring-sky-300/60"}`}>
                <div className="flex items-center gap-2 text-xs">
                  <span className={`rounded-full px-2 py-0.5 ${CLS[a.kind]}`}>{ALERT_LABEL[a.kind] ?? a.kind}</span>
                  <span className="text-slate-400">{timeAgo(a.created_at)}</span>
                  {!a.read && <span className="ml-auto h-2 w-2 rounded-full bg-sky-500" />}
                </div>
                <div className="mt-1 font-semibold truncate">{p?.title ?? "(삭제된 상품)"}{p?.variant ? <span className="font-normal text-slate-500 text-xs"> · {p.variant}</span> : null}</div>
                <div className="text-sm text-slate-600 dark:text-slate-300 tabular-nums">
                  {fmtPrice(a.price, p?.currency ?? "KRW")}
                  {a.baseline != null && a.kind !== "fake" && a.kind !== "paused" && <> · 기준선 {fmtPrice(a.baseline, p?.currency ?? "KRW")}</>}
                  {a.pct != null && a.kind !== "fake" && <span className="text-emerald-600 font-semibold"> ▼{a.pct}%</span>}
                </div>
                {a.note && <div className="mt-1 text-xs text-amber-600">⚠ {a.note}</div>}
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

const md = (d: Date) => `${d.getMonth() + 1}/${d.getDate()}`;

// 렌더 함수 밖에 정의 — 안에서 만들면 매 렌더마다 새 컴포넌트가 되어 전부 리마운트된다
const Row = ({ icon, title, children }: { icon: string; title: string; children: React.ReactNode }) => (
  <div className="mt-2">
    <div className="text-xs font-semibold">{icon} {title}</div>
    <ul className="mt-0.5 text-xs text-slate-600 dark:text-slate-300 space-y-0.5">{children}</ul>
  </div>
);
const Item = ({ p, right }: { p: ProductOverview; right: string }) => (
  <li className="flex justify-between gap-2"><Link to={`/p/${p.id}`} className="truncate hover:text-sky-600">{p.title}</Link><span className="shrink-0 tabular-nums text-slate-500">{right}</span></li>
);

/** 이번 주 요약 — 워커가 월요일 아침 텔레그램/이메일로 보내는 리포트와 같은 내용 */
function WeeklyCard({ w }: { w: ReturnType<typeof weeklySummary> }) {
  const kinds = Object.entries(w.alerts).sort((a, b) => b[1] - a[1]).map(([k, n]) => `${ALERT_LABEL[k] ?? k} ${n}`).join(" · ");
  return (
    <div className="card p-4 bg-gradient-to-br from-indigo-50 to-white dark:from-indigo-950/40 dark:to-slate-900">
      <div className="flex items-baseline justify-between gap-2">
        <div className="font-semibold">📋 이번 주 요약 <span className="text-xs font-normal text-slate-500">{md(w.start)}~{md(w.end)}</span></div>
        <div className="text-xs text-slate-500">추적 {w.tracked}개 · 알림 {w.total}건</div>
      </div>
      {kinds && <div className="mt-0.5 text-xs text-slate-500">{kinds}</div>}
      {w.buyNow.length > 0 && <Row icon="✅" title={`지금 사도 됨 (${w.buyNow.length})`}>
        {w.buyNow.slice(0, 5).map(({ p, why }) => <Item key={p.id} p={p} right={`${fmtPrice(p.last_price, p.currency)} · ${why}`} />)}
      </Row>}
      {w.targetNear.length > 0 && <Row icon="🎯" title={`목표가 근접 (${w.targetNear.length})`}>
        {w.targetNear.slice(0, 5).map(({ p, gap }) => <Item key={p.id} p={p} right={`${fmtPrice(p.last_price, p.currency)} · 목표가까지 ${gap.toFixed(0)}%`} />)}
      </Row>}
      {w.sales.length > 0 && <Row icon="⏳" title="30일 내 세일">
        {w.sales.slice(0, 5).map((s) => <li key={s.name} className="flex justify-between gap-2"><span>{s.name} {dday(s.daysUntil)}</span><span className="text-slate-500">상품 {s.count}개</span></li>)}
      </Row>}
      {w.purchases > 0 && <div className="mt-2 text-xs">💰 이번 주 구매 {w.purchases}건 · 절약 ≈ <b>{fmtPrice(w.savedKrw, "KRW")}</b> <span className="text-slate-500">(기준선 대비)</span></div>}
      {w.riskHigh.length > 0 && <Row icon="⚠" title={`정품 리스크 높음 ${w.riskHigh.length}개 — 판매자를 확인하세요`}>
        {w.riskHigh.slice(0, 3).map((p) => <Item key={p.id} p={p} right="" />)}
      </Row>}
      {w.paused.length > 0 && <div className="mt-2 text-xs text-slate-500">⏸ 추적 중단 {w.paused.length}개 — 상세에서 재개하거나 북마클릿으로 기록하세요</div>}
      {w.empty && <div className="mt-2 text-xs text-slate-500">조용한 한 주였습니다. 특별한 신호 없음.</div>}
      <div className="mt-2 text-[11px] text-slate-400">텔레그램·이메일을 켜 두면 월요일 아침에 같은 요약이 도착합니다 (설정).</div>
    </div>
  );
}
