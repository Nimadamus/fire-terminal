# FIRE customer facing documents

Working drafts. **These have not been reviewed by a lawyer.** Do not publish
or ship them until they have been. They exist so the shape is settled and the
review is cheap, not so we can skip the review.

Covers launch checklist G1 to G4 and E3.

Six documents: risk disclosure, licence agreement, privacy policy, refunds
and cancellation, terms of service, and the independence statement.

---

## 1. Risk disclosure (shown during setup, before live trading is enabled)

**FIRE is a tool, not advice.**

FIRE displays market data and sends the orders you click. It does not tell you
what to trade, when to trade, or whether any trade is a good idea. Every order
comes from a deliberate action you take.

**You can lose money.** Event contracts settle at either their full value or
at nothing. If a contract you hold settles against you, you lose everything
you paid for it. There is no partial recovery and no stop loss that can
prevent it, because settlement is a single instant.

**Speed does not mean safety.** FIRE is built to place orders quickly. That
makes it easier to act on a decision, and equally easier to act on a bad one.

**Software fails.** Your internet connection can drop, your computer can
sleep, the exchange can become unreachable, and FIRE itself can contain bugs.
An order you believe was sent may not have been sent, and an order you believe
failed may have filled. Always confirm your true position with your exchange
account, which is the only authoritative record.

**The maximum loss limit is a convenience, not a guarantee.** It checks the
worst case cost of a single order before that order is sent. It does not
limit your total exposure across several orders, it cannot cancel an order
that has already filled, and it does nothing if you turn it off.

**Only risk money you can afford to lose entirely.**

---

## 2. Licence agreement (EULA)

**1. What you are buying.** A personal, non exclusive, non transferable
licence to install and use FIRE on computers you control, for as long as your
subscription is active. You are buying access to software, not a service that
trades for you and not any promise about results.

**2. What you may not do.** Resell, sublicense, rent or redistribute FIRE.
Reverse engineer, decompile or attempt to derive its source, except where that
right cannot lawfully be excluded. Remove or obscure any notice in it. Use it
to break the rules of any exchange or any law that applies to you.

**3. Your exchange account is yours.** FIRE connects to your exchange using
credentials you supply. You remain solely responsible for that account, for
complying with your exchange's own terms, and for every order placed from it,
whether placed through FIRE or otherwise. We are not a broker, we are not your
agent, we take no custody of your funds, and we have no access to your
account.

**4. No warranty.** FIRE is provided "as is" and "as available", without
warranty of any kind, express or implied, including merchantability, fitness
for a particular purpose, accuracy, and non infringement. We do not warrant
that FIRE will be uninterrupted, error free, or that any data it displays is
accurate, complete or timely.

**5. Limitation of liability.** To the maximum extent permitted by law, we are
not liable for any trading losses, lost profits, lost opportunity, missed or
duplicated orders, incorrect or delayed market data, or any indirect,
incidental, special or consequential damages, arising from your use of or
inability to use FIRE. **Our total aggregate liability to you for any claim is
limited to the amount you paid us in the twelve months before the claim
arose.** Nothing here excludes liability that cannot lawfully be excluded.

**6. Assumption of risk.** You acknowledge that trading event contracts can
result in the total loss of the amount risked, that you have read the risk
disclosure, and that you make your own trading decisions.

**7. Termination.** You may stop using FIRE at any time. We may terminate this
licence if you materially breach it. On termination your licence ends; your
exchange account and its contents are unaffected because we never had access
to them.

**8. Changes.** We may update FIRE and these terms. Material changes will be
notified in the application before they take effect.

