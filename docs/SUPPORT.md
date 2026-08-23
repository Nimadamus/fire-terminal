# Support: what we promise and how it works

Checklist item G5. This is the policy. One thing in it is a decision only you
can make, and it is marked.

## What a customer can do inside FIRE

**Diagnostics → Create support bundle.** It writes a single file containing the
environment, the recent log, the connection state and whatever note they typed.
Secrets are removed before it is written, not after, and if FIRE cannot verify
the result is clean it throws the bundle away rather than saving it.

The window then tells them where to send it. That address comes from one
constant, `SUPPORT_EMAIL` in `src/fire/version.py`.

**It is empty today.** A release build cannot ship with it empty: the release
gate blocks, because a support bundle the customer cannot send anywhere is not
support. **You need to pick the address.** Anything you already control works.
Use a dedicated address rather than a personal inbox, so it can be handed to
somebody else later without moving a mailbox.

## What we promise

Publish this and then meet it. An unmet promise is worse than a modest one.

* **First reply within one business day.** At a subscription in the forty to
  sixty dollar range, one business day is what customers expect and it is
  achievable by one person. Do not promise an hour.
* **Support is by email.** No phone, no live chat. Say so plainly so nobody
  buys expecting one.
* **We answer questions about FIRE.** Installing it, connecting an account,
  what a control does, something that looks wrong, billing.
* **We do not answer questions about what to trade.** Not as a policy dodge but
  because it is the line that keeps FIRE a tool rather than an advisory
  service. See the independence statement in `docs/LEGAL.md`.

## What we will never ask for

A private key, a password, or a screen share showing either. Nobody needs them
to help. This is written in `docs/CREDENTIALS.md` too, so a customer who gets a
phishing message asking for their key already knows it did not come from us.

## Handling a bundle

1. Confirm receipt the same day, even if the answer takes longer.
2. Read the bundle before asking questions the bundle already answers.
3. If the bundle shows something sensitive got through the redaction, that is a
   defect in FIRE, not a customer problem. Fix it before replying.

## Known things to expect

* **SmartScreen warnings on first run** until the installer is signed. This
  will be the single most common first contact until item H5 is resolved, so
  have a canned reply ready, and expect a share of customers to simply not
  install rather than write in.
* **"My positions disappeared."** Almost always demo mode. The banner says
  PAPER and the balance is a round thousand dollars.
* **"It will not let me trade."** Check subscription state first. A lapsed
  subscription now disables order entry and says so, so this should be rare.

## Still to decide

| Item | Needed for | Owner |
|---|---|---|
| The support address itself | Release gate blocks without it | You |
| Whether replies come from the same address customers write to | Deliverability | You |
| A public page describing this policy | Checklist G5 closes fully | You, once the site exists |
