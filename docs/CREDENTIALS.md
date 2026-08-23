# Your API key, and how to take it back

FIRE connects to your exchange account with an API key that you create and
that you own. This page explains where that key lives, how to replace it, and
how to cut it off. Keep it: the day you need it is usually a bad day.

## What FIRE does with your key

You paste two things during setup: a key ID, and the private key file the
exchange gave you when you created it.

* The private key is encrypted immediately using your operating system's own
  secret store, and only the encrypted form is written to disk. On Windows that
  is DPAPI, which ties the encrypted copy to your Windows sign-in. Someone who
  copies the file to another computer cannot read it.
* The key is decrypted in memory only for as long as it takes to sign a
  request, and it is never written to a log, a crash report or a support
  bundle. If FIRE cannot verify that a support bundle is clean, it throws the
  bundle away rather than sending it.
* FIRE never transmits your private key anywhere. It is used to sign requests
  on your computer. We do not have it and cannot recover it for you.
* FIRE ships with no credentials of its own. Nothing in the download connects
  to any account until you supply a key.

If your operating system has no secret store available, FIRE refuses to save
the key at all rather than writing it somewhere readable.

## Removing the key from this computer

**Preferences → Remove saved credentials.**

This deletes the encrypted copy from your computer. FIRE drops back to demo
mode. Nothing is cancelled and nothing is sold: any positions you hold stay
open at the exchange, where you manage them as normal.

Removing the key from FIRE does **not** disable it at the exchange. The key
still exists and still works. To stop it working, revoke it (below).

## Rotating your key

Do this on a schedule you are comfortable with, and immediately after anything
that might have exposed the key.

1. In your exchange account, create a **new** API key. Keep the old one alive
   for now.
2. In FIRE, open **Preferences → Remove saved credentials**, then set up again
   with the new key ID and new private key file.
3. Place one small order, or simply confirm the connection indicator reads
   *connected* and your balance is correct.
4. Once the new key is confirmed working, **revoke the old key** at the
   exchange.

Doing it in that order means you are never locked out mid-window.

## Revoking a key

Revocation happens at the **exchange**, not in FIRE. FIRE holds a copy of your
key; it does not control whether the exchange honours it. Sign in to your
exchange account, find its API key settings, and delete or disable the key.

Once a key is revoked, FIRE will show *sign in required* and will not be able
to place orders with it.

Revoke immediately if:

* your computer is lost, stolen, or sold
* you pasted the private key anywhere other than FIRE's setup screen
* you shared a screen, a screenshot, or a screen recording while the key was
  visible
* you no longer use FIRE
* anything about your account activity looks unfamiliar

Revoking a key does not close positions. Check your exchange account for open
positions after revoking.

## If your computer is lost or stolen

1. **Revoke the key at the exchange first.** Do this before anything else. The
   encrypted copy on that computer is tied to the Windows sign-in, but revoking
   removes the question entirely.
2. Check your exchange account for orders and positions you did not place.
3. Create a fresh key for your replacement computer.

## What we will never ask you for

We will never ask you to send us your private key, paste it into an email, a
chat, a form, or a support ticket. Nobody needs it to help you. If you receive
a message asking for it, it did not come from us.

Support bundles are safe to send: they are scrubbed of key material before they
are written, and FIRE discards any bundle it cannot verify as clean.

## One key, one purpose

Use a key created specifically for FIRE rather than reusing one you already use
elsewhere. If you ever need to revoke it, you then cut off exactly one thing
instead of everything you own at once.
