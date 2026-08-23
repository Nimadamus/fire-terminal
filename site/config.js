/* Deployment configuration for the FIRE website.
 *
 * This is the ONLY file that changes between a staging deploy and a live one.
 * Nothing secret belongs here: it is served to every visitor. The Stripe keys
 * live in the licence service, which is the only thing that talks to Stripe.
 */
window.FIRE_CONFIG = {
  // Base URL of the licence service, no trailing slash.
  api: "",

  // Where a customer reaches a human.
  supportEmail: "",

  // Direct download for the current release. Left empty until the first
  // installer is published, which hides the download buttons rather than
  // pointing them at a 404.
  downloadUrl: "",
  version: ""
};

window.FIRE_API = window.FIRE_CONFIG.api;

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

  // A build with no licence service cannot take money. Say so plainly rather
  // than letting somebody click a button that silently fails.
  if (!c.api) {
    document.querySelectorAll("[data-plan]").forEach(function (el) {
      el.textContent = "Coming soon";
      el.classList.add("btn-ghost");
      el.classList.remove("btn-primary");
      el.style.pointerEvents = "none";
      el.style.opacity = "0.6";
    });
  }
});
