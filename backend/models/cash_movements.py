"""Cash drawer movements tied to a shift (FIN-04 / POS-09, F-044).

A shift's physical drawer doesn't only hold the opening float plus cash sales
minus cash refunds — a cashier also **pays cash in** (adds change/float),
**pays cash out** (petty-cash purchases, supplier paid from the till) and does a
**cash-drop** (skims cash to the safe). Without recording these, the close-time
drawer reconciliation (``compute_shift_cash_reconciliation``) is wrong the moment
any cash leaves or enters the drawer outside a sale, and the Z/X-report can't show
the payouts line RPT-06 requires.

Each row is owned by ``user_id`` (the cashier's own login account, SEC-02) and tied
to the ``shift_id`` it was recorded against, so one client can never list or affect
another client's drawer movements. ``amount`` is always stored as a **positive
magnitude**; the sign is implied by ``movement_type``:

* ``pay_in``    — cash added to the drawer (e.g. extra change float)  → increases expected cash
* ``pay_out``   — cash paid out of the drawer (petty cash / supplier) → decreases expected cash
* ``cash_drop`` — cash skimmed from the drawer to the safe           → decreases expected cash
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String

from core.database import Base


class Cash_movements(Base):
    __tablename__ = "cash_movements"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    # Owner — the cashier's own login account (SEC-02 scoping).
    user_id = Column(String, nullable=False, index=True)
    client_id = Column(Integer, nullable=True, index=True)
    # The open shift this movement was recorded against (POS-09 drawer tie).
    shift_id = Column(Integer, nullable=False, index=True)
    # pay_in / pay_out / cash_drop
    movement_type = Column(String, nullable=False)
    # Always a positive magnitude; the sign is implied by movement_type.
    amount = Column(Float, nullable=False, default=0)
    reason = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
