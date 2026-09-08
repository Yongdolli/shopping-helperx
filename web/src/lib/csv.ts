/** CSV 내보내기/가져오기. 열: url,variant,title,site,currency,category,captured_at,price,list_price,seller,in_stock */
import type { Product, Snapshot } from "../types";

export const CSV_HEADER = ["url", "variant", "title", "site", "currency", "category", "captured_at", "price", "list_price", "seller", "in_stock"];

const esc = (v: unknown) => { const s = v == null ? "" : String(v); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };

export function toCsv(products: Product[], snapsById: Record<string, Snapshot[]>): string {
  const rows = [CSV_HEADER.join(",")];
  for (const p of products) {
    const snaps = snapsById[p.id] ?? [];
    if (!snaps.length) rows.push([p.url, p.variant ?? "", p.title, p.site, p.currency, p.category ?? "", "", "", "", "", ""].map(esc).join(","));
    for (const s of snaps) rows.push([p.url, p.variant ?? "", p.title, p.site, p.currency, p.category ?? "", s.captured_at, s.price, s.list_price ?? "", s.seller ?? "", s.in_stock ? 1 : 0].map(esc).join(","));
  }
  return "﻿" + rows.join("\n");
}

export interface CsvRow { url: string; variant: string | null; title: string; currency: string; category: string | null; captured_at: string | null; price: number | null; list_price: number | null; seller: string | null; in_stock: boolean }

export function parseCsv(text: string): CsvRow[] {
  const lines: string[][] = [];
  let cur = "", row: string[] = [], q = false;
  const src = text.replace(/^﻿/, "");
  for (let i = 0; i < src.length; i++) {
    const c = src[i];
    if (q) { if (c === '"') { if (src[i + 1] === '"') { cur += '"'; i++; } else q = false; } else cur += c; }
    else if (c === '"') q = true;
    else if (c === ",") { row.push(cur); cur = ""; }
    else if (c === "\n" || c === "\r") { if (c === "\r" && src[i + 1] === "\n") i++; row.push(cur); lines.push(row); row = []; cur = ""; }
    else cur += c;
  }
  if (cur.length || row.length) { row.push(cur); lines.push(row); }
  const [head, ...body] = lines.filter((l) => l.some((x) => x.trim()));
  const idx = (k: string) => head.indexOf(k);
  return body.map((r) => ({
    url: r[idx("url")] ?? "", variant: r[idx("variant")] || null, title: r[idx("title")] ?? "", currency: r[idx("currency")] || "KRW",
    category: r[idx("category")] || null, captured_at: r[idx("captured_at")] || null,
    price: r[idx("price")] ? Number(r[idx("price")]) : null, list_price: r[idx("list_price")] ? Number(r[idx("list_price")]) : null,
    seller: r[idx("seller")] || null, in_stock: (r[idx("in_stock")] ?? "1") !== "0",
  })).filter((r) => /^https?:\/\//.test(r.url));
}
