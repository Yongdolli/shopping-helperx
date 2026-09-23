import { useState } from "react";
import { api } from "../lib/api";

/** 자동 로그인(VITE_LOGIN_EMAIL/PASSWORD)이 없거나 실패했을 때만 보이는 예비 화면 */
export default function Login({ autoError }: { autoError?: string | null }) {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    try { await api.signIn(email.trim()); setSent(true); } catch (ex) { setErr((ex as Error).message); }
  };

  return (
    <div className="min-h-full flex items-center justify-center p-6">
      <form onSubmit={submit} className="card w-full max-w-sm p-6 space-y-4">
        <div className="flex items-center gap-2"><img src="/icon.svg" className="h-9 w-9" alt="" /><span className="text-lg font-bold">Shopping Helper</span></div>
        <div className="rounded-xl bg-sky-50 dark:bg-sky-900/30 p-3 text-xs text-sky-900 dark:text-sky-100">받아 둔 <b>로그인 링크</b>(주소 끝이 <code>#login=…</code>)를 이 기기에서 한 번 열면 바로 로그인되고 이후엔 유지됩니다.</div>
        {autoError && <div className="text-sm text-rose-600">자동 로그인 실패: {autoError}<div className="text-xs text-slate-500 mt-1">worker 에서 <code>python -m worker user &lt;email&gt; &lt;비밀번호&gt;</code> 로 계정을 만들고 web/.env.local 의 VITE_LOGIN_* 과 맞추세요.</div></div>}
        <p className="text-sm text-slate-500">이메일로 로그인 링크를 보내드립니다.</p>
        {sent ? (
          <div className="text-sm text-emerald-600">메일함을 확인하세요. 링크를 누르면 로그인됩니다.</div>
        ) : (
          <>
            <input className="input" type="email" required placeholder="you@example.com" value={email} onChange={(e) => setEmail(e.target.value)} />
            {err && <div className="text-sm text-rose-600">{err}</div>}
            <button className="btn-primary w-full">로그인 링크 보내기</button>
          </>
        )}
      </form>
    </div>
  );
}
