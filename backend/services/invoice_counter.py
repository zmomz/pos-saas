"""Atomic fiscal-number minting (DAT-05).

Every fiscal document (a sale invoice, an offline-synced sale, a credit note)
draws its sequential number from the owning client's ``invoice_counter``. Minting
it with a read-modify-write (``counter = client.invoice_counter + 1``) races under
concurrency — two sales that both read the same value mint the *same* fiscal
number. :func:`mint_invoice_number` increments the counter with a single atomic
``UPDATE ... SET invoice_counter = invoice_counter + 1 RETURNING invoice_counter``
inside the caller's transaction, so concurrent sales always read back distinct,
sequential values. The unique index on ``(client_id, invoice_number)`` is the
last-line backstop. Does **not** commit — the number is consumed atomically with
the sale it numbers.
"""
from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.clients import Clients


async def mint_invoice_number(
    db: AsyncSession, client_id: int, prefix: str = "INV"
) -> str:
    """Atomically consume the next counter value for ``client_id`` and format it.

    Returns ``f"{prefix}-{client_id:04d}-{counter:06d}"`` where ``counter`` is the
    post-increment value read back from the same UPDATE. ``prefix`` is ``INV`` for
    a sale and ``CRN`` for a credit note.
    """
    counter = (
        await db.execute(
            update(Clients)
            .where(Clients.id == client_id)
            .values(invoice_counter=func.coalesce(Clients.invoice_counter, 0) + 1)
            .returning(Clients.invoice_counter)
        )
    ).scalar_one()
    return f"{prefix}-{client_id:04d}-{counter:06d}"
