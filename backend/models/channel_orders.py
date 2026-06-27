"""Omnichannel — imported online-store orders (OMN-01/03, F-046).

The first connector of the "sell online too" vision (CLAUDE.md / INTENDED_BEHAVIOR
§4.12): an order placed in the merchant's **Salla** online store is pushed to us by
a webhook, materialized as a real POS ``Transactions`` sale (so it lands on the
back-office, decrements the *same* shared stock pool, and is ZATCA-signed like any
sale — OMN-03), and recorded here as the durable channel record linking the external
order to the materialized invoice.

Every row carries ``user_id`` (the merchant's own login account) so reads are scoped
to the owner exactly like every other entity — one client can never see another
client's channel orders (SEC-02). Idempotency is enforced on
``(provider, external_order_id, client_id)`` so re-delivery of the same Salla webhook
never double-books a sale.

``status`` follows the OMN order line ``received`` (ingested, awaiting materialization)
→ ``imported`` (a transaction was created) → ``fulfilled`` (C&C / fulfilment, OMN-05
vision). The one-step ingest the webhook performs lands directly in ``imported``.
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String, Text, UniqueConstraint

from core.database import Base


class Channel_orders(Base):
    __tablename__ = "channel_orders"
    # Idempotency arbiter (OMN/DAT-07): one channel order per
    # (client_id, provider, external_order_id). The ingest path claims the order
    # (inserts status="received") BEFORE minting the ZATCA invoice, so a crash mid-
    # settle — or a concurrent re-delivery racing past the SELECT pre-check — can
    # never double-book a signed invoice; the loser's insert conflicts here.
    __table_args__ = (
        UniqueConstraint(
            "client_id", "provider", "external_order_id",
            name="uq_channel_order_client_provider_ext",
        ),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False, index=True)
    client_id = Column(Integer, nullable=True, index=True)
    # Source channel. "salla" (OMN-01); "zid" (OMN-02) reuses this table later;
    # "deliverect" / "delivery_hero" are the delivery-aggregator middleware
    # connectors (F-060) — the same idempotency mechanism, keyed on
    # (provider, external_order_id, client_id), guards every provider.
    provider = Column(String, nullable=False, default="salla", server_default="salla")
    # The external store/order identity used for routing + idempotent ingest.
    external_order_id = Column(String, nullable=False, index=True)
    external_reference = Column(String, nullable=True)
    # The materialized POS sale (Transactions.id). Null only if no order line could
    # be matched to a product (nothing rung up) — the channel record is still kept.
    transaction_id = Column(Integer, nullable=True, index=True)
    # The order ticket this claim materialized (REV-02). Written before the fiscal
    # settle so a crash mid-settle is recoverable: a re-delivery of a claim still at
    # "received" / transaction_id NULL re-uses this ticket — re-settling it when it
    # never settled, or detecting it already "settled" (DAT-07 crash-AFTER-settle) so
    # it never mints a second invoice. Null when no ticket was opened yet (a fresh
    # claim before ticket creation, or a no-lines order — DAT-08).
    ticket_id = Column(Integer, nullable=True, index=True)
    # received / settling / imported / fulfilled.
    #
    # REV-05: ``settling`` is a short-lived *settle lock* on the claim. The aggregator
    # middleware re-delivers (sometimes concurrently); the resume path (REV-02) used to
    # re-run settlement for ANY claim still at ``received`` with no transaction, with no
    # mutual exclusion, so two concurrent re-deliveries both settled — minting two ZATCA
    # invoices + two KDS tickets for one order. The settler now wins an atomic
    # ``received -> settling`` compare-and-set before any fiscal work; a loser backs off
    # as a duplicate. ``settling_at`` stamps when the lock was taken so a *bounded sweep*
    # can re-open a claim whose settler crashed mid-flight (left it ``settling`` forever)
    # without letting a concurrent caller resume on sight.
    status = Column(String, nullable=False, default="imported", server_default="imported")
    # When the claim entered ``settling`` (the settle lock was acquired). Null unless the
    # claim is currently held for settlement; read only by the bounded recovery sweep.
    settling_at = Column(DateTime(timezone=True), nullable=True)
    customer_name = Column(String, nullable=True)
    customer_phone = Column(String, nullable=True)
    total_amount = Column(Float, nullable=True)
    currency = Column(String, nullable=True, default="SAR", server_default="SAR")
    # The raw webhook payload, retained for audit / re-processing.
    raw_payload = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
