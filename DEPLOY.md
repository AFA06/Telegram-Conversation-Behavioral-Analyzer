# Deploying the production (multi-tenant) bot + Mini App

This is the "no local setup, just talk to the bot" version described in
the README's cloud mode. It's the same codebase — `MULTI_TENANT=true`
switches on tenant isolation and Telegram authentication; everything else
(parsing, analysis, dashboard) is identical to the local-first product.

**Recommended stack (free, no credit card required):**

- **[Render](https://render.com)** — hosts the app itself. Free web
  services have no persistent disk and sleep after 15 minutes of
  inactivity, which is why the two points below matter.
- **[Neon](https://neon.tech)** — a free serverless Postgres. Tenant data
  lives here instead of on local disk, isolated per user by Postgres
  *schema* (`tenant_<telegram_user_id>`), so it survives Render's sleep
  cycles and redeploys. Neon auto-suspends when idle and resumes itself on
  the next query — no manual "wake up" step needed.
- **Webhook mode**, not polling — Render can't run a process that's
  asleep, so the bot can't continuously poll Telegram for updates.
  Instead Telegram pushes each update to us via HTTPS POST, which wakes
  the sleeping service like any other incoming request.

If you outgrow the free tiers later (real usage, need it always warm, no
cold-start delay), the same Docker image runs on Railway/Fly/a VPS — just
switch `TENANT_BACKEND` back to `sqlite_file` with a persistent volume, or
keep Postgres and upgrade the Neon plan. Nothing about the migration is a
dead end.

## What you need to do (I can't create these for you)

### 1. Create the bot with @BotFather

Already done if you've been following along — you have `@DialogIQbot` and
its token. If starting fresh: message **@BotFather** → `/newbot`.

### 2. Create a free Postgres on Neon

1. Sign up at [neon.tech](https://neon.tech) (GitHub login works, no card).
2. Create a project (any name/region).
3. Copy the connection string it gives you — it looks like:
   `postgresql://user:password@ep-xxxx.region.aws.neon.tech/dbname?sslmode=require`
4. Turn that into `POSTGRES_URL` below by changing the scheme to
   `postgresql+psycopg2://` (SQLAlchemy needs the driver named explicitly):
   `postgresql+psycopg2://user:password@ep-xxxx.region.aws.neon.tech/dbname?sslmode=require`

### 3. Deploy to Render

1. Sign up at [render.com](https://render.com) (GitHub login, no card).
2. **New** → **Web Service** → connect the
   `AFA06/Telegram-Conversation-Behavioral-Analyzer` repo. Render detects
   the `Dockerfile` automatically.
3. Choose the **Free** instance type.
4. Environment → add these variables:
   ```
   TELEGRAM_BOT_TOKEN=<your bot token>
   MULTI_TENANT=true
   RUN_BOT_IN_PROCESS=true
   TENANT_BACKEND=postgres_schema
   POSTGRES_URL=<the postgresql+psycopg2://... string from Neon>
   TELEGRAM_WEBHOOK_URL=https://<your-service>.onrender.com/telegram/webhook
   TELEGRAM_WEBHOOK_SECRET=<any random string you make up — treat it like a password>
   PUBLIC_WEB_APP_URL=https://<your-service>.onrender.com
   DASHBOARD_ORIGIN=https://<your-service>.onrender.com
   ```
   Render shows your service's `.onrender.com` URL once created — you may
   need to deploy once first to learn it, then come back and fill in the
   two URL-shaped variables above and redeploy.
5. Deploy. Check the logs for `Telegram bot started in-process (webhook: ...)`.
6. Message @BotFather → your bot → **Bot Settings** → **Menu Button** →
   **Configure Menu Button** → paste the same `PUBLIC_WEB_APP_URL`.

### 4. Try it

Message your bot: `/start`, then send it a `result.json` export (or
`/language` first if you want Uzbek). It should reply with an import
summary and an **Open Dashboard** button that opens the full chart
dashboard right inside Telegram.

**About cold starts:** the first message after 15+ minutes of inactivity
will be slow (Render waking the service, ~30-60s) — that's the tradeoff
for free hosting. Once warm, it's fast until it sleeps again.

## How tenant isolation works

- Every Telegram user's imported conversation lives in its own Postgres
  **schema** (`tenant_<telegram_user_id>`) on your shared Neon database —
  nobody can see anyone else's data, enforced at the database level, not
  just in application code.
- The bot already knows the verified Telegram user id of whoever messages
  it (Telegram's own servers guarantee that), so it needs no separate
  login for its own actions.
- The Mini App dashboard authenticates via Telegram's signed `initData`
  (validated server-side against `TELEGRAM_BOT_TOKEN` — see `app/auth.py`),
  so it can only ever read the data belonging to the person who opened it.
- The webhook endpoint (`/telegram/webhook`) verifies Telegram's
  `X-Telegram-Bot-Api-Secret-Token` header against `TELEGRAM_WEBHOOK_SECRET`
  before processing anything, so nobody else can POST fake updates to it.

## Monetization (Telegram Stars) — not enforced yet

The product is free for every user right now; nothing gates any feature.
When you're ready to charge:

1. Decide what's free vs. paid (e.g. free: `/overview`, `/fastest`,
   `/slowest`; paid: full dashboard, `/ask`, exports).
2. Add a `is_premium` / `premium_until` field to `AppConfig` (per tenant).
3. In the bot, use `await context.bot.send_invoice(..., currency="XTR",
   prices=[LabeledPrice("Full access", <amount in Stars>)])`, handle the
   `pre_checkout_query` update (approve it) and `successful_payment`
   (flip `is_premium` on for that tenant).
4. Gate the relevant routes/commands on that flag, with a clear message
   pointing back to `/upgrade`.

This is intentionally not built yet, per "free for now, monetize later."

## Local development is unaffected

Everything above only activates when `MULTI_TENANT=true`. Running this
repo locally (`python -m analyzer server`, `npm run dev`, `python -m
bot.main`) behaves exactly as before — single user, single local SQLite
database, polling mode, no Telegram auth required.
