import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useStore } from "../store";
import ProductCard from "../components/ProductCard";
import type { Country, ProductOverview } from "../types";
import { COUNTRY_FLAG, SITE_LABEL, fmtPrice } from "../lib/format";
import { api } from "../lib/api";
import { toKrw } from "../lib/fx";
import { DealCard } from "./Deals";
import { effectivePct, groupDeals } from "../types";

type Filter = "all" | Country | "buy" | "risk" | "paused" | "bought";
type Sort = "pct" | "landed" | "recent" | "added";
const SORT_LABEL: Record<Sort, string> = { pct: "할인율", landed: "최종가", recent: "최근 갱신", added: "추가순" };

export default function Dashboard() {
  const { products, settings, loading, error, rates, deals } = useStore();
  const minDeal = settings?.deal_min_pct ?? 10;
  const topDeals = useMemo(() => groupDeals(deals).filter((d) => !d.ended && (effectivePct(d) ?? -1) >= minDeal)
    .sort((a, b) => Number(b.below_pct != null) - Number(a.below_pct != null) || (effectivePct(b) ?? 0) - (effectivePct(a) ?? 0)).slice(0, 4), [deals, minDeal]);
  const [filter, setFilter] = useState<Filter>("all");
  const [site, setSite] = useState<string>("");
  const [tag, setTag] = useState<string>("");
  const [sort, setSort] = useState<Sort>("pct");
  const [q, setQ] = useState("");
  const threshold = settings?.threshold_pct ?? 10;

  const active = products.filter((p) => p.active);
  const paused = products.filter((p) => !p.active && !p.purchased_at);
  const bought = products.filter((p) => p.purchased_at);
  const sites = Array.from(new Set(active.map((p) => p.site)));
  const tags = Array.from(new Set(active.flatMap((p) => p.tags ?? [])));

  const list = useMemo(() => {
    let l: ProductOverview[] = filter === "paused" ? paused : filter === "bought" ? bought : active;
    if (filter === "buy") l = l.filter((p) => p.decision.verdict === "buy");
    else if (filter === "risk") l = l.filter((p) => p.risk.level !== "low");
    else if (filter === "KR" || filter === "CN" || filter === "US") l = l.filter((p) => p.country === filter);
    if (site) l = l.filter((p) => p.site === site);
    if (tag) l = l.filter((p) => p.tags?.includes(tag));
    if (q.trim()) l = l.filter((p) => p.title.toLowerCase().includes(q.toLowerCase()));
    const by: Record<Sort, (a: ProductOverview, b: ProductOverview) => number> = {
      pct: (a, b) => (b.pct_vs_baseline ?? -999) - (a.pct_vs_baseline ?? -999),
      landed: (a, b) => (a.landed_krw ?? Infinity) - (b.landed_krw ?? Infinity),
      recent: (a, b) => (b.last_captured_at ?? "").localeCompare(a.last_captured_at ?? ""),
      added: (a, b) => b.created_at.localeCompare(a.created_at),
    };
    return [...l].sort(by[sort]);
  }, [active, paused, bought, filter, site, tag, q, sort]);

  const buyCount = active.filter((p) => p.decision.verdict === "buy").length;
  const riskCount = active.filter((p) => p.risk.level !== "low").length;
  const monthAgo = Date.now() - 30 * 86400_000;
  const saved = bought.filter((p) => p.purchased_at && new Date(p.purchased_at).getTime() >= monthAgo)
    .reduce((a, p) => a + Math.max(0, toKrw((p.baseline ?? p.purchased_price ?? 0) - (p.purchased_price ?? 0), p.currency, rates)), 0);

  const chip = (on: boolean, label: string, onClick: () => void, key?: string) => (
    <button key={key ?? label} onClick={onClick}
      className={`rounded-full px-3 py-1.5 text-sm whitespace-nowrap transition ${on ? "bg-slate-900 text-white dark:bg-white dark:text-slate-900" : "bg-white dark:bg-slate-900 ring-1 ring-slate-200 dark:ring-slate-800 text-slate-600 dark:text-slate-300"}`}>
      {label}
    </button>
  );

  return (
    <div className="space-y-4">
      <div className="flex items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold">오늘의 쇼핑</h1>
          <p className="text-sm text-slate-500">{active.length}개 추적 중 · 지금 사도 되는 것 {buyCount}개{paused.length ? ` · 중단 ${paused.length}` : ""}{bought.length ? ` · 구매 ${bought.length}` : ""}</p>
        </div>
        <div className="hidden md:block"><Link to="/add" className="btn-primary">＋ 상품 추가</Link></div>
      </div>

      {api.mode === "demo" && <Onboarding />}
      <InstallBanner />

      {topDeals.length > 0 && (
        <section className="space-y-2">
          <div className="flex items-baseline justify-between">
            <h2 className="font-semibold">🔥 지금 평소보다 싼 딜</h2>
            <Link to="/deals" className="text-sm text-sky-600 font-medium">전체 보기 →</Link>
          </div>
          <ul className="grid grid-cols-1 gap-2.5 lg:grid-cols-2">{topDeals.map((d) => <DealCard key={d.url} d={d} minPct={minDeal} />)}</ul>
        </section>
      )}

      <h2 className="font-semibold pt-1">📦 내가 추적하는 상품</h2>

      <div className="grid grid-cols-3 gap-3">
        <Stat label="지금 사도 됨" value={String(buyCount)} accent="text-emerald-600" onClick={() => setFilter("buy")} />
        <Stat label="정품 리스크" value={String(riskCount)} accent="text-rose-600" onClick={() => setFilter("risk")} />
        <Stat label="최근 30일 절약" value={fmtPrice(saved, "KRW")} accent="text-sky-600" onClick={() => setFilter("bought")} small />
      </div>

      <div className="flex gap-2 overflow-x-auto pb-1 -mx-4 px-4 md:mx-0 md:px-0">
        {chip(filter === "all", "전체", () => setFilter("all"))}
        {chip(filter === "buy", "✅ 사도 됨", () => setFilter("buy"))}
        {chip(filter === "risk", "리스크", () => setFilter("risk"))}
        {(["KR", "CN", "US"] as Country[]).map((c) => chip(filter === c, `${COUNTRY_FLAG[c]} ${c}`, () => setFilter(c), c))}
        {paused.length > 0 && chip(filter === "paused", `중단 ${paused.length}`, () => setFilter("paused"))}
        {bought.length > 0 && chip(filter === "bought", `구매함 ${bought.length}`, () => setFilter("bought"))}
      </div>
      {(sites.length > 1 || tags.length > 0) && (
        <div className="flex gap-2 overflow-x-auto pb-1 -mx-4 px-4 md:mx-0 md:px-0 text-xs">
          {sites.length > 1 && sites.map((s) => chip(site === s, SITE_LABEL[s] ?? s, () => setSite(site === s ? "" : s), "s-" + s))}
          {tags.map((t) => chip(tag === t, `#${t}`, () => setTag(tag === t ? "" : t), "t-" + t))}
        </div>
      )}
      <div className="flex gap-2">
        <input className="input flex-1 min-w-0" placeholder="상품명 검색" value={q} onChange={(e) => setQ(e.target.value)} />
        <select className="shrink-0 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 text-sm" value={sort} onChange={(e) => setSort(e.target.value as Sort)}>
          {(Object.keys(SORT_LABEL) as Sort[]).map((k) => <option key={k} value={k}>{SORT_LABEL[k]}</option>)}
        </select>
      </div>

      {error && <div className="card p-4 text-sm text-rose-600">{error}</div>}
      {loading && !products.length && <Skeleton />}
      {!loading && !list.length && (
        <div className="card p-8 text-center text-sm text-slate-500">
          {filter === "all" && !q && !site && !tag ? <>추적 중인 상품이 없습니다. <Link to="/add" className="text-sky-600 font-semibold">상품 URL을 추가</Link>해 보세요.</> : "해당하는 상품이 없습니다."}
        </div>
      )}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {list.map((p) => <ProductCard key={p.id} p={p} threshold={threshold} />)}
      </div>
    </div>
  );
}

