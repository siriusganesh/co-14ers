# Supabase setup — step 1

You have to do this part by hand (account creation + project provisioning aren't automatable). Should take ~5 minutes.

## 1. Create the project

1. Go to https://supabase.com and sign in (GitHub login is fine).
2. New project → name it `co-14ers`. Region: `us-west-1` or whatever's closest to Colorado.
3. Generate a strong DB password. Save it in a password manager. You almost certainly won't need it day-to-day, but losing it means resetting via the dashboard.
4. Wait ~2 min for provisioning.

## 2. Run the schema

1. Left sidebar → SQL editor → New query.
2. Open `supabase/schema.sql` from this repo, paste the whole file, run it.
3. Expect "Success. No rows returned." Three tables (`summits`, `routes_climbed`, `planned`) should appear in Table editor with the lock icon (RLS on).

## 3. Auth settings

1. Left sidebar → Authentication → Providers → Email. Make sure these are on:
   - "Enable email provider": on
   - "Confirm email": on (this turns on email verification)
2. Authentication → URL Configuration:
   - Site URL: `https://siriusganesh.github.io/co-14ers/`
   - Redirect URLs (add both):
     - `https://siriusganesh.github.io/co-14ers/`
     - `https://siriusganesh.github.io/co-14ers/reset.html`

## 4. Grab the public keys

1. Project settings (gear icon) → API.
2. Copy:
   - Project URL — looks like `https://xxxxxxxxxxxx.supabase.co`
   - `anon` `public` key — long JWT-looking string. Safe to embed in client code.
3. Do NOT copy or share the `service_role` key. That one bypasses RLS. If you ever paste it into client code, rotate it from the same page.

## 5. Hand them to me

Reply in chat with:

```
SUPABASE_URL=<your project URL>
SUPABASE_ANON_KEY=<your anon key>
```

I'll wire them into `index.html` and ship step 2 (the auth gate + DB hydration).

## Smoke tests you can run before handing off

In the SQL editor, run each of these as the anon role (top-right role switcher in the SQL editor → `anon`). Each should return zero rows:

```sql
select count(*) from public.summits;
select count(*) from public.routes_climbed;
select count(*) from public.planned;
```

If any returns a row, RLS is misconfigured — re-run `schema.sql`.
