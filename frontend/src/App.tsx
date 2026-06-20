import { Navigate, Route, Routes } from "react-router-dom";
import { ROUTES } from "./routes";
import { AuthGuard } from "./components/AuthGuard";
import { AppShell } from "./shell/AppShell";
import { AutonomousTaskPage } from "./pages/AutonomousTaskPage";
import { BrowserProfilesPage } from "./pages/BrowserProfilesPage";
import { BrowserSessionsPage } from "./pages/BrowserSessionsPage";
import { CredentialsListPage } from "./pages/CredentialsListPage";
import { OAuthCallbackPage } from "./pages/OAuthCallbackPage";
import { LoginPage } from "./pages/LoginPage";
import { AuthOAuthCallbackPage } from "./pages/AuthOAuthCallbackPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { RecordingDetailPage } from "./pages/RecordingDetailPage";
import { RecordingsListPage } from "./pages/RecordingsListPage";
import { RunHistoryListPage } from "./pages/RunHistoryListPage";
import { RunReplayPage } from "./pages/RunReplayPage";
import { SettingsPage } from "./pages/SettingsPage";
import { OrgMembersPage } from "./pages/OrgMembersPage";
import { WorkflowDetailPage } from "./pages/WorkflowDetailPage";
import { WorkflowsListPage } from "./pages/WorkflowsListPage";
import { ClientDownloadPage } from "./pages/ClientDownloadPage";
import { AdminConsolePage } from "./pages/admin/AdminConsolePage";

export function App() {
  return (
    <Routes>
      <Route path={ROUTES.login} element={<LoginPage />} />
      <Route path={ROUTES.loginOAuthCallback} element={<AuthOAuthCallbackPage />} />
      <Route path={ROUTES.clientDownload} element={<ClientDownloadPage />} />
      <Route element={<AuthGuard />}>
        <Route path={ROUTES.admin} element={<Navigate to="/admin/orgs" replace />} />
        <Route path={ROUTES.adminSection} element={<AdminConsolePage />} />
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
          <Route
            path={ROUTES.credentialsOAuthCallback}
            element={<OAuthCallbackPage />}
          />
          <Route path={ROUTES.runs} element={<RunHistoryListPage />} />
          <Route path={ROUTES.runReplay} element={<RunReplayPage />} />
          <Route path={ROUTES.tasks} element={<AutonomousTaskPage />} />
          <Route
            path={ROUTES.browserSessions}
            element={<BrowserSessionsPage />}
          />
          <Route
            path={ROUTES.browserProfiles}
            element={<BrowserProfilesPage />}
          />
          <Route path={ROUTES.recordings} element={<RecordingsListPage />} />
          <Route
            path={ROUTES.recordingDetail}
            element={<RecordingDetailPage />}
          />
          <Route path={ROUTES.settings} element={<SettingsPage />} />
          <Route path={ROUTES.members} element={<OrgMembersPage />} />
          <Route path={ROUTES.notFound} element={<NotFoundPage />} />
        </Route>
      </Route>
    </Routes>
  );
}
