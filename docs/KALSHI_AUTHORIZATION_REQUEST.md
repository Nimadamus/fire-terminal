# Kalshi authorization request

**Status: not sent.**

---

## Exactly where to send it

**Primary: the support messenger, while logged in to your Kalshi account.**
Open kalshi.com, sign in, and use the chat launcher in the bottom right. Kalshi
states this is the fastest route and it attaches your member account
automatically, which matters here because the request only makes sense coming
from an identified member.

The first line asks for routing to legal or compliance. Without it, front line
support sends a canned answer, because front line support cannot authorize any
of this.

**If there is no substantive reply in five business days:** send the same text
to **legal@kalshi.com**, from the email address registered to your Kalshi
account, and mention that you raised it in the support messenger first and on
what date.

**Do not use:** the Discord developer community. It is a good place for API
questions and the wrong place for a permission request, because nothing said
there is binding on anyone.

**Do not attach:** trading records, performance figures, screenshots, or
anything about automated strategies. This is a request about distributing a
manual execution client. Anything else invites a different and worse
conversation.

---

## The message

Paste everything between the lines.

---

**Subject:** Authorization request: paid third party execution terminal (Developer Agreement 3.1, 3.2, 3.7, 6.4)

Please route this to legal or compliance. I am asking for written permission
before releasing, not afterwards.

I am a Kalshi member and API user, writing from the address registered to my
account. I have built a desktop execution terminal called FIRE and would like
to sell it as a paid subscription to other Kalshi members. Before I release it
to anyone, I want your position in writing.

**What FIRE is**

A Windows desktop application that a customer installs on their own computer.
It displays open markets on one screen with live prices and order book depth,
and places immediate or cancel limit orders when the customer clicks. It is an
order entry tool, nothing more.

**How customers authenticate**

Each customer creates their own API key inside their own Kalshi account and
enters it into their own copy of FIRE. There is no shared key, no key of mine,
and no account of mine involved in any customer's trading.

**Whether credentials stay local**

They do, entirely. The key is encrypted on the customer's machine using the
Windows credential store, tied to that Windows sign in, and only the encrypted
form is written to disk. It is decrypted in memory only for the moment a
request is signed. It is never written to a log, a crash report or a support
file, and there is no mechanism by which it could reach me. I could not produce
a customer's key if you asked me to.

**What API functionality FIRE requires**

Read: open markets and their metadata, order book depth, index or underlying
price, the customer's own balance, positions and fills.

Write: place an order, and cancel an order.

Nothing else. No administrative endpoints, no data outside the authenticated
customer's own account.

**What FIRE does**

Displays those markets, and sends a limit order when the customer clicks buy.
Orders are immediate or cancel, priced from the visible book, so nothing rests.
Every order is one deliberate human click.

**What FIRE does not do**

* It routes no orders through any infrastructure of mine. Each installation
  connects from the customer's own machine directly to Kalshi with that
  customer's own key.
* It holds no customer funds and takes no custody of anything.
* It aggregates, stores, resells or republishes no Kalshi market data. I
  operate no market data server. Data is shown on the screen of the customer
  whose key fetched it.
* It gives no recommendations, signals, scores or trade suggestions, and it
  performs no automated or scheduled trading.
* It uses no Kalshi name, logo or mark anywhere in the product or in any
  marketing, and it will not unless you approve specific wording.

**Safeguards already built in**

* A maximum loss ceiling per order, set by the customer and enforced before any
  order is sent.
* A client side rate limiter with exponential backoff and jitter on 429 and 5xx
  responses, and a bounded retry count. I will design to whatever ceiling you
  specify.
* A fully separated demo mode with no networking code at all, so a customer can
  evaluate the product without touching Kalshi.
* Explicit risk acknowledgements before a customer can connect a live account,
  including that they are responsible for complying with your Developer
  Agreement in their own name.
* An automated release check that fails the build if any credential, key
  material or server side component is present in what customers receive.

**Business model**

A paid monthly or annual subscription for the software itself. I take no fee,
commission, rebate or share of any kind on trading activity, and my revenue is
unrelated to how much any customer trades.

**Why I am asking**

Section 3 limits use of the API to my own trading and 3.2 addresses
facilitating trading by other members. On a plain reading, selling software
that other members use to trade needs your permission, and I would rather have
that answer in writing before anyone pays me than discover it afterwards.

**My questions**

1. May I distribute software that other members use, with their own keys, to
   facilitate their own trading?
2. Is there a registration, review or approval process for third party
   applications, and does FIRE need to go through it?
3. Where each customer holds their own key and accepts your Developer Agreement
   in their own name, is section 3.7 implicated?
4. Do you want customer API keys used as described, or do you prefer a
   different flow such as OAuth for third party applications?
5. What are the limits on displaying live prices and order book depth inside a
   paid third party application, and on transient local caching on the
   customer's own machine for that customer's own trading? Section 3.1 is the
   clause I want to be certain about.
6. Is direct customer machine to Kalshi routing the arrangement you want?
7. Are rate limits applied per key or per application? If per application, what
   should I design to?
8. May I state factually that FIRE works with Kalshi, and in what wording? I
   assume I may not use your marks and I will not until told otherwise in
   writing.
9. Do you object to this being sold as a paid subscription rather than given
   away?
10. Is there specific language you require a third party application to show
    its users?

**What I am offering**

I am happy to submit the build for review before any release, to run against
the demo environment first, to accept written conditions, or to sign a separate
distribution agreement if you prefer one. I can also provide a build to your
team to inspect.

If the answer is no, that is genuinely useful and I will not proceed.

**Contact**

[your name]
[the email registered to your Kalshi account]
[your Kalshi account email, if different]

Thank you for your time.

---

## If they come back with questions

Most likely follow ups, and the short answers:

**"Do you see customer trading data?"** No. There is no server of mine between
the customer and Kalshi. The only service I run answers whether a subscription
is paid, and it never sees a Kalshi key, an order, a position or a balance.

**"How many users are you expecting?"** Tens, not thousands. Individual members
trading their own accounts with their own keys.

**"What happens if we say no?"** I do not release it. The product also has a
fully separated demo mode with no exchange connection, which I can continue to
show without touching your API.

**"Can we see it?"** Yes, immediately. I can provide the installer, a walk
through, or a build to inspect.

**"Who is liable if a customer loses money?"** The customer makes every trading
decision and clicks every order. The licence terms carry a risk disclosure, no
warranty and a liability cap, and customers acknowledge in the application that
FIRE gives no advice and that they are responsible for their own exchange
account and for your Developer Agreement.

---

## Expected outcomes

| Answer | What happens |
|---|---|
| Yes, unconditionally | Launch proceeds. Wording for question 8 goes into the site. |
| Yes, with conditions | Apply them, then launch. Most likely conditions are rate limits, disclosure language and no use of their marks. |
| Register as a third party app | Do that first. Adds time, not risk. |
| No | Do not release. Demo mode still exists and touches nothing of theirs. |
| No reply | Chase once at five business days by email to legal@kalshi.com. Do not release on silence. Silence is not permission. |
