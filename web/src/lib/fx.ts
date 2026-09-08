/** 환율 (통화 → KRW). 무료·키 불필요 open.er-api.com, 6시간 캐시, 실패 시 폴백. 워커 fx.py 와 동일 소스. */
export type Rates = Record<string, number>;
export const FALLBACK_KRW: Rates = { USD: 1380, CNY: 190, EUR: 1500, JPY: 9.3, KRW: 1 };
const KEY = "shopping-helper-fx";
const TTL = 6 * 3600_000;

let memo: { at: number; rates: Rates; live: boolean } | null = null;

export async function getRates(): Promise<{ rates: Rates; live: boolean; at: number }> {
  if (memo && Date.now() - memo.at < TTL) return memo;
  try {
    const cached = JSON.parse(localStorage.getItem(KEY) || "null");
    if (cached && Date.now() - cached.at < TTL) { memo = cached; return cached; }
  } catch { /* ignore */ }
  try {
    const r = await fetch("https://open.er-api.com/v6/latest/USD");
    const d = await r.json();
    const krwPerUsd = Number(d.rates.KRW);
    const rates: Rates = { KRW: 1, USD: krwPerUsd };
    for (const [cur, v] of Object.entries(d.rates as Record<string, number>)) if (v) rates[cur] = krwPerUsd / v;
    memo = { at: Date.now(), rates, live: true };
    try { localStorage.setItem(KEY, JSON.stringify(memo)); } catch { /* ignore */ }
    return memo;
  } catch {
    memo = { at: Date.now(), rates: FALLBACK_KRW, live: false };
    return memo;
  }
}

export const toKrw = (amount: number, currency: string, rates: Rates) => amount * (rates[currency.toUpperCase()] ?? FALLBACK_KRW[currency.toUpperCase()] ?? 1);
