import { Navigate, Route, Routes } from "react-router-dom";
import { DesktopAuthProvider, useDesktopAuth } from "./DesktopAuthContext";
import { DesktopShell } from "./DesktopShell";
import { RuntimeStatusProvider } from "./RuntimeStatusContext";
import { RuntimeWarningBanner } from "./RuntimeWarningBanner";
import { DesktopLoginPage } from "./pages/LoginPage";
import { PendingAuthorizationPage } from "./pages/PendingAuthorizationPage";
import { OverviewPage } from "./pages/OverviewPage";
import { RunConsolePage } from "./pages/RunConsolePage";
import { WorkflowsPage } from "./pages/WorkflowsPage";
import { WorkflowViewPage } from "./pages/WorkflowViewPage";
import { DesktopSettingsPage } from "./pages/SettingsPage";
import { RecordingsListPage } from "@/pages/RecordingsListPage";
import { RecordingDetailPage } from "@/pages/RecordingDetailPage";
import { AutonomousTaskPage } from "@/pages/AutonomousTaskPage";
import { RunReplayPage } from "@/pages/RunReplayPage";

function AuthenticatedRoutes() {
  return (
    <Routes>
      <Route element={<DesktopShell />}>
        <Route index element={<OverviewPage />} />
        <Route path="runs" element={<RunConsolePage />} />
        <Route path="runs/:runId" element={<RunReplayPage />} />
        <Route path="workflows" element={<WorkflowsPage />} />
        <Route path="workflows/:workflowId" element={<WorkflowViewPage />} />
        <Route path="drafts/:draftId" element={<WorkflowViewPage />} />
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
  const { session, isLoading } = useDesktopAuth();
  if (isLoading) {
    return (
      <div
        className="flex min-h-screen items-center justify-center bg-background p-6 text-center"
        style={{ backgroundColor: "#0a0a0a", color: "#fafafa" }}
      >
        <p className="text-lg font-medium">Loading…</p>
      </div>
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
  return (
    <>
      <RuntimeWarningBanner />
      <Routes>
        <Route path="/login" element={<DesktopLoginPage />} />
        <Route path="/pending" element={<PendingAuthorizationPage />} />
        <Route path="/*" element={<SessionGate />} />
      </Routes>
    </>
  );
}

export function DesktopApp() {
  return (
    <RuntimeStatusProvider>
      <DesktopAuthProvider>
        <DesktopRoutes />
      </DesktopAuthProvider>
    </RuntimeStatusProvider>
  );
}
