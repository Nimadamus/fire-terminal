"""Order planning: turn "spend this much on this side" into a concrete order.

Shared by every venue so the guarantee is written once and tested once. The
audit of the internal tool showed what happens when execution mechanics are
copied per venue: they drift, and the drift is silent because each copy looks
locally correct.

THE GUARANTEE
    count * limit_price <= budget_dollars, always.

An immediate or cancel order can fill any of its contracts at the limit, so
sizing against the cheaper ladder average is wrong: a deep walk then spends
more than the customer typed. Size against the limit.

This module contains no view about whether an order is a good idea. It only
makes the order match the amount that was asked for.
"""
from __future__ import annotations

from typing import Sequence

from fire.core.errors import BookTooThin
from fire.core.models import Book, BookLevel, OrderRequest, Side


def plan_from_book(ticker: str, side: Side, budget_dollars: float,
                   book: Book) -> OrderRequest:
    levels: Sequence[BookLevel] = book.yes if side is Side.YES else book.no
    if not levels:
        raise BookTooThin("There is nothing offered on that side right now.")
    if budget_dollars <= 0:
        raise BookTooThin("Enter an amount above zero.")

    # Walk the visible ladder to find how deep we would have to reach.
    spent, count, limit = 0.0, 0, levels[0].price
    for level in levels:
        if level.price <= 0:
            continue
        if spent + level.price > budget_dollars:
            break
        take = min(level.size, int((budget_dollars - spent) // level.price))
        if take <= 0:
            break
        count += take
        spent += take * level.price
        limit = level.price

    # Enforce the guarantee against the LIMIT, not the ladder average.
    affordable = int(budget_dollars // limit) if limit > 0 else 0
    count = min(count, affordable)

    if count <= 0:
        raise BookTooThin(
            f"${budget_dollars:,.2f} does not buy a single contract at "
            f"{levels[0].price:.2f}."
        )

    request = OrderRequest(ticker=ticker, side=side, limit_price=limit,
                           count=count, budget_dollars=budget_dollars)
    assert request.count * request.limit_price <= budget_dollars + 1e-9
    return request
