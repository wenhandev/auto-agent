## 1. Schema

- [x] 1.1 Add `login` to the `NodeType` literal
- [x] 1.2 Add `LoginParams` `{credential, url?, success_criteria?, totp_identifier?}`

## 2. Login handler

- [x] 2.1 Build a login-specialised vision sub-flow prompt
- [x] 2.2 Implement `fill_credential(index, field)` tool that types real secrets server-side (masked in context)
- [x] 2.3 Integrate the TOTP service for the 2FA step, with one fresh-code retry on rejection
- [x] 2.4 Success verification: explicit `success_criteria` or the default no-password-field heuristic
- [x] 2.5 Profile short-circuit when already authenticated
- [x] 2.6 Output `{logged_in, method, steps, final_url}`

## 3. Executor & events

- [x] 3.1 Route `login` in the executor dispatch
- [x] 3.2 Emit `login_started` / `login_completed` / `login_failed` (masked); add to event literal
- [x] 3.3 Enforce per-workflow credential link

## 4. Prompts

- [x] 4.1 Planner + editor prompts document `login` and prefer it over hand-rolled login sequences

## 5. Frontend

- [ ] 5.1 NodeInspector login form (linked-credential picker, url, success criteria, totp identifier)
- [ ] 5.2 RunLog padlock row with login outcome

## 6. Tests

- [x] 6.1 Successful login against a fixture form
- [x] 6.2 Secret never appears in model context / traces
- [x] 6.3 Unlinked-credential rejection
- [x] 6.4 Profile short-circuit path
