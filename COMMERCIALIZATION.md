# FIRE Commercialization

Running record of architecture, decisions, what was removed, what is still
blocked, and the launch checklist. Updated as work proceeds.

**Status:** v1 skeleton complete, demo path working end to end, 119 tests green.
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
   DemoVenue                 KalshiVenue
   (no network at all)       (not implemented yet)
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
| Diagnostics | `diagnostics/redact.py`, `bundle.py` | redaction at the write boundary |

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
| `kalshi_live_order.py` (the coupling hub) | `interfaces/venue.py` + per venue execution | interface done, live impl pending |
| `fire_interlock.py`, `shared_book.py`, `market_claim.py` | not reproduced. Single customer, single app, no arbitration needed. | **dropped by design** |
| `fortress_owner.py`, `fire_supervisor.py` | a simple single instance check, when needed | pending |
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

## 5. Bugs found and fixed during the build

* **Order sizing could exceed the stated budget.** The planner walked the
  ladder and sized against the cheaper ladder average, but an immediate or
  cancel order can fill any contract at the limit. A deep walk therefore
  spent more than the amount the customer typed. Now clamped to
  `floor(budget / limit)`. Caught by `test_demo_plan_never_exceeds_budget`.

## 6. Open blockers

| Blocker | Owner | Status |
|---|---|---|
| Written distribution permission from the exchange | Nima | **unsent.** Draft ready. Nothing ships until this resolves. |
| Live adapter not implemented | Claude | next work item, safe to build |
| Onboarding flow | Claude | scheduled |
| Packaging and update feed | Claude | scheduled |
| Billing backend | later | interface exists, no implementation |

## 7. Verified state

```
119 tests passing
Demo mode runs, 12 simulated markets, order entry works end to end
No network imports anywhere in the demo package
No private module imports anywhere in src/fire
No PEM blocks or key shaped identifiers anywhere in src/fire
```
