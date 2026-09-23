import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useStore } from "../store";
import { toast } from "../components/Toast";
import { SITE_LABEL, fmtPrice, timeAgo } from "../lib/format";
import { effectivePct, type Deal } from "../types";

type Sort = "recent" | "pct";
type Mode = "cheap" | "all" | "kw";
const SOURCE_LABEL: Record<string, string> = { ppomppu: "뽐뿌", ruliweb: "루리웹", clien: "클리앙", quasarzone: "퀘이사존", fmkorea: "에펨" };

/** 딜 탭 — 등록 없이 핫딜 커뮤니티에 올라온 모든 사이트의 할인을 모아 본다. 워커가 매시간 수집. */
export default function Deals() {
  const { deals, settings, addProduct } = useStore();
  const nav = useNavigate();
  const [busy, setBusy] = useState<string | null>(null);
  const track = async (d: Deal) => {
    if (!d.shop_url) { nav(`/add?title=${encodeURIComponent(d.title)}`); return; }
    setBusy(d.url);
    try { await addProduct(d.shop_url, d.title); toast("추적을 시작했습니다 — 3회 이상 가격이 쌓이면 판정이 붙습니다"); nav("/"); }
    catch (e) { toast("실패: " + (e as Error).message); } finally { setBusy(null); }
  };
  const minPct = settings?.deal_min_pct ?? 10;
  const keywords = (settings?.deal_keywords ?? []).map((k) => k.toLowerCase()).filter(Boolean);
  const [q, setQ] = useState("");
  const [site, setSite] = useState("");
  const [mode, setMode] = useState<Mode>("cheap");       // 기본: 평소보다 싼 딜만
  const [sort, setSort] = useState<Sort>("pct");

  const kwOf = (d: Deal) => keywords.find((k) => d.title.toLowerCase().includes(k)) ?? null;
  const sites = useMemo(() => Object.entries(deals.reduce<Record<string, number>>((a, d) => { a[d.site] = (a[d.site] ?? 0) + 1; return a; }, {}))
    .sort((a, b) => b[1] - a[1]).slice(0, 12).map(([s]) => s), [deals]);

  const list = useMemo(() => {
    let l = deals;
    if (mode === "cheap") l = l.filter((d) => (effectivePct(d) ?? -1) >= minPct);
    if (mode === "kw") l = l.filter((d) => kwOf(d));
    if (site) l = l.filter((d) => d.site === site);
    if (q.trim()) l = l.filter((d) => d.title.toLowerCase().includes(q.toLowerCase()) || (d.site_label ?? "").toLowerCase().includes(q.toLowerCase()));
    return [...l].sort(sort === "pct" ? (a, b) => (effectivePct(b) ?? -999) - (effectivePct(a) ?? -999) || b.posted_at.localeCompare(a.posted_at) : (a, b) => b.posted_at.localeCompare(a.posted_at));
  }, [deals, mode, site, q, sort, minPct, keywords]);   // eslint-disable-line react-hooks/exhaustive-deps

  const pctCount = deals.filter((d) => (effectivePct(d) ?? -1) >= minPct).length;
  const checked = deals.filter((d) => d.below_pct != null).length;
  const kwCount = keywords.length ? deals.filter((d) => kwOf(d)).length : 0;
  const chip = (on: boolean, label: string, onClick: () => void, key?: string) => (
    <button key={key ?? label} onClick={onClick} className={`rounded-full px-3 py-1.5 text-sm whitespace-nowrap transition ${on ? "bg-slate-900 text-white dark:bg-white dark:text-slate-900" : "bg-white dark:bg-slate-900 ring-1 ring-slate-200 dark:ring-slate-800 text-slate-600 dark:text-slate-300"}`}>{label}</button>
  );

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-bold">🔥 딜</h1>
        <p className="text-sm text-slate-500">핫딜 커뮤니티에서 모은 최근 7일 딜 {deals.length}건 중 <b className="text-emerald-600">평소보다 {minPct}%↑ 싼 것 {pctCount}건</b>{keywords.length ? ` · 관심 키워드 ${kwCount}건` : ""}</p>
        <p className="text-[11px] text-slate-400">평소 가격 = 같은 상품의 다나와 전체 쇼핑몰 최저가를 매번 관측해 쌓은 중앙값 (시세 확인 {checked}건, 쌓일수록 정확해짐). 기준은 설정에서 바꿀 수 있어요.</p>
      </div>

      <div className="flex gap-2 overflow-x-auto pb-1 -mx-4 px-4 md:mx-0 md:px-0">
        {chip(mode === "cheap", `💰 평소보다 ${minPct}%↑ 싼 것 ${pctCount}`, () => setMode("cheap"))}
        {chip(mode === "all", `전체 ${deals.length}`, () => setMode("all"))}
        {keywords.length > 0 && chip(mode === "kw", `관심 키워드 ${kwCount}`, () => setMode("kw"))}
        {!keywords.length && <Link to="/settings" className="rounded-full px-3 py-1.5 text-sm whitespace-nowrap bg-white dark:bg-slate-900 ring-1 ring-dashed ring-slate-300 text-slate-500">+ 관심 키워드 (설정)</Link>}
      </div>
      {sites.length > 1 && (
        <div className="flex gap-2 overflow-x-auto pb-1 -mx-4 px-4 md:mx-0 md:px-0 text-xs">
          {sites.map((s) => chip(site === s, SITE_LABEL[s] ?? s, () => setSite(site === s ? "" : s), "s-" + s))}
        </div>
      )}
      <div className="flex gap-2">
        <input className="input flex-1 min-w-0" placeholder="상품명 검색 (예: 마우스, 헤드폰)" value={q} onChange={(e) => setQ(e.target.value)} />
        <select className="shrink-0 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 text-sm" value={sort} onChange={(e) => setSort(e.target.value as Sort)}>
          <option value="pct">많이 싼 순</option><option value="recent">최신순</option>
        </select>
      </div>

      {!deals.length && <div className="card p-8 text-center text-sm text-slate-500">아직 수집된 딜이 없습니다. 워커가 매시간 핫딜 커뮤니티를 읽어 옵니다 (`python -m worker deals`).</div>}
      {deals.length > 0 && !list.length && <div className="card p-8 text-center text-sm text-slate-500">{mode === "cheap" ? <>아직 평소보다 {minPct}% 이상 싼 딜이 없습니다. 워커가 매시간 새 딜의 시세를 확인합니다. <button className="text-sky-600 font-semibold" onClick={() => setMode("all")}>전체 보기</button></> : "조건에 맞는 딜이 없습니다."}</div>}

      <ul className="space-y-2">
        {list.map((d) => {
          const kw = kwOf(d);
          return (
            <li key={d.url} className={`card p-3 md:p-4 ${kw ? "ring-2 ring-amber-300/70" : ""}`}>
              <div className="flex gap-3">
                {d.image_url && <img src={d.image_url} alt="" className="h-14 w-14 shrink-0 rounded-lg object-cover bg-slate-100" loading="lazy" />}
                <div className="min-w-0 flex-1">
                  <div className="text-[11px] text-slate-500 truncate">
                    <span className="font-medium text-slate-700 dark:text-slate-200">{d.site_label || SITE_LABEL[d.site] || d.site}</span>
                    {" · "}{SOURCE_LABEL[d.source] ?? d.source} · {timeAgo(d.posted_at)}{d.category ? ` · ${d.category}` : ""}
                  </div>
                  <a href={d.url} target="_blank" rel="noreferrer" className="block font-semibold leading-snug hover:text-sky-600 line-clamp-2">{d.title}</a>
                  <div className="mt-1 flex items-baseline gap-2 flex-wrap text-sm">
                    <span className="font-bold tabular-nums">{d.price != null ? fmtPrice(d.price, d.currency) : "가격 미상"}</span>
                    {d.shipping && <span className="text-xs text-slate-500">배송 {d.shipping}</span>}
                    {d.below_pct != null && d.ref_price != null ? (
                      <a href={d.ref_url ?? undefined} target="_blank" rel="noreferrer" title={`비교 상품: ${d.ref_name ?? ""}`}
                        className={`rounded-full px-2 py-0.5 text-[11px] ${d.below_pct >= minPct ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/50 dark:text-emerald-200" : d.below_pct > 0 ? "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300" : "bg-rose-50 text-rose-600 dark:bg-rose-900/40 dark:text-rose-200"}`}>
                        평소 {fmtPrice(d.ref_price, d.currency)} {d.below_pct > 0 ? `대비 ▼${d.below_pct}%` : "보다 비쌈"}
                      </a>
                    ) : d.pct != null && <span className={`rounded-full px-2 py-0.5 text-[11px] ${d.pct >= minPct ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/50 dark:text-emerald-200" : "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300"}`}>{d.list_price ? `정가 ${fmtPrice(d.list_price, d.currency)} 대비` : "표시"} ▼{d.pct}%</span>}
                    {kw && <span className="rounded-full bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-200 px-2 py-0.5 text-[11px]">#{kw}</span>}
                  </div>
                </div>
                <div className="shrink-0 flex flex-col gap-1 text-xs">
                  <a href={d.shop_url ?? d.url} target="_blank" rel="noreferrer" className="btn-ghost py-1.5 px-2.5 text-center">{d.shop_url ? "상품 열기" : "글 열기"}</a>
                  <button onClick={() => track(d)} disabled={busy === d.url} className={`py-1.5 px-2.5 rounded-xl ${d.shop_url ? "btn-primary" : "btn-ghost"}`} title={d.shop_url ? "이 상품을 추적 목록에 넣습니다" : "게시글에서 상품 주소를 복사해 붙여넣으면 추적합니다"}>{busy === d.url ? "…" : "추적"}</button>
                </div>
              </div>
            </li>
          );
        })}
      </ul>
      <div className="text-[11px] text-slate-400">"평소 대비"는 다나와에서 같은 상품을 찾아 비교한 값이고, 못 찾은 딜은 게시글·상점 표시 할인율로 판단합니다(정가 부풀리기가 섞일 수 있음). "추적"으로 등록하면 평소 가격 대비 진짜 할인인지 판정이 붙습니다. 워커가 새 딜의 게시글에서 상점 주소를 찾아 두면 원클릭으로 추적됩니다.</div>
    </div>
  );
}
