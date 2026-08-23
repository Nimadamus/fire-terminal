# FIRE Launch Checklist

**Nothing on this list is cleared. FIRE must not be distributed, sold,
advertised or publicly described until the blocking items are resolved in
writing.** Safe engineering continues in the meantime; that is deliberate and
carries no permission implication.

Legend: **BLOCKING** stops launch outright. **REQUIRED** must be done before
launch but is within our control. **OPEN** needs an answer we do not have.

---

## A. Distribution permission

| # | Item | Type | State |
|---|---|---|---|
| A1 | Written authorization to distribute software other members use for their own trading | **BLOCKING** | Message drafted at `docs/KALSHI_AUTHORIZATION_REQUEST.md`, **not sent** |
| A2 | Confirmation that supplying software to members who each hold their own API key and their own developer agreement is not sublicensing | **BLOCKING** | Open |
| A3 | Confirmation that local caching of market data on the end user's own machine, for that user's own trading, is in scope | **BLOCKING** | Open |
| A4 | Prior written approval for any marketing that references the exchange | **BLOCKING** | Open |

The relevant developer agreement language, quoted:

> "Use of Kalshi APIs is expressly limited to facilitating a member's own
> trading on the Exchange; all other usages are disallowed and may result in
> account suspension."

> 3.2. Facilitating trading or account creation by other members
> 3.7. Sublicensing the API for use by a third party
> 6.4. You must obtain prior written approval from Kalshi prior to releasing
> any statements ... including promotional or marketing materials

**The stated penalty is account suspension.** Our own live trading account is
the thing at risk, which is why A1 to A4 are blocking rather than advisory.

## B. Customer authentication and credentials

| # | Item | Type | State |
|---|---|---|---|
| B1 | Every customer supplies their own API key; FIRE ships with none | REQUIRED | **Done**, enforced by test |
| B2 | Credentials stored via OS secret store, never plaintext | REQUIRED | **Done** (DPAPI) |
| B3 | Each customer accepts the exchange developer agreement themselves | REQUIRED | **Done**, explicit acknowledgement before credentials, gated by test |
| B4 | Confirm whether the exchange requires per-application registration | **OPEN** | Ask in A1 |
| B5 | Credential revocation and rotation path documented for customers | REQUIRED | **Done**, `docs/CREDENTIALS.md` ships inside the build and Preferences links to it; release gate fails without it |

## C. Data rights

| # | Item | Type | State |
|---|---|---|---|
| C1 | No market data leaves the customer's machine | REQUIRED | **Done** by architecture |
| C2 | We aggregate no customer market data server side | REQUIRED | **Done**, no server exists |
| C3 | Confirm display and caching limits on market data | **OPEN** | Ask in A1 |
| C4 | No redistribution of exchange data between customers | REQUIRED | **Done** by architecture |

## D. Rate limits and technical conduct

| # | Item | Type | State |
|---|---|---|---|
| D1 | Exponential backoff on all retries | REQUIRED | **Done** (`transport.py`, with jitter) |
| D2 | Bounded retry counts | REQUIRED | **Done** (4 attempts, then a customer error) |
| D3 | Per customer polling budget that will not trip limits at scale | REQUIRED | **Done** (client side rate gate on the endpoint profile) |
| D4 | Confirm whether limits are per key or per application | **OPEN** | Ask in A1 |
| D5 | Graceful degradation when limited, never a retry storm | REQUIRED | **Done** (poll interval triples while degraded) |

## E. Branding and trademark

| # | Item | Type | State |
|---|---|---|---|
| E1 | Product name is "FIRE", not derived from any exchange mark | REQUIRED | **Done** |
| E2 | No exchange logo, wordmark or colour in product or marketing | REQUIRED | **Done** |
| E3 | Clear statement that FIRE is independent and unaffiliated | REQUIRED | **Drafted**; naming any exchange still gated on A4 |
| E4 | Trademark search on "FIRE" for trading software | REQUIRED | **Preliminary search done**, `docs/TRADEMARK.md`. Not blocked, but the bare word is weak: already registered by others in class 9 and swamped in finance by "Financial Independence Retire Early". Needs a real clearance opinion, same attorney conversation as F1. |

## F. Regulatory posture

| # | Item | Type | State |
|---|---|---|---|
| F1 | No trade recommendations, signals or scoring anywhere in the product | REQUIRED | **Done**, enforced by test |
| F2 | No discretion over any customer account, no custody of funds | REQUIRED | **Done** by architecture |
| F3 | No advice tailored to any customer's account or circumstances | REQUIRED | **Done** by architecture |
| F4 | No performance claims in any marketing, ever | REQUIRED | Standing rule |
| F5 | Confirm CFTC Rule 4.14(a)(9) posture with counsel before launch | **OPEN** | Not started. Same attorney conversation as F1 and E4. |

**F4 is absolute.** The trading record must never appear in any marketing
material. It converts a software sale into a performance claim and invites
scrutiny of the automated system, which is not what is being sold.

## G. Consumer facing requirements

| # | Item | Type | State |
|---|---|---|---|
| G1 | EULA with no warranty and a liability cap | REQUIRED | **Drafted** (`docs/LEGAL.md`), needs legal review |
| G2 | Risk disclosure: trading can lose money, software can fail | REQUIRED | **Shown in setup** before any live account connects; wording still needs legal review |
| G3 | Privacy policy covering what FIRE stores and where | REQUIRED | **Drafted**, needs legal review |
| G4 | Refund and cancellation terms | REQUIRED | **Drafted** (14 day full refund), needs legal review |
| G5 | Support channel and response expectation | REQUIRED | **Policy written**, `docs/SUPPORT.md`, and the app tells the customer where to send a bundle from one constant. **The address itself is your decision**; the release gate blocks a beta or stable build while it is empty. |
| G6 | Business entity in place before taking payment | REQUIRED | **Yours.** Stripe can onboard an individual, so this is not strictly blocking, but the licence agreement's governing law clause stays incomplete without it. |

## H. Product readiness

| # | Item | Type | State |
|---|---|---|---|
| H1 | No proprietary logic in the customer build | REQUIRED | **Done**, enforced by test |
| H2 | Demo mode usable without any account | REQUIRED | **Done** |
| H3 | Support bundle redacts secrets, verified | REQUIRED | **Done**, enforced by test |
| H4 | No stack traces reach the customer | REQUIRED | **Done** |
| H5 | Signed installer, code signing certificate | REQUIRED | **Installer done**: `FIRE-<version>-setup.exe`, 11.7 MB, per user, no admin prompt, silent install and uninstall verified. **Certificate still needed** and is on you: unsigned means a SmartScreen warning on every first run. |
| H6 | Update feed and version check | REQUIRED | **Done end to end**: the client checks, the terminal shows one quiet line with a download button, and `packaging/make_feed.py` generates the feed with a checksum. Only the hosting URL is outstanding. |
| H7 | Crash reporting, sanitized | REQUIRED | **Done**, no locals rendered, credential frames withheld, discarded if not verifiably clean |

---

## Release gate

`packaging/verify_bundle.py` runs against a built bundle and exits non zero
if it finds private key material, a private module, internal vocabulary, or an
oversized bundle. Verified working in both directions: it passes a clean build
and blocks a deliberately planted private key.

## The one thing to do next

**Send A1.** Every blocking item resolves through that one conversation, and
until it comes back the answer to "can we sell this" is unknown rather than
yes. Engineering continues regardless, because none of it is wasted if the
answer is yes and all of it is cheap if the answer is no.
