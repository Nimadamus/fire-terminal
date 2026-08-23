# Kalshi authorization request

**Status: not sent.**

**Channel:** the in app support messenger while logged in to the Kalshi
account. Kalshi states this is preferred, and it identifies the member account
automatically. Alternative is support@kalshi.com sent from the address
registered to the account.

**Before sending:** the first line asks for routing to legal, compliance or
the API team. Front line support cannot authorize any of this, and without
that line the request gets a canned reply.

**Do not include:** any trading record or performance figure, any reference to
automated strategies, any screenshots. This is a request about distributing a
manual execution client and nothing else.

---

**Subject:** Written authorization request: paid third party execution terminal (Developer Agreement 3.1, 3.2, 3.7, 6.4)

---

Please route this to legal, compliance or the API team. I am asking for
written permission before building toward release, not after.

I am a Kalshi member and API user, writing from the address registered to my
account. I am developing a desktop execution terminal called FIRE and intend
to sell it as a paid subscription to other Kalshi members.

**What FIRE is**

A local Windows application. It shows open markets on one screen with live
prices and order book depth, and places immediate or cancel limit orders on
one click. Each customer supplies their own Kalshi API key, which is stored in
their own operating system credential store on their own machine.

**What FIRE does not do**

* It holds no customer funds and has no custody of anything.
* It routes no orders through my infrastructure. Each installation connects
  directly from the customer's machine to Kalshi using that customer's key.
* I never receive, transmit, store or have any means of accessing a
  customer's API key or private key.
* It aggregates, stores and redistributes no Kalshi market data on my side. I
  operate no server. Data is displayed on the customer's screen and used only
  to facilitate that customer's own trading.
* It gives no trade recommendations, signals, scoring or automated trading.
  Every order is a deliberate human click.
* It uses no Kalshi name, logo or mark in the product or in any marketing,
  and will not until you approve specific wording.

**What I am asking**

1. **API use.** May I distribute software that other members use, with their
   own keys, to facilitate their own trading, given the limitation in
   section 3 and the prohibition in 3.2?
2. **Third party application requirements.** Is there a registration,
   review or approval process for third party applications, and does FIRE
   need to be registered as one?
3. **Sublicensing.** Where each customer holds their own key and accepts your
   Developer Agreement in their own name, and no access of mine is passed to
   anyone, is section 3.7 implicated?
4. **Customer authentication.** Do you expect an application like this to use
   customer API keys as it does now, or is there a preferred flow such as
   OAuth for third party applications?
5. **Market data.** What are the limits on displaying live prices and order
   book depth inside a paid third party application, and on caching that data
   locally on the customer's own machine for their own trading? Section 3.1
   is the clause I want to be certain about.
6. **Order routing.** Is direct customer machine to Kalshi routing, using the
   customer's own key, the arrangement you want, or do you require anything
   different from third party clients?
7. **Rate limits.** Are limits applied per key or per application? If per
   application, what should I design to? FIRE currently paces itself with a
   client side ceiling, exponential backoff with jitter, and bounded retries.
8. **Branding.** May I state factually that FIRE works with Kalshi, and if so
   in what wording? I assume I may not use your marks, and I will not until
   you tell me otherwise in writing.
9. **Subscription sales.** Do you object to this being sold as a paid monthly
   subscription rather than given away?
10. **Disclosures.** Is there specific language you require a third party
    application to display to its users?

I am happy to submit the build for review before any release, to work in the
demo environment first, to accept written conditions, or to sign a separate
distribution agreement if you prefer one.

If the answer is no, that is genuinely useful to know now and I will not
proceed. I would rather ask first than discover the answer afterwards.

Thank you for your time.

---

## Technical annex: hold this back until they ask

Do not send this with the first message. It makes a short, answerable request
look like a submission, and the first message needs to be read by a person and
routed. Send it when they come back with questions, which they will.

**Architecture.** A single Windows desktop application. No server of ours sits
between the customer and Kalshi. The only service we operate is a licence
endpoint that answers whether a subscription is paid; it never sees a Kalshi
key, an order, a position or a balance, and it does not proxy any Kalshi
traffic.

**Credential handling.** The customer creates their own API key in their own
Kalshi account and pastes the key ID and private key into the application once.
It is encrypted immediately with the Windows DPAPI store, tied to that Windows
sign in, and only the encrypted form is written to disk. The key is decrypted in
memory for the duration of a request signature and never written to a log, a
crash report or a support bundle. Support bundles are redacted at the point of
writing, and any bundle that cannot be verified clean is discarded rather than
saved. We have no mechanism by which a key could reach us.

**Order handling.** Every order originates in a human click. Orders are
immediate or cancel limit orders priced from the visible book, so nothing rests.
There is no scheduling, no automation, no strategy and no queue. The application
also enforces a customer set maximum loss per order before anything is sent.

**Market data.** Displayed on screen for the customer whose key fetched it.
Nothing is aggregated, stored on our side, resold, republished or shared between
customers. Any local caching is transient and on the customer's own machine, for
that customer's own trading.

**Rate limiting.** A client side token bucket paces requests, with exponential
backoff and jitter on 429 and 5xx responses and a bounded retry count. We will
design to whatever ceiling you specify, per key or per application.

**Release control.** Builds are gated automatically before release: the
application is verified to contain no credentials, no key material and no
server side components. We are happy to submit a build for review, to run in
the demo environment first, or to accept written conditions on distribution.

**Scale.** We expect tens of customers, not thousands. Each is an individual
member trading their own account with their own key.

---

## Expected outcomes

| Answer | What we do |
|---|---|
| Yes in writing | Wire the approved endpoint profile, work the launch checklist, release |
| Yes with conditions | Apply the conditions, re-verify, then release |
| No | Stop. Keep the client for personal use. Nothing is wasted except time |
| Silence | One polite follow up after ten business days, then treat as no |
