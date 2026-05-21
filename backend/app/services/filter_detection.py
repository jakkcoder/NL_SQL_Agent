"""Routing hint: whether an investor message likely carries filter semantics.

Used by ``app.services.routing.classify_message`` to set ``has_search_filters`` on the
routing state (e.g. for ``greeting_tool`` session bookkeeping). It does **not** parse NL
into a ``SearchPlan`` and is unrelated to the catalog SQL generator.
"""


def message_has_search_filters(message: str, prior_step: str | None = None) -> bool:
    """Return True when the message should be treated as filter-bearing for routing hints."""

    del prior_step  # reserved for session-aware routing extensions
    return bool((message or "").strip())
