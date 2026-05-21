from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class InvestorTab(str, Enum):
    INDIVIDUAL = "individual"
    NON_INDIVIDUAL = "non_individual"
    UNKNOWN = "unknown"
    PENDING = "pending"


class BinaryFilter(str, Enum):
    ALL = "ALL"
    WITH = "WITH"
    WITHOUT = "WITHOUT"


class InvestorTypeFilter(str, Enum):
    ALL = "ALL"
    ACTIVE = "ACTIVE"
    DORMANT = "DORMANT"


class EligibilityFilter(str, Enum):
    ALL = "ALL"
    YES = "YES"
    NO = "NO"


class IndividualOtmFilter(str, Enum):
    ALL = "ALL"
    YES = "Y"
    NO = "NOT_AVAILABLE"


class NonIndividualOtmFilter(str, Enum):
    ALL = "ALL"
    YES = "YES"
    NO = "NO"


class InvestorSubtype(str, Enum):
    CGF = "CGF"
    MINOR = "MINOR"
    OTHERS = "OTHERS"


class SystematicPlanType(str, Enum):
    SIP = "SIP"
    STP = "STP"
    SWP = "SWP"
    FLEXSTP = "FLEXSTP"
    FLEXINDEX = "FLEXINDEX"
    DTP = "DTP"
    SWINGSTP = "SWINGSTP"
    SMARTSWAP = "SMARTSWAP"
    FLEXSIP = "FLEXSIP"


class ActivityType(str, Enum):
    PURCHASE = "PURCHASE"
    SWITCH = "SWITCH"
    REDEMPTION = "REDEMPTION"
    SIP = "SIP"
    DTP = "DTP"
    STP = "STP"
    SWP = "SWP"
    FLEXSIP = "FLEXSIP"


ALLOWED_DURATIONS = {
    "1 month",
    "2 month",
    "3 month",
    "6 month",
    "1 year",
    "2 year",
    "3 year",
    "this financial year",
}


DEFAULT_OPTIONS = ["Z", "N", "Y"]
DEFAULT_SYSTEMATIC_PLANS = [plan.value for plan in SystematicPlanType]
DEFAULT_ACTIVITY_TYPES = [activity.value for activity in ActivityType]


class HoldingFilter(BaseModel):
    mode: BinaryFilter = BinaryFilter.ALL
    schemes: list[str] = Field(default_factory=lambda: ["ALL"])
    inv_options: list[str] = Field(default_factory=lambda: DEFAULT_OPTIONS.copy())


class SystematicFilter(BaseModel):
    mode: BinaryFilter = BinaryFilter.ALL
    plans: list[str] = Field(default_factory=lambda: DEFAULT_SYSTEMATIC_PLANS.copy())
    schemes: list[str] = Field(default_factory=lambda: ["ALL"])
    inv_options: list[str] = Field(default_factory=lambda: DEFAULT_OPTIONS.copy())


class ActivityFilter(BaseModel):
    mode: BinaryFilter = BinaryFilter.ALL
    activity_types: list[str] = Field(default_factory=lambda: DEFAULT_ACTIVITY_TYPES.copy())
    schemes: list[str] = Field(default_factory=lambda: ["ALL"])
    inv_options: list[str] = Field(default_factory=lambda: DEFAULT_OPTIONS.copy())
    duration: str = "1 month"


class SearchPlan(BaseModel):
    investor_tab: InvestorTab = InvestorTab.INDIVIDUAL
    name_search: str | None = None
    city: str | None = Field(
        default=None,
        description="Registered address city on sphmf.customer_master.city (folio-scoped).",
    )
    age_min: int | None = Field(
        default=None,
        ge=0,
        le=130,
        description="Minimum investor age in full years (from public.investor.dob).",
    )
    age_max: int | None = Field(
        default=None,
        ge=0,
        le=130,
        description="Maximum investor age in full years (from public.investor.dob).",
    )
    eligibility: EligibilityFilter = EligibilityFilter.ALL
    individual_otm: IndividualOtmFilter = IndividualOtmFilter.ALL
    non_individual_otm: NonIndividualOtmFilter = NonIndividualOtmFilter.ALL
    investor_type: InvestorTypeFilter = InvestorTypeFilter.ALL
    investor_subtypes: list[InvestorSubtype] = Field(default_factory=list)
    holding: HoldingFilter = Field(default_factory=HoldingFilter)
    systematic: SystematicFilter = Field(default_factory=SystematicFilter)
    activity: ActivityFilter = Field(default_factory=ActivityFilter)
    sort_key: str = "first_name"
    sort_order: str = "ASC"
    page_limit: int = 25
    page_offset: int = 0
    unsupported_reasons: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def align_age_bounds(self) -> SearchPlan:
        if self.age_min is not None and self.age_max is not None and self.age_min > self.age_max:
            self.age_min, self.age_max = self.age_max, self.age_min
        return self

    @property
    def has_individual_only_filters(self) -> bool:
        return (
            bool(self.city and self.city.strip())
            or self.age_min is not None
            or self.age_max is not None
            or self.eligibility != EligibilityFilter.ALL
            or self.holding.mode != BinaryFilter.ALL
            or self.systematic.mode != BinaryFilter.ALL
            or self.activity.mode != BinaryFilter.ALL
        )


class SearchPlanLLMOutput(BaseModel):
    """Strict JSON contract returned by the search-plan LLM builder."""

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    investor_tab: InvestorTab
    normalized_query: str
    name_search: str | None = None
    city: str | None = None
    age_min: int | None = Field(default=None, ge=0, le=130)
    age_max: int | None = Field(default=None, ge=0, le=130)
    eligibility: EligibilityFilter = EligibilityFilter.ALL
    individual_otm: IndividualOtmFilter = IndividualOtmFilter.ALL
    non_individual_otm: NonIndividualOtmFilter = NonIndividualOtmFilter.ALL
    investor_type: InvestorTypeFilter = InvestorTypeFilter.ALL
    investor_subtypes: list[InvestorSubtype] = Field(default_factory=list)
    holding_mode: BinaryFilter = BinaryFilter.ALL
    systematic_mode: BinaryFilter = BinaryFilter.ALL
    systematic_plans: list[str] = Field(default_factory=list)
    activity_mode: BinaryFilter = BinaryFilter.ALL
    activity_types: list[str] = Field(default_factory=list)
    activity_duration: str = "1 month"
    unsupported_reasons: list[str] = Field(default_factory=list)
    plan_source: Literal["llm"] = "llm"

    @field_validator("activity_duration", mode="before")
    @classmethod
    def default_activity_duration(cls, value: str | None) -> str:
        if value is None or (isinstance(value, str) and not value.strip()):
            return "1 month"
        return str(value).strip().lower()
