import { useEffect, useState } from "react";
import { BrowserRouter, Outlet, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import ProductDetail from "./pages/ProductDetail";
import AddProduct from "./pages/AddProduct";
import Alerts from "./pages/Alerts";
import Settings from "./pages/Settings";
import Login from "./pages/Login";
import Capture from "./pages/Capture";
import Share from "./pages/Share";
import SharedView from "./pages/SharedView";
import { api, supabase } from "./lib/api";
import { useStore } from "./store";

export default function App() {
  const refresh = useStore((s) => s.refresh);
  const [authed, setAuthed] = useState<boolean | null>(api.mode === "demo" ? true : null);

  useEffect(() => {
    if (!supabase) return;
    supabase.auth.getSession().then(({ data }) => setAuthed(!!data.session));
    const { data: sub } = supabase.auth.onAuthStateChange((_e, session) => setAuthed(!!session));
    return () => sub.subscription.unsubscribe();
  }, []);

  useEffect(() => { if (authed) refresh(); }, [authed, refresh]);

  // 로그인 게이트는 라우터 안에서: 공유 링크(/s/:token)는 로그인 없이, 나머지는 세션 필요 (클라이언트 내비게이션에도 적용)
  return (
    <BrowserRouter>
      <Routes>
        <Route path="s/:token" element={<SharedView />} />
        <Route element={authed === null ? null : authed ? <Outlet /> : <Login />}>
        <Route element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="p/:id" element={<ProductDetail />} />
          <Route path="add" element={<AddProduct />} />
          <Route path="alerts" element={<Alerts />} />
          <Route path="settings" element={<Settings />} />
          <Route path="capture" element={<Capture />} />
          <Route path="share" element={<Share />} />
        </Route>
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
