"""Expected filters per planning/Investor_Filter_Query_Mapping - Individual Investors.csv rows 2-31."""

from dataclasses import dataclass, field

from app.models.search_plan import DEFAULT_ACTIVITY_TYPES, DEFAULT_SYSTEMATIC_PLANS


@dataclass(frozen=True)
class CsvFilterExpectation:
    row: int
    label: str
    query: str
    eligibility: str = "ALL"
    otm: str = "ALL"
    investor_type: str = "ALL"
    investor_subtypes: list[str] = field(default_factory=list)
    holding_mode: str = "ALL"
    systematic_mode: str = "ALL"
    systematic_plans: list[str] | None = None  # None = default all plans when WITH
    activity_mode: str = "ALL"
    activity_types: list[str] | None = None
    activity_duration: str = "1 month"
    name_search: str | None = None
    sql_has_holding: bool = False
    sql_has_systematic: bool = False
    sql_has_activity: bool = False


# Natural-language samples from column 1 of the CSV (individual context added where needed).
INDIVIDUAL_CSV_CASES: list[CsvFilterExpectation] = [
    CsvFilterExpectation(2, "no_filter", "show all individual investors"),
    CsvFilterExpectation(3, "eligibility_yes", "show eligible individual investors", eligibility="YES"),
    CsvFilterExpectation(3, "eligibility_yes_alt", "individual investors with email registered", eligibility="YES"),
    CsvFilterExpectation(4, "eligibility_no", "individual investors without email", eligibility="NO"),
    CsvFilterExpectation(5, "otm_yes", "individual investors with OTM", otm="Y"),
    CsvFilterExpectation(5, "otm_yes_alt", "individual investors with auto debit enabled", otm="Y"),
    CsvFilterExpectation(6, "otm_not_available", "individual investors without OTM", otm="NOT_AVAILABLE"),
    CsvFilterExpectation(7, "investor_active", "show active individual investors", investor_type="ACTIVE"),
    CsvFilterExpectation(7, "investor_active_alt", "individual investors who transacted recently", investor_type="ACTIVE"),
    CsvFilterExpectation(8, "investor_dormant", "show dormant individual investors", investor_type="DORMANT"),
    CsvFilterExpectation(8, "investor_dormant_alt", "inactive individual investors", investor_type="DORMANT"),
    CsvFilterExpectation(9, "subtype_cgf", "individual CGF investors", investor_subtypes=["CGF"]),
    CsvFilterExpectation(10, "subtype_minor", "individual minor investors", investor_subtypes=["MINOR"]),
    CsvFilterExpectation(11, "subtype_others", "individual other investors", investor_subtypes=["OTHERS"]),
    CsvFilterExpectation(
        12,
        "subtype_cgf_minor",
        "individual CGF and minor investors",
        investor_subtypes=["CGF", "MINOR"],
    ),
    CsvFilterExpectation(
        13,
        "holding_with",
        "individual investors who currently hold units",
        holding_mode="WITH",
        sql_has_holding=True,
    ),
    CsvFilterExpectation(
        14,
        "holding_without",
        "individual investors with no holdings",
        holding_mode="WITHOUT",
        sql_has_holding=True,
    ),
    CsvFilterExpectation(
        15,
        "systematic_sip",
        "individual investors with SIP",
        systematic_mode="WITH",
        systematic_plans=["SIP"],
        sql_has_systematic=True,
    ),
    CsvFilterExpectation(
        16,
        "systematic_without_sip",
        "individual investors without SIP",
        systematic_mode="WITHOUT",
        systematic_plans=["SIP"],
        sql_has_systematic=True,
    ),
    CsvFilterExpectation(
        17,
        "systematic_stp",
        "individual investors with STP",
        systematic_mode="WITH",
        systematic_plans=["STP"],
        sql_has_systematic=True,
    ),
    CsvFilterExpectation(
        18,
        "systematic_swp",
        "individual investors with SWP",
        systematic_mode="WITH",
        systematic_plans=["SWP"],
        sql_has_systematic=True,
    ),
    CsvFilterExpectation(
        19,
        "systematic_dtp",
        "individual investors with DTP",
        systematic_mode="WITH",
        systematic_plans=["DTP"],
        sql_has_systematic=True,
    ),
    CsvFilterExpectation(
        20,
        "systematic_flexsip",
        "individual investors with FlexSIP",
        systematic_mode="WITH",
        systematic_plans=["FLEXSIP"],
        sql_has_systematic=True,
    ),
    CsvFilterExpectation(
        21,
        "systematic_flexindex",
        "individual investors with FlexIndex",
        systematic_mode="WITH",
        systematic_plans=["FLEXINDEX"],
        sql_has_systematic=True,
    ),
    CsvFilterExpectation(
        22,
        "systematic_swingstp",
        "individual investors with SwingSTP",
        systematic_mode="WITH",
        systematic_plans=["SWINGSTP"],
        sql_has_systematic=True,
    ),
    CsvFilterExpectation(
        23,
        "systematic_smartswap",
        "individual investors with SmartSwap",
        systematic_mode="WITH",
        systematic_plans=["SMARTSWAP"],
        sql_has_systematic=True,
    ),
    CsvFilterExpectation(
        24,
        "systematic_all",
        "individual investors with any systematic plan",
        systematic_mode="WITH",
        systematic_plans=sorted(DEFAULT_SYSTEMATIC_PLANS),
        sql_has_systematic=True,
    ),
    CsvFilterExpectation(
        25,
        "systematic_without_all",
        "individual investors with no systematic plan",
        systematic_mode="WITHOUT",
        systematic_plans=sorted(DEFAULT_SYSTEMATIC_PLANS),
        sql_has_systematic=True,
    ),
    CsvFilterExpectation(
        26,
        "activity_purchase",
        "individual investors who made a purchase recently",
        activity_mode="WITH",
        activity_types=["PURCHASE"],
        sql_has_activity=True,
    ),
    CsvFilterExpectation(
        27,
        "activity_redemption",
        "individual investors with recent redemption",
        activity_mode="WITH",
        activity_types=["REDEMPTION"],
        sql_has_activity=True,
    ),
    CsvFilterExpectation(
        28,
        "activity_switch",
        "individual investors with switch activity recently",
        activity_mode="WITH",
        activity_types=["SWITCH"],
        sql_has_activity=True,
    ),
    CsvFilterExpectation(
        29,
        "activity_sip",
        "individual investors with SIP transactions recently",
        activity_mode="WITH",
        activity_types=["SIP"],
        sql_has_activity=True,
    ),
    CsvFilterExpectation(
        30,
        "activity_all_types",
        "individual investors with any recent transaction",
        activity_mode="WITH",
        activity_types=sorted(DEFAULT_ACTIVITY_TYPES),
        sql_has_activity=True,
    ),
]
