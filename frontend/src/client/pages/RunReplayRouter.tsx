import { useParams } from "react-router-dom";
import { RunReplayPage } from "@/pages/RunReplayPage";
import { LocalRunReplayPage } from "./LocalRunReplayPage";

export function RunReplayRouter() {
  const { runId } = useParams<{ runId: string }>();
  if (runId?.startsWith("local_")) {
    return <LocalRunReplayPage />;
  }
  return <RunReplayPage />;
}
