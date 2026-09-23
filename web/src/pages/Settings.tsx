import { useEffect, useState } from "react";
import { useStore } from "../store";
import { api, VAPID_PUBLIC_KEY } from "../lib/api";
import { currentSubscription, disablePush, enablePush, pushSupported } from "../lib/push";
import type { ShareLink, UserSettings } from "../types";
import { bookmarkletHref } from "../lib/bookmarklet";
import { parseCsv, toCsv } from "../lib/csv";
import { toast } from "../components/Toast";

export default function Settings() {
  const { settings, saveSettings, userEmail, refresh } = useStore();
  const [s, setS] = useState<UserSettings | null>(settings);
  const [saved, setSaved] = useState(false);
  const [pushState, setPushState] = useState<"off" | "local" | "on" | "denied" | "unsupported">("off");
  const [pushBusy, setPushBusy] = useState(false);

  useEffect(() => setS(settings), [settings]);
  useEffect(() => {
    if (!pushSupported()) { setPushState("unsupported"); return; }
    if (Notification.permission === "denied") { setPushState("denied"); return; }
    currentSubscription().then((sub) => setPushState(sub ? "on" : Notification.permission === "granted" ? "local" : "off"));
  }, []);

  if (!s) return null;
  const set = <K extends keyof UserSettings>(k: K, v: UserSettings[K]) => setS({ ...s, [k]: v });
  const save = async () => { await saveSettings(s); setSaved(true); toast("설정을 저장했습니다"); setTimeout(() => setSaved(false), 1500); };

  const togglePush = async () => {
    setPushBusy(true);
    try {
      if (pushState === "on") { await disablePush(); setPushState("off"); }
      else {
        const r = await enablePush();
        setPushState(r === "subscribed" ? "on" : r === "local-only" ? "local" : r === "denied" ? "denied" : "unsupported");
      }
    } finally { setPushBusy(false); }
  };

  return (
    <div className="max-w-xl space-y-4">
      <h1 className="text-xl font-bold">설정</h1>

      <section className="card p-4 md:p-6 space-y-4">
        <h2 className="font-semibold">알림 기준</h2>
        <Field label={`하락 임계값: ${s.threshold_pct}%`} hint="평소 가격보다 이만큼 싸지면 알림">
          <input type="range" min={3} max={40} step={1} value={s.threshold_pct} onChange={(e) => set("threshold_pct", Number(e.target.value))} className="w-full accent-sky-600" />
        </Field>
        <Field label="기준선 기간" hint="이 기간의 가격 중앙값을 '평소 가격'으로 봅니다">
          <div className="flex gap-2">
            {[30, 60, 90, 180].map((d) => (
              <button key={d} onClick={() => set("window_days", d)} className={`rounded-lg px-3 py-1.5 text-sm ${s.window_days === d ? "bg-slate-900 text-white dark:bg-white dark:text-slate-900" : "bg-slate-100 dark:bg-slate-800"}`}>{d}일</button>
            ))}
          </div>
        </Field>
        <div className="text-xs text-slate-500">가짜 할인 의심: 사이트 표시 할인이 20% 이상인데 평소 가격 대비 3% 이하일 때 (주 1회만 알림)</div>
      </section>

      <section className="card p-4 md:p-6 space-y-4">
        <h2 className="font-semibold">알림 채널</h2>
        <div className="rounded-xl bg-slate-50 dark:bg-slate-800/60 p-3 space-y-1">
          <Toggle label="하루 3회 모아 받기" checked={s.digest ?? true} onChange={(v) => set("digest", v)} hint="아침 08:00 · 점심 12:30 · 저녁 19:00" />
          {(s.digest ?? true) && <Toggle label="목표가 도달은 즉시 보내기" checked={s.instant_target ?? true} onChange={(v) => set("instant_target", v)} hint="놓치면 아까운 알림" />}
          <div className="text-xs text-slate-500">{(s.digest ?? true) ? "감지된 알림을 모아 세 번만 보냅니다. 앱 알림 탭에는 즉시 쌓입니다." : "끄면 워커가 감지하는 즉시 보냅니다 (같은 상품·종류는 24시간에 1회)."} 주간 요약은 월요일 09:00.</div>
        </div>

        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="text-sm">웹푸시 (폰·PC 알림)</div>
            <div className="text-xs text-slate-500">
              {pushState === "on" && "연결됨 — 워커가 감지하면 이 기기로 알림이 옵니다"}
              {pushState === "local" && (VAPID_PUBLIC_KEY ? "권한만 있음 — 다시 눌러 구독" : "권한 허용됨 · 서버 푸시는 VAPID 키 설정 후 가능")}
              {pushState === "off" && "홈화면에 설치하면 앱처럼 알림을 받습니다"}
              {pushState === "denied" && "브라우저에서 알림이 차단됨 — 사이트 설정에서 허용하세요"}
              {pushState === "unsupported" && "이 브라우저는 푸시를 지원하지 않습니다 (iOS는 홈화면 설치 후 가능)"}
            </div>
          </div>
          <button className={`shrink-0 whitespace-nowrap ${pushState === "on" ? "btn-ghost" : "btn-primary"}`} disabled={pushBusy || pushState === "denied" || pushState === "unsupported"} onClick={togglePush}>
            {pushBusy ? "…" : pushState === "on" ? "끄기" : "켜기"}
          </button>
        </div>
        <Toggle label="푸시 알림 받기" checked={s.notify_push} onChange={(v) => set("notify_push", v)} hint="서버 발송 on/off" />

        <Toggle label="이메일" checked={s.notify_email} onChange={(v) => set("notify_email", v)} />
        {s.notify_email && <input className="input" type="email" placeholder="받을 이메일" value={s.email ?? ""} onChange={(e) => set("email", e.target.value)} />}
        <Toggle label="텔레그램" checked={s.notify_telegram} onChange={(v) => set("notify_telegram", v)} />
        {s.notify_telegram && (
          <div className="space-y-1">
            <input className="input" placeholder="Telegram chat ID" value={s.telegram_chat_id ?? ""} onChange={(e) => set("telegram_chat_id", e.target.value)} />
            <p className="text-xs text-slate-500">봇에게 /start 를 보낸 뒤 @userinfobot 등으로 chat ID 를 확인하세요. 봇 토큰은 워커 환경변수(TELEGRAM_BOT_TOKEN)에 넣습니다.</p>
          </div>
        )}
        <button className="btn-primary" onClick={save}>{saved ? "저장됨 ✓" : "저장"}</button>
      </section>

      <section className="card p-4 md:p-6 space-y-4">
        <h2 className="font-semibold">🔥 딜 필터</h2>
        <p className="text-xs text-slate-500">핫딜 커뮤니티 5곳(뽐뿌·루리웹·클리앙·퀘이사존·에펨코리아)에서 매시간 모은 딜 중, 아래 조건에 맞는 것을 딜 탭에서 강조하고 아침·점심·저녁 다이제스트에 넣습니다.</p>
        <Field label={`평소보다 ${s.deal_min_pct ?? 10}% 이상 싸면`} hint="평소 가격(다나와 시세 중앙값) 대비. 시세를 못 찾은 딜은 게시글에 적힌 할인율로 판단">
          <input type="range" min={5} max={60} step={5} value={s.deal_min_pct ?? 10} onChange={(e) => set("deal_min_pct", Number(e.target.value))} className="w-full accent-sky-600" />
        </Field>
        <Field label="관심 키워드" hint="쉼표로 구분. 제목에 포함되면 할인율이 없어도 알려줍니다 (예: 마우스, 헤드폰, 로봇청소기)">
          <input className="input" placeholder="마우스, 헤드폰, 로봇청소기" value={(s.deal_keywords ?? []).join(", ")}
            onChange={(e) => set("deal_keywords", e.target.value.split(/[,，]/).map((k) => k.trim()).filter(Boolean))} />
        </Field>
        <button className="btn-primary" onClick={save}>{saved ? "저장됨 ✓" : "저장"}</button>
      </section>

      <ShareSection />
      <BookmarkletSection />
      <CsvSection />

      <section className="card p-4 md:p-6 space-y-2 text-sm">
        <h2 className="font-semibold">계정</h2>
        {api.mode === "demo" ? (
          <p className="text-slate-500">데모 모드입니다. 데이터는 이 브라우저에만 저장됩니다. <code>web/.env.local</code> 에 Supabase 키를 넣으면 계정·동기화·워커 연동이 켜집니다.</p>
        ) : (
          <div className="flex items-center justify-between">
            <span>{userEmail}</span>
            <button className="btn-ghost" onClick={async () => { await api.signOut(); await refresh(); }}>로그아웃</button>
          </div>
        )}
      </section>
    </div>
  );
}

