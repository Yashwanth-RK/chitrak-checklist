# Supabase setup

The dashboard syncs checklist progress to Supabase so everyone on the team sees
the same state. **The app still works fully with this unconfigured** — it falls
back to browser-only storage and the status pill reads "Local only".

## How it works

| Concern | Where it lives |
|---|---|
| Rule text, codes, titles (239 items) | The HTML file — immutable, ships with the app |
| Completion, notes, timestamps | Supabase tables |
| Offline copy / instant paint | `localStorage` |

Only the *mutable* state is synced. That keeps the database to ~239 small rows
instead of duplicating the rulebook, and it means wording fixes ship with a file
update rather than a migration.

Writes are debounced (~900 ms) and batched. Only rows whose `updated_at` changed
are sent, so ticking one box pushes one row, not 239. Conflicts resolve
last-write-wins per item. If the network drops, writes queue in an outbox and
flush on reconnect — nothing is lost.

## 1. Create the project

1. Go to <https://supabase.com> → **New project**.
2. Pick a name, set a database password, choose a region near your team.
3. Wait for the project to finish provisioning.

## 2. Create the tables

In the dashboard go to **SQL Editor** → **New query**, paste the **entire
contents** of [`supabase/paste-ready.sql`](supabase/paste-ready.sql), and click
**Run**.

> Paste the file's *contents*, not its path. Pasting `supabase/schema.sql`
> produces `syntax error at or near "supabase"`.

That creates four tables (`rule_state`, `inspection_state`, `team_members`,
`app_meta`), enables row-level security, and adds the policies the app needs.
It is idempotent, so re-running is harmless.

[`supabase/schema.sql`](supabase/schema.sql) is the same thing written out
longhand, with more comments — use it if you prefer to read before running.

You do not need to seed anything — the app uploads state on first save.

## 3. Get your credentials

**Project Settings → API Keys**. Copy two values:

- **Project URL** — looks like `https://abcdefghijklm.supabase.co`
- **Publishable key** — labelled `anon public` on the legacy tab, or
  `sb_publishable_…` on the newer "Publishable and secret" tab. Either works.

> Do **not** use the Secret / `service_role` key. It bypasses row-level
> security and must never be committed or pasted into a client-side file. If it
> ever leaks, regenerate it immediately.

The client sends the key in the `apikey` header and, if the gateway rejects
that, retries with it as a bearer token only — so both the legacy JWT `anon`
key and the newer non-JWT publishable key work without changes.

> The publishable key is designed to be public, so pasting it is fine. Still,
> if this repo ever goes public, remember the anon role can read and write the
> checklist — see "Adding authentication" below.

## 4. Paste them into the dashboard

Open `Chitrak — Rulebook Checklist.html` and find the `SYNC` config near the top
of the `<script>` block:

```js
const SYNC = {
  url: '',        // <- paste your Project URL
  anonKey: '',    // <- paste your anon public key
```

Paste the values, save the file, and reload. The status pill in the top bar
should read **Synced** within a second or two.

## 5. Deploy to Vercel

1. Put the file in a Git repo as `index.html` (Vercel serves a directory root,
   so the filename matters).
2. Import the repo at <https://vercel.com/new>.
3. Framework preset: **Other**. No build command, no output directory.
4. Deploy.

> Deploying changes the origin, so `localStorage` data from `localhost` does not
> carry over. Everyone starts from whatever is already in Supabase. If you want
> to bring local progress across, use **Export JSON** before deploying and
> **Import JSON** after.

## Adding authentication

Out of the box the anon role can read and write, which is fine for a small team
on an unguessable URL but means **anyone with the link can edit your checklist**.

The schema already has RLS enabled, so adding auth is a policy change rather
than a rewrite:

1. Enable Email or Google auth under **Authentication → Providers**.
2. Replace the `anon` policies in `supabase/schema.sql` with `authenticated`
   policies (drop the `anon` ones).
3. In the client, sign in before syncing and send the session token:

```js
const { data } = await sb.auth.signInWithPassword({ email, password });
// then use data.session.access_token as the Bearer token
```

Optionally scope rows to a team by adding a `team_id uuid` column and filtering
every policy on `team_id = auth.uid()`.

## Verifying it works

Open the dashboard in two different browsers (or one normal + one private
window), tick a box in one, and confirm it appears in the other within a couple
of seconds. If it does not, hover the status pill — its tooltip shows the last
pull/push time and the last error.

## Troubleshooting

| Symptom | Cause |
|---|---|
| Pill says **Local only** | `url` or `anonKey` still blank, or the URL is not a valid `http(s)` URL |
| Pill says **Sync error** | Hover for the message. Usually the schema was not run, or the wrong key |
| `401` / `403` errors | Wrong key, or RLS policies missing |
| `404` on `/rest/v1/...` | Table names do not match, so the schema was not applied |
| Progress not appearing for teammates | Both browsers on the same origin, and a pull has run |
| Nothing syncs from `file://` | Some browsers block `fetch` on `file://`. Serve over HTTP (Vercel or `python3 -m http.server`) |

## Local testing without a Supabase account

The sync client is exercised end-to-end by a mock PostgREST server, so you can
validate the integration before creating a project:

```bash
node mock-supabase.js          # serves http://127.0.0.1:54321
# point SYNC.url at that address in the browser console:
#   SYNC.url = 'http://127.0.0.1:54321'; SYNC.anonKey = 'test'; syncInit();
```
