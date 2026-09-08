import { create } from "zustand";

interface ToastState { msg: string | null; kind: "ok" | "err"; show: (msg: string, kind?: "ok" | "err") => void }
export const useToast = create<ToastState>((set) => ({
  msg: null, kind: "ok",
  show: (msg, kind = "ok") => { set({ msg, kind }); setTimeout(() => set({ msg: null }), 2200); },
}));
export const toast = (msg: string, kind: "ok" | "err" = "ok") => useToast.getState().show(msg, kind);

export default function Toast() {
  const { msg, kind } = useToast();
  if (!msg) return null;
  return (
    <div className="fixed bottom-20 md:bottom-6 inset-x-0 z-50 flex justify-center pointer-events-none">
      <div className={`rounded-full px-4 py-2 text-sm font-medium shadow-lg ${kind === "ok" ? "bg-slate-900 text-white dark:bg-white dark:text-slate-900" : "bg-rose-600 text-white"}`}>{msg}</div>
    </div>
  );
}
