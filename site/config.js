/* Deployment configuration for the FIRE website.
 *
 * This is the ONLY file that changes between a staging deploy and a live one.
 * Nothing secret belongs here: it is served to every visitor. The Stripe keys
 * live in the licence service, which is the only thing that talks to Stripe.
 */
window.FIRE_CONFIG = {
  // Base URL of the licence service, no trailing slash.
  //
  // Leave as "" when the service is serving this site itself, which is the
  // default arrangement: same origin, no CORS, one thing to deploy. Set it to
  // a full URL only if the site is hosted somewhere separate.
  api: "",          // same origin: the service serves this site

  // Flip to true only when payments are live AND the exchange has authorised
  // distribution in writing. While it is false the page shows prices and a
  // waitlist instead of buy buttons, which is honest and still collects the
  // people who would have bought.
  selling: false,

  // Lemon Squeezy hosted checkout, one URL per plan. They are the merchant of
  // record, so the buy buttons are plain links and this site never touches a
  // card or a payment API.
  checkoutMonthly: "https://fireterminalapp.lemonsqueezy.com/checkout/buy/2d7763bd-a79b-4417-9844-d2bb99998812",
  checkoutAnnual: "https://fireterminalapp.lemonsqueezy.com/checkout/buy/76eec69b-d2ae-41c5-a74e-973143a8e450",

  // Where a customer reaches a human.
  supportEmail: "nj2121@gmail.com",

  // Direct download for the current release. Left empty until the first
  // installer is published, which hides the download buttons rather than
  // pointing them at a 404.
  downloadUrl: "",
  version: ""
};

window.FIRE_API = window.FIRE_CONFIG.api;   // "" means same origin

document.addEventListener("DOMContentLoaded", function () {
  var c = window.FIRE_CONFIG;

  if (c.supportEmail) {
    document.querySelectorAll('a[href="mailto:SUPPORT_EMAIL"]').forEach(function (a) {
      a.href = "mailto:" + c.supportEmail;
      if (a.dataset.showAddress) { a.textContent = c.supportEmail; }
    });
  }

  document.querySelectorAll("[data-download]").forEach(function (el) {
    if (c.downloadUrl) {
      el.href = c.downloadUrl;
      el.removeAttribute("hidden");
    } else {
      el.setAttribute("hidden", "hidden");
    }
  });

  document.querySelectorAll("[data-version]").forEach(function (el) {
    el.textContent = c.version || "";
  });

  // Before selling opens, the buy buttons come off entirely and the waitlist
  // takes their place. A button that silently fails is worse than one that is
  // honestly not there yet.
  var open = c.selling === true
             && Boolean(c.checkoutMonthly || c.checkoutAnnual || c.api);
  var waitlist = document.getElementById("waitlist");
  if (!open) {
    document.querySelectorAll("[data-plan]").forEach(function (el) {
      el.remove();
    });
    if (waitlist) { waitlist.hidden = false; }
    document.querySelectorAll('a[href="#pricing"].btn').forEach(function (el) {
      el.textContent = "Join the waitlist";
    });
    // The hero promised a trial. There is no trial to start yet, so do not
    // promise one.
    var note = document.getElementById("hero-note");
    if (note) {
      note.textContent = "Not on sale yet. Leave your address below and you "
        + "will hear the day it opens, at the founding price.";
    }
  } else if (waitlist) {
    waitlist.hidden = true;
  }
});
