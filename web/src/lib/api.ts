/**
 * 데이터 접근은 이 파일만 통한다.
 * VITE_SUPABASE_URL 이 있으면 Supabase, 없으면 브라우저 로컬 데모 저장소.
 */
import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import type { Alert, Product, ProductOverview, PushSubscriptionJson, ShareLink, Snapshot, UserSettings } from "../types";
import { claimedPct, detectSite, isFakeDiscount, median, parseVariant } from "./format";
import { assessRisk, countSellerChanges, guessModelNo } from "./risk";
import { decide } from "./decision";
import { trendPct } from "./trend";
import { landedPrice } from "./landed";
import { buyTiming, upcomingSales } from "./sales";
import type { Rates } from "./fx";
import { seedDemo } from "./demo";

export interface Api {
  readonly mode: "supabase" | "demo";
  listOverview(rates: Rates, threshold: number): Promise<ProductOverview[]>;   // 중단·구매 상품 포함
  getProduct(id: string): Promise<Product | null>;
  history(id: string, days: number): Promise<Snapshot[]>;
  addProduct(url: string, title?: string): Promise<Product>;
  /** 북마클릿/수동 기록: 상품이 없으면 만들고 스냅샷 1건 추가 */
  capture(input: CaptureInput): Promise<{ id: string; title: string; currency: string; count: number }>;
  setActive(id: string, active: boolean): Promise<void>;
  setVerified(id: string, verified: boolean): Promise<void>;
  setCategory(id: string, category: string): Promise<void>;
  setTarget(id: string, target: number | null): Promise<void>;
  setTags(id: string, tags: string[]): Promise<void>;
  markPurchased(id: string, price: number | null): Promise<void>;   // null = 구매 취소
  exportAll(): Promise<{ products: Product[]; snapsById: Record<string, Snapshot[]> }>;
  importRows(rows: import("./csv").CsvRow[]): Promise<number>;
  removeProduct(id: string): Promise<void>;
  listAlerts(): Promise<Alert[]>;
  markRead(id: string): Promise<void>;
  markAllRead(): Promise<void>;
  getSettings(): Promise<UserSettings>;
  saveSettings(s: UserSettings): Promise<void>;
  savePushSubscription(sub: PushSubscriptionJson): Promise<void>;
  removePushSubscription(endpoint: string): Promise<void>;
  listShares(): Promise<ShareLink[]>;
  createShare(tag: string | null, name: string): Promise<ShareLink>;
  deleteShare(token: string): Promise<void>;
  /** 공유 링크 열람 — 로그인 불필요. 없으면 null. 임계값은 기본 10% */
  sharedView(token: string, rates: Rates): Promise<{ share: ShareLink; products: ProductOverview[] } | null>;
  currentUserEmail(): Promise<string | null>;
  signIn(email: string): Promise<void>;
  signOut(): Promise<void>;
}

export interface CaptureInput { url: string; price: number; currency: string; title?: string; list_price?: number | null; seller?: string }
const CAPTURE_SELLER = "직접 기록";

const DEFAULT_SETTINGS: UserSettings = {
  threshold_pct: 10, window_days: 90, notify_push: true, notify_email: false, notify_telegram: false, email: "", telegram_chat_id: "", digest: true, instant_target: true,
};

function dominantSeller(snaps: Snapshot[]): string | null {
  const c: Record<string, number> = {};
  for (const s of snaps) if (s.seller) c[s.seller] = (c[s.seller] ?? 0) + 1;
  const best = Object.entries(c).sort((a, b) => b[1] - a[1])[0];
  return best ? best[0] : null;
}

