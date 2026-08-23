# Deployment runbook

One service, on Render, serving both the website and the licence API. One
thing to deploy, one domain, no CORS, and no second hosting account that can
expire out from under us. Cloudflare is not involved and is not needed.

## What gets deployed

| | |
|---|---|
| Service | `fire-licence`, a Python web service |
| Serves | the website at `/`, the API at `/activate`, `/entitlement`, `/licence`, `/portal`, `/waitlist`, `/stripe/webhook` |
| Database | Render Postgres, `fire-licences` |
| Health check | `GET /health` |
| Blueprint | `server/render.yaml` |
| Container fallback | `server/Dockerfile`, so any host that runs a container will do |

## The minimum GitHub access, and why

Render pulls from a Git repository. That is the only reason GitHub is
involved, so the access should be as narrow as that job.

**Use a fine grained token, not a classic one.** A classic token with the
`repo` scope can read and write every repository on the account, which is far
more than pushing one project needs.

Create it at **https://github.com/settings/personal-access-tokens/new**:

* Repository access: **Only select repositories** → `fire-terminal`
* Permissions → Repository permissions → **Contents: Read and write**
* Nothing else. No account permissions, no organisation permissions.

That token can push code to one repository and can do nothing else, on
anything else, ever.

**Render's own connection is separate and narrower still.** In the Render
dashboard, connecting GitHub installs the Render GitHub App. When it asks
which repositories, choose **Only select repositories** and pick
`fire-terminal`. Render never sees the token above, and the app cannot reach
any other repository.

If you would rather issue no token at all: make the repository public and
Render can pull it with no credential whatsoever. The repository contains no
secrets by design, and the release gate fails the build if any ever appear.
That is a real option, not a fallback, but it also publishes the source, so it
is your call.

## First deploy

1. **Create the repository** and push:

   ```
   git remote add origin https://github.com/<you>/fire-terminal.git
   git push -u origin main
   ```

2. **Generate the signing key pair**, once, ever:

   ```
   python server/make_keys.py
   ```

   The **private** key goes into the Render environment as `FIRE_SIGNING_KEY`
   and nowhere else. The **public** key goes into `src/fire/version.py` as
   `LICENCE_PUBLIC_KEY` and ships inside the application.

3. **Create the service.** In Render, New → Blueprint, point it at the
   repository. `server/render.yaml` creates the web service and the database
   together.

4. **Set the environment** (below), then deploy.

5. **Check `/health`.** It reports whether the signing key, billing, webhooks
   and the site are each present, without revealing any of them.

## Environment

| Variable | Value | Secret |
|---|---|---|
| `FIRE_SIGNING_KEY` | private key from `make_keys.py` | **yes, treat as a payment credential** |
| `STRIPE_SECRET_KEY` | `sk_live_...` or `sk_test_...` | **yes** |
| `STRIPE_WEBHOOK_SECRET` | `whsec_...` from the Stripe webhook | **yes** |
| `STRIPE_PRICE_MONTHLY` | `price_...` | no |
| `STRIPE_PRICE_ANNUAL` | `price_...` | no |
| `FIRE_SITE_URL` | `https://<domain>`, no trailing slash | no |
| `FIRE_SITE_DIR` | `../site` | no |
| `PYTHONPATH` | `../src` | no |
| `DATABASE_URL` | wired by the blueprint | **yes** |
| `FIRE_TRIAL_DAYS` | `14` (default) | no |
| `FIRE_GRACE_DAYS` | `7` (default) | no |

Anyone holding `FIRE_SIGNING_KEY` can mint themselves a subscription. If it
ever leaks: generate a new pair, set the new private key, ship a build carrying
the new public key, and every old token stops verifying at once.

## Domain and HTTPS

1. Render dashboard → the service → **Settings → Custom Domains → Add**.
   Add both `fireterminal.app` and `www.fireterminal.app`.
2. Render shows the DNS records to create. At the registrar:
   * apex domain → **ALIAS** or **ANAME** to the Render target, or the A record
     Render gives you if the registrar has no ALIAS support
   * `www` → **CNAME** to the Render target
3. Render issues and renews the TLS certificate automatically once DNS
   resolves. There is nothing to buy and nothing to renew.
4. Set `FIRE_SITE_URL` to the final `https://` address, because Stripe redirects
   back to it after checkout.

Propagation is usually minutes. Until it finishes, Render shows the domain as
pending and serves the `onrender.com` address, which works for testing.

## Logging

Render keeps the service log and it is visible in the dashboard under Logs.

What is logged: which Stripe event arrived, that a licence was issued for a
checkout session, activation of a non active licence, and failures to reach
Stripe. What is never logged: a signing key, a Stripe key, an API key, a
licence key in full, or a customer's card details, none of which this service
ever holds.

For anything longer than Render's retention, add a log drain in the dashboard.
Not needed on day one.

## Backup and recovery

**What is irreplaceable:** `FIRE_SIGNING_KEY` and the database. Everything else
can be rebuilt from the repository in minutes.

**The signing key.** Keep one copy in a password manager. It is not in the
repository and not in any build, so if Render lost it and you had no copy,
every existing customer's licence would stop verifying and all of them would
need a new key.

**The database.** Render Postgres takes daily backups on a paid plan. Enable
point in time recovery in the database settings. Verify a restore once, before
you have customers, because an untested backup is a hope rather than a backup.

**If the database were lost entirely**, licences could be rebuilt from Stripe:
every one carries its `checkout_session` and `stripe_sub`, and Stripe holds the
authoritative list of who is paying. Customers would need new keys. Painful,
survivable, and a reason to test the restore.

**If Render were lost entirely**, `server/Dockerfile` runs the same service on
any container host. Point DNS at the new one and set the same environment. The
only thing that must come with you is the signing key.

## Rolling back

Render keeps previous deploys. Dashboard → the service → Deploys → **Rollback**
on the last good one. The database is unaffected, so a rollback is safe unless
a migration ran, and there are no migrations yet.

## Deploying an update

Push to `main`. Render builds and deploys, and holds traffic on the old
instance until `/health` answers on the new one. If the health check never
passes, the old instance keeps serving.
