# Troubleshooting

Most problems fall into one of the six below. If none of them fit, open
**Diagnostics** in FIRE, create a support bundle and send it to us. The bundle
tells us in one file what would otherwise take ten emails to establish, and it
contains no credentials.

## Windows warns about an unknown publisher when I install

Click **More info**, then **Run anyway**. FIRE is a small independent product
and Windows shows this warning for any installer it has not seen many times
before. Nothing is wrong with the download.

## FIRE says PAPER and my balance is exactly one thousand dollars

You are in demo mode. Everything on screen is simulated: the prices, the
balance, the fills. No order reaches an exchange and no money is involved.

To connect a real account, open **Preferences**, add your exchange API
credentials, then reopen FIRE. The banner across the top always tells you which
mode you are in, and it is red and says **LIVE** when real money is involved.

## The BUY buttons are greyed out

Three possible reasons, and FIRE tells you which one on the card:

* **Waiting for the next window.** The market you are looking at is between
  windows. It reopens on its own.
* **Subscription ended.** Open **Account** and renew. Your positions are
  untouched and nothing has been sold.
* **Trading is switched off.** Access to this installation was withdrawn. Send
  us a support bundle if that looks wrong.

## It says sign in required, or my credentials were rejected

Your API key is not being accepted by the exchange. In order of likelihood:

1. The key was revoked or expired at the exchange. Create a new one and add it
   in **Preferences**.
2. The private key was pasted incompletely. It must include the first and last
   lines of the file.
3. The key is password protected. FIRE cannot use an encrypted key file.
   Create one without a password.

See `Preferences → Key security and rotation` for the full procedure.

## An order did not fill

FIRE sends immediate or cancel orders. They either fill against what is on the
book right now or they are cancelled. They never sit waiting. If nothing filled,
nothing was charged.

The usual cause is that the price moved between the book you looked at and the
moment you clicked, or there were not enough contracts at your limit. Both are
normal in short duration markets.

## Prices have stopped updating

Check the connection indicator at the top right.

* **connecting** or **degraded**: FIRE is retrying on its own. Nothing to do.
* **rate limited**: the exchange asked FIRE to slow down and it has. Prices
  update less often until it clears.
* **offline**: check your internet connection.

FIRE reconnects by itself in all of these cases. You do not need to restart it.

## Reinstalling or updating

Download the latest installer and run it. It installs over the top and keeps
your settings, your saved credentials and your subscription. There is no need
to uninstall first.

If you do uninstall, FIRE asks whether to remove your settings and the
encrypted copy of your API key. Removing them does **not** revoke the key at
your exchange. Do that in your exchange account.

## My subscription is not recognised

Open **Account** and press **Refresh**. If it still shows the wrong state,
create a support bundle from **Diagnostics** and send it with the email address
you bought with. Do not send a licence key by email.

## Lost or stolen computer

Revoke your API key at your exchange first, before anything else. Then check
your exchange account for orders you did not place. The full procedure is in
`Preferences → Key security and rotation`.
