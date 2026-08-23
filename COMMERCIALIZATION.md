# FIRE Commercialization

Running record of architecture, decisions, what was removed, what is still
blocked, and the launch checklist. Updated as work proceeds.

**Status:** v1 feature complete for demo. Live adapter written and tested but
unwired pending authorization. 205 tests green, zero skipped.
**Not shipped. Not launched. No distribution permission yet.** See
[LAUNCH_CHECKLIST.md](LAUNCH_CHECKLIST.md).

---

## 1. The separation

This repository is **standalone**. It shares no git history, no parent
directory and no import path with the private trading system. The private
system was not modified, refactored, branched or moved. It continues to run
untouched.

```
C:\Users\BL\kalshi          private system, READ ONLY, never edited
C:\Users\BL\fire-terminal   this repository, no dependency on the above
```

The commercial client does not import the private package. That is enforced by
`tests/test_architecture.py`, which fails the build if any module in `src/fire`
imports a private module name, contains internal vocabulary, or embeds anything
credential shaped.

## 2. Architecture

```
                    UI  (tkinter, fire/ui)
                     |
                  Session  (fire/core/session.py)
                     |          enforces mode integrity on every access
      +--------------+--------------+
      |                             |
 MarketDataSource            ExecutionVenue / AccountAdapter
      |                             |
      +----------- Venue -----------+
                     |
        +------------+------------+
        |                         |
   DemoVenue                 LiveVenue
   (no network at all)       (written, tested, UNWIRED:
                              endpoints.ACTIVE is UNCONFIGURED)
```

Supporting layers, all independent of venue:

| Layer | Module | Job |
|---|---|---|
| Domain types | `core/models.py` | the only shapes crossing a venue boundary |
| Errors | `core/errors.py` | every customer facing failure, each with a remedy |
| Risk | `risk/limits.py` | max loss ceiling, evaluated before every submit |
| Credentials | `config/credentials.py` | DPAPI backed, purpose built, never plaintext |
| Preferences | `config/prefs.py` | local JSON, nothing secret |
| Entitlement | `interfaces/entitlement.py` + `entitlement/local.py` | one seam for billing |
| Diagnostics | `diagnostics/redact.py`, `bundle.py`, `crash.py` | redaction at the write boundary |
| Updates | `updates.py` | non blocking, anonymous, disabled without a feed |

### The venue interface carries no strategy surface

`interfaces/venue.py` offers methods for listing instruments, reading a book,
planning an order and submitting it. There is no method for "what is this
worth", "should I trade this" or "which is the best candidate". No
implementation of this interface can pass proprietary logic upward, because
there is no channel for it. A test asserts the interface never grows one.

### Demo and live are separated structurally

Three independent barriers, not a UI toggle:

1. `venues/demo/` imports no network library. A parametrized test asserts this
   per file, so a demo order has no code path to any endpoint.
2. Every component declares a constant `mode`. `Session` re-checks it on every
   single accessor call, so a wiring mistake raises before an order is built.
3. `Session.raw_venue()` refuses in live mode, so demo-only controls such as
   Reset cannot be reached against a real account.

## 3. Component disposition

Derived from the audit. Categories are as requested: reuse safely, rewrite,
isolate, delete.

### Reuse safely (migrate mechanics only, when the live adapter is built)

| Source | Notes |
|---|---|
| `btc/eth/sol/xrp/doge15m_fire_paper.py` | ladder walk, best ask, fee math, IOC planning. Strip the hardcoded key and the module level PEM load. |
| `crypto_universe.py` | market discovery and structure validation. Genuine product value. |
| `crypto_panel.py` | per series module factory. |
| `market_lot.py`, `lot_quantum.py` | lot arithmetic. |

### Rewrite (done, or scheduled)

