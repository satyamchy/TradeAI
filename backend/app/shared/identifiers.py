"""Stable identities shared by decisions, monitoring and paper lifecycle views."""

from uuid import UUID, uuid5

POSITION_NAMESPACE = UUID("acaa5b27-6c90-4ae1-a3af-8f40414c8e11")


def position_id_for(
    *, owner_id: int, exchange: str, symbol: str, product_type: str, trade_key: str | None = None
) -> UUID:
    """Return a stable identity for one position lifecycle.

    New Module 3 intents pass their analysis ID as `trade_key`, preventing a
    later trade in the same symbol from sharing an old monitoring trigger.
    Older intents retain the prior user/instrument/product identity.
    """
    identity = (
        f"{owner_id}:trade:{trade_key}"
        if trade_key
        else f"{owner_id}:{exchange.strip().upper()}:{symbol.strip().upper()}:{product_type.strip().upper()}"
    )
    return uuid5(POSITION_NAMESPACE, identity)
