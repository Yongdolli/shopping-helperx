import { NavLink, Outlet } from "react-router-dom";
import { useStore } from "../store";
import { api } from "../lib/api";
import Toast from "./Toast";

const NAV = [
  { to: "/", label: "홈", icon: "⌂" },
  { to: "/deals", label: "딜", icon: "🔥" },
  { to: "/alerts", label: "알림", icon: "🔔" },
  { to: "/add", label: "추가", icon: "＋" },
  { to: "/settings", label: "설정", icon: "⚙" },
];

export default function Layout() {
  const unread = useStore((s) => s.alerts.filter((a) => !a.read).length);
  const userEmail = useStore((s) => s.userEmail);

  const link = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition ${
      isActive ? "bg-sky-600 text-white" : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
    }`;

  return (
    <div className="min-h-full md:flex">
      {/* 데스크톱/패드 사이드바 */}
      <aside className="hidden md:flex md:w-60 lg:w-64 shrink-0 flex-col gap-1 border-r border-slate-200 dark:border-slate-800 p-4 sticky top-0 h-screen">
        <div className="mb-4 flex items-center gap-2 px-2">
          <img src="/icon.svg" className="h-8 w-8" alt="" />
          <div>
            <div className="font-bold leading-tight">Shopping Helper</div>
            <div className="text-[11px] text-slate-500">{api.mode === "demo" ? "데모 모드" : userEmail}</div>
          </div>
        </div>
        {NAV.map((n) => (
          <NavLink key={n.to} to={n.to} end={n.to === "/"} className={link}>
            <span className="w-5 text-center">{n.icon}</span>
            {n.label}
            {n.to === "/alerts" && unread > 0 && (
              <span className="ml-auto rounded-full bg-rose-500 px-2 py-0.5 text-[11px] text-white">{unread}</span>
            )}
          </NavLink>
        ))}
        <div className="mt-auto px-2 text-[11px] text-slate-400">v0.9 · 90일 중앙값 기준</div>
      </aside>

      {/* 본문 */}
      <main className="flex-1 min-w-0 pb-20 md:pb-8">
        <header className="md:hidden sticky top-0 z-10 flex items-center gap-2 border-b border-slate-200 dark:border-slate-800 bg-slate-50/90 dark:bg-slate-950/90 backdrop-blur px-4 py-3">
          <img src="/icon.svg" className="h-7 w-7" alt="" />
          <span className="font-bold">Shopping Helper</span>
          {api.mode === "demo" && <span className="ml-auto rounded-full bg-amber-100 text-amber-800 px-2 py-0.5 text-[11px]">데모</span>}
        </header>
        <div className="mx-auto max-w-5xl px-4 py-4 md:px-8 md:py-8">
          <Outlet />
        </div>
      </main>

      <Toast />

      {/* 모바일 하단 탭 */}
      <nav className="md:hidden fixed bottom-0 inset-x-0 z-10 grid grid-cols-5 border-t border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 pb-[env(safe-area-inset-bottom)]">
        {NAV.map((n) => (
          <NavLink key={n.to} to={n.to} end={n.to === "/"}
            className={({ isActive }) => `relative flex flex-col items-center py-2 text-[11px] ${isActive ? "text-sky-600" : "text-slate-500"}`}>
            <span className="text-lg leading-none">{n.icon}</span>
            {n.label}
            {n.to === "/alerts" && unread > 0 && (
              <span className="absolute top-1 right-[calc(50%-18px)] h-4 min-w-4 rounded-full bg-rose-500 px-1 text-[10px] leading-4 text-white">{unread}</span>
            )}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
