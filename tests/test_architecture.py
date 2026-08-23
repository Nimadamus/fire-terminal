"""Architectural rules, enforced as tests.

These are the guarantees we sell. If one of them breaks, the build is not
shippable, so they are tests rather than documentation.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "fire"

NETWORK_MODULES = {
    "requests", "urllib", "urllib3", "http", "httpx", "socket",
    "websocket", "websockets", "ftplib", "telnetlib", "smtplib", "aiohttp",
}

# Anything that would mean the private bot leaked into the customer build.
FORBIDDEN_NAMES = {
    "fair_model", "kalshi_live_order", "fire_interlock", "shared_book",
    "market_claim", "trade_lease", "global_kill", "fortress_owner",
    "order_gateway", "order_ack", "fill_reconcile", "integrity_gate",
    "proc_census", "runtime_identity", "health_checks", "filter_heartbeat",
    "filter_manifest_report", "shadow_compare", "btc15m_fire_paper",
    "eth15m_fire_paper", "sol15m_fire_paper", "xrp15m_fire_paper",
    "doge15m_fire_paper", "crypto_panel", "crypto_universe",
    "kalshi_price_widget", "kalshi_risk_cap", "fire_render_log",
}

# Internal vocabulary that must never reach a customer build.
FORBIDDEN_STRINGS = (
    "C4_FORTRESS", "c9_tick", "ponr_arm", "PONR", "BOT WINDOW",
    "MODEL_REGISTRY", "fortress_v2", "FORTRESS", "live auto lane",
    "qualification", "candidate selection",
)

ALLOWED_STRING_FILES = {"test_architecture.py"}


def _py_files(root: pathlib.Path):
    return sorted(root.rglob("*.py"))


def _imports(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module.split(".")[0])
    return found


@pytest.mark.parametrize("path", _py_files(SRC / "venues" / "demo"),
                         ids=lambda p: p.name)
def test_demo_package_cannot_reach_the_network(path: pathlib.Path):
    """Demo mode is separated structurally, not by a UI toggle. If the demo
    package cannot import a network library, a demo order cannot reach a live
    endpoint even if every other guard fails."""
    offending = _imports(path) & NETWORK_MODULES
    assert not offending, f"{path.name} imports network modules: {sorted(offending)}"


@pytest.mark.parametrize("path", _py_files(SRC), ids=lambda p: str(p.relative_to(SRC)))
def test_no_private_bot_imports(path: pathlib.Path):
    offending = _imports(path) & FORBIDDEN_NAMES
    assert not offending, f"{path} imports private bot modules: {sorted(offending)}"


@pytest.mark.parametrize("path", _py_files(SRC), ids=lambda p: str(p.relative_to(SRC)))
def test_no_internal_vocabulary(path: pathlib.Path):
    if path.name in ALLOWED_STRING_FILES:
        return
    text = path.read_text(encoding="utf-8")
    hits = [s for s in FORBIDDEN_STRINGS if s in text]
    assert not hits, f"{path} contains internal vocabulary: {hits}"


# The redaction module has to contain the patterns it detects, so the literal
# PEM marker is expected there and only there.
PEM_PATTERN_ALLOWED = {"redact.py"}


@pytest.mark.parametrize("path", _py_files(SRC), ids=lambda p: str(p.relative_to(SRC)))
def test_no_embedded_secrets(path: pathlib.Path):
    """No key IDs, no PEM blocks, no bundled credentials of any kind."""
    import re
    text = path.read_text(encoding="utf-8")
    if path.name not in PEM_PATTERN_ALLOWED:
        assert "-----BEGIN" not in text, f"{path} contains a PEM block"
    uuids = re.findall(
        r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
        r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b", text)
    assert not uuids, f"{path} contains UUID-shaped identifiers: {uuids}"


def test_interfaces_expose_no_strategy_surface():
    """The venue interface must offer no place to hang proprietary logic."""
    text = (SRC / "interfaces" / "venue.py").read_text(encoding="utf-8")
    tree = ast.parse(text)
    methods = {n.name for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef)}
    banned = {"fair_value", "probability", "qualify", "should_trade",
              "select_candidate", "edge", "signal", "score"}
    assert not (methods & banned), f"strategy-shaped methods on the venue interface: {methods & banned}"


# -- the licence service ----------------------------------------------------
SERVER = pathlib.Path(__file__).resolve().parents[1] / "server"

# The service shares exactly one thing with the application: the token format.
# Anything else would mean the billing backend could reach into trading code.
SERVER_ALLOWED_FIRE_IMPORTS = {"fire.entitlement.token"}


@pytest.mark.parametrize("path", _py_files(SERVER),
                         ids=lambda p: str(p.relative_to(SERVER)))
def test_the_service_only_shares_the_token_format(path: pathlib.Path):
    import ast
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        module = ""
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
        elif isinstance(node, ast.Import):
            module = node.names[0].name
        if module.startswith("fire."):
            assert module in SERVER_ALLOWED_FIRE_IMPORTS, (
                f"{path.name} imports {module}; the licence service must not "
                f"reach into the application")


@pytest.mark.parametrize("path", _py_files(SERVER),
                         ids=lambda p: str(p.relative_to(SERVER)))
def test_the_service_embeds_no_secrets(path: pathlib.Path):
    """Signing keys and Stripe keys come from the environment, never source."""
    text = path.read_text(encoding="utf-8")
    assert "-----BEGIN" not in text, f"{path} contains a PEM block"
    for marker in ("sk_live_", "sk_test_", "whsec_", "rk_live_"):
        assert marker not in text, f"{path} contains a Stripe key"
