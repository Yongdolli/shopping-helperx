import { create } from "zustand";
import { api } from "./lib/api";
import type { Alert, ProductOverview, UserSettings } from "./types";
import { getRates, FALLBACK_KRW, type Rates } from "./lib/fx";
import type { CsvRow } from "./lib/csv";

interface State {
  products: ProductOverview[];   // 중단 상품 포함
  alerts: Alert[];
  settings: UserSettings | null;
  loading: boolean;
  error: string | null;
  userEmail: string | null;
  rates: Rates;
  ratesLive: boolean;
  refresh: () => Promise<void>;
  addProduct: (url: string, title?: string) => Promise<void>;
  setActive: (id: string, active: boolean) => Promise<void>;
  setVerified: (id: string, verified: boolean) => Promise<void>;
  setCategory: (id: string, category: string) => Promise<void>;
  setTarget: (id: string, target: number | null) => Promise<void>;
  setTags: (id: string, tags: string[]) => Promise<void>;
  markPurchased: (id: string, price: number | null) => Promise<void>;
  importCsv: (rows: CsvRow[]) => Promise<number>;
  removeProduct: (id: string) => Promise<void>;
  markRead: (id: string) => Promise<void>;
  markAllRead: () => Promise<void>;
  saveSettings: (s: UserSettings) => Promise<void>;
}

export const useStore = create<State>((set, get) => ({
  products: [],
  alerts: [],
  settings: null,
  loading: false,
  error: null,
  userEmail: null,
  rates: FALLBACK_KRW,
  ratesLive: false,

  refresh: async () => {
    set({ loading: true, error: null });
    try {
      const [settings, fx] = await Promise.all([api.getSettings(), getRates()]);
      const [products, alerts, userEmail] = await Promise.all([
        api.listOverview(fx.rates, settings.threshold_pct), api.listAlerts(), api.currentUserEmail(),
      ]);
      set({ products, alerts, settings, userEmail, rates: fx.rates, ratesLive: fx.live, loading: false });
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
    }
  },
  addProduct: async (url, title) => { await api.addProduct(url, title); await get().refresh(); },
  setActive: async (id, active) => {
    await api.setActive(id, active);
    set({ products: get().products.map((p) => (p.id === id ? { ...p, active } : p)) });
  },
  setVerified: async (id, verified) => { await api.setVerified(id, verified); await get().refresh(); },
  setCategory: async (id, category) => { await api.setCategory(id, category); await get().refresh(); },
  setTarget: async (id, target) => { await api.setTarget(id, target); await get().refresh(); },
  setTags: async (id, tags) => { await api.setTags(id, tags); await get().refresh(); },
  markPurchased: async (id, price) => { await api.markPurchased(id, price); await get().refresh(); },
  importCsv: async (rows) => { const n = await api.importRows(rows); await get().refresh(); return n; },
  removeProduct: async (id) => { await api.removeProduct(id); await get().refresh(); },
  markRead: async (id) => {
    await api.markRead(id);
    set({ alerts: get().alerts.map((a) => (a.id === id ? { ...a, read: true } : a)) });
  },
  markAllRead: async () => {
    await api.markAllRead();
    set({ alerts: get().alerts.map((a) => ({ ...a, read: true })) });
  },
  saveSettings: async (s) => { await api.saveSettings(s); set({ settings: s }); },
}));
