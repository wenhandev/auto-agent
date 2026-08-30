import { Navigate, Route, Routes } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { DesktopAuthProvider, useDesktopAuth } from "./DesktopAuthContext";
import { DesktopShell } from "./DesktopShell";
import { DesktopSplash } from "./DesktopSplash";
import { DesktopStartupGate } from "./DesktopStartupGate";
import { RuntimeStatusProvider } from "./RuntimeStatusContext";
import { RuntimeWarningBanner } from "./RuntimeWarningBanner";
import { DesktopLoginPage } from "./pages/LoginPage";
import { DesktopOAuthCallbackPage } from "./pages/OAuthCallbackPage";
import { useDesktopOAuthCallback } from "./useDesktopOAuthCallback";
import { PendingAuthorizationPage } from "./pages/PendingAuthorizationPage";
import { HomePage } from "./pages/HomePage";
import { DeviceStatusPage } from "./pages/DeviceStatusPage";
import { DesktopRunsLayout } from "./pages/DesktopRunsLayout";
import { RunConsolePage } from "./pages/RunConsolePage";
import { RunReplayRouter } from "./pages/RunReplayRouter";
import { RunHistoryListPage } from "@/pages/RunHistoryListPage";
import { WorkflowsPage } from "./pages/WorkflowsPage";
import { WorkflowDetailPage } from "@/pages/WorkflowDetailPage";
import { WorkflowDraftEditPage } from "./pages/WorkflowDraftEditPage";
import { DesktopSettingsPage } from "./pages/SettingsPage";
import { RecordingsListPage } from "@/pages/RecordingsListPage";
import { RecordingDetailPage } from "@/pages/RecordingDetailPage";
import { AutonomousTaskPage } from "@/pages/AutonomousTaskPage";

function AuthenticatedRoutes() {
  return (
    <Routes>
      <Route element={<DesktopShell />}>
        <Route index element={<HomePage />} />
        <Route path="device" element={<DeviceStatusPage />} />
        <Route path="runs" element={<DesktopRunsLayout />}>
          <Route index element={<RunHistoryListPage />} />
          <Route path="console" element={<RunConsolePage />} />
          <Route path=":runId" element={<RunReplayRouter />} />
        </Route>
        <Route path="workflows" element={<WorkflowsPage />} />
        <Route path="workflows/:workflowId" element={<WorkflowDetailPage />} />
        <Route path="drafts/:draftId" element={<WorkflowDraftEditPage />} />
        <Route path="recordings" element={<RecordingsListPage />} />
        <Route path="recordings/:recordingId" element={<RecordingDetailPage />} />
        <Route path="tasks/new" element={<AutonomousTaskPage />} />
        <Route path="settings" element={<DesktopSettingsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

function SessionGate() {
  const { t } = useTranslation();
  const { session, isLoading } = useDesktopAuth();
  if (isLoading) {
    return (
      <DesktopSplash message={t("desktop.splash.loadingSession")} />
    );
  }
  if (!session) {
    return <Navigate to="/login" replace />;
  }
  if (session.approvalStatus === "pending") {
    return <Navigate to="/pending" replace />;
  }
  if (session.approvalStatus === "rejected") {
    return <Navigate to="/login" replace />;
  }
  return <AuthenticatedRoutes />;
}

function DesktopRoutes() {
  useDesktopOAuthCallback();
  return (
    <>
      <RuntimeWarningBanner />
      <Routes>
        <Route path="/login" element={<DesktopLoginPage />} />
        <Route path="/login/oauth/callback" element={<DesktopOAuthCallbackPage />} />
        <Route path="/pending" element={<PendingAuthorizationPage />} />
        <Route path="/*" element={<SessionGate />} />
      </Routes>
    </>
  );
}

export function DesktopApp() {
  return (
    <RuntimeStatusProvider>
      <DesktopStartupGate>
        <DesktopAuthProvider>
          <DesktopRoutes />
        </DesktopAuthProvider>
      </DesktopStartupGate>
    </RuntimeStatusProvider>
  );
}