/** 2차 가공: 리스크(같은 모델 교차 비교) → 최종가·순위 → 추세 → 결정 */
function enrich(list: ProductOverview[], snapsById: Record<string, Snapshot[]>, rates: Rates, threshold: number, windowDays = 90): ProductOverview[] {
  const withRisk = list.map((p) => {
    const others = list.filter((o) => o.id !== p.id && o.active && o.model_no && o.model_no === p.model_no && o.currency === p.currency && o.last_price != null && o.in_stock).map((o) => o.last_price as number);
    const cross = others.length >= 1 ? (others.length >= 3 ? median(others) : others.reduce((a, b) => a + b, 0) / others.length) : null;
    const risk = assessRisk({ title: p.title, site: p.site, price: p.last_price, seller: p.last_seller, baseline: p.baseline, crossBaseline: cross, modelNo: p.model_no, usualSeller: dominantSeller((snapsById[p.id] ?? []).slice(0, -1)), verified: p.verified, sellerChanges: countSellerChanges(snapsById[p.id] ?? [], windowDays) });
    const landed_krw = p.last_price != null ? landedPrice(p.last_price, p.currency, p.site, rates, p.category ?? "전자").totalKrw : null;
    return { ...p, risk, landed_krw };
  });
  return withRisk.map((p) => {
    const group = withRisk.filter((o) => o.active && o.landed_krw != null && o.risk.level !== "high" && ((o.model_no && o.model_no === p.model_no) || o.url.split("?")[0] === p.url.split("?")[0]));
    const sorted = [...group].sort((a, b) => (a.landed_krw as number) - (b.landed_krw as number));
    const idx = sorted.findIndex((o) => o.id === p.id);
    const landed_rank: [number, number] | null = idx >= 0 && sorted.length > 1 ? [idx + 1, sorted.length] : null;
    const trend_pct = trendPct(snapsById[p.id] ?? []);
    const judged = p.in_stock && !p.pending_confirm;                 // 품절·확인 대기면 급락으로 치지 않음 (워커와 동일)
    const pct = judged ? p.pct_vs_baseline : null;
    const drop = pct != null && pct >= threshold;
    const timing = buyTiming(drop, upcomingSales(p.country, p.site, p.category ?? "전자"));
    const decision = decide({ pctVsBaseline: pct, threshold, risk: p.risk.level, fake: p.fake, targetHit: p.target_hit, landedRank: landed_rank, waitLabel: timing.verdict === "wait" ? timing.label : null, trendPct: trend_pct });
    return { ...p, landed_rank, trend_pct, decision };
  });
}

function overview(p: Product, snaps: Snapshot[], windowDays: number): ProductOverview {
  const cutoff = Date.now() - windowDays * 86400_000;
  const inWin = snaps.filter((s) => s.in_stock && !s.suspect && new Date(s.captured_at).getTime() >= cutoff).map((s) => s.price);
  const last = snaps.length ? snaps[snaps.length - 1] : null;
  const baseline = median(inWin);
  const lows = snaps.filter((s) => s.in_stock && !s.suspect).map((s) => s.price);
  const real = baseline && last ? +(((baseline - last.price) / baseline) * 100).toFixed(1) : null;
  const judged = !!last && last.in_stock && !last.suspect;   // 워커 judge(): 품절·확인 대기 스냅샷은 알림 없음
  const claimed = claimedPct(last?.price ?? null, last?.list_price);
  return {
    ...p,
    last_price: last?.price ?? null,
    last_list_price: last?.list_price ?? null,
    last_seller: last?.seller ?? null,
    last_captured_at: last?.captured_at ?? null,
    baseline,
    all_time_low: lows.length ? Math.min(...lows) : null,
    pct_vs_baseline: real,
    claimed_pct: claimed,
    fake: isFakeDiscount(claimed, real),
    in_stock: last?.in_stock ?? true,
    pending_confirm: !!last?.suspect,
    target_hit: p.target_price && last && judged ? last.price <= p.target_price : null,
    model_no: p.model_no ?? guessModelNo(p.title),
    risk: { level: "low", score: 0, reasons: [] },
    trend_pct: null, landed_krw: null, landed_rank: null,
    decision: { verdict: "neutral", headline: "", reasons: [] },
  };
}

// ------------------------------------------------------------------ Demo (localStorage)
interface DemoDb { products: Product[]; snapshots: Record<string, Snapshot[]>; alerts: Alert[]; settings: UserSettings; push?: PushSubscriptionJson[]; shares?: ShareLink[] }
const KEY = "shopping-helper-demo-v4";

