from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class GoalSnapshot:
    account_name: str
    current_value: float
    initial_capital: float
    recovery_target: float
    recovery_months: int
    current_loss: float
    current_loss_pct: float
    gain_needed: float
    gain_needed_pct: float
    required_monthly_return_pct: float
    required_total_return_pct: float
    post_recovery_monthly_goal_pct: float
    post_recovery_annualized_goal_pct: float
    realism_label: str
    risk_note: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _realism_label(monthly_return_pct: float) -> tuple[str, str]:
    if monthly_return_pct <= 2:
        return "Reasonable", "Target is in a range that can fit patient ETF-style investing."
    if monthly_return_pct <= 5:
        return "Ambitious", "Target likely needs favorable market conditions and tight risk control."
    if monthly_return_pct <= 8:
        return "Aggressive", "Target likely requires concentrated exposure or tactical trades."
    return "Very aggressive", "Target implies high drawdown risk if forced."


def compute_goal_snapshot(portfolio: dict[str, Any]) -> GoalSnapshot:
    current_value = float(portfolio.get("current_value", 0))
    initial_capital = float(portfolio.get("initial_capital", current_value))
    recovery_target = float(portfolio.get("recovery_target", initial_capital))
    recovery_months = max(1, int(portfolio.get("recovery_months", 3)))
    post_goal_pct = float(portfolio.get("target_monthly_return_after_recovery_pct", 0))

    current_loss = current_value - initial_capital
    current_loss_pct = (current_loss / initial_capital) * 100 if initial_capital else 0.0
    gain_needed = recovery_target - current_value
    gain_needed_pct = (gain_needed / current_value) * 100 if current_value else 0.0
    required_monthly = ((recovery_target / current_value) ** (1 / recovery_months) - 1) * 100 if current_value else 0.0
    required_total = ((recovery_target / current_value) - 1) * 100 if current_value else 0.0
    annualized_goal = ((1 + post_goal_pct / 100) ** 12 - 1) * 100 if post_goal_pct else 0.0
    label, note = _realism_label(required_monthly)

    return GoalSnapshot(
        account_name=str(portfolio.get("account_name", "Brokerage")),
        current_value=round(current_value, 2),
        initial_capital=round(initial_capital, 2),
        recovery_target=round(recovery_target, 2),
        recovery_months=recovery_months,
        current_loss=round(current_loss, 2),
        current_loss_pct=round(current_loss_pct, 2),
        gain_needed=round(gain_needed, 2),
        gain_needed_pct=round(gain_needed_pct, 2),
        required_monthly_return_pct=round(required_monthly, 2),
        required_total_return_pct=round(required_total, 2),
        post_recovery_monthly_goal_pct=round(post_goal_pct, 2),
        post_recovery_annualized_goal_pct=round(annualized_goal, 2),
        realism_label=label,
        risk_note=note,
    )