| Internal | Commercial replacement | State |
|---|---|---|
| `kalshi_risk_cap.py` (49 KB, fixed house fraction, multi runner) | `risk/limits.py` (2 KB, one account, customer configurable) | **done** |
| `kalshi_live_order.py` (the coupling hub) | `interfaces/venue.py` + per venue execution + shared `core/planning.py` | **done**, unwired by design |
| `fire_interlock.py`, `shared_book.py`, `market_claim.py` | not reproduced. Single customer, single app, no arbitration needed. | **dropped by design** |
| `fortress_owner.py`, `fire_supervisor.py` | a simple single instance check, when needed | not needed yet |
| `fire_render_log.py` | plain redacted app log, no valuation fields | **done** (`app.py` logging) |

### Isolate behind a server (deferred, and probably never needed)

The audit found the valuation model is used at exactly one line and its output
is never displayed. So there is nothing for a pricing server to serve in v1.
Revisit only if a future feature genuinely needs it.

### Delete from customer build

`fair_model.py`, the BOT WINDOW panel, the valuation and edge logging block,
the eleven telemetry modules with zero GUI references, all `.pem` files, the
internal key registry, the model registry, the shared account state directory
and roughly 24 GB of research. None of it exists in this repository.

## 4. Decisions

| # | Decision | Reasoning |
|---|---|---|
| D1 | Standalone repository, not a branch or worktree of the private system | A worktree shares history and makes an accidental cross import one path traversal away. Standalone makes leakage require deliberate effort. |
| D2 | Keep tkinter for v1 | The panels are already tkinter, it ships without a runtime dependency, and packaging stays simple. Revisit only if the UI becomes the reason people do not buy. |
| D3 | Windows DPAPI for credentials, not a bundled secret or a config file | No dependency, ties ciphertext to the Windows account, and needs no master password. `keyring` is the fallback elsewhere; if neither exists FIRE refuses to save rather than writing plaintext. |
| D4 | Demo uses a naive terminal price model | It has to look like a market without carrying any real analysis. Anyone who reverse engineers the simulator learns first year probability and nothing else. |
| D5 | Entitlement is local and offline for now | It answers "what should the UI show" and gives billing a clean seam. It is explicitly not copy protection; a local licence file is trivially editable and pretending otherwise would be theatre. Real enforcement has to be server side. |
| D6 | Redaction runs at the log write boundary, not at bundle time | A secret that reaches a log file has already leaked. |
| D7 | Live trading is gated on entitlement, demo never is | A customer who cannot evaluate the product will not buy it. |
| D8 | Architectural rules are tests, not documentation | The separation is the thing being sold. It has to fail the build when broken. |
| D9 | Exchange authorization is a launch gate, not an engineering blocker | Nima's call. Everything that can be built safely gets built; nothing ships or is advertised until permission is in writing. The endpoint profile is the single seam that stays empty until then. |
| D10 | Tkinter for v1, revisit after launch | Nima's call. Priority is a stable sellable v1, not a framework migration. |
| D12 | A skipped test is treated as a failing test | Two UI tests silently skipped because the instrument map is only filled by the refresh loop. A green run containing skips is not a green run, so the fixture now primes the state and the tests assert instead of skipping. |
| D13 | One shared Tk root for the whole UI test module | Creating and destroying Tk roots repeatedly in one process leaves Tcl unable to initialise the next one. That is a tkinter constraint, not an application bug, so the module builds one root and shares it. |
| D11 | The release gate judges `.pem` files by content, not extension | A CA trust bundle is a `.pem` full of certificates and ships legitimately with any HTTPS client. Blocking the extension produced a false positive on `certifi` and would have trained us to ignore the gate. It now looks for private key markers, and is tested against a planted key. |

## 5. Bugs found and fixed during the build

* **Order sizing could exceed the stated budget.** The planner walked the
  ladder and sized against the cheaper ladder average, but an immediate or
  cancel order can fill any contract at the limit. A deep walk therefore
  spent more than the amount the customer typed. Now clamped to
  `floor(budget / limit)`. Caught by `test_demo_plan_never_exceeds_budget`.

