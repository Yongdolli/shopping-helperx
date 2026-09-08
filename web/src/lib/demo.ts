/** Supabase 없이 화면을 볼 수 있게 하는 데모 데이터. worker `python -m worker demo` 와 같은 상품. */
import type { Alert, Product, Snapshot } from "../types";

function rng(seed: number) {
  return () => { seed = (seed * 1664525 + 1013904223) % 4294967296; return seed / 4294967296; };
}

// [title, site, country, currency, base, url, variant, list_price]
const ITEMS: Array<[string, string, Product["country"], string, number, string, string | null, number | null]> = [
  ["소니 WH-1000XM6 노이즈캔슬링 헤드폰", "coupang", "KR", "KRW", 449000, "https://www.coupang.com/vp/products/demo1?vendorItemId=1001", "vendorItemId=1001", null],
  ["소니 WH-1000XM6 노이즈캔슬링 헤드폰", "coupang", "KR", "KRW", 469000, "https://www.coupang.com/vp/products/demo1?vendorItemId=1002", "vendorItemId=1002", null],
  ["소니 WH-1000XM6 S급 미러급 헤드폰 해외직구", "11st", "KR", "KRW", 89000, "https://www.11st.co.kr/products/demo8", null, null],
  ["LG 올레드 evo C5 65인치 OLED65C5", "11st", "KR", "KRW", 2890000, "https://www.11st.co.kr/products/demo2", null, null],
  ["Anker 737 Power Bank 24000mAh 140W", "aliexpress", "CN", "USD", 89.99, "https://ko.aliexpress.com/item/demo3.html", null, null],
  ["Kindle Paperwhite 16GB (2024)", "amazon", "US", "USD", 159.99, "https://www.amazon.com/dp/demo4", null, null],
  ['Apple iPad Air 11" M3 128GB', "bestbuy", "US", "USD", 599, "https://www.bestbuy.com/site/demo5.p?skuId=demo5", "skuId=demo5", 799],
  ["Logitech MX Master 4 Wireless Mouse", "ebay", "US", "USD", 119.99, "https://www.ebay.com/itm/demo6", null, null],
];

export function seedDemo(): { products: Product[]; snapshots: Record<string, Snapshot[]>; alerts: Alert[] } {
  const rand = rng(42);
  const now = Date.now();
  const products: Product[] = [];
  const snapshots: Record<string, Snapshot[]> = {};
  const alerts: Alert[] = [];

  ITEMS.forEach(([title, site, country, currency, base, url, variant, listPrice], idx) => {
    const id = `demo-${idx + 1}`;
    products.push({ id, title, url, site, country, currency, variant, active: true, created_at: new Date(now - 90 * 86400_000).toISOString(), model_no: idx <= 2 ? "WH-1000XM6" : idx === 3 ? "OLED65C5" : null, fail_count: 0, verified: false, tags: idx <= 2 ? ["헤드폰"] : idx === 3 ? ["TV", "거실"] : idx >= 5 ? ["선물"] : [], target_price: idx === 0 ? 400000 : null });
    const arr: Snapshot[] = [];
    let price = base;
    for (let d = 90; d >= 1; d--) {
      price = Math.max(base * 0.7, Math.min(base * 1.15, price * (1 + (rand() - 0.5) * 0.06)));
      if (d >= 59 && d <= 61) price = base * 0.86;
      if (listPrice) price = base * (1 + (rand() - 0.5) * 0.02);   // 가짜 할인: 가격은 늘 그대로
      const p = currency === "KRW" ? Math.round(price / 100) * 100 : +price.toFixed(2);
      arr.push({ price: p, currency, seller: idx <= 1 ? "쿠팡 로켓" : idx === 2 ? "해외셀러" : "demo", in_stock: rand() > 0.02, captured_at: new Date(now - d * 86400_000).toISOString(), list_price: listPrice });
    }
    if (idx === ITEMS.length - 1) {                 // 지금 급락
      const p = +(base * 0.82).toFixed(2);
      arr.push({ price: p, currency, seller: "demo", in_stock: true, captured_at: new Date(now - 3600_000).toISOString() });
      alerts.push({ id: "a1", product_id: id, kind: "drop", price: p, baseline: base, pct: 18, read: false, created_at: new Date(now - 3600_000).toISOString() });
    }
    if (idx === 3) {                                // 역대 최저 갱신
      const low = Math.min(...arr.map((s) => s.price));
      const p = Math.round((low * 0.985) / 100) * 100;
      arr.push({ price: p, currency, seller: "demo", in_stock: true, captured_at: new Date(now - 7200_000).toISOString() });
      alerts.push({ id: "a2", product_id: id, kind: "low", price: p, baseline: null, pct: null, read: false, created_at: new Date(now - 7200_000).toISOString() });
    }
    if (idx === 1) {                                // 판매자 변경 + 급락 (다른 셀러가 싸게 올림)
      const p = Math.round((base * 0.86) / 100) * 100;
      arr.push({ price: p, currency, seller: "제3자 판매자", in_stock: true, captured_at: new Date(now - 1800_000).toISOString() });
      alerts.push({ id: "a3", product_id: id, kind: "drop", price: p, baseline: base, pct: 14, note: "판매자 변경: 쿠팡 로켓 → 제3자 판매자", read: false, created_at: new Date(now - 1800_000).toISOString() });
    }
    if (listPrice) {                                // 가짜 할인 의심
      alerts.push({ id: "a4", product_id: id, kind: "fake", price: base, baseline: base, pct: 0, note: "표시 할인 25% 지만 평소 가격과 차이 0.0%", read: true, created_at: new Date(now - 86400_000).toISOString() });
    }
    snapshots[id] = arr;
  });
  return { products, snapshots, alerts };
}
