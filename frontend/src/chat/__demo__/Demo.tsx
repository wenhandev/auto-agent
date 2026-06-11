import { useState } from "react";
import { ChatPanel } from "../ChatPanel";
import { setChatTransport, type ChatTransport } from "../api";
import type {
  ChatMessageOut,
  ChatTurnResponse,
  PatchOp,
  Workflow,
  WorkflowNode,
  WorkflowVersionOut,
} from "../../types-platform";

const baseWorkflow: Workflow = {
  nodes: [
    { id: "n1", type: "start", label: "\u8d77\u70b9", params: {} },
    {
      id: "n2",
      type: "navigate",
      label: "\u6253\u5f00 example.com",
      params: { url: "https://example.com" },
    },
    {
      id: "n3",
      type: "extract",
      label: "\u63d0\u53d6\u4e3b\u6807\u9898",
      params: { selector: "h1" },
    },
  ],
  edges: [
    { id: "e1", source: "n1", target: "n2" },
    { id: "e2", source: "n2", target: "n3" },
  ],
  start_id: "n1",
};

const initialHistory: ChatMessageOut[] = [
  {
    id: "msg_1",
    session_id: "sess_demo",
    role: "user",
    content: "\u5728 example.com \u63d0\u53d6\u4e3b\u6807\u9898",
    workflow_version_id: null,
    created_at: "2026-05-15T03:30:00Z",
  },
  {
    id: "msg_2",
    session_id: "sess_demo",
    role: "assistant",
    content:
      "\u5df2\u6784\u5efa\u4e00\u4e2a\u6293\u53d6 example.com \u4e3b\u6807\u9898\u7684\u5de5\u4f5c\u6d41\u3002",
    workflow_version_id: "ver_1",
    created_at: "2026-05-15T03:30:05Z",
  },
];

let turn = 1;
let workflowState: Workflow = { ...baseWorkflow };

const mockTransport: ChatTransport = {
  async fetchHistory() {
    await delay(150);
    return [...initialHistory];
  },
  async sendMessage(_workflowId, content): Promise<ChatTurnResponse> {
    await delay(600);
    turn += 1;

    if (content.includes("fail")) {
      throw new Error("\u540e\u7aef\u6a21\u62df\u9519\u8bef: " + content);
    }

    const newNodeId = `n_demo_${turn}`;
    const newNode: WorkflowNode = {
      id: newNodeId,
      type: "wait",
      label: `${content.slice(0, 14)} \u7b49\u5f85`,
      params: { ms: 1000 },
    };
    const newEdgeId = `e_demo_${turn}`;
    const lastNode = workflowState.nodes[workflowState.nodes.length - 1];
    const patch: PatchOp[] = [
      { op: "add_node", node: newNode },
      {
        op: "add_edge",
        edge: { id: newEdgeId, source: lastNode.id, target: newNodeId },
      },
    ];

    workflowState = {
      ...workflowState,
      nodes: [...workflowState.nodes, newNode],
      edges: [
        ...workflowState.edges,
        { id: newEdgeId, source: lastNode.id, target: newNodeId },
      ],
    };

    const newVersion: WorkflowVersionOut = {
      id: `ver_${turn}`,
      workflow_id: "demo",
      version_index: turn,
      authored_by: "editor",
      workflow: workflowState,
      created_at: new Date().toISOString(),
    };

    return {
      assistant_message: {
        id: `msg_${turn}`,
        session_id: "sess_demo",
        role: "assistant",
        content: `\u597d\u7684\uff0c\u5df2\u52a0\u5165\u300c${newNode.label}\u300d\u3002`,
        workflow_version_id: newVersion.id,
        created_at: new Date().toISOString(),
      },
      patch,
      new_version: newVersion,
    };
  },
};

function delay(ms: number): Promise<void> {
  return new Promise((res) => setTimeout(res, ms));
}

setChatTransport(mockTransport);

export function Demo() {
  const [log, setLog] = useState<string[]>([]);

  return (
    <div style={{ display: "flex", height: "100vh", background: "#0f1115" }}>
      <div
        style={{
          flex: 1,
          padding: 16,
          color: "#e6e8eb",
          fontFamily: "system-ui, sans-serif",
        }}
      >
        <h3 style={{ marginTop: 0 }}>ChatPanel demo (mocked transport)</h3>
        <p style={{ color: "#8a93a3", fontSize: 13 }}>
          Send any prompt; include the word "fail" to simulate a transport error.
        </p>
        <h4>onWorkflowUpdated log</h4>
        <ol style={{ fontFamily: "monospace", fontSize: 12, color: "#c8cdd6" }}>
          {log.map((l, i) => (
            <li key={i}>{l}</li>
          ))}
        </ol>
      </div>
      <div style={{ width: 420, height: "100vh" }}>
        <ChatPanel
          workflowId="demo"
          onWorkflowUpdated={(v) =>
            setLog((prev) => [
              ...prev,
              `v${v.version_index} ${v.id} nodes=${v.workflow.nodes.length}`,
            ])
          }
        />
      </div>
    </div>
  );
}
