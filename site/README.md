# The FIRE website

Static. No build step, no framework, no server. Deploy the contents of this
directory to any static host.

## Before it goes live

Edit `config.js`. It is the only file that differs between a staging deploy and
a live one, and nothing in it is secret:

| Field | What it is |
|---|---|
| `api` | Base URL of the licence service, no trailing slash |
| `supportEmail` | Where a customer reaches a human |
| `downloadUrl` | Direct link to the current installer |
| `version` | Shown next to the download button |

While `api` is empty the pricing buttons say **Coming soon** and cannot be
clicked, and while `downloadUrl` is empty the download buttons are hidden. That
is deliberate: a button that silently fails is worse than one that is honestly
not there yet.

## Pages

| Path | Purpose |
|---|---|
| `/` | The sales page |
| `/welcome` | After checkout. Shows the licence key and the four setup steps |
| `/account` | Sends a customer to the Stripe billing portal |
| `/legal/*` | Generated from `docs/LEGAL.md` by `site/build_legal.py` |

The legal pages are generated, not hand written. Run `python site/build_legal.py`
after any change to `docs/LEGAL.md`, so the text a customer reads and the text a
lawyer reviews cannot drift apart.

## Recommended hosting

**Cloudflare Pages** for the site: free, fast, clean URLs, and it serves
`/legal/risk` from `legal/risk.html` without configuration.

**GitHub Releases** for the installer. Version specific URLs that never change,
no bandwidth cost, and a hash published next to each file.

Keep `updates.json` on the website rather than with the installer, so a release
can be pulled by editing one small file we control.
