# FX Trading Frontend Integration Guide

Use this as the contract between the React/Vue client and the Django backend. All authenticated calls expect `Authorization: Bearer <access_token>` in headers (SimpleJWT). CORS is limited to `http://localhost:5173`/`127.0.0.1:5173`; add new origins via `core/settings.py`.

## Auth + Identity
- `POST /api/auth/login/` → `{identifier|email|username, password}`. Fails with `KYC_PENDING`/`KYC_REJECTED` until KYC approved. Returns `access` + `refresh`.
- `POST /api/auth/refresh/` → `{refresh}` to rotate tokens (rotation + blacklist enabled).
- `POST /api/auth/logout/` → `{refresh}` to blacklist refresh token.
- `POST /api/auth/register/` → `{username, email, password}` (no auto-login). Creates user + empty KYC row.
- Profile: `GET/PATCH /api/me/` → `{id, username, email, first_name, last_name, full_name, kyc_status, aadhaar_last4, profile.avatar_url}`. PATCH only supports `first_name`, `last_name`.
- Password change: `POST /api/me/change_password/` → `{old_password, new_password}`.

## KYC
- `POST /api/kyc/submit/` (auth, multipart) → `{aadhaar_number (12 digits), doc_front, doc_back}`. Validates file type (jpeg/png/heic/heif, ≤5MB). Sets status to `pending`.
- `GET /api/kyc/status/` (auth) → `{status, submitted_at, reviewed_at, aadhaar_last4}`.
- `POST /api/kyc/submit_public/` (no auth, multipart) → `{email, aadhaar_number, doc_front, doc_back}` to tie docs to an existing email before login.

## Market Data & Trading
- `GET /health` → `{status:"ok"}` for uptime checks.
- `GET /api/candles?symbol=EURUSD&interval=1m&limit=200` → OHLCV array. Intervals map: `1m,5m,15m,30m,1h,4h,1d`.
- `GET /api/symbols` → symbol catalog keyed by code with `display, precision, pip, contract_size, min_lot, lot_step, max_lot, leverage_max`.
- `GET /api/positions/snapshot` (auth) → list of Redis live positions `{id, symbol, net_lots, side, open_price, mark, unreal_pnl, margin, open_time, ts}`.
- `POST /api/margin/check` (auth) → `{symbol, lots, price, leverage?}`. Returns `{ok, margin_required}` or `{ok:false, error}` using server margin math.
- `POST /api/sim/fill` (auth, dev helper) → `{symbol, side:"Buy"|"Sell", lots, price, leverage?}`. Applies fill, updates Redis, records order/fill, and broadcasts WS update.
- `POST /api/positions/close` (auth) → `{symbol, lots?}` closes up to `lots` (defaults to full) using latest mark from Redis.
- `POST /api/exit_position/` (auth) → `{position_id, exit_price}` force-closes a specific Redis position id at provided price.
- `GET /api/orders` (auth) → list of user orders (optional `?symbol=`). Fields mirror `Order` model including `position_id`.
- `GET /api/fills` (auth) → list of user fills (optional `?symbol=`).
- `GET /api/orderhistory/` (auth) → realized PnL grouped by position `{pos_id, symbol, realized, last_ts}`.
- `GET /api/capital/` (auth) → `{balance, equity, used_margin, free_margin}` from `UserAccount`.

## Payments & Withdrawals
- `GET /api/deposit/crypto-methods/` (auth) → available chains `{name, network, address, min_amount, max_amount, status, qr_url}`. Optional `?online=true` filters by status.
- `POST /api/deposit/upi/request/` (auth) → `{amount, payer_vpa, note?}`. Creates request + Telegram alert. Min amount ₹10.
- `GET /api/deposit/upi/requests/` (auth) → paginated list of the user’s UPI requests.
- Withdrawals (router): `POST /api/withdrawals/` → `{amount}` (must be ≤ available balance). `GET /api/withdrawals/` lists own requests; `GET /api/withdrawals/{id}/` fetches one. Admin-side approval handled elsewhere.

## Admin Trades Feed
- `GET /api/admin_trades/` (auth) → closed broadcast trades for groups the user belongs to. Fields: `ref, symbol, side, lots, leverage, entry_price, exit_price, status, opened_at, closed_at, notes`.

## WebSockets
- Public quotes: `ws/quotes/<symbol>/` (unauthenticated). Messages: initial `{type:"status", message}` then `{type:"tick", symbol, ts, bid, ask, last}`. Server normalizes zero-spread mid when possible.
- User stream: `ws/user/stream/` (JWT via `Authorization: Bearer ...` header in the WS handshake). On connect sends `{type:"positions_snapshot", data:[...]}`. Ongoing messages: `positions_update` (per-symbol mark/unreal/margin), `margin_alert`, and optional `capital_update`.
- Capital stream: `ws/user/capital/` (JWT) → initial `{type:"capital", balance, equity, used_margin, free_margin}` then `capital` updates.

## Integration Notes
- Default base URL: `http://localhost:8000/`; static served at `/static/`, media at `/media/` when `DEBUG=True`.
- Symbol list (contracts.py) currently: `EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, BTCUSDT, XAUUSD, XAGUSD, NZDUSD`; leverage_max typically 500.
- Orders/positions logic is netting-based; `net_lots` sign determines `side` (`Buy` >0, `Sell` <0). Closing uses latest mark in Redis unless `exit_price` supplied.
- JWT + KYC: login blocked until KYC approved; surface backend `code`/`message` to users.
- Redis URL configurable via `REDIS_URL`; Alltick price feeds configured via `ALLTICK_*` envs. Zero spread toggle `ZERO_SPREAD` (default true) affects displayed bid/ask.
