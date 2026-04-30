# Auth + sync design

Adding accounts so each climber sees their own summited peaks, summit dates, route checkmarks, and planned trips. Site stays on GitHub Pages, no backend to operate, free for ~20 users.

## Requirements

Functional: email + password signup with verification; login; password reset; per-user storage of summited peaks (with date), route-level checkmarks, planned-trip peaks; fully private — no user sees another's data.

Non-functional: ~20 users, low write volume, must be free end-to-end, no build step required, single-developer maintainability.

Constraints: site is static on GitHub Pages, can't run a server. JS competent, Python rusty.

## High-level design

```
                    +---------------------------+
                    |  GitHub Pages (static)    |
                    |  index.html / reset.html  |
                    |  + supabase-js (esm.sh)   |
                    +-------------+-------------+
                                  |
                       JWT-authed HTTPS (anon key + RLS)
                                  |
       +--------------------------+--------------------------+
       |                          |                          |
+------v------+          +--------v--------+         +-------v-------+
| Supabase    |          |  Supabase       |         |  Supabase     |
| Auth        |          |  Postgres + RLS |         |  Email (SMTP) |
| (managed)   |          |  (managed)      |         |  (managed)    |
+-------------+          +-----------------+         +---------------+
```

The browser holds the JWT (stored in localStorage by the supabase-js SDK). Every read and write is a direct call from the browser to Supabase. The anon key shipped in the HTML is fine — Postgres Row Level Security is what actually enforces "fully private." The anon key without a valid session JWT can do nothing on the user tables.

## Data model

Three tables, all keyed by `auth.users.id`. Peak and route identifiers are reused from the existing dataset (`peak_id`, `route_key`) so client code maps cleanly to what's already in `peaks.json`.

```sql
create table summits (
  user_id     uuid not null references auth.users on delete cascade,
  peak_id     text not null,
  summit_date date,                       -- null = "I've done it, no date logged"
  notes       text,
  created_at  timestamptz default now(),
  primary key (user_id, peak_id)
);

create table routes_climbed (
  user_id      uuid not null references auth.users on delete cascade,
  route_key    text not null,             -- matches routes csv route_key, e.g. 'lapl1'
  peak_id      text not null,             -- denormalized for "by-peak" queries
  climbed_date date,
  notes        text,
  created_at   timestamptz default now(),
  primary key (user_id, route_key)
);

create table planned (
  user_id     uuid not null references auth.users on delete cascade,
  peak_id     text not null,
  target_date date,
  notes       text,
  created_at  timestamptz default now(),
  primary key (user_id, peak_id)
);
```

Row Level Security — one policy per table per operation, all of the same shape:

```sql
alter table summits enable row level security;
alter table routes_climbed enable row level security;
alter table planned enable row level security;

create policy "own rows select" on summits for select using (auth.uid() = user_id);
create policy "own rows write"  on summits for all    using (auth.uid() = user_id) with check (auth.uid() = user_id);
-- repeat the two policies on routes_climbed and planned
```

Two policies per table (select + all) is the smallest cover for read + insert/update/delete with the same predicate. No anonymous read policy, so an unauthenticated request returns zero rows — that's the "fully private" guarantee.

## API surface

No custom backend; the supabase-js SDK is the API. Each UI action maps to one call:

| Action | Call |
|---|---|
| Sign up | `auth.signUp({ email, password })` |
| Verify email | (handled by Supabase via emailed link → returns to site) |
| Log in | `auth.signInWithPassword({ email, password })` |
| Log out | `auth.signOut()` |
| Forgot password | `auth.resetPasswordForEmail(email, { redirectTo: '<site>/reset.html' })` |
| Set new password | `auth.updateUser({ password })` (on reset.html) |
| Mark peak summited | `from('summits').upsert({ peak_id, summit_date })` |
| Unmark peak | `from('summits').delete().eq('peak_id', id)` |
| List my summits | `from('summits').select('*')` (RLS scopes it) |
| Mark route climbed | `from('routes_climbed').upsert({ route_key, peak_id, climbed_date })` |
| Add to planned | `from('planned').upsert({ peak_id, target_date })` |
| Remove from planned | `from('planned').delete().eq('peak_id', id)` |

## Auth flows

Signup → verify → in:
1. User submits email + password.
2. `signUp` returns success, no session yet.
3. App shows "check your email."
4. User clicks the verification link → Supabase confirms, redirects to `index.html`.
5. App calls `auth.getSession()`, finds an active session, switches into the authed state.

Login: `signInWithPassword` returns a session immediately; UI flips to authed.

