## 1. Credential kinds

- [x] 1.1 Add `totp` field schema `{secret, digits?, period?, algorithm?}` to the credential layer
- [x] 1.2 Add `credit_card` field schema `{number, exp_month, exp_year, cvc, holder_name?, zip?}`
- [x] 1.3 Extend the masker: TOTP secret fully masked; card number last-4; cvc fully masked
- [x] 1.4 Ensure read endpoints never return TOTP secret / full card number

## 2. TOTP service

- [x] 2.1 Create `app/services/totp.py` (RFC 6238 via stdlib `hmac`/`hashlib`/`struct`/`base64`)
- [x] 2.2 `current_code(credential_name)` honouring digits/period/algorithm
- [x] 2.3 Unit test against RFC 6238 reference vectors

## 3. Interpolation

- [x] 3.1 Add `{{totp.<name>}}` token to the chained resolver
- [x] 3.2 Add `{{card.<name>.<field>}}` token to the chained resolver
- [x] 3.3 Apply per-workflow link enforcement to both token families
- [x] 3.4 Tests: resolution, unlinked rejection, masking in traces/events

## 4. Run option

- [x] 4.1 `POST /api/runs` accepts optional `totp_identifier`
- [x] 4.2 Expose a `get_totp()` tool to the vision agent gated on a configured identifier

## 5. Frontend

- [ ] 5.1 Typed `totp` create form with "validate now" (shows current code)
- [ ] 5.2 Typed `credit_card` create form (masked) with the "local POC, not PCI" caveat
- [ ] 5.3 Masked displays on the credentials list/detail
