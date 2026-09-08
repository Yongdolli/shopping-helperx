import { useState } from "react";
import { api } from "../lib/api";

export default function Login() {
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
