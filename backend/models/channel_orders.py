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

from sqlalchemy import Column, DateTime, Float, Integer, String, Text

from core.database import Base


class Channel_orders(Base):
    __tablename__ = "channel_orders"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False, index=True)
    client_id = Column(Integer, nullable=True, index=True)
    # Source channel. "salla" today; "zid" (OMN-02) reuses this table later.
    provider = Column(String, nullable=False, default="salla", server_default="salla")
    # The external store/order identity used for routing + idempotent ingest.
    external_order_id = Column(String, nullable=False, index=True)
    external_reference = Column(String, nullable=True)
    # The materialized POS sale (Transactions.id). Null only if no order line could
    # be matched to a product (nothing rung up) — the channel record is still kept.
    transaction_id = Column(Integer, nullable=True, index=True)
    # received / imported / fulfilled.
    status = Column(String, nullable=False, default="imported", server_default="imported")
    customer_name = Column(String, nullable=True)
    customer_phone = Column(String, nullable=True)
    total_amount = Column(Float, nullable=True)
    currency = Column(String, nullable=True, default="SAR", server_default="SAR")
    # The raw webhook payload, retained for audit / re-processing.
    raw_payload = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