Forgot password:
1. User clicks "forgot password," enters email.
2. `resetPasswordForEmail` sends an email with a recovery link pointing at `reset.html`.
3. `reset.html` reads the recovery token from the URL hash, the SDK exchanges it for a temporary session, the page shows a "new password" form, calls `auth.updateUser({ password })`, then redirects back to `index.html`.

Disabling email verification is a one-flag toggle in the Supabase dashboard if friction outweighs the security benefit at this scale (~20 known users). Recommend leaving it on.

## Client architecture

Two pages instead of one:
- `index.html` — main app. Adds an auth gate: a small login/signup card that replaces the peak table while unauthed. Once authed, the existing peak browser renders, but the summited / planned / route-climbed state comes from Supabase instead of localStorage.
- `reset.html` — small standalone page that handles the password recovery token and posts a new password.

State machine inside `index.html`:
```
       boot
        │
        ▼
   getSession()
        │
   ┌────┴────┐
   │         │
 session?   no session
   │         │
   ▼         ▼
 authed    unauth (show login/signup)
   │
   │  (on login event)
   │  ──► hydrate from DB
   │      ├─ summits      → Set<peak_id> + Map<peak_id, date>
   │      ├─ routes_climbed → Map<route_key, date>
   │      └─ planned      → Set<peak_id>
   ▼
 render peak table with merged state
```

Library load: `import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'` inside an `<script type="module">` block. No bundler, no build step.

## Migration of existing localStorage

Anyone who's already used the site has summit data under `co14ers.summited.v1`. On first successful login, if the user's `summits` table is empty and that key exists, batch-insert each `peak_id` with `summit_date = null`, then write `co14ers.migrated_at` so it doesn't re-run. Don't delete the localStorage payload — keep it as a fallback if Supabase is unreachable.

## Offline / failure behavior

Supabase down: SDK calls reject. App keeps the last hydrated state in memory; new toggles queue in `localStorage` under `co14ers.pendingOps` and replay once a write succeeds. With ~20 users this is overkill but cheap.

Email delivery fails: user sees a "didn't get the email?" link that calls `auth.resend({ type: 'signup' })`.

Forgot password without email access: you (admin) can trigger a recovery from the Supabase dashboard — the most likely path for ~20 friends.

## Scale and reliability

At ~20 users:
- Supabase free tier (50K MAU, 500MB DB, 5GB egress) leaves at least 3 orders of magnitude of headroom.
- Total expected rows: 20 users × ~150 rows worst-case = 3,000 rows.
- No caching layer, no queue, no read replicas.

Monitoring is the Supabase dashboard plus its built-in auth event log. Sufficient for this size.

## Trade-offs

Anon key + RLS in the client. Free, simple, no server. The risk surface is RLS misconfiguration — a missing or broad policy leaks rows. Mitigation: explicit policies per operation, a smoke test that confirms a logged-out client returns zero rows from each table, and a second test user that confirms user A can't read user B's rows.

Static SPA + managed BaaS. No ops burden, but the system inherits Supabase's uptime and free-tier pricing terms. If they tighten the free tier, you migrate the data (it's small) to Pocketbase on a $5 box.

Email/password instead of magic-link. User asked for it. Magic-link would have eliminated the password reset flow entirely and given equivalent security at this scale; flagging this as a future swap that costs ~30 LOC.

Inline migration of localStorage. Best-effort. If the upsert partially fails, leave the localStorage entry intact so a re-login retries. Don't delete until the user has been authed-and-synced for a session.

Email verification on. ~30 seconds of friction on signup, prevents typo accounts and gives a real recovery channel. Worth it.

## What I'd revisit as it grows

- 200+ users or public signup: add captcha on signup, rate limit on `auth.*` via Supabase project settings, add a `profiles` table for display names.
- Photos: Supabase Storage with a per-user bucket policy. Watch the 1GB free quota.
- Real-time leaderboard or shared trips: drop "fully private" — needs a `visibility` column on summits and a public-read policy filtered on it.
- Mobile / offline-first: replace `localStorage` with IndexedDB and do proper sync (Last-Write-Wins by `created_at` is fine for this data shape).

## Implementation order (small, ship-each-step)

1. Create Supabase project, paste the SQL above, enable email auth, set the site URL.
2. Add `reset.html`, wire login/signup card into `index.html` behind a feature flag.
3. Hydrate from `summits` table; flip the existing checkbox handler to call `upsert` / `delete`.
4. Add `routes_climbed` UI (route-row checkbox in the detail panel) and `planned` UI (a "plan it" button on each peak).
5. Migration: on first authed render, copy localStorage → DB if DB is empty.
6. Smoke test with two accounts; verify cross-user isolation.
