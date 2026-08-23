# Launch readiness

Everything in this file is current as of the last commit. `LAUNCH_CHECKLIST.md`
has the full item by item detail; this is the short version and the order of
operations.

## The shortest path to a first paying customer

Eight steps. Steps 1 and 2 can run at the same time as everything else, and
step 1 is the only one with an unknown answer.

1. **Send the Kalshi authorization request.** `docs/KALSHI_AUTHORIZATION_REQUEST.md`,
   in the in app support messenger. Everything else can be finished while it
   sits with them, but nothing can be sold until it comes back.
2. **Buy a domain and point it at Cloudflare Pages.** The website in `site/` is
   ready to deploy as it stands.
3. **Set up Stripe.** `docs/STRIPE_SETUP.md` is the checklist. Test mode first,
   then live. About an hour of clicking.
4. **Deploy the licence service.** `server/`, using `render.yaml`. Generate the
   signing key pair first with `python server/make_keys.py`.
5. **Fill in four constants.** `LICENCE_API_URL`, `LICENCE_PUBLIC_KEY`,
   `SUPPORT_EMAIL` and `BUILD_CHANNEL` in `src/fire/version.py`, and the four
   fields in `site/config.js`. The release gate refuses a stable build with any
   of them missing.
6. **Sign up for Azure Artifact Signing** at $9.99 a month and set the three
   signing variables. `docs/CODE_SIGNING.md` explains why not EV. Identity
   validation is the slow part, so start it early.
7. **Build and publish.** `powershell -File packaging\build.ps1`, upload the
   installer to GitHub Releases, generate `updates.json` with
   `packaging/make_feed.py`, put it on the website.
8. **Walk the seven payment paths in Stripe test mode** before switching to
   live keys. The list is at the end of `docs/STRIPE_SETUP.md`.

## What is genuinely blocking

| Blocker | Who | Why it blocks |
|---|---|---|
| Kalshi authorization | Them | Selling software other members trade through is the thing section 3 restricts. Everything else is ready to go the day this comes back. |
| Legal review of six documents | An attorney | We wrote them. We are not lawyers, and one clause in the licence agreement is still a placeholder. |

## What is not blocking, whatever it looks like

**Code signing.** Customers can install unsigned. It costs conversions, not
sales, and it can be fixed after launch without a rebuild of anything but the
installer.

**A business entity.** Stripe onboards individuals. The governing law clause in
the licence agreement stays incomplete until there is one, which is a reason to
do it soon rather than a reason to wait.

**Emailing the licence key.** The key is on the success page the instant the
payment clears, and support can resend it. An email provider is another account,
another credential and another thing that fails at the worst moment.
