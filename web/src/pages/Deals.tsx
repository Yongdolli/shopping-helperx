import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useStore } from "../store";
import { toast } from "../components/Toast";
import { SITE_LABEL, fmtPrice, timeAgo } from "../lib/format";
import { effectivePct, groupDeals, type Deal } from "../types";

type Sort = "recent" | "pct";
type Mode = "cheap" | "all" | "kw";
type GDeal = Deal & { sources: string[] };
const SOURCE_LABEL: Record<string, string> = { ppomppu: "뽐뿌", ruliweb: "루리웹", clien: "클리앙", quasarzone: "퀘이사존", fmkorea: "에펨" };
export const siteName = (d: Deal) => d.site_label || SITE_LABEL[d.site] || (d.site === "unknown" ? "기타" : d.site);

/** 딜 탭 — 등록 없이 핫딜 커뮤니티에 올라온 모든 사이트의 할인을 모아, 평소 가격보다 싼 것부터 보여준다. 워커가 매시간 수집. */
export default function Deals() {
  const { deals: rawDeals, settings, addProduct } = useStore();
  const deals = useMemo(() => groupDeals(rawDeals), [rawDeals]);   // 여러 커뮤니티의 같은 딜은 하나로
  const nav = useNavigate();
  const [busy, setBusy] = useState<string | null>(null);
  const minPct = settings?.deal_min_pct ?? 10;
  const keywords = useMemo(() => (settings?.deal_keywords ?? []).map((k) => k.toLowerCase()).filter(Boolean), [settings?.deal_keywords]);
  const [q, setQ] = useState("");
  const [site, setSite] = useState("");
  const [mode, setMode] = useState<Mode>("cheap");
  const [sort, setSort] = useState<Sort>("pct");

  const kwOf = (d: Deal) => keywords.find((k) => d.title.toLowerCase().includes(k)) ?? null;
  const cheap = (d: Deal) => (effectivePct(d) ?? -1) >= minPct;
  const sites = useMemo(() => Object.entries(deals.reduce<Record<string, number>>((a, d) => { const s = siteName(d); a[s] = (a[s] ?? 0) + 1; return a; }, {}))
    .sort((a, b) => b[1] - a[1]).slice(0, 10).map(([s]) => s), [deals]);

  const list = useMemo(() => {
    let l: GDeal[] = deals;
    if (mode === "cheap") l = l.filter(cheap);
    if (mode === "kw") l = l.filter((d) => kwOf(d));
    if (site) l = l.filter((d) => siteName(d) === site);
    const t = q.trim().toLowerCase();
    if (t) l = l.filter((d) => d.title.toLowerCase().includes(t) || siteName(d).toLowerCase().includes(t));
    // 많이 싼 순: 평소 가격과 비교해 확인된 딜 먼저, 그다음 게시글·상점 표시 할인율
    return [...l].sort(sort === "pct" ? (a, b) => Number(b.below_pct != null) - Number(a.below_pct != null) || (effectivePct(b) ?? -999) - (effectivePct(a) ?? -999) || b.posted_at.localeCompare(a.posted_at) : (a, b) => b.posted_at.localeCompare(a.posted_at));
  }, [deals, mode, site, q, sort, minPct, keywords]);   // eslint-disable-line react-hooks/exhaustive-deps

  const cheapCount = deals.filter(cheap).length;
  const checked = deals.filter((d) => d.below_pct != null).length;
  const kwCount = keywords.length ? deals.filter((d) => kwOf(d)).length : 0;

  const track = async (d: Deal) => {
    if (!d.shop_url) { nav(`/add?title=${encodeURIComponent(d.title)}`); return; }
    setBusy(d.url);
    try { await addProduct(d.shop_url, d.title); toast("추적을 시작했습니다 — 가격이 3회 이상 쌓이면 판정이 붙습니다"); nav("/"); }
    catch (e) { toast("실패: " + (e as Error).message); } finally { setBusy(null); }
  };

  const tab = (on: boolean, label: string, count: number, onClick: () => void) => (
    <button key={label} onClick={onClick} className={`flex-1 rounded-lg px-3 py-2 text-sm font-medium transition ${on ? "bg-white text-slate-900 shadow-sm dark:bg-slate-700 dark:text-white" : "text-slate-500 hover:text-slate-800 dark:hover:text-slate-200"}`}>
      {label} <span className={`tabular-nums ${on ? "text-emerald-600 dark:text-emerald-400" : ""}`}>{count}</span>
    </button>
  );

  return (
    <div className="space-y-4 min-w-0">
      <header className="flex items-end justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-xl font-bold">🔥 오늘의 딜</h1>
          <p className="text-sm text-slate-500">핫딜 커뮤니티의 최근 7일 딜 <b className="text-slate-700 dark:text-slate-200">{deals.length}</b>건을 평소 가격과 비교했어요</p>
        </div>
        <details className="relative shrink-0 text-xs">
          <summary className="cursor-pointer list-none rounded-full px-2.5 py-1 text-slate-500 ring-1 ring-slate-200 dark:ring-slate-700">ⓘ 평소 가격?</summary>
          <div className="absolute right-0 z-20 mt-2 w-72 card p-3 text-slate-600 dark:text-slate-300 leading-relaxed">
            같은 상품을 <b>다나와·에누리</b>(전체 쇼핑몰 최저가)와 <b>옥션</b>(판매가 중앙값)에서 찾아, 매번 관측한 값을 쌓은 <b>중앙값</b>입니다. 시세 확인 {checked}건 — 쌓일수록 정확해져요.
            못 찾은 딜은 게시글·상점에 적힌 할인율로 판단합니다(정가 부풀리기가 섞일 수 있음). 기준 {minPct}%는 <Link to="/settings" className="text-sky-600 underline">설정</Link>에서 바꿀 수 있어요.
          </div>
        </details>
      </header>

      <div className="flex gap-1 rounded-xl bg-slate-100 p-1 dark:bg-slate-800/70">
        {tab(mode === "cheap", `평소보다 ${minPct}%↓`, cheapCount, () => setMode("cheap"))}
        {tab(mode === "all", "전체", deals.length, () => setMode("all"))}
        {keywords.length > 0 && tab(mode === "kw", "관심", kwCount, () => setMode("kw"))}
      </div>

      <div className="flex gap-2">
        <div className="relative flex-1 min-w-0">
          <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400">⌕</span>
          <input className="input !pl-9" placeholder="상품명 검색 (예: 마우스, 헤드폰)" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <select className="shrink-0 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-2.5 text-sm" value={sort} onChange={(e) => setSort(e.target.value as Sort)} aria-label="정렬">
          <option value="pct">많이 싼 순</option><option value="recent">최신순</option>
        </select>
      </div>

      {sites.length > 1 && (
        <div className="flex gap-1.5 overflow-x-auto pb-1 -mx-4 px-4 md:mx-0 md:px-0 [scrollbar-width:none]">
          {sites.map((s) => (
            <button key={s} onClick={() => setSite(site === s ? "" : s)}
              className={`shrink-0 rounded-full px-3 py-1 text-xs transition ${site === s ? "bg-slate-900 text-white dark:bg-white dark:text-slate-900" : "bg-white text-slate-600 ring-1 ring-slate-200 dark:bg-slate-900 dark:text-slate-300 dark:ring-slate-800"}`}>{s}</button>
          ))}
          {!keywords.length && <Link to="/settings" className="shrink-0 rounded-full px-3 py-1 text-xs text-sky-700 ring-1 ring-sky-200 dark:text-sky-300 dark:ring-sky-900">+ 관심 키워드</Link>}
        </div>
      )}

      {!deals.length && <Empty>아직 수집된 딜이 없어요. 워커가 매시간 핫딜 커뮤니티를 읽어 옵니다.</Empty>}
      {deals.length > 0 && !list.length && (
        <Empty>{mode === "cheap" ? <>아직 평소보다 {minPct}% 이상 싼 딜이 없어요. 매시간 새 딜의 시세를 확인합니다.<button className="mt-2 block mx-auto text-sky-600 font-semibold" onClick={() => setMode("all")}>전체 딜 보기 →</button></> : "조건에 맞는 딜이 없어요."}</Empty>
      )}

      <ul className="grid grid-cols-1 gap-2.5 lg:grid-cols-2">
        {list.map((d) => <DealCard key={d.url} d={d} minPct={minPct} kw={kwOf(d)} busy={busy === d.url} onTrack={() => track(d)} />)}
      </ul>
    </div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <div className="card p-8 text-center text-sm text-slate-500">{children}</div>;
}

/** 딜 카드: 왼쪽 큰 할인율 · 제목 · 딜가/평소가 · 출처 · 동작. 좁은 화면에서도 가로로 넘치지 않게 min-w-0·줄바꿈 처리 */
export function DealCard({ d, minPct, kw, busy, onTrack }: { d: GDeal; minPct: number; kw?: string | null; busy?: boolean; onTrack?: () => void }) {
  const [imgOk, setImgOk] = useState(!!d.image_url);
  const eff = effectivePct(d);
  const vsUsual = d.below_pct != null && d.ref_price != null;
  const good = eff != null && eff >= minPct;
  const pctCls = eff == null ? "bg-slate-100 text-slate-400 dark:bg-slate-800" : good
    ? (vsUsual ? "bg-emerald-500 text-white" : "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/60 dark:text-emerald-200")
    : eff > 0 ? "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200" : "bg-rose-50 text-rose-600 dark:bg-rose-950/60 dark:text-rose-300";
  const refPrice = vsUsual ? d.ref_price ?? null : d.list_price ?? null;
  return (
    <li className={`card p-3 flex gap-3 min-w-0 ${kw ? "ring-2 ring-amber-300/80 dark:ring-amber-700/70" : ""}`}>
      <div className="flex w-16 shrink-0 flex-col items-center gap-1.5">
        <div className={`flex h-14 w-16 flex-col items-center justify-center rounded-xl ${pctCls}`}>
          {eff == null ? <span className="text-[11px] font-medium">가격만</span> : eff > 0 ? (
            <><span className="text-lg font-extrabold leading-none tabular-nums">{Math.round(eff)}%</span><span className="mt-0.5 text-[10px] opacity-90">{vsUsual ? "평소보다↓" : "표시 할인"}</span></>
          ) : <span className="text-[11px] font-semibold">{eff < 0 ? "평소보다↑" : "평소 수준"}</span>}
        </div>
        {imgOk && d.image_url && <img src={d.image_url} alt="" referrerPolicy="no-referrer" loading="lazy" onError={() => setImgOk(false)} className="h-16 w-16 rounded-lg object-cover bg-slate-100" />}
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5 text-[11px] text-slate-500 min-w-0">
          <span className="shrink-0 rounded bg-slate-100 px-1.5 py-0.5 font-semibold text-slate-700 dark:bg-slate-800 dark:text-slate-200">{siteName(d)}</span>
          <span className="truncate">{d.sources.map((s) => SOURCE_LABEL[s] ?? s).join("·")}{d.sources.length > 1 ? ` ${d.sources.length}곳` : ""} · {timeAgo(d.posted_at)}</span>
          {kw && <span className="shrink-0 rounded bg-amber-100 px-1.5 py-0.5 text-amber-800 dark:bg-amber-900/50 dark:text-amber-200">#{kw}</span>}
        </div>
        <a href={d.url} target="_blank" rel="noreferrer" className="mt-1 block font-semibold leading-snug hover:text-sky-600 line-clamp-2 [overflow-wrap:anywhere]">{d.title}</a>
        <div className="mt-1.5 flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
          <span className="text-base font-bold tabular-nums">{d.price != null ? fmtPrice(d.price, d.currency) : "가격 미상"}</span>
          {refPrice != null && d.price != null && refPrice > d.price && (
            <span className="text-xs text-slate-400 tabular-nums" title={vsUsual ? `비교: ${d.ref_name ?? ""}` : "상점 표시 정가"}>
              {vsUsual ? "평소" : "정가"} <s>{fmtPrice(refPrice, d.currency)}</s>
            </span>
          )}
          {vsUsual && d.ref_price != null && d.price != null && d.ref_price <= d.price && <span className="text-xs text-slate-400 tabular-nums">평소 {fmtPrice(d.ref_price, d.currency)}</span>}
          {d.shipping && <span className="text-[11px] text-slate-500">· 배송 {d.shipping}</span>}
        </div>
        <div className="mt-2 flex gap-1.5">
          <a href={d.shop_url ?? d.url} target="_blank" rel="noreferrer" className="rounded-lg bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-200">{d.shop_url ? "상품 보기 ↗" : "글 보기 ↗"}</a>
          {vsUsual && d.ref_url && <a href={d.ref_url} target="_blank" rel="noreferrer" title={d.ref_name ?? ""} className="rounded-lg px-2.5 py-1 text-xs text-slate-500 hover:text-sky-600">시세 근거</a>}
          {onTrack && <button onClick={onTrack} disabled={busy} className="ml-auto rounded-lg bg-sky-600 px-2.5 py-1 text-xs font-semibold text-white hover:bg-sky-500 disabled:opacity-50"
            title={d.shop_url ? "이 상품을 추적 목록에 넣습니다" : "게시글에서 상품 주소를 붙여넣으면 추적합니다"}>{busy ? "…" : "＋ 추적"}</button>}
        </div>
      </div>
    </li>
  );
}