## 6. Open blockers

| Blocker | Owner | Status |
|---|---|---|
| Written distribution permission from the exchange | Nima | **unsent.** Message drafted at `docs/KALSHI_AUTHORIZATION_REQUEST.md`. Treated as a launch gate, not an engineering blocker, per decision D9. |
| UI toolkit | Nima | **decided: tkinter for v1** (D10) |
| Code signing certificate | Nima | needed before any public release |
| Update feed hosting | Nima | needed before update checks do anything |
| Billing backend | later | interface exists, no implementation |

## 7. Progress log

**Build 2.** Onboarding and preferences.

* First run flow: welcome, then either demo in one click or a credentials
  step, then a mandatory risk ceiling before the terminal opens. Closing the
  window is treated as consenting to neither and exits without connecting.
* The credentials step validates by actually parsing the key rather than
  string matching, so the customer gets a precise reason when a paste is
  wrong (truncated, or password protected).
* Preferences covers risk, stake buttons, default amount, markets per page,
  theme, sound, update checks, and removing saved credentials. Risk changes
  apply live; theme and layout ask for a restart rather than pretending to
  hot swap.

**Build 3.** Live adapter, packaging, shared planner.

* **Shared order planner** (`core/planning.py`). The budget guarantee is now
  written once and used by both venues. The audit showed exactly what happens
  when execution mechanics are copied per venue: they drift silently, because
  each copy looks locally correct. Demo was refactored onto it.
* **Live adapter complete but unwired.** `endpoints.ACTIVE` is
  `UNCONFIGURED`, so every live construction raises `ExchangeNotConfigured`
  and the app falls back to demo with a clear message. Wiring it is filling
  in one `EndpointProfile` object; a test proves URL and signature path
  construction works against a configured profile, so the wiring step is
  mechanical rather than a restructure.
* **Credential injection by construction.** `RequestSigner` takes a
  `Credentials` argument. Nothing in the venue package reads a file path, an
  environment variable or a bundled key. The signer parses the key once and
  keeps no reference to the PEM text, so a traceback cannot reach it. A test
  asserts that.
* **Conduct controls** in `transport.py`: client side rate ceiling, bounded
  retries, exponential backoff with jitter, degrade rather than fail. Written
  to satisfy checklist section D before it is ever needed.
* **Packaging built and verified.** PyInstaller bundle produced at 31.8 MB
  across 963 files, and the packaged exe launches. `packaging/verify_bundle.py`
  is a release gate that inspects the built bundle for private keys, private
  modules, internal vocabulary and size.

**Build 4.** Crash handling, account UI, legal drafts, UI smoke tests.

* **Sanitized crash capture** (`diagnostics/crash.py`). A traceback is the
  most dangerous thing we write to disk, because frame locals can be rendered
  into it. So local variables are never rendered, frames in credential or auth
  modules have their source withheld, every line passes redaction, and if the
  result cannot be verified clean the report is discarded rather than written.
  Losing a report beats leaking a key. Installed for worker threads too.
* **Account window** reading only the entitlement interface, so connecting a
  billing backend later changes nothing in the UI. Trial, active, expired,
  revoked and unlicensed each get their own plain explanation of what still
  works, and demo is stated as always available.
* **Legal drafts** at `docs/LEGAL.md`: risk disclosure, EULA, privacy policy,
  refund terms and the independence statement. **Not lawyer reviewed.** They
  exist so the shape is settled and the review is cheap.
* **UI smoke tests.** Every window is now built and torn down against a real
  session in the suite, plus the real order path and the risk block. This is
  the layer that catches a renamed attribute or a dead callback, which the
  other suites cannot see.

**Build 5.** Consent gating.

* The live path now requires explicit acknowledgement before credentials are
  even requested: five separate statements covering no advice, total loss,
  responsibility for the customer's own exchange terms and developer
  agreement, software failure, and the licence. Continue stays disabled until
  every one is ticked.
