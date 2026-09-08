/** 안드로이드 공유 대상: 쿠팡·네이버 앱에서 "공유 → Shopping Helper" 하면 여기로 들어와 /add 로 넘긴다. */
import { useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

export default function Share() {
  const [sp] = useSearchParams();
  const nav = useNavigate();
  useEffect(() => {
    const blob = [sp.get("url"), sp.get("text"), sp.get("title")].filter(Boolean).join(" ");
    const m = blob.match(/https?:\/\/[^\s"'<>]+/);
    const title = (sp.get("title") || "").replace(/https?:\/\/\S+/g, "").trim();
    const q = new URLSearchParams();
    if (m) q.set("url", m[0]);
    if (title) q.set("title", title.slice(0, 120));
    nav(`/add?${q.toString()}`, { replace: true });
  }, [sp, nav]);
  return <div className="text-sm text-slate-500">공유된 링크를 여는 중…</div>;
}
