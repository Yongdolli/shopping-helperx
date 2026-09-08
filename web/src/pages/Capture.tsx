/** 북마클릿이 여는 화면: 쿼리로 받은 가격을 기록하고 결과를 보여준다. */
import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../lib/api";
import { useStore } from "../store";
import { COUNTRY_FLAG, SITE_LABEL, detectSite, fmtPrice } from "../lib/format";

export default function Capture() {
  const [sp] = useSearchParams();
  const refresh = useStore((s) => s.refresh);
  const url = sp.get("url") ?? "";
  const priceParam = Number(sp.get("price"));
  const [price, setPrice] = useState(Number.isFinite(priceParam) && priceParam > 0 ? priceParam : 0);
  const [title, setTitle] = useState(sp.get("title") ?? "");
  const [state, setState] = useState<"idle" | "saving" | "done" | "error">("idle");
  const [result, setResult] = useState<{ id: string; title: string; currency: string; count: number } | null>(null);
  const [err, setErr] = useState("");
  const ran = useRef(false);
  const det = url ? detectSite(url) : null;
  const currency = sp.get("currency") || det?.currency || "KRW";
  const listPrice = Number(sp.get("list_price")) || null;

  const save = async () => {
    if (!url || !price) return;
    setState("saving");
    try {
      const r = await api.capture({ url, price, currency, title: title || undefined, list_price: listPrice });
      setResult(r); setState("done"); await refresh();
    } catch (e) { setErr((e as Error).message); setState("error"); }
  };

  // 가격·URL 이 모두 있으면 자동 저장 (북마클릿을 눌렀다는 것 자체가 의도)
  useEffect(() => { if (!ran.current && url && price) { ran.current = true; void save(); } }, []); // eslint-disable-line react-hooks/exhaustive-deps

  if (!url) return <div className="text-sm text-slate-500">잘못된 접근입니다. 설정 화면의 북마클릿을 사용하세요.</div>;

  return (
    <div className="max-w-xl space-y-4">
      <h1 className="text-xl font-bold">가격 기록</h1>
      <div className="card p-4 md:p-6 space-y-3">
        <div className="text-xs text-slate-500">{det && <>{COUNTRY_FLAG[det.country]} {SITE_LABEL[det.site] ?? det.site} · </>}<span className="break-all">{url}</span></div>
        {state === "done" && result ? (
          <>
            <div className="text-emerald-600 font-semibold">기록됨 ✓</div>
            <div className="font-semibold">{result.title}</div>
            <div className="text-2xl font-bold tabular-nums">{fmtPrice(price, result.currency)}</div>
            <div className="text-xs text-slate-500">누적 {result.count}회 기록 · 3회 이상이면 기준선이 생기고 급락 판정이 시작됩니다.</div>
            <div className="flex gap-2"><Link to={`/p/${result.id}`} className="btn-primary">상품 보기</Link><Link to="/" className="btn-ghost">홈</Link></div>
          </>
        ) : (
          <>
            <label className="block text-sm font-medium">상품명</label>
            <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} />
            <label className="block text-sm font-medium">가격 ({currency})</label>
            <input className="input" type="number" inputMode="decimal" value={price || ""} onChange={(e) => setPrice(Number(e.target.value))} />
            {listPrice && <div className="text-xs text-slate-500">표시 정가 {fmtPrice(listPrice, currency)}</div>}
            {state === "error" && <div className="text-sm text-rose-600">{err}</div>}
            <button className="btn-primary w-full" disabled={!price || state === "saving"} onClick={save}>{state === "saving" ? "저장 중…" : "기록"}</button>
          </>
        )}
      </div>
    </div>
  );
}
