# FIRE launch state

**Live staging:** https://fire-terminal.onrender.com (Render `srv-da5mdu6417fc73fvg68g`,
free plan, repo `github.com/Nimadamus/fire-terminal`, branch main, autoDeploy on).
Site, legal pages, waitlist and entitlement all verified live over HTTPS.

**Repo is PUBLIC** so Render could fetch it without a GitHub App grant (2FA blocked
the sign in). Contains no secrets; the release gate fails a build if any appear.
Flip back to private once Render is granted access to the private repo.

**Free plan spins down when idle**, and the first request after that can 404 or hang.
Production must move to `starter` before selling. That is a spend decision.

## Blocked on Nima
1. Create the FIRE Stripe account, save test key to `C:\Users\BL\fire-terminal-stripe-test.txt`
2. Buy `fireterminal.app` (verified available; `fireterm.app`, `firedesk.io` also free)
3. Send the Kalshi authorization message (text in docs/KALSHI_AUTHORIZATION_REQUEST.md)

## Then, automated
- `python server/setup_stripe.py` creates product, prices, FOUNDING50, portal
- `python tests/qa_stripe_journey.py` re-proves purchase to activation to cancellation (27 checks)
- Set `LICENCE_API_URL`, `LICENCE_PUBLIC_KEY`, `SUPPORT_EMAIL` in src/fire/version.py
- Set api/supportEmail/downloadUrl/version in site/config.js
- Map the domain in Render, HTTPS is automatic

## Not started
Code signing (Azure Artifact Signing, $9.99/mo), Postgres for production,
legal review of docs/LEGAL.md.
