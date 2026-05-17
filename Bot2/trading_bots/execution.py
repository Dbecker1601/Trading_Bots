from dataclasses import dataclass


@dataclass(frozen=True)
class EntryPlan:
    action: str
    order_type: str
    time_in_force: str
    allow_chase: bool


def build_entry_plan(action: str, spread_bps: float, max_spread_for_limit_bps: float = 2.0) -> EntryPlan:
    if action not in {"long", "short"}:
        return EntryPlan(action="flat", order_type="none", time_in_force="DAY", allow_chase=False)

    if spread_bps <= max_spread_for_limit_bps:
        return EntryPlan(action=action, order_type="limit", time_in_force="IOC", allow_chase=True)

    return EntryPlan(action=action, order_type="market", time_in_force="IOC", allow_chase=False)
