# FIRE launch package

One source for every listing, so the description does not drift between
directories. Copy from here, never rewrite from memory.

**Status note that governs all of it:** until Kalshi answers the authorization
request, FIRE is described as **pre-launch with a waitlist**. No listing may
imply an exchange has approved us, and none may be worded as if live trading is
purchasable today.

---

## Identity

| Field | Value |
|---|---|
| Name | FIRE |
| Tagline | Every market on one screen. One click to take a side. |
| Category | Trading tools, desktop software, finance |
| Platform | Windows 10 and 11 |
| Website | https://fireterminal.app |
| Pricing | $59/month, $590/year, 14 day free trial, no card |
| Founding offer | First 50 subscribers $39/month or $390/year, locked while active |
| Icon | `packaging/fire.ico`, 256px PNG at `site/img/icon.png` |
| Screenshots | `site/img/terminal.png`, `site/img/activity.png` |

## Short description, 1 line

> A Windows execution terminal for short duration event contracts: every open
> market on one screen, priced off the live book, with a loss ceiling checked
> before every order.

## Short description, 2 sentences

> FIRE is a Windows desktop terminal for trading short duration event
> contracts. It shows every open market at once with live prices and order book
> depth, sends immediate or cancel orders on one click, and refuses any order
> whose worst case loss is larger than the ceiling you set.

## Long description

> Short duration contracts settle in minutes. By the time you have tabbed
> between a chart, a book and an order form, the window you were looking at has
> already moved.
>
> FIRE puts every open market on one screen. Each card shows where the market
> is, the level it has to finish past, and the gap between them, with both
> sides of the book underneath. You type a dollar amount, FIRE walks the
> visible depth and sends a count that cannot cost more than you typed, as an
> immediate or cancel order so nothing rests on a book you have stopped
> watching.
>
> It is order entry software and nothing else. There are no signals, no scores,
> no alerts and no recommendations, and it never trades on your behalf. You
> connect your own exchange account with your own API key, which is encrypted
> by your operating system and never leaves your computer. We never receive it.
>
> A fully separated demo mode with simulated markets and a simulated balance is
> free forever and requires no exchange account.

## Feature list

- Every open market on one screen, with live prices and order book depth
- Index price and the level to beat shown together, with the gap worked out
- Orders priced from the real book, never from a guess
- Immediate or cancel only, so nothing rests after you look away
- A maximum loss ceiling you set, checked before every order leaves the machine
- Positions and fills in one place, with cost and payout side by side
- Connection, subscription and mode always visible
- Demo and live are separate implementations, not a toggle
- Your API key is encrypted by Windows and never transmitted to us
- Support bundles are scrubbed of key material before they are written

## Windows requirements

Windows 10 or 11, 64 bit. About 60 MB of disk. An internet connection. No
Python, no command line, no configuration files. An account and API key at a
supported exchange are needed for live trading only; demo needs nothing.

## Security explanation

Your API key is encrypted with the Windows credential store, tied to your
Windows sign in, and only the encrypted form is written to disk. It is
decrypted in memory only long enough to sign a request, and never written to a
log, a crash report or a support bundle. FIRE ships with no credentials of any
kind and the build is checked automatically before every release. We will never
ask you for your private key.

## Demo and live

Demo mode is a separate implementation containing no networking code at all, so
a demo order has nowhere to go. It uses simulated markets, a simulated balance
and simulated fills, is free forever, and shows a blue PAPER banner throughout.
Live mode uses your own exchange account and your own key, shows a red LIVE
banner, and asks you to confirm each order until you turn that off.

FIRE never moves you from live to demo on its own.

## Risk disclosure, required on any listing that mentions trading

> Event contracts can settle at nothing. You can lose the entire amount you pay
> for any contract, and no setting in FIRE can prevent that once an order has
> filled. FIRE is order entry software: it provides no investment advice, no
> recommendations and no trading signals, and it does not trade on anyone's
> behalf. We are not a broker, dealer or registered investment adviser, and we
> are not affiliated with or endorsed by any exchange.

## Things that must never appear

- Any profit, return, win rate or performance figure
- "Risk free", "guaranteed", "passive income", "beat the market"
- Any claim that an exchange has approved, endorsed or partnered with FIRE
- Any exchange's name, logo or mark, until authorization is in writing
- Backtests, equity curves, or screenshots of real account balances

## Support

Email, one business day. In app: Diagnostics writes a support bundle with
credentials removed. Guides ship inside the product and at
https://fireterminal.app/support

## Website CTA

Pre-launch: **Join the waitlist**
After authorization: **Start your free trial**
