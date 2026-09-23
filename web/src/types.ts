export type Country = "KR" | "CN" | "US";
export type AlertKind = "target" | "drop" | "low" | "restock" | "fake" | "paused";

export interface Product {
  id: string;
  title: string;
  url: string;
  site: string;
  country: Country;
  currency: string;
  external_id?: string | null;
  model_no?: string | null;
  image_url?: string | null;
  variant?: string | null;      // 옵션 식별자 (예: vendorItemId=123)
  active: boolean;
  fail_count?: number;
  last_error?: string | null;
  verified?: boolean;            // 사용자가 '정품 확인됨' 표시
  category?: string | null;      // 관세 계산용 (전자/의류/…)
  target_price?: number | null;  // 목표가
  tags?: string[];               // 태그
  purchased_at?: string | null;  // 구매 기록 → 추적 종료, 절약액 계산
  purchased_price?: number | null;
  created_at: string;
}

export interface Snapshot {
  price: number;
  currency: string;
  seller?: string | null;
  in_stock: boolean;
  captured_at: string;
  list_price?: number | null;   // 사이트 표시 정가
  suspect?: boolean;            // 극단값 — 확인 전
}

export interface Alert {
  id: string;
  product_id: string;
  kind: AlertKind;
  price: number;
  baseline?: number | null;
  pct?: number | null;
  note?: string | null;
  read: boolean;
  created_at: string;
}

export interface UserSettings {
  threshold_pct: number;
  window_days: number;
  notify_push: boolean;
  notify_email: boolean;
  notify_telegram: boolean;
  email?: string | null;
  telegram_chat_id?: string | null;
  digest: boolean;               // 하루 3회 모아 받기 (08:00·12:30·19:00 KST). false = 감지 즉시
  instant_target: boolean;       // digest 여도 목표가 도달은 즉시
  deal_min_pct: number;          // 딜 탭·다이제스트: 이 할인율 이상만 '확인된 딜'
  deal_keywords: string[];       // 관심 키워드 — 일치하면 할인율 없어도 다이제스트에 포함
}

/** 핫딜 커뮤니티에서 워커가 모은 딜 (전 사용자 공용). url = 게시글 */
export interface Deal {
  url: string; source: string; site: string; site_label?: string | null; title: string;
  price: number | null; currency: string; shipping?: string | null; pct: number | null;
  image_url?: string | null; category?: string | null; posted_at: string;
  shop_url?: string | null;      // 상점 상품 주소 (있으면 원클릭 추적)
  list_price?: number | null;    // 상점 정가 (있으면 pct 는 정가 대비 계산값)
  ref_price?: number | null;     // 평소 가격 = 다나와 전체 쇼핑몰 최저가 관측 중앙값 (워커 market.py)
  ref_name?: string | null; ref_url?: string | null;
  below_pct?: number | null;     // 평소 대비 % (양수 = 평소보다 쌈)
}

/** 판단에 쓰는 할인율: 평소 대비가 있으면 그것, 없으면 표시 할인율 (워커 Deal.effective_pct 와 동일) */
export const effectivePct = (d: Deal) => (d.below_pct ?? d.pct ?? null);

/** 여러 커뮤니티에 올라온 같은 딜을 묶는 키: 제목 글자(공백·기호 제거) + 가격. 워커 deals.same_key 와 동일 */
export const dealKey = (d: Deal) => `${d.title.toLowerCase().replace(/[^0-9a-z가-힣]/g, "")}|${d.price ? Math.trunc(d.price) : ""}`;

/** 같은 딜 묶음: 시세 확인된 것 → 최신 순으로 대표 1건, 나머지 출처는 sources 로 */
export function groupDeals(list: Deal[]): Array<Deal & { sources: string[] }> {
  const by = new Map<string, Deal[]>();
  for (const d of list) { const k = dealKey(d); by.set(k, [...(by.get(k) ?? []), d]); }
  return [...by.values()].map((g) => {
    const rep = [...g].sort((a, b) => Number(a.below_pct == null) - Number(b.below_pct == null) || b.posted_at.localeCompare(a.posted_at))[0];
    return { ...rep, sources: [...new Set(g.map((x) => x.source))] };
  });
}

/** 가족 공유 링크 — 태그(또는 전체) 단위 읽기 전용. /s/:token 은 로그인 없이 열린다 */
export interface ShareLink { token: string; tag: string | null; name: string; created_at: string }

export interface PushSubscriptionJson {
  endpoint: string;
  keys: { p256dh: string; auth: string };
}

/** 대시보드 카드용: 상품 + 파생 지표 */
export interface ProductOverview extends Product {
  last_price: number | null;
  last_list_price: number | null;
  last_seller: string | null;
  last_captured_at: string | null;
  baseline: number | null;
  all_time_low: number | null;
  pct_vs_baseline: number | null; // 양수 = 기준선보다 싸다 (실제 할인율)
  claimed_pct: number | null;     // 사이트가 표시하는 할인율 (정가 대비)
  fake: boolean;                  // 가짜 할인 의심
  in_stock: boolean;
  pending_confirm: boolean;       // 마지막 수집이 극단값이라 확인 대기
  target_hit: boolean | null;     // 목표가 이하 (목표가 없으면 null)
  trend_pct: number | null;       // 최근 30일 추세(%)
  landed_krw: number | null;      // 한국 도착 최종가 (KRW)
  landed_rank: [number, number] | null; // 같은 모델 비교 순위
  decision: import("./lib/decision").Decision;
  risk: import("./lib/risk").RiskResult;  // 정품 리스크 (규칙 기반)
}
