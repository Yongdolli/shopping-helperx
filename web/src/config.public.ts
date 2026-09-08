/** 배포 빌드용 공개 설정 — Vercel 대시보드/.env 없이도 빌드에 포함되도록 코드로 둔다 (저장소 Private).
 *  전부 웹 번들에 어차피 들어가는 값(publishable 키·VAPID 공개키·개인용 자동 로그인). import.meta.env 값이 있으면 그쪽이 우선.
 *  값이 바뀌면 web/.env.local 과 이 파일을 같이 갱신. */
export const PUBLIC_CONFIG = {
  VITE_SUPABASE_URL: "https://fswqgcgyfuirihluoglh.supabase.co",
  VITE_SUPABASE_ANON_KEY: "sb_publishable_4JpLKj9aRsgeAokBVYJ0kQ_87j0In0M",
  VITE_VAPID_PUBLIC_KEY: "BKd20nQd6Cvj0wsnNcq29lQed1uh_VyIBcZAEP2VeZtFmIn9SwKFfv42dODczm98rtzYVB-luRMSeX33ctGtNvw",
  VITE_LOGIN_EMAIL: "jiyongseog@gmail.com",
  VITE_LOGIN_PASSWORD: "fiLDW2Cw1ZHpRRg2MTiOVdSw",
} as const;

export const cfg = (k: keyof typeof PUBLIC_CONFIG): string => ((import.meta.env[k] as string | undefined) || PUBLIC_CONFIG[k] || "");