class DemoApi implements Api {
  readonly mode = "demo" as const;
  private db: DemoDb;

  constructor() {
    let db: DemoDb | null = null;
    try { db = JSON.parse(localStorage.getItem(KEY) || "null"); } catch { /* ignore */ }
    this.db = db ?? { ...seedDemo(), settings: DEFAULT_SETTINGS };
    this.persist();
  }
  private persist() { try { localStorage.setItem(KEY, JSON.stringify(this.db)); } catch { /* ignore */ } }

  async listOverview(rates: Rates, threshold: number) {
    return enrich(this.db.products.map((p) => overview(p, this.db.snapshots[p.id] ?? [], this.db.settings.window_days)), this.db.snapshots, rates, threshold, this.db.settings.window_days);
  }
  async getProduct(id: string) { return this.db.products.find((p) => p.id === id) ?? null; }
  async history(id: string, days: number) {
    const cutoff = Date.now() - days * 86400_000;
    return (this.db.snapshots[id] ?? []).filter((s) => new Date(s.captured_at).getTime() >= cutoff);
  }
  async addProduct(url: string, title?: string) {
    const { site, country, currency } = detectSite(url);
    const variant = parseVariant(url, site);
    const dup = this.db.products.find((p) => p.url === url && (p.variant ?? null) === variant);
    if (dup) { dup.active = true; this.persist(); return dup; }
    const p: Product = { id: crypto.randomUUID(), title: title || url, url, site, country, currency, variant, active: true, created_at: new Date().toISOString() };
    this.db.products.unshift(p);
    this.db.snapshots[p.id] = [];
    this.persist();
    return p;
  }
  async capture(input: CaptureInput) {
    const p = await this.addProduct(input.url, input.title);
    if (input.title && p.title === p.url) { p.title = input.title; }
    if (p.currency !== input.currency) { p.currency = input.currency; }
    const arr = (this.db.snapshots[p.id] ??= []);
    arr.push({ price: input.price, currency: input.currency, seller: input.seller ?? CAPTURE_SELLER, in_stock: true, captured_at: new Date().toISOString(), list_price: input.list_price ?? null });
    this.persist();
    return { id: p.id, title: p.title, currency: p.currency, count: arr.length };
  }
  async setActive(id: string, active: boolean) { const p = this.db.products.find((x) => x.id === id); if (p) { p.active = active; this.persist(); } }
  async setVerified(id: string, verified: boolean) { const p = this.db.products.find((x) => x.id === id); if (p) { p.verified = verified; this.persist(); } }
  async setCategory(id: string, category: string) { const p = this.db.products.find((x) => x.id === id); if (p) { p.category = category; this.persist(); } }
  async setTarget(id: string, target: number | null) { const p = this.db.products.find((x) => x.id === id); if (p) { p.target_price = target; this.persist(); } }
  async setTags(id: string, tags: string[]) { const p = this.db.products.find((x) => x.id === id); if (p) { p.tags = tags; this.persist(); } }
  async markPurchased(id: string, price: number | null) {
    const p = this.db.products.find((x) => x.id === id); if (!p) return;
    if (price == null) { p.purchased_at = null; p.purchased_price = null; p.active = true; }
    else { p.purchased_at = new Date().toISOString(); p.purchased_price = price; p.active = false; }
    this.persist();
  }
  async exportAll() { return { products: this.db.products, snapsById: this.db.snapshots }; }
  async importRows(rows: import("./csv").CsvRow[]) {
    let n = 0;
    for (const r of rows) {
      const p = await this.addProduct(r.url, r.title || undefined);
      if (r.category) p.category = r.category;
      if (r.price != null) {
        (this.db.snapshots[p.id] ??= []).push({ price: r.price, currency: r.currency, seller: r.seller, in_stock: r.in_stock, captured_at: r.captured_at || new Date().toISOString(), list_price: r.list_price });
        n++;
      }
    }
    for (const id of Object.keys(this.db.snapshots)) this.db.snapshots[id].sort((a, b) => a.captured_at.localeCompare(b.captured_at));
    this.persist();
    return n;
  }
  async removeProduct(id: string) {
    this.db.products = this.db.products.filter((p) => p.id !== id);
    delete this.db.snapshots[id];
    this.db.alerts = this.db.alerts.filter((a) => a.product_id !== id);
    this.persist();
  }
  async listAlerts() { return [...this.db.alerts].sort((a, b) => b.created_at.localeCompare(a.created_at)); }
  async markRead(id: string) { const a = this.db.alerts.find((x) => x.id === id); if (a) { a.read = true; this.persist(); } }
  async markAllRead() { this.db.alerts.forEach((a) => (a.read = true)); this.persist(); }
  async getSettings() { return { ...DEFAULT_SETTINGS, ...this.db.settings }; }
  async saveSettings(s: UserSettings) { this.db.settings = s; this.persist(); }
  async savePushSubscription(sub: PushSubscriptionJson) { this.db.push = [...(this.db.push ?? []).filter((s) => s.endpoint !== sub.endpoint), sub]; this.persist(); }
  async removePushSubscription(endpoint: string) { this.db.push = (this.db.push ?? []).filter((s) => s.endpoint !== endpoint); this.persist(); }
  async listShares() { return [...(this.db.shares ?? [])]; }
  async createShare(tag: string | null, name: string) {
    const s: ShareLink = { token: Array.from(crypto.getRandomValues(new Uint8Array(12))).map((b) => b.toString(16).padStart(2, "0")).join(""), tag, name: name || "가족", created_at: new Date().toISOString() };
    this.db.shares = [...(this.db.shares ?? []), s]; this.persist(); return s;
  }
  async deleteShare(token: string) { this.db.shares = (this.db.shares ?? []).filter((s) => s.token !== token); this.persist(); }
  async sharedView(token: string, rates: Rates) {
    const share = (this.db.shares ?? []).find((s) => s.token === token);
    if (!share) return null;
    const list = this.db.products.filter((p) => p.active && !p.purchased_at && (!share.tag || p.tags?.includes(share.tag)));
    const snaps: Record<string, Snapshot[]> = Object.fromEntries(list.map((p) => [p.id, this.db.snapshots[p.id] ?? []]));
    return { share, products: enrich(list.map((p) => overview(p, snaps[p.id], 90)), snaps, rates, 10, 90) };
  }
  async currentUserEmail() { return "demo@local"; }
  async signIn() { /* no-op */ }
  async signOut() { /* no-op */ }
}

