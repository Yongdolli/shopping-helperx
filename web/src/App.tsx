import { useEffect, useState } from "react";
import { BrowserRouter, Outlet, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import ProductDetail from "./pages/ProductDetail";
import AddProduct from "./pages/AddProduct";
import Alerts from "./pages/Alerts";
import Deals from "./pages/Deals";
import Settings from "./pages/Settings";
import Login from "./pages/Login";
import Capture from "./pages/Capture";
import Share from "./pages/Share";
import SharedView from "./pages/SharedView";
import { AUTO_LOGIN, api, supabase } from "./lib/api";
import { useStore } from "./store";

// 기기별 로그인 링크(#login=…)는 모듈 로드 즉시 주소창에서 지운다 (세션 조회를 기다리는 동안 노출되지 않게)
const LINK_PW = (() => {
  const m = location.hash.match(/(?:^#|&)login=([^&]+)/);
  if (!m) return "";
  history.replaceState(null, "", location.pathname + location.search);
  return decodeURIComponent(m[1]);
})();

export default function App() {
  const refresh = useStore((s) => s.refresh);
  const [authed, setAuthed] = useState<boolean | null>(api.mode === "demo" ? true : null);
  const [autoErr, setAutoErr] = useState<string | null>(null);

  useEffect(() => {
    if (!supabase) return;
    supabase.auth.getSession().then(async ({ data }) => {
      // 기기별 로그인 링크: https://…/#login=<비밀번호> 를 한 번 열면 로그인 후 주소에서 지운다. 세션은 이 기기에 유지된다.
      const linkPw = LINK_PW;
      if (data.session && !linkPw) { setAuthed(true); return; }
      const pw = linkPw || AUTO_LOGIN.password;           // 로컬 개발은 .env.local 의 VITE_LOGIN_PASSWORD
      if (AUTO_LOGIN.email && pw) {
        try { await api.signInWithPassword(AUTO_LOGIN.email, pw); return; }
        catch (e) {
          if (data.session) { setAuthed(true); return; }     // 옛 링크여도 이미 로그인된 기기는 그대로
          setAutoErr((e as Error).message);
        }
      }
      setAuthed(false);
    });
    const { data: sub } = supabase.auth.onAuthStateChange((_e, session) => setAuthed(!!session));
    return () => sub.subscription.unsubscribe();
  }, []);

  useEffect(() => { if (authed) refresh(); }, [authed, refresh]);

  // 로그인 게이트는 라우터 안에서: 공유 링크(/s/:token)는 로그인 없이, 나머지는 세션 필요 (클라이언트 내비게이션에도 적용)
  return (
    <BrowserRouter>
      <Routes>
        <Route path="s/:token" element={<SharedView />} />
        <Route element={authed === null ? null : authed ? <Outlet /> : <Login autoError={autoErr} />}>
        <Route element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="p/:id" element={<ProductDetail />} />
          <Route path="add" element={<AddProduct />} />
          <Route path="deals" element={<Deals />} />
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