* Five separate statements rather than one blanket tick, because a single
  "I agree to everything" box is not meaningful consent to distinct facts.
* **The demo path requires none of it**, and a test enforces that. Putting a
  wall of legal tickboxes in front of a free trial costs customers and
  protects nobody, since no money and no exchange account are involved.
* `accepted_terms_version` is recorded, so bumping `TERMS_VERSION` re-prompts
  everyone. Changed terms need fresh consent rather than silent drift.

**Build 6.** Lapsed subscriptions, the credential guide, and a real installer.

* **A lapse reaches the interface before the click.** `entitlement/policy.py`
  answers what each state permits and `entitlement/watch.py` checks for changes
  off the UI thread. Order entry switches off, every card says so in one line,
  and a bar across the top carries the full reason with both ways out. Renewing
  from the Account window brings the buttons back without a restart.
* Demo has its own gate, so REVOKED stops demo too. Otherwise revocation would
  be decoration. EXPIRED and UNLICENSED leave demo open, because a customer who
  cannot evaluate the product will not buy it.
* **A failed check never downgrades anyone.** If the provider raises, the last
  known good answer stands. Losing access because the wifi dropped is a worse
  failure than a few minutes of stale state.
* **Switching to demo is an explicit click behind a confirmation.** Never
  automatic. A simulated balance appearing where a real one was, while real
  positions are still open at the exchange, is how somebody gets hurt.
* **`docs/CREDENTIALS.md`** ships inside the build and Preferences links to it:
  where the key lives, how to rotate it in an order that cannot lock you out
  mid window, how to revoke it, what to do if the laptop is stolen, and the
  promise that we will never ask for the private key. The release gate fails a
  build that does not contain it.
* **A real installer**, not a folder. Per user, no administrator prompt, fixed
  AppId so versions upgrade in place, and uninstall asks before touching
  customer data and states plainly that removing the local copy of a key does
  not revoke it at the exchange.
* One bug found and fixed in the installer: a plain `MsgBox` in the uninstall
  step ignores `/SUPPRESSMSGBOXES`, so a silent uninstall hung forever on a
  dialog nobody could see. `SuppressibleMsgBox` with an explicit default fixes
  it. Verified: silent install and uninstall round trip in 2.7 seconds,
  customer data correctly kept.

**Build 7.** The finishing items that were still open.

* **Preliminary name search** in `docs/TRADEMARK.md`. FIRE is not blocked, but
  the bare word is weak: already registered by others in class 9, and in
  finance the term is dominated by "Financial Independence Retire Early",
  which costs us both distinctiveness and discoverability. Recommendation is
  to ship v1 as FIRE, register nothing yet, and fold a real clearance opinion
  into the same attorney conversation as the EULA review.
* **Support policy** in `docs/SUPPORT.md`, and the app now tells the customer
  where to send a bundle instead of referring vaguely to "your support email".
  The address is one constant.
* **The release gate now enforces the finishing items**, but only on beta and
  stable builds, so a dev build stays workable. It blocks a release with no
  support contact, and a release whose licence text still says DRAFT. Both
  proven to block and then to pass.

## 8. Verified state

```
234 tests passing, zero skipped
Packaged FIRE.exe builds and launches (31.8 MB, 965 files)
Installer builds, installs, launches and uninstalls silently (11.7 MB)
A lapsed subscription disables order entry before anyone can click
A redeemed licence re-enables it without a restart
Every window builds and tears down under test
Risk limit proven to block an oversized order through the real UI path
Release gate passes a clean bundle and blocks a planted private key
First run onboarding renders and gates the terminal
Demo mode runs, 12 simulated markets, order entry works end to end
Live adapter fully covered by tests with no network access
Live endpoint ships UNCONFIGURED, asserted by test
No network imports anywhere in the demo package
No private module imports anywhere in src/fire
No PEM blocks or key shaped identifiers anywhere in src/fire
```