// ------------------------------------------------------------------ Supabase
class SupabaseApi implements Api {
  readonly mode = "supabase" as const;
  constructor(private sb: SupabaseClient) {}

  private async uid(): Promise<string> {
    const { data } = await this.sb.auth.getUser();
    if (!data.user) throw new Error("로그인이 필요합니다");
    return data.user.id;
  }

  async listOverview(rates: Rates, threshold: number) {
    const settings = await this.getSettings();
    const { data: products, error } = await this.sb.from("products").select("*").order("created_at", { ascending: false });
    if (error) throw error;
    const ids = (products ?? []).map((p) => p.id);
    if (!ids.length) return [];
    const cutoff = new Date(Date.now() - 365 * 86400_000).toISOString();
    const { data: snaps } = await this.sb.from("price_snapshots").select("product_id,price,list_price,currency,seller,in_stock,suspect,captured_at")
      .in("product_id", ids).gte("captured_at", cutoff).order("captured_at");
    const by: Record<string, Snapshot[]> = {};
    for (const s of snaps ?? []) (by[s.product_id] ??= []).push({ ...s, price: Number(s.price), list_price: s.list_price == null ? null : Number(s.list_price) });
    return enrich((products as Product[]).map((p) => overview({ ...p, target_price: p.target_price == null ? null : Number(p.target_price), purchased_price: p.purchased_price == null ? null : Number(p.purchased_price) }, by[p.id] ?? [], settings.window_days)), by, rates, threshold, settings.window_days);
  }
  async getProduct(id: string) {
    const { data } = await this.sb.from("products").select("*").eq("id", id).maybeSingle();
    return (data as Product) ?? null;
  }
  async history(id: string, days: number) {
    const cutoff = new Date(Date.now() - days * 86400_000).toISOString();
    const { data } = await this.sb.from("price_snapshots").select("price,list_price,currency,seller,in_stock,suspect,captured_at")
      .eq("product_id", id).gte("captured_at", cutoff).order("captured_at");
    return (data ?? []).map((s) => ({ ...s, price: Number(s.price), list_price: s.list_price == null ? null : Number(s.list_price) })) as Snapshot[];
  }
  async addProduct(url: string, title?: string) {
    const { site, country, currency } = detectSite(url);
    const variant = parseVariant(url, site);
    // 이미 있으면 그대로 돌려준다 — upsert 의 DO UPDATE 로 사용자가 고친 제목·통화·구매 상태를 덮어쓰지 않도록
    const uid = await this.uid();
    const { data: existing } = await this.sb.from("products").select("*").eq("user_id", uid).eq("url", url).eq("variant_key", variant ?? "").maybeSingle();
    if (existing) {
      if (!existing.active && !existing.purchased_at) await this.sb.from("products").update({ active: true }).eq("id", existing.id);   // 중단된 상품 재등록 = 재개
      return { ...existing, active: existing.active || !existing.purchased_at } as Product;
    }
    const { data, error } = await this.sb.from("products")
      .upsert({ user_id: uid, url, title: title || url, site, country, currency, variant, active: true }, { onConflict: "user_id,url,variant_key", ignoreDuplicates: true })
      .select().maybeSingle();
    if (error) throw error;
    if (data) return data as Product;
    const { data: raced } = await this.sb.from("products").select("*").eq("user_id", uid).eq("url", url).eq("variant_key", variant ?? "").single();
    return raced as Product;
  }
  async capture(input: CaptureInput) {
    const p = await this.addProduct(input.url, input.title);
    if ((input.title && p.title === p.url) || p.currency !== input.currency) {
      await this.sb.from("products").update({ title: input.title || p.title, currency: input.currency }).eq("id", p.id);
    }
    const { error } = await this.sb.from("price_snapshots").insert({
      product_id: p.id, price: input.price, currency: input.currency, seller: input.seller ?? CAPTURE_SELLER,
      in_stock: true, list_price: input.list_price ?? null,
    });
    if (error) throw error;
    const { count } = await this.sb.from("price_snapshots").select("id", { count: "exact", head: true }).eq("product_id", p.id);
    return { id: p.id, title: input.title || p.title, currency: input.currency, count: count ?? 1 };
  }
  async setActive(id: string, active: boolean) { await this.sb.from("products").update({ active }).eq("id", id); }
  async setVerified(id: string, verified: boolean) { await this.sb.from("products").update({ verified }).eq("id", id); }
  async setCategory(id: string, category: string) { await this.sb.from("products").update({ category }).eq("id", id); }
  async setTarget(id: string, target: number | null) { await this.sb.from("products").update({ target_price: target }).eq("id", id); }
  async setTags(id: string, tags: string[]) { await this.sb.from("products").update({ tags }).eq("id", id); }
  async markPurchased(id: string, price: number | null) {
    await this.sb.from("products").update(price == null ? { purchased_at: null, purchased_price: null, active: true } : { purchased_at: new Date().toISOString(), purchased_price: price, active: false }).eq("id", id);
  }
  async exportAll() {
    const { data: products } = await this.sb.from("products").select("*").order("created_at");
    const { data: snaps } = await this.sb.from("price_snapshots").select("product_id,price,list_price,currency,seller,in_stock,suspect,captured_at").order("captured_at");
    const by: Record<string, Snapshot[]> = {};
    for (const s of snaps ?? []) (by[s.product_id] ??= []).push({ ...s, price: Number(s.price), list_price: s.list_price == null ? null : Number(s.list_price) });
    return { products: (products ?? []) as Product[], snapsById: by };
  }
  async importRows(rows: import("./csv").CsvRow[]) {
    let n = 0;
    for (const r of rows) {
      const p = await this.addProduct(r.url, r.title || undefined);
      if (r.category) await this.sb.from("products").update({ category: r.category }).eq("id", p.id);
      if (r.price != null) {
        const { error } = await this.sb.from("price_snapshots").insert({ product_id: p.id, price: r.price, currency: r.currency, seller: r.seller, in_stock: r.in_stock, list_price: r.list_price, captured_at: r.captured_at || new Date().toISOString() });
        if (!error) n++;
      }
    }
    return n;
  }
  async removeProduct(id: string) { await this.sb.from("products").delete().eq("id", id); }
  async listAlerts() {
    const { data } = await this.sb.from("alerts").select("*").order("created_at", { ascending: false }).limit(100);
    return (data ?? []).map((a) => ({ ...a, id: String(a.id), price: Number(a.price), baseline: a.baseline == null ? null : Number(a.baseline), pct: a.pct == null ? null : Number(a.pct) })) as Alert[];
  }
  async markRead(id: string) { await this.sb.from("alerts").update({ read: true }).eq("id", id); }
  async markAllRead() { await this.sb.from("alerts").update({ read: true }).eq("read", false); }
  async getSettings() {
    const { data } = await this.sb.from("user_settings").select("*").maybeSingle();
    return data ? { ...DEFAULT_SETTINGS, ...data, threshold_pct: Number(data.threshold_pct) } : DEFAULT_SETTINGS;
  }
  async saveSettings(s: UserSettings) {
    const { error } = await this.sb.from("user_settings").upsert({ ...s, user_id: await this.uid(), updated_at: new Date().toISOString() });
    if (error) throw error;
  }
  async savePushSubscription(sub: PushSubscriptionJson) {
    const { error } = await this.sb.from("push_subscriptions").upsert({ user_id: await this.uid(), endpoint: sub.endpoint, p256dh: sub.keys.p256dh, auth: sub.keys.auth }, { onConflict: "endpoint" });
    if (error) throw error;
  }
  async removePushSubscription(endpoint: string) { await this.sb.from("push_subscriptions").delete().eq("endpoint", endpoint); }
  async listShares() {
    const { data } = await this.sb.from("shares").select("token,tag,name,created_at").order("created_at");
    return (data ?? []) as ShareLink[];
  }
  async createShare(tag: string | null, name: string) {
    const { data, error } = await this.sb.from("shares").insert({ user_id: await this.uid(), tag, name: name || "가족" }).select("token,tag,name,created_at").single();
    if (error) throw error;
    return data as ShareLink;
  }
  async deleteShare(token: string) { await this.sb.from("shares").delete().eq("token", token); }
  async sharedView(token: string, rates: Rates) {
    const { data: info } = await this.sb.rpc("shared_info", { p_token: token });
    const share = (info ?? [])[0] as ShareLink | undefined;
    if (!share) return null;
    const [{ data: products }, { data: snaps }] = await Promise.all([
      this.sb.rpc("shared_products", { p_token: token }), this.sb.rpc("shared_snapshots", { p_token: token, p_days: 365 }),
    ]);
    const by: Record<string, Snapshot[]> = {};
    for (const s of snaps ?? []) (by[s.product_id] ??= []).push({ ...s, price: Number(s.price), list_price: s.list_price == null ? null : Number(s.list_price) });
    const list = ((products ?? []) as Product[]).filter((p) => !p.purchased_at).map((p) => ({ ...p, target_price: p.target_price == null ? null : Number(p.target_price) }));
    return { share, products: enrich(list.map((p) => overview(p, by[p.id] ?? [], 90)), by, rates, 10, 90) };
  }
  async currentUserEmail() { const { data } = await this.sb.auth.getUser(); return data.user?.email ?? null; }
  async signIn(email: string) {
    const { error } = await this.sb.auth.signInWithOtp({ email, options: { emailRedirectTo: location.origin } });
    if (error) throw error;
  }
  async signOut() { await this.sb.auth.signOut(); }
}

const url = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const key = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined;
export const supabase = url && key ? createClient(url, key) : null;
export const api: Api = supabase ? new SupabaseApi(supabase) : new DemoApi();
export const VAPID_PUBLIC_KEY = (import.meta.env.VITE_VAPID_PUBLIC_KEY as string | undefined) ?? "";
