import { Route, Routes } from "react-router-dom";

import { AppShell } from "@/components/layout/AppShell";
import { HomePage } from "@/pages/HomePage";
import { RepositoryPage } from "@/pages/RepositoryPage";

export function AppRouter() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/" element={<HomePage />} />
        <Route path="/repositories/:id" element={<RepositoryPage />} />
      </Route>
    </Routes>
  );
}
