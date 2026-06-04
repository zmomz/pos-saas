"""Commission / revenue-split computation (RSL-01, F-029).

A single pure function decomposes a client's gross subscription fee into the
platform master's share and the agent's net margin, so the split is unit-testable
in isolation from the sale/payment transaction. See ``models/commission_ledger``
for the data model and ``routers/tenant.py::pay_client_subscription`` for the
write site.
"""
from typing import Tuple


def compute_commission_split(
    gross: float,
    wholesale_price: float,
    client_slots: int,
) -> Tuple[float, float]:
    """Split ``gross`` into ``(master_cut, agent_net)``.

    The master's cut is the per-client amortized wholesale of the agent's package
    — ``wholesale_price / client_slots`` — i.e. what the agent paid the platform
    for this one client slot. It is clamped to ``[0, gross]`` so the platform
    never claims more than was actually collected (a loss-leader fee below
    wholesale yields a zero-margin agent_net, never a negative master_cut). The
    agent keeps the remainder.

    The invariant ``master_cut + agent_net == gross`` always holds (both are
    rounded to 2 decimals and ``agent_net`` is derived by subtraction), so the
    ledger reconciles. When the package can't be resolved (``client_slots <= 0``)
    the whole fee falls to the agent and the master cut is zero — a safe,
    non-blocking degradation that still writes a balanced row.
    """
    gross = round(float(gross or 0), 2)
    slots = int(client_slots or 0)
    if slots > 0:
        per_slot = float(wholesale_price or 0) / slots
    else:
        per_slot = 0.0
    master_cut = round(max(0.0, min(per_slot, gross)), 2)
    agent_net = round(gross - master_cut, 2)
    return master_cut, agent_net