function ShareSection() {
  const products = useStore((s) => s.products);
  const tags = Array.from(new Set(products.filter((p) => p.active).flatMap((p) => p.tags ?? [])));
  const [shares, setShares] = useState<ShareLink[]>([]);
  const [tag, setTag] = useState<string>("");
  const [name, setName] = useState("가족");
  const [busy, setBusy] = useState(false);
  useEffect(() => { api.listShares().then(setShares).catch(() => undefined); }, []);
  const create = async () => {
    setBusy(true);
    try { const s = await api.createShare(tag || null, name.trim() || "가족"); setShares((l) => [...l, s]); toast("공유 링크를 만들었습니다"); }
    catch (e) { toast("실패: " + (e as Error).message); } finally { setBusy(false); }
  };
  const remove = async (t: string) => { await api.deleteShare(t); setShares((l) => l.filter((s) => s.token !== t)); };
  const copy = async (t: string) => { try { await navigator.clipboard.writeText(`${location.origin}/s/${t}`); toast("링크를 복사했습니다"); } catch { /* ignore */ } };
  return (
    <section className="card p-4 md:p-6 space-y-3 text-sm">
      <h2 className="font-semibold">가족 공유 — 읽기 전용 링크</h2>
      <p className="text-xs text-slate-500">태그 하나(예: #선물)나 전체 목록을 링크로 공유합니다. 받은 사람은 로그인 없이 현재가·"지금 사도 됨" 판단을 봅니다. 수정은 못 합니다.{api.mode === "demo" && " 데모 모드에선 이 브라우저에서만 열립니다."}</p>
      <div className="flex flex-wrap gap-2">
        <select className="rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm" value={tag} onChange={(e) => setTag(e.target.value)}>
          <option value="">전체 상품</option>
          {tags.map((t) => <option key={t} value={t}>#{t}</option>)}
        </select>
        <input className="input flex-1 min-w-32" placeholder="이름 (예: 가족)" value={name} onChange={(e) => setName(e.target.value)} />
        <button className="btn-primary" disabled={busy} onClick={create}>링크 만들기</button>
      </div>
      {shares.length > 0 && (
        <ul className="space-y-1.5">
          {shares.map((s) => (
            <li key={s.token} className="flex items-center gap-2 rounded-xl bg-slate-50 dark:bg-slate-800/60 px-3 py-2">
              <span className="font-medium">{s.name}</span><span className="text-xs text-slate-500">{s.tag ? `#${s.tag}` : "전체"}</span>
              <a href={`/s/${s.token}`} target="_blank" rel="noreferrer" className="ml-auto text-xs text-sky-600">열기</a>
              <button className="text-xs text-sky-600" onClick={() => copy(s.token)}>복사</button>
              <button className="text-xs text-rose-500" onClick={() => remove(s.token)}>삭제</button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function BookmarkletSection() {
  const href = bookmarkletHref(location.origin);
  const [copied, setCopied] = useState(false);
  const copy = async () => { try { await navigator.clipboard.writeText(href); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { /* ignore */ } };
  return (
    <section className="card p-4 md:p-6 space-y-3 text-sm">
      <h2 className="font-semibold">북마클릿 — 보고 있는 페이지 가격 기록</h2>
      <p className="text-slate-500 text-xs">
        네이버 스마트스토어·쿠팡·아마존처럼 자동 수집이 막힌 사이트는 <b>내 브라우저가 대신 읽습니다</b>. 상품 페이지에서 이 북마크를 누르면 가격이 여기에 기록되고, 3회 이상 쌓이면 급락 판정이 시작됩니다.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <a href={href} onClick={(e) => e.preventDefault()} draggable
          className="inline-flex items-center gap-1 rounded-xl bg-sky-600 px-4 py-2.5 text-sm font-semibold text-white cursor-grab" title="이 버튼을 북마크바로 드래그">
          📌 가격 기록
        </a>
        <button className="btn-ghost" onClick={copy}>{copied ? "복사됨 ✓" : "코드 복사"}</button>
      </div>
      <details className="text-xs text-slate-500">
        <summary className="cursor-pointer">설치 방법</summary>
        <ul className="mt-2 space-y-1 list-disc pl-4">
          <li><b>PC</b>: 위 파란 버튼을 북마크바로 드래그. 상품 페이지에서 그 북마크 클릭.</li>
          <li><b>iPhone/iPad Safari</b>: 아무 페이지나 북마크에 추가 → "코드 복사" → 북마크 편집에서 주소를 붙여넣기로 교체. 상품 페이지에서 주소창에 북마크 이름을 입력해 실행.</li>
          <li><b>Android Chrome</b>: 같은 방법으로 북마크 주소를 교체한 뒤, 주소창에 북마크 이름을 입력해 실행.</li>
        </ul>
      </details>
    </section>
  );
}

function CsvSection() {
  const importCsv = useStore((s) => s.importCsv);
  const [msg, setMsg] = useState("");
  const exportCsv = async () => {
    const { products, snapsById } = await api.exportAll();
    const blob = new Blob([toCsv(products, snapsById)], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = `shopping-helper-${new Date().toISOString().slice(0, 10)}.csv`; a.click();
    URL.revokeObjectURL(a.href);
  };
  const onFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]; if (!f) return;
    try { const rows = parseCsv(await f.text()); const n = await importCsv(rows); setMsg(`${rows.length}행 읽음 · 가격 ${n}건 추가`); toast(`가져오기 완료 — ${n}건`); }
    catch (ex) { setMsg("가져오기 실패: " + (ex as Error).message); }
    e.target.value = "";
  };
  return (
    <section className="card p-4 md:p-6 space-y-3 text-sm">
      <h2 className="font-semibold">백업 · 이전 (CSV)</h2>
      <p className="text-xs text-slate-500">추적 상품과 가격 이력을 CSV 로 내보내거나, 다른 기기에서 내보낸 파일을 가져옵니다. 같은 URL 은 같은 상품에 합쳐집니다.</p>
      <div className="flex flex-wrap gap-2">
        <button className="btn-ghost" onClick={exportCsv}>내보내기</button>
        <label className="btn-ghost cursor-pointer">가져오기<input type="file" accept=".csv,text/csv" className="hidden" onChange={onFile} /></label>
      </div>
      {msg && <div className="text-xs text-slate-600 dark:text-slate-300">{msg}</div>}
    </section>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-sm font-medium">{label}</div>
      {hint && <div className="text-xs text-slate-500 mb-2">{hint}</div>}
      {children}
    </div>
  );
}

function Toggle({ label, checked, onChange, disabled, hint }: { label: string; checked: boolean; onChange?: (v: boolean) => void; disabled?: boolean; hint?: string }) {
  return (
    <label className={`flex items-center justify-between ${disabled ? "opacity-60" : "cursor-pointer"}`}>
      <span className="text-sm">{label}{hint && <span className="ml-2 text-xs text-slate-400">{hint}</span>}</span>
      <span className={`relative inline-block h-6 w-11 rounded-full transition ${checked ? "bg-sky-600" : "bg-slate-300 dark:bg-slate-700"}`}>
        <input type="checkbox" className="sr-only" checked={checked} disabled={disabled} onChange={(e) => onChange?.(e.target.checked)} />
        <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition ${checked ? "left-[22px]" : "left-0.5"}`} />
      </span>
    </label>
  );
}
