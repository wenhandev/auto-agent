# 11 · Desktop browser-agent loop

WorkerX may use this loop under [GRANT-WORKERX.md](../../../GRANT-WORKERX.md).

| Idea | Where |
|------|--------|
| Numbered control tree (`0. [button] Submit`) | `backend/app/services/perception.py` — `control_tree()`, `Observation.compact_payload()["tree"]` |
| Set-of-marks on the screenshot the model sees | `perception.py` — `_paint_set_of_marks` / `_clear_set_of_marks` |
| Click / type by **index or ref**, not invented CSS | `click_element(index=…, ref=…)` plus the tree |
| Take control / Give back on the live preview | `livestream.py` (`set_control`, `dispatch_input`, `user_has_control`); `LiveStreamPanel.tsx` |
| Agent write tools pause while the user drives | `autonomous.py` `_execute_tool` |
