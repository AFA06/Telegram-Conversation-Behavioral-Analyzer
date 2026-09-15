# Deploying the production (multi-tenant) bot + Mini App

This is the "no local setup, just talk to the bot" version described in
the README's cloud mode. It's the same codebase — `MULTI_TENANT=true`
switches on tenant isolation and Telegram authentication; everything else
(parsing, analysis, dashboard) is identical to the local-first product.

## What you need to do (I can't create these for you)

### 1. Create the bot with @BotFather

1. Open Telegram, message **@BotFather**.
2. `/newbot` → choose a name and a `@username` ending in `bot`.
3. Save the token it gives you (looks like `123456:ABC-DEF...`) — this is
   `TELEGRAM_BOT_TOKEN` below. Treat it like a password.
4. `/mybots` → your bot → **Bot Settings** → **Menu Button** → **Configure
   Menu Button** → paste your deployed app's URL (you'll have this after
   step 2 below; come back and set this once you know it) and a label like
   "Open Dashboard". This registers the domain for Mini Apps.

### 2. Deploy to Railway

1. Create an account at [railway.app](https://railway.app) and connect
   your GitHub account.
2. **New Project** → **Deploy from GitHub repo** → pick
   `AFA06/Telegram-Conversation-Behavioral-Analyzer`. Railway detects the
   `Dockerfile` at the repo root automatically (`railway.toml` is already
   configured for it).
3. **Add a Volume**: Service → Settings → Volumes → New Volume → mount
   path `/app/data`. This is where every tenant's imported conversation
   lives — without this, all data is lost on every redeploy.
4. Service → Variables → add:
   ```
   TELEGRAM_BOT_TOKEN=<the token from BotFather>
   MULTI_TENANT=true
   RUN_BOT_IN_PROCESS=true
   PUBLIC_WEB_APP_URL=https://<your-service>.up.railway.app
   DASHBOARD_ORIGIN=https://<your-service>.up.railway.app
   ```
   (Railway shows your service's public domain under Settings → Networking
   once you generate one — click **Generate Domain** if you don't have one
   yet, then fill that exact URL into the two variables above.)
5. Deploy. Check the logs for `Telegram bot started in-process (polling)`
   and `Application startup complete`.
6. Go back to BotFather (step 1.4) and set the Menu Button URL to the same
   `PUBLIC_WEB_APP_URL`.

### 3. Try it

Message your bot: `/start`, then send it a `result.json` export. It
should reply with an import summary and an **Open Dashboard** button that
opens the full chart dashboard right inside Telegram.

## How tenant isolation works

- Every Telegram user's imported conversation lives in its own SQLite file
  under `/app/data/tenants/<telegram_user_id>.db` — nobody can see anyone
  else's data.
- The bot already knows the verified Telegram user id of whoever messages
  it (Telegram's own servers guarantee that), so it needs no separate
  login for its own actions.
- The Mini App dashboard authenticates via Telegram's signed `initData`
  (validated server-side against `TELEGRAM_BOT_TOKEN` — see `app/auth.py`),
  so it can only ever read the data belonging to the person who opened it.

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
repo locally (`python -m analyzer server`, `npm run dev`) behaves exactly
as before — single user, single local database, no Telegram auth required.
