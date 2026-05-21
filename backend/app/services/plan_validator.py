from dataclasses import dataclass
from typing import Literal

from app.models.search_plan import (
    ALLOWED_DURATIONS,
    BinaryFilter,
    IndividualOtmFilter,
    InvestorTab,
    NonIndividualOtmFilter,
    SearchPlan,
)
from app.services.filter_catalog import get_filter_catalog


@dataclass(frozen=True)
class ValidationResult:
    status: Literal["valid", "clarification", "out_of_scope"]
    message: str | None = None

    @property
    def can_execute(self) -> bool:
        return self.status == "valid"


class PlanValidator:
    """Deterministic gatekeeper for all agent-produced search plans."""

    def validate(self, plan: SearchPlan) -> ValidationResult:
        if plan.investor_tab == InvestorTab.PENDING:
            return ValidationResult(
                status="out_of_scope",
                message="Pending investors are not in scope for this MVP. Please ask for Individual or Non-Individual investors.",
            )

        if plan.unsupported_reasons:
            return ValidationResult(status="out_of_scope", message=" ".join(plan.unsupported_reasons))

        if plan.investor_tab == InvestorTab.NON_INDIVIDUAL:
            return ValidationResult(
                status="out_of_scope",
                message=(
                    "Non-Individual investor search is not available in this MVP. "
                    "I can help with Individual investor search only."
                ),
            )

        catalog = get_filter_catalog()
        allowed_durations = set(catalog.get_values("activity_duration")) or ALLOWED_DURATIONS
        if plan.activity.duration not in allowed_durations:
            return ValidationResult(
                status="out_of_scope",
                message="That duration is not supported. Use 1, 2, 3, or 6 months; 1, 2, or 3 years; or this financial year.",
            )

        invalid_scheme = self._first_invalid_scheme(plan)
        if invalid_scheme:
            return ValidationResult(
                status="out_of_scope",
                message=f"Scheme code '{invalid_scheme}' is not in the allowed catalog. Use ALL or a valid scheme from the distributor menu.",
            )

        if plan.investor_tab == InvestorTab.NON_INDIVIDUAL and plan.has_individual_only_filters:
            return ValidationResult(
                status="out_of_scope",
                message="That filter is only available for Individual investors in the current MVP.",
            )

        return ValidationResult(status="valid")

    def _first_invalid_scheme(self, plan: SearchPlan) -> str | None:
        catalog = get_filter_catalog()
        for schemes in (plan.holding.schemes, plan.systematic.schemes, plan.activity.schemes):
            for scheme in schemes:
                if scheme == "ALL":
                    continue
                if not catalog.allows("scheme_codes", scheme):
                    return scheme
        return None

    def has_any_filter(self, plan: SearchPlan) -> bool:
        return (
            bool(plan.name_search)
            or plan.individual_otm != IndividualOtmFilter.ALL
            or plan.non_individual_otm != NonIndividualOtmFilter.ALL
            or bool(plan.investor_subtypes)
            or plan.holding.mode != BinaryFilter.ALL
            or plan.systematic.mode != BinaryFilter.ALL
            or plan.activity.mode != BinaryFilter.ALL
        )
