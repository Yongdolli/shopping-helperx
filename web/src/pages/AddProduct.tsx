import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useStore } from "../store";
import { COUNTRY_FLAG, SITE_LABEL, detectSite, parseVariant } from "../lib/format";
import { toast } from "../components/Toast";

const EXAMPLES = [
  "https://smartstore.naver.com/…/products/…", "https://www.coupang.com/vp/products/…?vendorItemId=…", "https://www.11st.co.kr/products/…", "https://ko.aliexpress.com/item/….html",
  "https://www.amazon.com/dp/…", "https://www.ebay.com/itm/…", "https://www.bestbuy.com/site/….p?skuId=…",
];

export default function AddProduct() {
  const nav = useNavigate();
  const [sp] = useSearchParams();
  const addProduct = useStore((s) => s.addProduct);
  const [url, setUrl] = useState(sp.get("url") ?? "");
  const [title, setTitle] = useState(sp.get("title") ?? "");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const valid = /^https?:\/\//i.test(url.trim());
  const det = valid ? detectSite(url.trim()) : null;
  const variant = det ? parseVariant(url.trim(), det.site) : null;
  const needsTitle = det?.site === "coupang";
  const canSubmit = valid && !busy && (!needsTitle || title.trim().length > 0);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    setBusy(true); setErr(null);
    try { await addProduct(url.trim(), title.trim() || undefined); toast("추적을 시작했습니다"); nav("/"); }
    catch (ex) { setErr((ex as Error).message); }
    finally { setBusy(false); }
  };

  return (
    <div className="max-w-xl space-y-4">
      <h1 className="text-xl font-bold">상품 추가</h1>
      <p className="text-sm text-slate-500">쇼핑몰 상품 페이지 주소를 붙여넣으세요. 워커가 주기적으로 가격을 수집하고, 평소 가격(90일 중앙값)보다 10% 이상 싸지면 알려줍니다.</p>

      <form onSubmit={submit} className="card p-4 md:p-6 space-y-3">
        <label className="block text-sm font-medium">상품 URL</label>
        <input className="input" inputMode="url" placeholder="https://…" value={url} onChange={(e) => setUrl(e.target.value)} autoFocus />
        {det && (
          <div className="text-sm text-slate-600 dark:text-slate-300 space-y-1">
            <div>감지: {COUNTRY_FLAG[det.country]} <b>{SITE_LABEL[det.site] ?? det.site}</b> · 통화 {det.currency}{variant && <> · 옵션 <code className="text-xs">{variant}</code></>}</div>
            {det.site === "generic" && <div className="text-xs text-amber-600">지원 목록에 없는 사이트입니다. 페이지에 JSON-LD 가격 정보가 있으면 수집됩니다.</div>}
            {det.site === "coupang" && <div className="text-xs text-amber-600">쿠팡은 상품명으로 검색해 매칭하므로 <b>정확한 상품명이 필요</b>합니다. 옵션(색상·용량)이 다르면 URL의 vendorItemId 로 따로 추적됩니다.</div>}
            {det.site === "naver" && <div className="text-xs text-amber-600">네이버는 공식 API가 없어 스마트스토어 페이지를 12시간마다 저빈도로 읽습니다. 차단되면 설정의 <b>북마클릿</b>으로 직접 기록하세요.</div>}
            {["amazon", "temu"].includes(det.site) && <div className="text-xs text-amber-600">{SITE_LABEL[det.site]}은(는) 봇 차단이 강해 자동 수집이 안 될 수 있습니다. 설정의 <b>북마클릿</b>으로 직접 기록하면 됩니다.</div>}
          </div>
        )}
        <label className="block text-sm font-medium">상품명 {needsTitle ? <span className="text-rose-500">(필수)</span> : "(선택 — 비우면 수집 시 자동 채움)"}</label>
        <input className="input" placeholder="예: 소니 WH-1000XM6" value={title} onChange={(e) => setTitle(e.target.value)} />
        {err && <div className="text-sm text-rose-600">{err}</div>}
        <button className="btn-primary w-full" disabled={!canSubmit}>{busy ? "추가 중…" : "추적 시작"}</button>
      </form>

      <div className="text-xs text-slate-400 space-y-1">
        <div>지원 주소 형태</div>
        {EXAMPLES.map((e) => <div key={e} className="font-mono">{e}</div>)}
      </div>
    </div>
  );
}
