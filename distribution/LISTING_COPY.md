# FIRE commercial listing package

Every claim below is checkable against the shipped product. No performance
claims, no profit claims, no statement that any exchange has authorized
distribution. Two copy variants: **A (exchange-neutral)** is safe to publish
before Kalshi answers A4; **B (named)** must not be published until A1-A4 are
answered in writing.

## Identity

- **Product name:** FIRE
- **Full name:** FIRE Terminal
- **Category (primary):** Trading / investment tools, Windows desktop
- **Category (secondary):** Finance, developer-adjacent power tools
- **Version:** 1.0.0
- **Platform:** Windows 10 and Windows 11, 64-bit desktop application
- **Website:** https://fireterminal.app *(not yet purchased; staging
  https://fire-terminal.onrender.com)*
- **Support:** one human reply within one business day, support@ on the FIRE
  domain *(address not yet created)*

## Short description (under 60 characters, Product Hunt tagline)

- A: `Every market on one screen. Order in one keystroke.`
- B: `A fast Windows terminal for trading Kalshi markets.`

## Medium description (under 260 characters)

- A: `FIRE is a Windows trading terminal for prediction markets. Every open
  market on one screen, orders priced from the real book, immediate-or-cancel
  execution, and a hard risk ceiling. Your API key never leaves your machine.`
- B: same, with "prediction markets" replaced by "Kalshi".

## Long description

FIRE is a desktop trading terminal for prediction markets, built for the ninety
seconds around a market close when speed decides the fill.

It puts every open market on one screen with the index price beside it, reads
the order book and prices your order from what is actually resting there, and
sends immediate-or-cancel orders so nothing you click sits working against you.
A hard risk ceiling refuses any order whose worst-case loss is larger than the
limit you set. Positions and fills stay in one place.

FIRE runs in two modes that cannot be confused for each other: a demo mode
against a simulated market, and a live mode that connects with your own API key.
Mode integrity is enforced on every access inside the session layer, not by a
label in the corner.

What FIRE deliberately is not: it does not tell you what to buy, there are no
signals and no model output; it does not trade on your behalf, nothing is sent
that you did not click; it does not hold your money, your account stays at your
exchange; and it does not promise a profit, because nobody honest can. It is not
a broker, a dealer, or an adviser.

## Feature list

- Every open market on one screen, with the index price alongside
- Orders priced from the live order book, not from a stale mid
- Immediate-or-cancel execution, no resting orders you forgot about
- Hard risk ceiling that refuses oversized worst-case loss
- Positions and fills in one view
- Demo and live modes with enforced separation
- Your API key is stored on your own machine and never transmitted to us
- Free updates while subscribed, up to 3 computers

## Pricing

- $59 per month, every feature, no limits, up to 3 computers
- $590 per year, works out at $49 per month
- 14-day trial, no card required
- Founding price $39 for the first fifty customers
- Cancel any time in one click

## Windows compatibility and installation

Windows 10 and 11, 64-bit. Signed installer *(code signing not yet purchased,
Azure Artifact Signing at $9.99/month is the planned route)*. Download from the
FIRE site, run the installer, paste your own exchange API key. No admin rights
required for normal use. No bundled toolbars, telemetry-by-default, or adware.

## Demo versus live

The download runs in demo mode against a simulated market so anyone can see the
interface without an exchange account. Live trading requires the customer's own
exchange account and their own API key, under their own agreement with the
exchange. FIRE ships with no keys of its own.

## Privacy and security

The API key is stored locally on the customer's machine and is never sent to us.
FIRE holds no customer funds and takes no custody. The build pipeline fails if
anything credential-shaped appears in the source. No analytics on trading
activity.

## Risk disclosure (include verbatim wherever the platform allows)

Trading prediction markets involves risk of loss. FIRE is execution software; it
provides no advice, no signals, and no recommendation to buy or sell anything.
It is not a broker, dealer, or investment adviser, and it is not affiliated with
any exchange. Past results, yours or anyone else's, do not predict future
results. You are responsible for your own trades and for complying with the
terms of the exchange you connect to.

## Calls to action

- Pre-launch / waitlist: `Join the waitlist. Founding price for the first fifty.`
- Post-launch: `Download FIRE. 14-day trial, no card.`

## Assets

| Asset | Path | State |
|---|---|---|
| Icon (PNG) | `site/img/icon.png` | ready |
| Windows icon | `packaging/fire.ico` | ready |
| Screenshot: terminal | `site/img/terminal.png` | ready |
| Screenshot: activity | `site/img/activity.png` | ready |
| Gallery images 5-8 (Product Hunt) | - | **missing**, needs capture from the running app |
| Demo video 45-60s | - | **missing** |

## Truth constraints for every listing

- Do not state or imply that any exchange has approved, endorsed, partnered
  with, or authorized FIRE.
- Do not publish performance figures, win rates, or profit examples.
- Do not describe live trading as available until it actually ships enabled.
- Where the product is not yet purchasable, list it as pre-launch with a
  waitlist rather than implying a working checkout.
