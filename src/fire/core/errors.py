"""Customer facing error taxonomy.

Rule: a customer never sees a stack trace and never sees an exchange payload.
Every failure that can reach the screen is one of these, and every one of them
carries `remedy` describing what the person can actually do about it.
"""
from __future__ import annotations


class FireError(Exception):
    """Base for anything we are willing to show a customer."""

    title = "Something went wrong"
    remedy = "Try again. If it keeps happening, open Diagnostics and send a support bundle."

    def __init__(self, detail: str = "", *, remedy: str | None = None):
        self.detail = detail
        if remedy:
            self.remedy = remedy
        super().__init__(detail or self.title)

    def as_display(self) -> dict[str, str]:
        return {"title": self.title, "detail": self.detail, "remedy": self.remedy}


class SetupIncomplete(FireError):
    title = "FIRE is not connected to an account yet"
    remedy = "Open Setup and add your exchange API credentials, or switch to Demo mode."


class CredentialsInvalid(FireError):
    title = "Your API credentials were rejected"
    remedy = ("Check the key ID and private key in Setup. If you rotated your key on the "
              "exchange, paste the new one.")


class CredentialsUnreadable(FireError):
    title = "FIRE could not read your saved credentials"
    remedy = ("Your operating system keychain refused access. Unlock it and restart FIRE, "
              "or re-enter your credentials in Setup.")


class ConnectionLost(FireError):
    title = "Lost connection to the exchange"
    remedy = "Check your internet connection. FIRE keeps retrying and reconnects on its own."


class RateLimited(FireError):
    title = "The exchange is rate limiting FIRE"
    remedy = "FIRE has slowed down automatically. Prices update less often until this clears."


class MarketUnavailable(FireError):
    title = "That market is not open"
    remedy = "Wait for the next window to open, or pick another coin."


class BookTooThin(FireError):
    title = "Not enough contracts available at your limit"
    remedy = "Lower the amount, or raise your limit price and try again."


class RiskLimitExceeded(FireError):
    title = "That order is larger than your risk limit"
    remedy = "Lower the amount, or raise the maximum loss limit in Preferences."


class OrderRejected(FireError):
    title = "The exchange rejected the order"
    remedy = "Nothing was bought and nothing was charged. Check your balance and try again."


class EntitlementRequired(FireError):
    title = "Your FIRE subscription is not active"
    remedy = "Open Account to restore or renew your subscription. Demo mode stays available."


class ExchangeNotConfigured(FireError):
    """Raised while the approved API path has not been supplied to the build."""
    title = "Live trading is not available in this build"
    remedy = "Demo mode is fully available. Live trading unlocks in a future update."


class DemoModeOnly(FireError):
    """Raised if anything ever tries to route a demo action to a live venue."""
    title = "Blocked: demo activity cannot reach a live account"
    remedy = "This is a safety stop. Nothing was sent. Please report it with a support bundle."


class TradingDisabled(FireError):
    """This installation is a viewer. It refuses before any request is built.

    Not a permission error from the exchange: FIRE never gets that far. The
    order path stops inside the application, so a read only install cannot
    reach a trading endpoint even if the credential would have allowed it.
    """
    title = "This copy of FIRE cannot place orders"
    remedy = ("It is running in live view mode, which is read only by design. "
              "Trading happens elsewhere.")
