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
  recommends?: number | null;    // 커뮤니티 추천 수 (013)
  comments?: number | null;
  ended?: boolean;               // 종료·품절
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
    return { ...rep, sources: [...new Set(g.map((x) => x.source))], ended: g.some((x) => x.ended),
      recommends: g.reduce((a, x) => a + (x.recommends ?? 0), 0), comments: g.reduce((a, x) => a + (x.comments ?? 0), 0) };
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

/** 인기 점수 = 추천×3 + 댓글 (여러 커뮤니티 합산) */
export const popularity = (d: Deal) => (d.recommends ?? 0) * 3 + (d.comments ?? 0);

/** 딜 분류 — 제목·커뮤니티 분류로 추정 (웹 전용, 필터용) */
export const DEAL_CATEGORIES = ["가전·디지털", "식품", "생활·뷰티", "패션", "게임·앱·쿠폰", "기타"] as const;
export type DealCategory = typeof DEAL_CATEGORIES[number];
const CAT_WORDS: Array<[DealCategory, RegExp]> = [
  ["게임·앱·쿠폰", /(스팀|steam|ps5|ps4|닌텐도|스위치|xbox|게임|dlc|앱|app|ios|android|구독|이용권|상품권|기프티콘|쿠폰|포인트|네이버페이|토스|페이백|멤버십|리딤|코드|e북|웹툰)/i],
  ["가전·디지털", /(노트북|모니터|키보드|마우스|이어폰|헤드폰|헤드셋|스피커|충전기|케이블|ssd|hdd|메모리|ddr|그래픽|cpu|갤럭시|아이폰|아이패드|태블릿|워치|tv|티비|냉장고|세탁기|건조기|청소기|에어컨|선풍기|공기청정|가습기|제습기|전자레인지|밥솥|에어프라이어|카메라|프린터|공유기|usb|hdmi|배터리|보조배터리|로지텍|삼성|lg|애플|샤오미|다이슨)/i],
  ["식품", /(\d+\s*(g|kg|ml|l)\b|라면|햇반|쌀|우유|두유|커피|음료|생수|콜라|사이다|제로|과자|김|고기|한우|돼지|닭|계란|달걀|과일|사과|배|귤|포도|샤인머스캣|멜론|반찬|김치|치즈|빵|떡|아이스크림|피자|치킨|햄버거|버거|도시락|간식|견과|꿀|올리브오일|소스|국|찌개|만두|냉동)/i],
  ["생활·뷰티", /(세제|섬유유연제|휴지|물티슈|키친타월|샴푸|린스|바디|치약|칫솔|로션|크림|선크림|화장품|마스크팩|향수|기저귀|생리대|수건|이불|베개|매트리스|의자|책상|수납|조명|캠핑|텀블러|냄비|프라이팬|영양제|비타민|유산균|오메가)/i],
  ["패션", /(티셔츠|반팔|긴팔|셔츠|바지|청바지|슬랙스|자켓|재킷|패딩|코트|니트|후드|맨투맨|원피스|스커트|양말|속옷|신발|운동화|스니커즈|슬리퍼|샌들|부츠|가방|백팩|지갑|모자|벨트|나이키|아디다스|뉴발란스|푸마|반스)/i],
];
export function dealCategory(d: Deal): DealCategory {
  const text = `${d.title} ${d.category ?? ""} ${d.site_label ?? ""}`;
  for (const [cat, re] of CAT_WORDS) if (re.test(text)) return cat;
  return "기타";
}
