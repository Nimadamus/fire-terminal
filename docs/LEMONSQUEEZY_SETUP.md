# Selling through Lemon Squeezy

The fastest route to a first paying customer, because Lemon Squeezy is the
**merchant of record**. They are the party selling to your customer, so they
own the card, the sales tax and the invoice, and they pay you out.

What that removes:

* no dedicated Stripe account
* no business entity
* no tax registration anywhere
* no privacy policy or terms of your own on the checkout

What it costs: roughly 5% plus payment fees, against Stripe's 2.9% plus 30c.
On the first fifty customers that difference is a few dollars a month, and it
buys you weeks.

The code is built and tested. Everything below is account setup.

---

## 1. Create the store

**https://app.lemonsqueezy.com/register**

Store name **FIRE**. You can sell in test mode immediately; payouts need
identity and bank details, which you can add later.

## 2. Create the product and two variants

Product: **FIRE**

| Variant | Price | Billing |
|---|---|---|
| FIRE Monthly | $59 | every month |
| FIRE Annual | $590 | every year |

**Name the variants exactly that.** The service reads monthly or annual out of
the variant name; anything with "annual" or "year" in it becomes FIRE Annual,
anything with "month" becomes FIRE Monthly.

Set the product description from `distribution/LAUNCH_PACKAGE.md`. Do not tick
any "software licence keys" option: FIRE issues its own keys and two systems
issuing keys is one too many.

## 3. Founding member discount

Discounts, new discount: **FOUNDING50**, 34% off, forever, limited to 50
redemptions. Same as the Stripe plan.

## 4. Webhook

Settings, Webhooks, add endpoint:

* URL: `https://<service>/ls/webhook`
* Signing secret: generate one and keep it
* Events: **order_created**, **subscription_created**,
  **subscription_updated**, **subscription_cancelled**,
  **subscription_expired**, **subscription_paused**,
  **subscription_unpaused**, **subscription_resumed**,
  **subscription_payment_success**, **subscription_payment_failed**

Put the signing secret in the service environment as
`LEMONSQUEEZY_SIGNING_SECRET`. Until it is set, the endpoint returns 503 and no
licence can be issued, so nothing half configured can take money.

## 5. Point the site at the checkout

Lemon Squeezy gives each variant a hosted checkout URL. Put them in
`site/config.js`:

```
checkoutMonthly: "https://<store>.lemonsqueezy.com/checkout/buy/<uuid>",
checkoutAnnual:  "https://<store>.lemonsqueezy.com/checkout/buy/<uuid>",
selling: true
```

Set the success URL on each product to `https://<site>/welcome`.

---

## What happens when somebody buys

1. They pay on Lemon Squeezy's hosted checkout. We never see the card.
2. They send `subscription_created`. We verify the signature, mint a licence
   key and store it against the subscription id.
3. The welcome page shows the key; they paste it into FIRE and it activates.
4. Renewals arrive as `subscription_payment_success` and push the expiry out.
5. Cancellation arrives as `subscription_cancelled` and the licence runs to
   `ends_at`, not to the next renewal date. They keep what they paid for.
6. A failed payment does **nothing**. Their dunning retries for days, and
   cutting somebody off over a card that succeeds on the second attempt is the
   worst thing this service can do.

## Testing before real money

Lemon Squeezy has a test mode with test cards. Buy, check the key appears on
the welcome page, activate FIRE, then cancel from their customer portal and
confirm FIRE stops allowing live trading while demo keeps working.

`tests/test_lemonsqueezy.py` already covers the webhook side, including a
forged signature, a duplicate event, a failed payment, past due, and the
cancellation date rule.

## Which one to use

Use Lemon Squeezy to get the first customers with the least setup. Move to
Stripe later if the volume makes the fee difference matter, and keep both:
the licence side does not care which one sent the event.
