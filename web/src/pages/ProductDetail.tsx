import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../lib/api";
import { useStore } from "../store";
import PriceChart from "../components/PriceChart";
import { toast } from "../components/Toast";
import type { Snapshot } from "../types";
import { ALERT_LABEL, COUNTRY_FLAG, SITE_LABEL, fmtPct, fmtPrice, isManualOnly, timeAgo } from "../lib/format";
import { RISK_CLS, RISK_LABEL } from "../lib/risk";
import { CATEGORIES, landedPrice } from "../lib/landed";
import { buyTiming, eventStats, purchaseReport, upcomingSales } from "../lib/sales";
import { VERDICT_CLS } from "../lib/decision";
import { trendLabel } from "../lib/trend";

type Tab = "summary" | "chart" | "compare" | "alerts";

export default function ProductDetail() {
  const { id = "" } = useParams();
  const nav = useNavigate();
  const { products, settings, removeProduct, setActive, setVerified, setCategory, setTarget, setTags, markPurchased, alerts, rates, ratesLive } = useStore();
  const p = products.find((x) => x.id === id);
  const [snaps, setSnaps] = useState<Snapshot[]>([]);
  const [days, setDays] = useState(90);
  const [tab, setTab] = useState<Tab>("summary");
  const [buyOpen, setBuyOpen] = useState(false);
  const threshold = settings?.threshold_pct ?? 10;

  useEffect(() => { api.history(id, days).then(setSnaps); }, [id, days]);

  if (!p) return <div className="text-sm text-slate-500">상품을 찾을 수 없습니다. <Link to="/" className="text-sky-600">홈으로</Link></div>;

  const myAlerts = alerts.filter((a) => a.product_id === id);
  const siblings = products.filter((x) => x.id !== id && x.active && (x.url.split("?")[0] === p.url.split("?")[0] || (p.model_no && x.model_no === p.model_no)));
  const category = p.category ?? "전자";
  const landed = p.last_price != null ? landedPrice(p.last_price, p.currency, p.site, rates, category) : null;
  const drop = p.pct_vs_baseline != null && p.pct_vs_baseline >= threshold;
  const upcoming = upcomingSales(p.country, p.site, category);
  const timing = buyTiming(drop, upcoming);
  const compare = [p, ...siblings].filter((x) => x.last_price != null)
    .map((x) => ({ x, l: landedPrice(x.last_price as number, x.currency, x.site, rates, x.category ?? category) }))
    .sort((a, b) => (a.x.risk.level === "high" ? 1 : 0) - (b.x.risk.level === "high" ? 1 : 0) || a.l.totalKrw - b.l.totalKrw);
  const hi = snaps.length ? Math.max(...snaps.map((s) => s.price)) : null;
  const lo = snaps.length ? Math.min(...snaps.map((s) => s.price)) : null;
  const sellers = Array.from(new Set(snaps.map((s) => s.seller).filter(Boolean)));
  const savedKrw = p.purchased_price != null && p.baseline != null ? Math.max(0, p.baseline - p.purchased_price) : null;
  const stats = eventStats(snaps, p.country, p.site, category);
  const report = p.purchased_at && p.purchased_price != null ? purchaseReport(snaps, p.purchased_at, p.purchased_price) : null;

  const TabBtn = ({ k, label, n }: { k: Tab; label: string; n?: number }) => (
    <button onClick={() => setTab(k)} className={`flex-1 rounded-lg px-2 py-1.5 text-sm ${tab === k ? "bg-white dark:bg-slate-900 shadow font-semibold" : "text-slate-500"}`}>
      {label}{n ? <span className="ml-1 text-xs text-slate-400">{n}</span> : null}
    </button>
  );

  return (
    <div className="space-y-4">
      <button onClick={() => nav(-1)} className="text-sm text-slate-500">← 뒤로</button>

      {/* 헤더 + 결정 카드 */}
      <div className="card p-4 md:p-6">
        <div className="text-xs text-slate-500">
          {COUNTRY_FLAG[p.country]} {SITE_LABEL[p.site] ?? p.site}{p.last_seller ? ` · ${p.last_seller}` : ""} · {timeAgo(p.last_captured_at)} 수집{p.model_no ? ` · 모델 ${p.model_no}` : ""}
        </div>
        <h1 className="mt-1 text-lg md:text-xl font-bold leading-snug">{p.title}</h1>
        {p.variant && <div className="text-xs text-slate-500 mt-0.5">옵션 {p.variant}</div>}
        <TagEditor tags={p.tags ?? []} onChange={(t) => setTags(p.id, t)} />

        <div className="mt-3 flex items-baseline gap-3 flex-wrap">
          <span className="text-3xl font-bold tabular-nums">{fmtPrice(p.last_price, p.currency)}</span>
          {p.pct_vs_baseline != null && <span className={`text-base font-semibold ${p.pct_vs_baseline >= 0 ? "text-emerald-600" : "text-rose-500"}`}>평소 대비 {fmtPct(p.pct_vs_baseline)}</span>}
          {landed && landed.origin !== "KR" && <span className="text-sm text-slate-500 tabular-nums">≈ {fmtPrice(landed.totalKrw, "KRW")} 도착가</span>}
        </div>

        {p.purchased_at ? (
          <div className="mt-3 rounded-xl p-3 text-sm ring-1 bg-emerald-50 text-emerald-900 dark:bg-emerald-900/40 dark:text-emerald-100 ring-emerald-200 dark:ring-emerald-800">
            <div className="font-semibold">🛍 {new Date(p.purchased_at).toLocaleDateString("ko-KR")} 에 {fmtPrice(p.purchased_price, p.currency)} 로 구매함</div>
            {savedKrw != null && <div className="text-xs mt-0.5">평소 가격 대비 {fmtPrice(savedKrw, p.currency)} 절약</div>}
            {report && <div className={`text-xs mt-1 font-medium ${report.grade === "great" ? "text-emerald-700 dark:text-emerald-200" : report.grade === "early" ? "text-amber-700 dark:text-amber-200" : ""}`}>📊 {report.label}{report.minAfter != null ? ` (이후 최저 ${fmtPrice(report.minAfter, p.currency)})` : ""}</div>}
            <button className="text-xs underline mt-1" onClick={() => markPurchased(p.id, null)}>구매 취소 · 추적 재개</button>
          </div>
        ) : (
          <div className={`mt-3 rounded-xl p-3 ring-1 ${VERDICT_CLS[p.decision.verdict]}`}>
            <div className="text-base font-bold">{p.decision.headline}</div>
            <div className="mt-0.5 text-xs opacity-80">{p.decision.reasons.join(" · ")}</div>
          </div>
        )}
        {!p.active && !p.purchased_at && <div className="mt-2 inline-block rounded-full bg-slate-200 dark:bg-slate-700 px-2 py-0.5 text-xs">추적 중단됨</div>}
        {isManualOnly(p.last_error) ? (
          <div className="mt-2 rounded-xl bg-sky-50 dark:bg-sky-900/30 p-3 text-xs text-sky-900 dark:text-sky-100">
            <b>{SITE_LABEL[p.site] ?? p.site}</b> 는 자동 수집을 막아 두어 워커가 가격을 못 읽습니다. 대신 <b>내 브라우저가 대신 읽는 📌 북마클릿</b>(PC Chrome: 설정 화면의 버튼을 북마크바로 끌어다 놓고, 이 상품 페이지에서 클릭)이나 Chrome 확장으로 기록하세요. 3회 이상 쌓이면 판정이 시작됩니다.
            {p.site === "coupang" && <> 쿠팡은 <b>파트너스 API 키</b>(무료)를 worker/.env 에 넣으면 자동 수집됩니다.</>}
            <div className="mt-1"><Link to="/settings" className="font-semibold underline">설정에서 북마클릿 가져오기 →</Link></div>
          </div>
        ) : (p.fail_count ?? 0) >= 3 && <div className="mt-2 rounded-xl bg-rose-50 dark:bg-rose-900/30 p-3 text-xs text-rose-700 dark:text-rose-200">수집이 {p.fail_count}회 연속 실패했습니다: {p.last_error}</div>}
        {p.pending_confirm && <div className="mt-2 rounded-xl bg-violet-50 dark:bg-violet-900/30 p-3 text-xs text-violet-800 dark:text-violet-200">마지막 수집값이 평소보다 40% 이상 낮아 <b>확인 대기</b> 중입니다. 다음 수집에서 같은 수준이면 알림이 나갑니다.</div>}

        <div className="mt-4 flex gap-2 flex-wrap">
          <a href={p.url} target="_blank" rel="noreferrer" className="btn-primary">사이트에서 보기 ↗</a>
          {p.active && <button className="btn-ghost" onClick={() => setBuyOpen(true)}>🛍 구매했어요</button>}
          {p.active
            ? <button className="btn-ghost" onClick={() => { setActive(p.id, false); toast("추적을 중단했습니다"); }}>추적 중단</button>
            : !p.purchased_at && <button className="btn-ghost" onClick={() => { setActive(p.id, true); toast("추적을 재개했습니다"); }}>추적 재개</button>}
          {!p.active && <button className="btn-ghost text-rose-600" onClick={async () => { if (confirm("이력까지 완전히 삭제할까요?")) { await removeProduct(p.id); nav("/"); } }}>삭제</button>}
        </div>
      </div>

      {buyOpen && <BuyModal defaultPrice={p.last_price ?? 0} currency={p.currency} baseline={p.baseline} onClose={() => setBuyOpen(false)}
        onSave={async (price) => { await markPurchased(p.id, price); setBuyOpen(false); toast("구매를 기록했습니다"); }} />}

      {/* 탭 */}
      <div className="flex gap-1 rounded-xl bg-slate-100 dark:bg-slate-800 p-1">
        <TabBtn k="summary" label="요약" />
        <TabBtn k="chart" label="추이" />
        <TabBtn k="compare" label="비교" n={siblings.length || undefined} />
        <TabBtn k="alerts" label="알림" n={myAlerts.length || undefined} />
      </div>

      {tab === "summary" && (
        <div className="space-y-3">
          {/* 목표가 */}
          <div className="card p-4 md:p-5">
            <div className="flex items-center justify-between">
              <div className="font-semibold text-sm">🎯 목표가 {p.target_hit && <span className="ml-1 text-xs text-emerald-600">도달!</span>}</div>
              <div className="text-sm tabular-nums font-semibold">{p.target_price ? fmtPrice(p.target_price, p.currency) : "미설정"}</div>
            </div>
            <TargetSlider baseline={p.baseline} last={p.last_price} currency={p.currency} value={p.target_price ?? null}
              onChange={(v) => { setTarget(p.id, v); toast(v ? "목표가를 설정했습니다" : "목표가를 해제했습니다"); }} />
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
            <Kv k={`${settings?.window_days ?? 90}일 기준선(중앙값)`} v={fmtPrice(p.baseline, p.currency)} />
            <Kv k={`알림 목표가 (-${threshold}%)`} v={p.baseline ? fmtPrice(p.baseline * (1 - threshold / 100), p.currency) : "—"} />
            <Kv k="역대 최저" v={fmtPrice(p.all_time_low, p.currency)} />
            <Kv k="30일 추세" v={trendLabel(p.trend_pct) ?? (p.trend_pct != null ? `보합 ${p.trend_pct}%` : "—")} />
          </div>

          {p.claimed_pct != null && (
            <div className={`card p-4 text-sm ${p.fake ? "bg-amber-50 dark:bg-amber-900/30 text-amber-800 dark:text-amber-200" : ""}`}>
              <div className="flex justify-between"><span>사이트 표시 할인 (정가 {fmtPrice(p.last_list_price, p.currency)} 대비)</span><b>-{p.claimed_pct}%</b></div>
              <div className="flex justify-between"><span>실제 할인 (평소 가격 대비)</span><b>{fmtPct(p.pct_vs_baseline)}</b></div>
              {p.fake && <div className="mt-1 text-xs">정가를 높게 표시해 할인처럼 보이지만, 평소 판매가와 거의 같습니다.</div>}
            </div>
          )}

          <div className={`card p-4 text-sm ${p.risk.level === "high" ? "bg-rose-50 dark:bg-rose-900/30" : p.risk.level === "medium" ? "bg-orange-50 dark:bg-orange-900/30" : ""}`}>
            <div className="flex items-center justify-between gap-2">
              <span className={`rounded-full px-2 py-0.5 text-xs ${RISK_CLS[p.risk.level]}`}>{RISK_LABEL[p.risk.level]}{p.verified ? " · 확인됨 ✓" : ""}</span>
              <button className="text-xs text-sky-600 underline" onClick={() => setVerified(p.id, !p.verified)}>{p.verified ? "정품 확인 취소" : "정품 확인됨으로 표시"}</button>
            </div>
            <ul className="mt-1.5 text-xs text-slate-600 dark:text-slate-300 space-y-0.5">{p.risk.reasons.map((r) => <li key={r}>· {r}</li>)}</ul>
            {p.risk.level === "high" && <div className="mt-1.5 text-xs text-rose-700 dark:text-rose-200">확정 판정이 아닙니다. 구매 전 판매자·구성품·보증 여부를 확인하세요.</div>}
          </div>

          <div className={`card p-4 text-sm flex items-center justify-between gap-2 ${timing.verdict === "buy" ? "bg-emerald-50 dark:bg-emerald-900/30" : timing.verdict === "wait" ? "bg-indigo-50 dark:bg-indigo-900/30" : ""}`}>
            <div>
              <div className="text-[11px] text-slate-500">세일 캘린더</div>
              <div className="font-semibold">{timing.verdict === "buy" ? "✅ " : timing.verdict === "wait" ? "⏳ " : ""}{timing.label}</div>
            </div>
            {upcoming.length > 0 && <div className="text-[11px] text-slate-500 text-right">{upcoming.slice(0, 3).map((u) => <div key={u.name}>{u.daysUntil === 0 ? "진행 중" : `D-${u.daysUntil}`} {u.name}</div>)}</div>}
          </div>
          {stats.length > 0 && (
            <div className="card p-4 text-sm">
              <div className="text-[11px] text-slate-500 mb-1">이 상품의 과거 세일 실적 (실제 데이터)</div>
              <ul className="space-y-0.5 text-xs">
                {stats.slice(0, 4).map((st) => (
                  <li key={st.name + st.date.toISOString()} className="flex justify-between">
                    <span>{st.date.getFullYear()}년 {st.name}</span>
                    <span className={`tabular-nums font-semibold ${st.dropPct >= 5 ? "text-emerald-600" : "text-slate-500"}`}>{st.dropPct > 0 ? `▼${st.dropPct}%` : "변화 없음"} <span className="font-normal text-slate-400">({fmtPrice(st.minPrice, p.currency)})</span></span>
                  </li>
                ))}
              </ul>
              <div className="mt-1 text-[11px] text-slate-400">직전 30일 중앙값 대비 세일 기간 최저가. 이 숫자가 쌓이면 "기다려볼 만함" 판단의 근거가 됩니다.</div>
            </div>
          )}

          {landed && landed.origin !== "KR" && (
            <div className="card p-4 text-sm">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[11px] text-slate-500">한국 도착 최종가 (추정{ratesLive ? ", 실시간 환율" : ", 폴백 환율"})</span>
                <select className="text-xs bg-transparent border border-slate-300 dark:border-slate-700 rounded-lg px-1.5 py-0.5" value={category} onChange={(e) => setCategory(p.id, e.target.value)}>
                  {Object.keys(CATEGORIES).map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
              <div className="text-2xl font-bold tabular-nums">{fmtPrice(landed.totalKrw, "KRW")}</div>
              <ul className="mt-1 text-xs text-slate-600 dark:text-slate-300 grid grid-cols-2 gap-x-3">
                {landed.lines.map(([k, v]) => <li key={k} className="flex justify-between"><span>{k}</span><span className="tabular-nums">{fmtPrice(v, "KRW")}</span></li>)}
              </ul>
              <div className="mt-1 text-[11px] text-slate-500">{landed.note} · 세율은 카테고리 대표값이라 실제와 다를 수 있습니다.</div>
            </div>
          )}
        </div>
      )}

      {tab === "chart" && (
        <div className="card p-4 md:p-6">
          <div className="flex items-center justify-between mb-2">
            <h2 className="font-semibold">가격 추이</h2>
            <div className="flex gap-1">
              {[30, 90, 180, 365].map((d) => <button key={d} onClick={() => setDays(d)} className={`rounded-lg px-2.5 py-1 text-xs ${days === d ? "bg-slate-900 text-white dark:bg-white dark:text-slate-900" : "text-slate-500"}`}>{d}일</button>)}
            </div>
          </div>
          <PriceChart snaps={snaps} currency={p.currency} baseline={p.baseline} threshold={threshold} alerts={myAlerts} target={p.target_price ?? null} scope={[p.country, p.site, category]} />
          <div className="mt-2 grid grid-cols-2 gap-2 text-xs text-slate-500">
            <div>기간 최저 / 최고: <b className="tabular-nums">{fmtPrice(lo, p.currency)} / {fmtPrice(hi, p.currency)}</b></div>
            {sellers.length > 1 && <div>판매자 {sellers.length}곳: {sellers.join(", ")}</div>}
          </div>
          <div className="mt-1 text-[11px] text-slate-400">● 알림 시점 · 세로선: 세일 이벤트(보라) / 판매자 변경(주황) · 🎯 목표가</div>
        </div>
      )}

      {tab === "compare" && (
        <div className="card p-4 md:p-6">
          <h2 className="font-semibold">어디서 사는 게 가장 싼가</h2>
          <p className="text-xs text-slate-500 mb-2">같은 모델·옵션을 한국 도착 최종가(환율·배송·세금 추정)로 비교. 정품 리스크 높음은 맨 아래.</p>
          {siblings.length === 0 ? (
            <div className="text-sm text-slate-500 py-4 text-center">같은 모델의 다른 판매처를 추가하면 여기서 비교됩니다. <Link to="/add" className="text-sky-600">다른 사이트 URL 추가</Link></div>
          ) : (
            <ul className="divide-y divide-slate-100 dark:divide-slate-800 text-sm">
              {compare.map(({ x, l }, i) => (
                <li key={x.id} className={`py-2 ${x.id === p.id ? "font-semibold" : ""}`}>
                  <Link to={`/p/${x.id}`} className="flex items-center justify-between gap-2">
                    <span className="truncate">
                      {i === 0 && x.risk.level !== "high" && <span className="mr-1 rounded bg-emerald-100 text-emerald-800 dark:bg-emerald-900/50 dark:text-emerald-200 px-1 text-[10px]">최저</span>}
                      {COUNTRY_FLAG[x.country]} {SITE_LABEL[x.site] ?? x.site}{x.variant ? ` · ${x.variant}` : ""}{x.id === p.id ? " (현재)" : ""}
                      {x.risk.level === "high" && <span className="ml-1 text-[10px] text-rose-600">리스크 높음</span>}
                    </span>
                    <span className="tabular-nums text-right shrink-0">
                      <div>{fmtPrice(l.totalKrw, "KRW")}</div>
                      {x.currency !== "KRW" && <div className="text-[11px] text-slate-500 font-normal">{fmtPrice(x.last_price, x.currency)} · {l.dutyFree ? "면세" : "세금 포함"}</div>}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {tab === "alerts" && (
        <div className="card p-4 md:p-6">
          <h2 className="font-semibold mb-2">이 상품의 알림</h2>
          {myAlerts.length === 0 ? <div className="text-sm text-slate-500 py-4 text-center">아직 알림이 없습니다.</div> : (
            <ul className="divide-y divide-slate-100 dark:divide-slate-800 text-sm">
              {myAlerts.map((a) => (
                <li key={a.id} className="py-2">
                  <div className="flex justify-between"><span>{ALERT_LABEL[a.kind]} · {fmtPrice(a.price, p.currency)}{a.pct != null && !["fake", "paused"].includes(a.kind) ? ` (▼${a.pct}%)` : ""}</span><span className="text-slate-400">{timeAgo(a.created_at)}</span></div>
                  {a.note && <div className="text-xs text-amber-600">⚠ {a.note}</div>}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

function Kv({ k, v }: { k: string; v: string }) {
  return <div className="card p-3"><div className="text-[11px] text-slate-500">{k}</div><div className="font-semibold tabular-nums">{v}</div></div>;
}

function TargetSlider({ baseline, last, currency, value, onChange }: { baseline: number | null; last: number | null; currency: string; value: number | null; onChange: (v: number | null) => void }) {
  const ref = baseline ?? last;
  const [local, setLocal] = useState<number | null>(value);
  useEffect(() => setLocal(value), [value]);
  if (!ref) return <div className="text-xs text-slate-500 mt-1">가격이 수집되면 설정할 수 있습니다.</div>;
  const min = Math.round(ref * 0.5), max = Math.round(ref);
  const step = currency === "KRW" ? 1000 : 1;
  const suggested = Math.round(ref * 0.85 / step) * step;
  const pct = local ? Math.round((1 - local / ref) * 100) : null;
  return (
    <div className="mt-2">
      <input type="range" min={min} max={max} step={step} value={local ?? suggested} onChange={(e) => setLocal(Number(e.target.value))} onMouseUp={() => onChange(local ?? suggested)} onTouchEnd={() => onChange(local ?? suggested)} className="w-full accent-emerald-600" />
      <div className="flex items-center justify-between text-xs text-slate-500">
        <span>{local ? `${fmtPrice(local, currency)} (평소 대비 -${pct}%)` : `추천: ${fmtPrice(suggested, currency)} (-15%)`}</span>
        <span className="flex gap-2">
          {!value && <button className="text-sky-600 underline" onClick={() => onChange(suggested)}>추천값으로 설정</button>}
          {value && <button className="text-slate-500 underline" onClick={() => onChange(null)}>해제</button>}
        </span>
      </div>
    </div>
  );
}

function TagEditor({ tags, onChange }: { tags: string[]; onChange: (t: string[]) => void }) {
  const [edit, setEdit] = useState(false);
  const [v, setV] = useState(tags.join(", "));
  useEffect(() => setV(tags.join(", ")), [tags]);
  if (!edit) return (
    <div className="mt-1 flex flex-wrap gap-1 text-xs">
      {tags.map((t) => <span key={t} className="rounded-full bg-slate-100 dark:bg-slate-800 px-2 py-0.5">#{t}</span>)}
      <button className="text-sky-600" onClick={() => setEdit(true)}>{tags.length ? "태그 편집" : "+ 태그"}</button>
    </div>
  );
  return (
    <div className="mt-1 flex gap-2">
      <input className="input py-1 text-xs" placeholder="쉼표로 구분: 노트북, 선물" value={v} onChange={(e) => setV(e.target.value)} autoFocus />
      <button className="btn-primary py-1 text-xs" onClick={() => { onChange(v.split(",").map((s) => s.trim().replace(/^#/, "")).filter(Boolean)); setEdit(false); }}>저장</button>
    </div>
  );
}

function BuyModal({ defaultPrice, currency, baseline, onClose, onSave }: { defaultPrice: number; currency: string; baseline: number | null; onClose: () => void; onSave: (price: number) => void }) {
  const [price, setPrice] = useState(defaultPrice);
  const saved = baseline != null ? Math.max(0, baseline - price) : null;
  return (
    <div className="fixed inset-0 z-40 bg-black/40 flex items-end md:items-center justify-center p-4" onClick={onClose}>
      <div className="card w-full max-w-sm p-5 space-y-3" onClick={(e) => e.stopPropagation()}>
        <div className="font-semibold">🛍 얼마에 구매했나요?</div>
        <input className="input" type="number" inputMode="decimal" value={price} onChange={(e) => setPrice(Number(e.target.value))} />
        {saved != null && <div className="text-sm text-emerald-700 dark:text-emerald-300">평소 가격 대비 <b>{fmtPrice(saved, currency)}</b> 절약</div>}
        <div className="text-xs text-slate-500">기록하면 추적이 종료되고 홈의 "최근 30일 절약"에 합산됩니다.</div>
        <div className="flex gap-2 justify-end"><button className="btn-ghost" onClick={onClose}>취소</button><button className="btn-primary" disabled={!price} onClick={() => onSave(price)}>기록</button></div>
      </div>
    </div>
  );
}
