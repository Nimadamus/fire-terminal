# FIRE distribution channel map

Researched 2026-08-23. Product state at time of writing: v1 feature complete,
demo only, staging at https://fire-terminal.onrender.com (free plan, spins down),
no domain, no Stripe account, no code signing, Kalshi A1-A4 unresolved.

## The gate that decides almost every row

`LAUNCH_CHECKLIST.md` A4: prior written Kalshi approval is required before any
marketing that references the exchange. FIRE is a Kalshi terminal, so a listing
that names Kalshi is exactly that marketing. Stated penalty is account
suspension, and the account at risk is the live trading account. Every row that
describes the product publicly is therefore gated on A1/A4, waitlist framing
included. Two mitigations exist and both are Nima's call, not mine:

- **Exchange-neutral copy.** Describe FIRE as a prediction-market trading
  terminal, never naming Kalshi, and let the user connect their own API key.
  Reduces A4 exposure. Does not resolve A1 (permission to distribute software
  other members use for their own trading).
- **Wait for the written answer.** The request is drafted at
  `docs/KALSHI_AUTHORIZATION_REQUEST.md` and has not been sent.

## Legend

- **POST NOW** publishable today without touching the gate
- **AFTER SITE** good fit, needs the permanent domain plus live Stripe
- **AFTER KALSHI** needs A1/A4 answered in writing
- **REJECT** bad fit, prohibited, uneconomic, or sells the wrong thing

## Master tracker

| CHANNEL | URL | STATUS | COST | COMMISSION | APPROVAL | DIRECT LINK OK | ACCOUNT | LISTING URL | NEXT ACTION |
|---|---|---|---|---|---|---|---|---|---|
| Product Hunt | producthunt.com | AFTER KALSHI | free | none | no review, ranked by votes | yes | none | - | Nima creates maker profile now; PH rewards 30 days of prior activity |
| Hacker News Show HN | news.ycombinator.com | AFTER KALSHI | free | none | none | yes | none | - | needs a working demo readers can run |
| Indie Hackers | indiehackers.com | AFTER KALSHI | free | none | none | yes | none | - | product page plus build-in-public post |
| BetaList | betalist.com | AFTER SITE | free tier, paid fast track | none | editorial review | yes | none | - | pre-launch waitlist fits BetaList exactly; copy ready |
| Microsoft Store | partner.microsoft.com | AFTER KALSHI | registration now free | 15% if MS handles commerce, 0% with own commerce | certification, identity verification | yes | none | - | **company account required**: Store policy requires one when financial information is core. Needs Nima's ID and MSIX signing |
| AlternativeTo | alternativeto.net | AFTER SITE | free | none | community moderation | yes | none | - | list as alternative to existing trading terminals |
| SaaSHub | saashub.com | AFTER SITE | free | none | light review | yes | none | - | free listing, dofollow link |
| Capterra / GetApp | capterra.com | AFTER SITE | free listing | pay-per-click optional | vendor verification | yes | none | - | category: trading / investment management |
| G2 | g2.com | AFTER SITE | free listing | paid plans from ~$3k/yr to reply to reviews | vendor verification | yes | none | - | free profile only, skip paid tier |
| SourceForge | sourceforge.net | AFTER SITE | free | none | none | yes | none | - | accepts commercial Windows software |
| Slant | slant.co | AFTER SITE | free | none | community | yes | none | - | answer "best prediction market tools" |
| Uneed / Peerlist / Launching Next | various | AFTER SITE | free, some paid boosts | none | light | yes | none | - | low effort, low return, batch them |
| r/Kalshi | reddit.com/r/Kalshi | AFTER KALSHI | free | none | subreddit rules | varies | betlegend (existing) | - | read rules; this is the highest-intent audience and the highest A4 exposure |
| r/predictionmarkets | reddit.com/r/predictionmarkets | AFTER KALSHI | free | none | subreddit rules | varies | betlegend | - | same |
| r/SideProject | reddit.com/r/SideProject | AFTER SITE | free | none | promo allowed | yes | betlegend | - | exchange-neutral framing works here |
| r/algotrading | reddit.com/r/algotrading | REJECT | - | - | - | - | - | - | self-promotion of paid tools is not welcome; posting there burns the account |
| Kalshi Discord / community | - | AFTER KALSHI | free | none | community rules | varies | none | - | do not post before written approval |
| X @betlegend | x.com | AFTER KALSHI | free | none | none | yes | **exists** | - | X prohibits paid promotion of financial-risk products; organic posts only |
| AppSumo | sell.appsumo.com | REJECT | free to apply | AppSumo takes roughly 60-70% | heavy review | n/a | none | - | lifetime-deal model at 80-95% off destroys a $59/mo price and locks in per-seat API risk forever |
| StackSocial / Dealify | - | REJECT | - | similar take | review | n/a | none | - | same economics as AppSumo |
| Acquire.com / Flippa / SideProjectors | - | REJECT | - | - | - | - | - | - | these sell the business or the codebase. We are selling access |
| CodeCanyon / Envato | - | REJECT | - | - | - | - | - | - | source-code marketplace |
| Gumroad | gumroad.com | REJECT as storefront | free | 10% flat | none | yes | none | - | Stripe direct is already built and cheaper; keep Gumroad only as a fallback if Stripe onboarding stalls |
| itch.io | - | REJECT | - | - | - | - | - | - | games platform |
| Paid directory farms | - | REJECT | $50-500 each | - | - | - | - | - | backlink dumps, no buyers |

## What only Nima can do

1. Send `docs/KALSHI_AUTHORIZATION_REQUEST.md` and get A1-A4 answered in writing.
2. Buy `fireterminal.app` (verified available at last check) and map it in Render.
3. Create the FIRE Stripe account and save the test key where `server/setup_stripe.py` expects it.
4. Create the platform accounts. I do not create accounts or accept terms as you;
   every row above that says "none" needs your signup, and Microsoft Store
   additionally needs a company account plus government ID verification.
5. Decide exchange-neutral copy versus waiting for written approval.

Once 1-4 are done, everything in `LISTING_COPY.md` is ready to paste and I can
drive the submissions.
