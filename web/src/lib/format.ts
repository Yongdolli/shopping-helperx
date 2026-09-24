import type { Country } from "../types";

export function fmtPrice(v: number | null | undefined, currency: string): string {
  if (v == null) return "—";
  if (currency === "KRW") return `${Math.round(v).toLocaleString("ko-KR")}원`;
  const sym: Record<string, string> = { USD: "$", CNY: "¥", EUR: "€", JPY: "¥" };
  return `${sym[currency] ?? currency + " "}${v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function fmtPct(v: number | null | undefined): string {
  if (v == null) return "—";
  const s = v >= 0 ? "▼" : "▲";
  return `${s}${Math.abs(v).toFixed(1)}%`;
}

export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "수집 전";
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return "방금";
  if (diff < 3600) return `${Math.floor(diff / 60)}분 전`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}시간 전`;
  return `${Math.floor(diff / 86400)}일 전`;
}

export const COUNTRY_FLAG: Record<Country, string> = { KR: "🇰🇷", CN: "🇨🇳", US: "🇺🇸" };

export const SITE_LABEL: Record<string, string> = {
  coupang: "쿠팡", "11st": "11번가", gmarket: "지마켓", auction: "옥션", ssg: "SSG", lotteon: "롯데온",
  danawa: "다나와", enuri: "에누리", musinsa: "무신사", oliveyoung: "올리브영", kurly: "컬리", naver: "네이버",
  aliexpress: "알리익스프레스", temu: "테무", shein: "쉬인", taobao: "타오바오", tmall: "티몰", jd: "징동", "1688": "1688",
  amazon: "Amazon", ebay: "eBay", walmart: "Walmart", bestbuy: "Best Buy", target: "Target", etsy: "Etsy", generic: "기타",
  toss: "토스", kakao: "카카오", ohouse: "오늘의집", steam: "스팀", apple: "애플", samsung: "삼성", lg: "LG", costco: "코스트코",
  homeplus: "홈플러스", emart: "이마트", wemakeprice: "위메프", tmon: "티몬", unknown: "기타",
};

const SITE_TABLE: Array<[string, string, Country, string]> = [
  ["coupang.com", "coupang", "KR", "KRW"], ["11st.co.kr", "11st", "KR", "KRW"], ["gmarket.co.kr", "gmarket", "KR", "KRW"],
  ["auction.co.kr", "auction", "KR", "KRW"], ["ssg.com", "ssg", "KR", "KRW"], ["lotteon.com", "lotteon", "KR", "KRW"],
  ["danawa.com", "danawa", "KR", "KRW"], ["enuri.com", "enuri", "KR", "KRW"], ["musinsa.com", "musinsa", "KR", "KRW"],
  ["oliveyoung.co.kr", "oliveyoung", "KR", "KRW"], ["kurly.com", "kurly", "KR", "KRW"], ["naver.com", "naver", "KR", "KRW"],
  ["aliexpress.com", "aliexpress", "CN", "USD"], ["aliexpress.us", "aliexpress", "CN", "USD"], ["temu.com", "temu", "CN", "USD"],
  ["shein.com", "shein", "CN", "USD"], ["taobao.com", "taobao", "CN", "CNY"], ["tmall.com", "tmall", "CN", "CNY"],
  ["jd.com", "jd", "CN", "CNY"], ["1688.com", "1688", "CN", "CNY"],
  ["amazon.com", "amazon", "US", "USD"], ["ebay.com", "ebay", "US", "USD"], ["walmart.com", "walmart", "US", "USD"],
  ["bestbuy.com", "bestbuy", "US", "USD"], ["target.com", "target", "US", "USD"], ["etsy.com", "etsy", "US", "USD"],
];

export function detectSite(url: string): { site: string; country: Country; currency: string } {
  let host = "";
  try { host = new URL(url).hostname.toLowerCase(); } catch { return { site: "generic", country: "US", currency: "USD" }; }
  for (const [domain, site, country, currency] of SITE_TABLE) {
    if (host === domain || host.endsWith("." + domain)) return { site, country, currency };
  }
  return { site: "generic", country: "US", currency: "USD" };
}

/** 워커 baseline.py 와 같은 규칙: 최근 windowDays 중앙값, 3개 미만이면 null */
export function median(values: number[]): number | null {
  if (values.length < 3) return null;
  const s = [...values].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

/** 워커 baseline.py 와 동일: 표시 할인 20%↑ 인데 실제(기준선 대비)는 3% 이하 → 가짜 할인 */
export function claimedPct(price: number | null, listPrice: number | null | undefined): number | null {
  if (price == null || !listPrice || listPrice <= price) return null;
  return +(((listPrice - price) / listPrice) * 100).toFixed(1);
}
export function isFakeDiscount(claimed: number | null, real: number | null): boolean {
  return claimed != null && real != null && claimed >= 20 && real <= 3;
}

/** 워커 models.VARIANT_PARAMS 와 동일 */
const VARIANT_PARAMS: Record<string, string[]> = {
  coupang: ["vendorItemId", "itemId"], aliexpress: ["sku_id"], amazon: ["th", "psc"], ebay: ["var"],
  "11st": ["optionNo"], gmarket: ["optionNo"], walmart: ["selected"], bestbuy: ["skuId"],
};
export function parseVariant(url: string, site: string): string | null {
  try {
    const q = new URL(url).searchParams;
    const parts = (VARIANT_PARAMS[site] ?? []).filter((k) => q.get(k)).map((k) => `${k}=${q.get(k)}`);
    return parts.length ? parts.join("&") : null;
  } catch { return null; }
}

/** 워커 models.is_manual_only 와 동일: robots.txt 금지 = 자동 수집 불가(실패 아님) → 북마클릿/확장으로 기록 */
export const isManualOnly = (err: string | null | undefined) => !!err && err.includes("robots.txt");

export const ALERT_LABEL: Record<string, string> = { target: "목표가 도달", drop: "가격 급락", low: "역대 최저가", restock: "재입고", fake: "가짜 할인 의심", paused: "추적 자동 중단" };