function Stat({ label, value, accent, onClick, small }: { label: string; value: string; accent: string; onClick?: () => void; small?: boolean }) {
  return (
    <button onClick={onClick} className="card p-3 md:p-4 text-left hover:ring-sky-400 transition min-w-0">
      <div className="text-[11px] md:text-xs text-slate-500 truncate">{label}</div>
      <div className={`${small ? "text-base md:text-xl" : "text-2xl"} font-bold tabular-nums truncate ${accent}`}>{value}</div>
    </button>
  );
}

function Skeleton() {
  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className="card p-4 flex gap-3 animate-pulse">
          <div className="h-16 w-16 rounded-xl bg-slate-200 dark:bg-slate-800" />
          <div className="flex-1 space-y-2"><div className="h-3 w-1/3 bg-slate-200 dark:bg-slate-800 rounded" /><div className="h-4 w-3/4 bg-slate-200 dark:bg-slate-800 rounded" /><div className="h-5 w-1/2 bg-slate-200 dark:bg-slate-800 rounded" /></div>
        </div>
      ))}
    </div>
  );
}

function Onboarding() {
  const [hidden, setHidden] = useState(() => { try { return localStorage.getItem("sh-onboard") === "1"; } catch { return false; } });
  if (hidden) return null;
  return (
    <div className="card p-4 md:p-5 bg-gradient-to-br from-sky-50 to-white dark:from-sky-950/40 dark:to-slate-900">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="font-semibold">처음이신가요? 3가지 방법으로 상품을 넣을 수 있어요</div>
          <ol className="mt-2 text-sm text-slate-600 dark:text-slate-300 space-y-1 list-decimal pl-5">
            <li><Link to="/add" className="text-sky-600 font-medium">URL 붙여넣기</Link> — 쿠팡·11번가·알리·eBay 등 상품 주소</li>
            <li><Link to="/settings" className="text-sky-600 font-medium">북마클릿</Link> — 보고 있는 페이지에서 한 번에 가격 기록 (네이버·아마존도 OK)</li>
            <li>안드로이드: 쇼핑 앱에서 <b>공유 → Shopping Helper</b> (홈화면 설치 후)</li>
          </ol>
          <div className="mt-2 text-xs text-slate-500">지금 보이는 상품은 데모입니다. 3회 이상 가격이 쌓이면 "지금 사도 됨 / 기다리기" 판단이 시작됩니다.</div>
        </div>
        <button className="text-slate-400 text-lg leading-none" onClick={() => { setHidden(true); try { localStorage.setItem("sh-onboard", "1"); } catch { /* ignore */ } }} aria-label="닫기">×</button>
      </div>
    </div>
  );
}

function InstallBanner() {
  const [evt, setEvt] = useState<(Event & { prompt: () => Promise<void> }) | null>(null);
  useEffect(() => {
    const h = (e: Event) => { e.preventDefault(); setEvt(e as Event & { prompt: () => Promise<void> }); };
    window.addEventListener("beforeinstallprompt", h);
    return () => window.removeEventListener("beforeinstallprompt", h);
  }, []);
  if (!evt) return null;
  return (
    <div className="card p-3 flex items-center justify-between gap-3 text-sm">
      <span>📱 홈화면에 설치하면 앱처럼 알림·공유를 쓸 수 있어요</span>
      <button className="btn-primary py-1.5" onClick={async () => { await evt.prompt(); setEvt(null); }}>설치</button>
    </div>
  );
}
