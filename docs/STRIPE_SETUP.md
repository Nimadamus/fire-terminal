# Turning on payments

Everything on the code side is built. This is the list of things only you can
do, in the order they need doing. Nothing here takes long; the slow parts are
waiting on Stripe to verify you and waiting on DNS.

Do the whole thing in **Stripe test mode** first. Every step below works the
same way in test mode, and Stripe gives you card numbers that succeed, fail and
require authentication so you can see all three paths before a real card is
involved.

---

## 1. Stripe account

You need one, and it needs to be able to accept subscriptions. Stripe will ask
for a business or individual identity, a bank account and a statement
descriptor.

**Set the statement descriptor to `FIRE`** or something a customer will
recognise on a card statement. An unrecognised descriptor is the single most
common cause of a chargeback, and a chargeback costs you the payment plus a
fee plus the dispute.

## 2. Products and prices

Create **one product** called FIRE, with **two recurring prices**:

| Price | Amount | Interval |
|---|---|---|
| Monthly | $59.00 USD | month |
| Annual | $590.00 USD | year |

Copy the two price ids. They look like `price_1ABC...`. They go in the service
environment as `STRIPE_PRICE_MONTHLY` and `STRIPE_PRICE_ANNUAL`.

Do **not** put a trial on the Stripe price. FIRE grants its own trial before a
customer pays anything, so a Stripe trial would give them a second one.

## 3. The founding member discount

Create a **coupon** for 34% off, forever, then create a **promotion code**
against it, for example `FOUNDING50`, limited to 50 redemptions.

Checkout already has promotion codes enabled, so the field appears on the
payment page with no further work.

Thirty four percent off $59 is $38.94, which rounds to the $39 in the pricing
note. If you would rather show exactly $39.00, create separate fixed prices
instead and hand out a direct payment link.

## 4. The customer portal

Stripe hosts this, and it is what `/account` on the website links to. In the
Stripe dashboard, under Billing, turn on the customer portal and allow:

* updating the payment method
* cancelling the subscription
* viewing invoice history
* switching between the monthly and annual price

Leave "cancel immediately" off and use "cancel at period end". A customer who
cancels has already paid for the current period and should keep it.

## 5. Deploy the licence service

The service is in `server/`. `render.yaml` describes it, including the database.

Before the first deploy, generate the signing key pair:

```
python server/make_keys.py
```

That prints two things. Handle them differently:

* the **private key** goes in the service environment as `FIRE_SIGNING_KEY`
  and nowhere else. Not in the repository, not in a build, not in a chat
  message. Anyone who has it can mint themselves a free subscription.
* the **public key** goes in `src/fire/version.py` as `LICENCE_PUBLIC_KEY`.
  It is safe to publish, and it must ship inside the application.

Then set the rest of the service environment:

| Variable | Value |
|---|---|
| `FIRE_SIGNING_KEY` | the private key from above |
| `STRIPE_SECRET_KEY` | from the Stripe dashboard, `sk_live_...` |
| `STRIPE_WEBHOOK_SECRET` | from step 6 |
| `STRIPE_PRICE_MONTHLY` | from step 2 |
| `STRIPE_PRICE_ANNUAL` | from step 2 |
| `FIRE_SITE_URL` | the website address, no trailing slash |
| `DATABASE_URL` | wired automatically by `render.yaml` |

Check `/health` after deploying. It reports whether the signing key, billing and
webhooks are each configured, without revealing any of them.

## 6. The webhook

In Stripe, add an endpoint pointing at `https://<service>/stripe/webhook` and
subscribe it to exactly these events:

* `checkout.session.completed`
* `customer.subscription.created`
* `customer.subscription.updated`
* `customer.subscription.deleted`
* `invoice.payment_failed`

Copy the signing secret into `STRIPE_WEBHOOK_SECRET`.

The service verifies every webhook signature and refuses anything unsigned, so
until this secret is set no webhook will be accepted, and no licence will ever
be issued.

## 7. Point the application at the service

In `src/fire/version.py`:

```
LICENCE_API_URL = "https://<service>"
LICENCE_PUBLIC_KEY = "<public key from step 5>"
SUPPORT_EMAIL = "<your support address>"
BUILD_CHANNEL = "stable"
```

The release gate refuses to package a stable build with any of those missing, so
this cannot be forgotten.

## 8. Point the website at the service

In `site/config.js`, set `api`, `supportEmail`, `downloadUrl` and `version`.
While `api` is empty the buy buttons say "Coming soon" and cannot be clicked.

---

## Test it before real money touches it

With Stripe in test mode, walk the whole thing:

1. **A successful subscription.** Card `4242 4242 4242 4242`, any future expiry.
   Checkout should redirect to `/welcome`, the key should appear within a few
   seconds, and pasting it into FIRE should turn the buy buttons on.
2. **A card that fails.** Card `4000 0000 0000 0002`. Checkout should refuse and
   no licence should be created.
3. **A card that needs authentication.** Card `4000 0025 0000 3155`. It should
   complete after the challenge.
4. **A renewal.** In the Stripe dashboard, advance the test clock or trigger
   `customer.subscription.updated`. The expiry in FIRE should move forward on
   the next refresh.
5. **A failed renewal.** Trigger `invoice.payment_failed`. FIRE should keep
   working, because Stripe is still retrying the card. Only give up when Stripe
   does.
6. **A cancellation.** Cancel in the portal. FIRE should keep working to the end
   of the period, then stop sending orders and say why.
7. **A duplicate webhook.** Resend the same event from the dashboard. No second
   licence should appear.

Steps 5 and 6 are the ones worth being fussy about. Cutting a paying customer
off over a card that would have succeeded on the second attempt is the worst
thing this system can do.

---

## What is deliberately not built

**We do not email the licence key.** The key appears on the success page the
moment the payment clears, and support can resend it. Adding an email provider
means another account, another set of credentials, another deliverability
problem and another thing that can fail at the exact moment a customer has just
paid you. Worth adding once there are customers; not worth blocking launch on.

**We do not store the customer's name, address or card.** Stripe holds all of
it. The licence database holds an email address, a plan, a status and an expiry.
That keeps the blast radius of a breach here close to nothing.
