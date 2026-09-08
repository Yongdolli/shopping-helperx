import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useStore } from "../store";
import { toast } from "../components/Toast";
import { SITE_LABEL, fmtPrice, timeAgo } from "../lib/format";
import type { Deal } from "../types";

type Sort = "recent" | "pct";
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
  const minPct = settings?.deal_min_pct ?? 30;
  const keywords = (settings?.deal_keywords ?? []).map((k) => k.toLowerCase()).filter(Boolean);
  const [q, setQ] = useState("");
  const [site, setSite] = useState("");
  const [onlyPct, setOnlyPct] = useState(false);
  const [onlyKw, setOnlyKw] = useState(false);
  const [sort, setSort] = useState<Sort>("recent");

  const kwOf = (d: Deal) => keywords.find((k) => d.title.toLowerCase().includes(k)) ?? null;
  const sites = useMemo(() => Object.entries(deals.reduce<Record<string, number>>((a, d) => { a[d.site] = (a[d.site] ?? 0) + 1; return a; }, {}))
    .sort((a, b) => b[1] - a[1]).slice(0, 12).map(([s]) => s), [deals]);

  const list = useMemo(() => {
    let l = deals;
    if (onlyPct) l = l.filter((d) => d.pct != null && d.pct >= minPct);
    if (onlyKw) l = l.filter((d) => kwOf(d));
    if (site) l = l.filter((d) => d.site === site);
    if (q.trim()) l = l.filter((d) => d.title.toLowerCase().includes(q.toLowerCase()) || (d.site_label ?? "").toLowerCase().includes(q.toLowerCase()));
    return [...l].sort(sort === "pct" ? (a, b) => (b.pct ?? -1) - (a.pct ?? -1) || b.posted_at.localeCompare(a.posted_at) : (a, b) => b.posted_at.localeCompare(a.posted_at));
  }, [deals, onlyPct, onlyKw, site, q, sort, minPct, keywords]);   // eslint-disable-line react-hooks/exhaustive-deps

  const pctCount = deals.filter((d) => d.pct != null && d.pct >= minPct).length;
  const kwCount = keywords.length ? deals.filter((d) => kwOf(d)).length : 0;
  const chip = (on: boolean, label: string, onClick: () => void, key?: string) => (
    <button key={key ?? label} onClick={onClick} className={`rounded-full px-3 py-1.5 text-sm whitespace-nowrap transition ${on ? "bg-slate-900 text-white dark:bg-white dark:text-slate-900" : "bg-white dark:bg-slate-900 ring-1 ring-slate-200 dark:ring-slate-800 text-slate-600 dark:text-slate-300"}`}>{label}</button>
  );

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-bold">🔥 딜</h1>
        <p className="text-sm text-slate-500">핫딜 커뮤니티 5곳에서 매시간 모은 최근 7일 할인 {deals.length}건 · 할인율 {minPct}%↑ 확인 {pctCount}건{keywords.length ? ` · 관심 키워드 ${kwCount}건` : ""}</p>
      </div>

      <div className="flex gap-2 overflow-x-auto pb-1 -mx-4 px-4 md:mx-0 md:px-0">
        {chip(!onlyPct && !onlyKw, "전체", () => { setOnlyPct(false); setOnlyKw(false); })}
        {chip(onlyPct, `할인율 ${minPct}%↑`, () => { setOnlyPct(!onlyPct); setOnlyKw(false); })}
        {keywords.length > 0 && chip(onlyKw, `관심 키워드`, () => { setOnlyKw(!onlyKw); setOnlyPct(false); })}
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
          <option value="recent">최신순</option><option value="pct">할인율순</option>
        </select>
      </div>

      {!deals.length && <div className="card p-8 text-center text-sm text-slate-500">아직 수집된 딜이 없습니다. 워커가 매시간 핫딜 커뮤니티를 읽어 옵니다 (`python -m worker deals`).</div>}
      {deals.length > 0 && !list.length && <div className="card p-8 text-center text-sm text-slate-500">조건에 맞는 딜이 없습니다.</div>}

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
                    {d.pct != null && <span className={`rounded-full px-2 py-0.5 text-[11px] ${d.pct >= minPct ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/50 dark:text-emerald-200" : "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300"}`}>{d.list_price ? `정가 ${fmtPrice(d.list_price, d.currency)} 대비` : "표시"} ▼{d.pct}%</span>}
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
      <div className="text-[11px] text-slate-400">할인율은 게시글에 적힌 값 또는 상점 정가 대비 계산값이라 정가 부풀리기가 섞일 수 있습니다. "추적"으로 등록하면 평소 가격 대비 진짜 할인인지 판정이 붙습니다. 워커가 새 딜의 게시글에서 상점 주소를 찾아 두면 원클릭으로 추적됩니다.</div>
    </div>
  );
}
