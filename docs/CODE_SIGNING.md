# Signing the Windows build

Unsigned, every customer meets a blue box that says "Windows protected your PC"
and names an unknown publisher. Some of them will click through. A meaningful
share will not, and you will never hear from them, which makes this the most
expensive unfixed thing on the list per dollar it costs to fix.

Researched August 2026. Two things changed recently and both matter.

## What changed

**EV no longer buys instant trust.** Until March 2024 an Extended Validation
certificate skipped the SmartScreen warning immediately. Microsoft removed that.
OV and EV now build SmartScreen reputation the same way, through download
volume. **This makes EV a poor buy for a first launch**: you pay two to three
times more for validation theatre and get the same warning until reputation
accrues either way.

**Private keys can no longer live on your disk.** Since June 2023 the CA/Browser
Forum requires code signing keys to sit on FIPS 140-2 Level 2 hardware. In
practice that means either a USB token posted to you, or a cloud signing
service. A `.pfx` file on the build machine is no longer an option for a
publicly trusted certificate.

**Certificates are shorter now.** From March 2026 the maximum validity is 460
days, roughly fifteen months, so this is a recurring task rather than a
three year one.

## The three options

| Option | Cost | Hardware | Notes |
|---|---|---|---|
| **Azure Artifact Signing** (was Trusted Signing) | **$9.99/month** for up to 5,000 signatures | None, Microsoft holds the key | Individuals in the US and Canada are eligible. Signs from the command line or CI. |
| Sectigo or Comodo OV / Individual Validation | from **$219/year** | USB token posted to you | Works, but you must physically have the token plugged in to build a release |
| DigiCert EV | **$685/year** | USB token or cloud HSM | No SmartScreen advantage any more. Not worth it for this launch. |

## Recommendation

**Azure Artifact Signing at $9.99 a month.** It is the cheapest option, it
removes the hardware token entirely, it works from the build script, and the
individual developer path covers someone in the United States without a
company. Compared with a $219 certificate plus a token you can lose, this is
not a close call.

Fall back to **Sectigo Individual Validation at $219/year** only if the Azure
individual onboarding is closed when you go to sign up, which has happened
before during the preview period.

Do **not** buy EV for launch. Revisit only if a specific customer requires it.

## What you have to do

1. Sign up for Azure Artifact Signing and complete identity validation. Expect
   to provide government ID. Individuals must be in the US or Canada.
2. Create a certificate profile and note the account name, the profile name and
   the endpoint region.
3. Put those three values in the build environment as `FIRE_SIGN_ACCOUNT`,
   `FIRE_SIGN_PROFILE` and `FIRE_SIGN_ENDPOINT`.

Validation is the slow part, so start it before you need it. The rest is
minutes.

## What is already done

`packaging/build.ps1` signs both the application executable and the installer
when those environment variables are present, and skips signing with a warning
when they are not. Nothing else has to change on the day the certificate
arrives.

The order matters and the script already gets it right: sign `FIRE.exe` inside
the bundle **before** the installer is built, then sign the installer itself.
Signing the installer alone leaves the executable it drops on the customer's
disk unsigned, which is exactly the file SmartScreen looks at when they run it.

## What to expect afterwards

The warning does not disappear the moment you sign. Reputation accrues with
download volume, so early customers may still see a milder prompt naming you as
the publisher rather than an unknown one. That is already a large improvement,
and it clears on its own.
