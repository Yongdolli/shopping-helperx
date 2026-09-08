import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../lib/api";
import { getRates } from "../lib/fx";
import ProductCard from "../components/ProductCard";
import type { ProductOverview, ShareLink } from "../types";

/** 공유 링크 열람 (/s/:token) — 로그인 없이 읽기 전용. 소유자가 설정에서 만든 태그 단위 목록. */
export default function SharedView() {
  const { token = "" } = useParams();
  const [state, setState] = useState<"loading" | "missing" | "ok">("loading");
  const [share, setShare] = useState<ShareLink | null>(null);
  const [products, setProducts] = useState<ProductOverview[]>([]);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const fx = await getRates();
        const r = await api.sharedView(token, fx.rates);
        if (!alive) return;
        if (!r) { setState("missing"); return; }
        setShare(r.share); setProducts(r.products); setState("ok");
      } catch { if (alive) setState("missing"); }
    })();
    return () => { alive = false; };
  }, [token]);

  const order = { buy: 0, wait: 1, neutral: 2, avoid: 3 } as const;
  const list = [...products].sort((a, b) => order[a.decision.verdict] - order[b.decision.verdict] || (b.pct_vs_baseline ?? -999) - (a.pct_vs_baseline ?? -999));
  const buy = products.filter((p) => p.decision.verdict === "buy").length;

  return (
    <div className="min-h-full">
      <header className="sticky top-0 z-10 flex items-center gap-2 border-b border-slate-200 dark:border-slate-800 bg-slate-50/90 dark:bg-slate-950/90 backdrop-blur px-4 py-3">
        <img src="/icon.svg" className="h-7 w-7" alt="" />
        <span className="font-bold">Shopping Helper</span>
        <span className="ml-auto text-xs text-slate-500">공유 보기 · 읽기 전용</span>
      </header>
      <div className="mx-auto max-w-5xl px-4 py-4 md:px-8 md:py-8 space-y-4">
        {state === "loading" && <div className="card p-8 text-center text-sm text-slate-500">불러오는 중…</div>}
        {state === "missing" && (
          <div className="card p-8 text-center text-sm text-slate-500">
            공유 링크가 없거나 만료되었습니다.
            {api.mode === "demo" && <div className="mt-2 text-xs">데모 모드의 공유 링크는 만든 브라우저에서만 열립니다.</div>}
            <div className="mt-3"><Link to="/" className="text-sky-600 font-semibold">내 목록으로</Link></div>
          </div>
        )}
        {state === "ok" && share && (
          <>
            <div>
              <h1 className="text-xl font-bold">🏷 {share.name}{share.tag ? <span className="text-slate-500 font-normal text-base"> · #{share.tag}</span> : null}</h1>
              <p className="text-sm text-slate-500">{products.length}개 추적 중 · 지금 사도 되는 것 {buy}개 · 가격은 최근 수집 기준, 해외 상품은 한국 도착 최종가(추정) 병기</p>
            </div>
            {!list.length && <div className="card p-8 text-center text-sm text-slate-500">이 목록에 아직 상품이 없습니다.</div>}
            <div className="grid gap-3 md:grid-cols-2">
              {list.map((p) => (
                <div key={p.id} className="space-y-1">
                  <ProductCard p={p} threshold={10} to={null} />
                  <a href={p.url} target="_blank" rel="noreferrer" className="block text-right text-xs text-sky-600">상품 페이지 열기 ↗</a>
                </div>
              ))}
            </div>
            <div className="text-[11px] text-slate-400">"지금 사도 됨 / 기다려볼 만함" 은 최근 90일 중앙값·세일 일정·정품 리스크를 합친 참고 판단입니다. 정품 리스크는 확정이 아니라 의심 신호의 합입니다.</div>
          </>
        )}
      </div>
    </div>
  );
}
