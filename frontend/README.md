# auto-agent — frontend

Vite + React 19 + TypeScript + `@xyflow/react` + `dagre` + `zustand`.

Renders the `Workflow` JSON as a glowing top-to-bottom flowchart and consumes
the `/ws/run` event stream to drive per-node status (idle / running / success /
error) and progress subtitles.

## First-time setup

```powershell
cd frontend
npm install
```

## Run dev server

```powershell
npm run dev
```

Opens on <http://localhost:5173> by default (Vite will auto-pick 5174/5175 if
something else is bound). The dev server proxies `/api/*` and `/ws/*` to
`http://localhost:8000`, so make sure the backend is running there first.

## Type-check / production build

```powershell
npm run build       # tsc -b && vite build
```

Both must finish with zero errors.

## Key files

- `src/App.tsx` — top-level layout, run button, sample-workflow bootstrap.
- `src/store.ts` — zustand store; `applyEvent` converts WS events into node state.
- `src/ws.ts` — opens `/ws/run`, sends the start frame, dispatches frames to the store.
- `src/api.ts` — `getSampleWorkflow()` and `generateWorkflow(description)`.
- `src/components/GlowNode.tsx` + `GlowNode.css` — per-node glow card.
- `src/components/WorkflowCanvas.tsx` — ReactFlow canvas + dagre auto-layout.
- `src/components/NLInput.tsx` — NL description box + 「生成工作流」/「加载示例」 buttons.
- `src/components/RunLog.tsx` — live event log sidebar.
