/** 배포 빌드용 공개 설정 — Vercel 대시보드/.env 없이도 빌드에 포함되도록 코드로 둔다 (저장소 Public).
 *  전부 공개돼도 되는 값(VAPID 공개키 등). 비밀번호·서비스 키·개인 이메일은 절대 여기 넣지 말 것. import.meta.env 값이 있으면 그쪽이 우선.
 */
export const PUBLIC_CONFIG = {
  VITE_VAPID_PUBLIC_KEY: "BKd20nQd6Cvj0wsnNcq29lQed1uh_VyIBcZAEP2VeZtFmIn9SwKFfv42dODczm98rtzYVB-luRMSeX33ctGtNvw",
} as const;

export const cfg = (k: keyof typeof PUBLIC_CONFIG): string => ((import.meta.env[k] as string | undefined) || PUBLIC_CONFIG[k] || "");
