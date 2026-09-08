/** 크로스보더 실구매가 추정 — 워커 landed.py 와 규칙 동일. 한국 소비자 기준. */
import type { Rates } from "./fx";

const US_SITES = new Set(["amazon", "ebay", "walmart", "bestbuy", "target", "etsy"]);
const CN_SITES = new Set(["aliexpress", "temu", "shein", "taobao", "tmall", "jd", "1688"]);
const DUTY_FREE_USD = { US: 200, OTHER: 150 };
// 카테고리: [관세율, 미국발 배송비 USD, 중국발 배송비 USD]
export const CATEGORIES: Record<string, [number, number, number]> = {
  전자: [0, 18, 0], 의류: [0.13, 15, 2], 신발: [0.13, 18, 3], 화장품: [0.065, 12, 2],
  식품: [0.30, 25, 5], 장난감: [0.08, 15, 2], 가방: [0.08, 15, 3], 기타: [0.08, 15, 3],
};
const VAT = 0.10;

export interface Landed { totalKrw: number; lines: Array<[string, number]>; dutyFree: boolean; note: string; origin: "KR" | "US" | "CN" }

export const originOf = (site: string): "KR" | "US" | "CN" => (US_SITES.has(site) ? "US" : CN_SITES.has(site) ? "CN" : "KR");

export function landedPrice(price: number, currency: string, site: string, rates: Rates, category = "전자"): Landed {
  const origin = originOf(site);
  if (origin === "KR") return { totalKrw: price, lines: [["상품가", price]], dutyFree: true, note: "국내", origin };
  const rate = rates[currency.toUpperCase()] ?? 1;
  const usdRate = rates.USD ?? 1380;
  const goodsKrw = price * rate;
  const goodsUsd = goodsKrw / usdRate;
  const [dutyRate, shipUs, shipCn] = CATEGORIES[category] ?? CATEGORIES.기타;
  const shipKrw = (origin === "US" ? shipUs : shipCn) * usdRate;
  const limit = origin === "US" ? DUTY_FREE_USD.US : DUTY_FREE_USD.OTHER;
  const lines: Array<[string, number]> = [["상품가", Math.round(goodsKrw)], ["배송비(추정)", Math.round(shipKrw)]];
  if (goodsUsd <= limit) {
    return { totalKrw: Math.round(goodsKrw + shipKrw), lines, dutyFree: true, note: `면세 (물품가 $${goodsUsd.toFixed(0)} ≤ $${limit})`, origin };
  }
  const taxable = goodsKrw + shipKrw;
  const duty = taxable * dutyRate;
  const vat = (taxable + duty) * VAT;
  lines.push([`관세 ${(dutyRate * 100).toFixed(1)}%`, Math.round(duty)], ["부가세 10%", Math.round(vat)]);
  return { totalKrw: Math.round(taxable + duty + vat), lines, dutyFree: false, note: `면세 한도 초과 (물품가 $${goodsUsd.toFixed(0)} > $${limit})`, origin };
}
