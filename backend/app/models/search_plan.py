"""Filter enums and defaults for ``filter_catalog.json`` (catalog SQL path)."""

from enum import Enum


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
