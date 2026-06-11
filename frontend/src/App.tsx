import { Navigate, Route, Routes } from "react-router-dom";
import { ROUTES } from "./routes";
import { AppShell } from "./shell/AppShell";
import { CredentialsListPage } from "./pages/CredentialsListPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { RunHistoryListPage } from "./pages/RunHistoryListPage";
import { RunReplayPage } from "./pages/RunReplayPage";
import { SettingsPage } from "./pages/SettingsPage";
import { WorkflowDetailPage } from "./pages/WorkflowDetailPage";
import { WorkflowsListPage } from "./pages/WorkflowsListPage";

export function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route
          path={ROUTES.root}
          element={<Navigate to={ROUTES.workflows} replace />}
        />
        <Route path={ROUTES.workflows} element={<WorkflowsListPage />} />
        <Route
          path={ROUTES.workflowDetail}
          element={<WorkflowDetailPage />}
        />
        <Route path={ROUTES.credentials} element={<CredentialsListPage />} />
        <Route path={ROUTES.runs} element={<RunHistoryListPage />} />
        <Route path={ROUTES.runReplay} element={<RunReplayPage />} />
        <Route path={ROUTES.settings} element={<SettingsPage />} />
        <Route path={ROUTES.notFound} element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
