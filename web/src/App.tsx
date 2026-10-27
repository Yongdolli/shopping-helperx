import { useEffect } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import ProductDetail from "./pages/ProductDetail";
import AddProduct from "./pages/AddProduct";
import Alerts from "./pages/Alerts";
import Deals from "./pages/Deals";
import Settings from "./pages/Settings";
import Capture from "./pages/Capture";
import Share from "./pages/Share";
import SharedView from "./pages/SharedView";
import { useStore } from "./store";

export default function App() {
  const refresh = useStore((s) => s.refresh);

  useEffect(() => { refresh(); }, [refresh]);

  // 로그인 없음 — 데이터는 이 브라우저에만 저장된다 (데모 모드)
  return (
    <BrowserRouter>
      <Routes>
        <Route path="s/:token" element={<SharedView />} />
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
      </Routes>
    </BrowserRouter>
  );
}
