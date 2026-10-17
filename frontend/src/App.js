import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import HomePage from "@/pages/HomePage";
import DesignSystemPage from "@/pages/DesignSystemPage";
import ComingSoonPage from "@/pages/ComingSoonPage";
import NotFoundPage from "@/pages/NotFoundPage";
import { FUTURE_ROUTES } from "@/config/site";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<HomePage />} />
          <Route path="design-system" element={<DesignSystemPage />} />
          {FUTURE_ROUTES.map((r) => (
            <Route key={r.path} path={r.path} element={<ComingSoonPage />} />
          ))}
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