**9. Governing law.** [To be completed once the business entity exists. This
should match the entity's jurisdiction, checklist item G6.]

---

## 3. Privacy policy

**The short version: FIRE has no server, and we do not collect your data.**

**What stays on your computer, and is never sent to us:**

* Your exchange API key and private key, held in your operating system's
  credential store. FIRE has no mechanism to transmit them anywhere.
* Your preferences, positions, orders, balances and market data. All of it is
  local, and there is no server for it to be sent to.

**What we receive:**

* **Nothing automatically.** FIRE does not phone home, has no analytics, and
  sends no telemetry.
* **Update checks**, if you leave them enabled, request a small file from our
  release feed. That request carries no identifier, no account information and
  nothing about your trading. You can turn it off in Preferences.
* **Support bundles**, only when you create one and choose to send it. Before
  a bundle is written, FIRE automatically removes credentials, private keys,
  licence keys, email addresses and your Windows user name. The bundle is
  saved to your own computer first so you can open it and check it before
  sending anything.

**What your exchange receives** is governed by their privacy policy, not ours.
FIRE connects your computer directly to them.

**Payment information** is handled entirely by our payment provider. We never
see or store your card details.

---

## 4. Refunds and cancellation

* Cancel at any time. Your subscription runs to the end of the period you have
  already paid for, then stops. There is no cancellation fee.
* **Full refund within 14 days of your first payment**, for any reason, no
  questions asked.
* After 14 days we refund the unused portion if FIRE has a fault we cannot fix
  in reasonable time.
* **We do not refund trading losses.** FIRE sends the orders you click, and no
  software vendor can be responsible for the outcome of your trades.
* Demo mode is free and always will be, so you can evaluate FIRE fully before
  paying anything.

---

## 5. Terms of service (the website and the subscription)

**1. What these cover.** These terms govern the FIRE website and the
subscription service that issues and checks licences. Use of the FIRE
application itself is governed by the licence agreement above. Where the two
overlap, the licence agreement governs the software.

**2. Eligibility.** You must be old enough to enter a contract where you live,
and you must not be located anywhere our exchange or our payment processor
prohibits. You are responsible for knowing whether trading event contracts is
lawful where you are.

**3. Your licence key.** A subscription grants one licence key, usable on up to
three computers. The key is yours to keep private. Sharing it, publishing it or
reselling access is a breach of these terms and we may revoke it.

**4. Billing.** Subscriptions renew automatically at the interval you chose
until cancelled. Prices are shown before you pay and we will give notice inside
the application before any price change takes effect for you. Payment is
handled by Stripe; we never receive or store your card details.

**5. Trials.** A trial gives full access for a limited period. One trial per
person. We may end a trial early if it is being abused.

**6. Cancellation and refunds.** See the refunds and cancellation terms below.
You can cancel yourself at any time through the billing portal.

**7. Suspension.** We may suspend or revoke access for non payment, for
breaching these terms, or where continuing would put us in breach of a law, a
payment processor rule or an exchange agreement. Where we can, we will tell you
why first.

**8. Availability.** We aim to keep the licence service up but we do not
guarantee it. FIRE is built so that a service outage does not stop a paying
customer trading, and no uptime figure is promised.

**9. Support.** Support is by email, and we aim to reply within one business
day. We answer questions about FIRE. We do not answer questions about what to
trade, and we cannot help with your exchange account.

**10. Changes.** We may update these terms. Material changes will be shown in
the application before they take effect, and continuing to use FIRE after that
means you accept them.

**11. Governing law.** [To be completed once the business entity exists,
checklist item G6. Must match the entity's jurisdiction.]

---

## 6. Independence statement (checklist E3)

> FIRE is an independent product. It is not affiliated with, endorsed by,
> sponsored by, or approved by any exchange. All trademarks belong to their
> respective owners.

**This wording is provisional.** Whether we may name a specific exchange at
all, and in what form, is question 8 in the authorization request. Until that
comes back in writing, no exchange is named in any customer facing material.

---

## Open items before any of this ships

| Item | Blocker |
|---|---|
| Legal review of all six documents | Not started |
| Governing law clause | Needs the business entity (G6) |
| Naming any exchange in customer material | Needs written authorization |
| Consumer law check for the customer's jurisdiction | Refund and liability terms differ by country |
