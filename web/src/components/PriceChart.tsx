import { Area, AreaChart, CartesianGrid, ReferenceDot, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Alert, Snapshot } from "../types";
import { ALERT_LABEL, fmtPrice } from "../lib/format";
import { SALE_EVENTS } from "../lib/sales";

interface Props { snaps: Snapshot[]; currency: string; baseline: number | null; threshold: number; alerts?: Alert[]; target?: number | null; scope?: string[] }

const ALERT_COLOR: Record<string, string> = { drop: "#10b981", low: "#0ea5e9", target: "#16a34a", fake: "#f59e0b", restock: "#8b5cf6", paused: "#64748b" };

export default function PriceChart({ snaps, currency, baseline, threshold, alerts = [], target, scope = [] }: Props) {
  const data = snaps.map((s) => ({ t: new Date(s.captured_at).getTime(), price: s.in_stock ? s.price : null, seller: s.seller, suspect: s.suspect }));
  if (!snaps.length) return <div className="h-56 flex items-center justify-center text-sm text-slate-400">아직 수집된 가격이 없습니다</div>;
  const prices = snaps.map((s) => s.price);
  const lo = Math.min(...prices, baseline ?? Infinity, target ?? Infinity) * 0.95;
  const hi = Math.max(...prices, baseline ?? 0) * 1.03;
  const tgt = baseline != null ? baseline * (1 - threshold / 100) : null;
  const t0 = data[0].t, t1 = data[data.length - 1].t;
  const fmtDate = (t: number) => { const d = new Date(t); return `${d.getMonth() + 1}/${d.getDate()}`; };

  // 판매자 변경 지점
  const sellerChanges: number[] = [];
  for (let i = 1; i < data.length; i++) if (data[i].seller && data[i - 1].seller && data[i].seller !== data[i - 1].seller) sellerChanges.push(data[i].t);
  // 기간 내 세일 이벤트
  const events: Array<{ t: number; name: string }> = [];
  for (const e of SALE_EVENTS) {
    if (!e.scope.some((s) => scope.includes(s))) continue;
    for (const y of new Set([new Date(t0).getFullYear(), new Date(t1).getFullYear()])) { const t = e.date(y).getTime(); if (t >= t0 && t <= t1) events.push({ t, name: e.name }); }
  }
  const marks = alerts.filter((a) => { const t = new Date(a.created_at).getTime(); return t >= t0 && t <= t1; });

  return (
    <ResponsiveContainer width="100%" height={240}>
      <AreaChart data={data} margin={{ top: 12, right: 8, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#0ea5e9" stopOpacity={0.35} /><stop offset="100%" stopColor="#0ea5e9" stopOpacity={0} /></linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="currentColor" opacity={0.12} />
        <XAxis dataKey="t" type="number" domain={["dataMin", "dataMax"]} tickFormatter={fmtDate} tick={{ fontSize: 11 }} stroke="currentColor" opacity={0.6} />
        <YAxis domain={[lo, hi]} width={64} tick={{ fontSize: 11 }} stroke="currentColor" opacity={0.6} tickFormatter={(v: number) => (currency === "KRW" ? `${Math.round(v / 10000)}만` : v.toFixed(0))} />
        <Tooltip labelFormatter={(t) => new Date(t as number).toLocaleDateString("ko-KR")}
          formatter={(v, _n, item) => [`${fmtPrice(v as number, currency)}${item?.payload?.seller ? ` · ${item.payload.seller}` : ""}${item?.payload?.suspect ? " (확인 대기)" : ""}`, "가격"]}
          contentStyle={{ borderRadius: 12, fontSize: 12 }} />
        {baseline != null && <ReferenceLine y={baseline} stroke="#64748b" strokeDasharray="4 4" label={{ value: "기준선", fontSize: 10, position: "insideTopRight", fill: "#64748b" }} />}
        {tgt != null && <ReferenceLine y={tgt} stroke="#10b981" strokeDasharray="4 4" label={{ value: `-${threshold}%`, fontSize: 10, position: "insideBottomRight", fill: "#10b981" }} />}
        {target != null && <ReferenceLine y={target} stroke="#16a34a" strokeWidth={1.5} label={{ value: "🎯 목표가", fontSize: 10, position: "insideBottomLeft", fill: "#16a34a" }} />}
        {events.map((e) => <ReferenceLine key={e.name + e.t} x={e.t} stroke="#6366f1" strokeDasharray="2 3" label={{ value: e.name, fontSize: 9, position: "insideTop", fill: "#6366f1" }} />)}
        {sellerChanges.map((t) => <ReferenceLine key={"s" + t} x={t} stroke="#f59e0b" strokeDasharray="2 3" label={{ value: "판매자 변경", fontSize: 9, position: "insideBottom", fill: "#f59e0b" }} />)}
        <Area type="monotone" dataKey="price" stroke="#0ea5e9" strokeWidth={2} fill="url(#g)" connectNulls dot={false} activeDot={{ r: 4 }} />
        {marks.map((a) => <ReferenceDot key={a.id} x={new Date(a.created_at).getTime()} y={a.price} r={5} fill={ALERT_COLOR[a.kind] ?? "#0ea5e9"} stroke="#fff" strokeWidth={1.5} label={{ value: ALERT_LABEL[a.kind], fontSize: 9, position: "top", fill: ALERT_COLOR[a.kind] }} />)}
      </AreaChart>
    </ResponsiveContainer>
  );
}
