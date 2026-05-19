from collections.abc import Iterable
from typing import Any

from app.core.settings import Settings
from app.db.postgres import PostgresClient
from app.models.search_plan import (
    InvestorSubtype,
    InvestorTypeFilter,
    NonIndividualOtmFilter,
    SearchPlan,
)


class NonIndividualInvestorExecutor:
    """Executes approved Non-Individual investor templates.

    The current portal behavior for combinations is intentionally preserved:
    run each individual filter query separately, then intersect result sets.
    """

    def __init__(self, db: PostgresClient, settings: Settings) -> None:
        self._db = db
        self._settings = settings

    def execute(self, plan: SearchPlan, arn_code: str) -> list[dict[str, Any]]:
        template_names = self._template_names(plan)
        if not template_names:
            sql, params = self._build_query("default", plan, arn_code, plan.page_limit, plan.page_offset)
            return self._db.fetch_all(sql, params)

        if len(template_names) == 1:
            sql, params = self._build_query(template_names[0], plan, arn_code, plan.page_limit, plan.page_offset)
            return self._db.fetch_all(sql, params)

        result_sets = []
        for template_name in template_names:
            sql, params = self._build_query(template_name, plan, arn_code, self._settings.max_intersection_rows, 0)
            result_sets.append(self._db.fetch_all(sql, params))
        return self._intersect_and_page(result_sets, plan.page_limit, plan.page_offset)

    def _template_names(self, plan: SearchPlan) -> list[str]:
        names: list[str] = []
        if plan.non_individual_otm == NonIndividualOtmFilter.YES:
            names.append("otm_yes")
        elif plan.non_individual_otm == NonIndividualOtmFilter.NO:
            names.append("otm_no")

        if plan.investor_type == InvestorTypeFilter.ACTIVE:
            names.append("active")
        elif plan.investor_type == InvestorTypeFilter.DORMANT:
            names.append("dormant")

        subtype_set = set(plan.investor_subtypes)
        if subtype_set == {InvestorSubtype.CGF, InvestorSubtype.MINOR}:
            names.append("cgf_minor")
        else:
            if InvestorSubtype.CGF in subtype_set:
                names.append("cgf")
            if InvestorSubtype.MINOR in subtype_set:
                names.append("minor")
            if InvestorSubtype.OTHERS in subtype_set:
                names.append("others")

        return names

    def _build_query(
        self,
        template_name: str,
        plan: SearchPlan,
        arn_code: str,
        limit: int,
        offset: int,
    ) -> tuple[str, list[Any]]:
        dim_where, investor_join, investor_condition, extra_params = self._template_parts(template_name)
        params: list[Any] = [arn_code]
        params.extend(extra_params(arn_code))
        params.extend([_search_text(plan.name_search), _search_text(plan.name_search), limit, offset])

        sql = f"""
            SELECT
                uuid,
                first_name,
                email,
                mobile_number,
                pan_number,
                dob,
                folio_number,
                BOOL_OR(otm) AS otm
            FROM (
                SELECT DISTINCT ON (i.pan_number)
                    i.pan_number,
                    TRIM(CONCAT(
                        LTRIM(CONCAT(NULLIF(i.first_name, NULL), ' ')),
                        LTRIM(CONCAT(NULLIF(i.middle_name, NULL), ' ')),
                        LTRIM(CONCAT(NULLIF(i.last_name, NULL), ' '))
                    )) AS first_name,
                    i.email,
                    i.mobile_number,
                    i.uuid,
                    i.dob,
                    dim.folio_number,
                    CASE
                        WHEN (
                            ib.acno_valid != 'R'
                            AND ib.paymech IN (
                                SELECT DISTINCT pay_mech
                                FROM payout_mechanism
                                WHERE otm_flag IS TRUE AND active_flag IS TRUE
                            )
                            AND ib.om_umrn IS NOT NULL
                            AND (ib.cease_dt IS NULL OR ib.cease_dt < CURRENT_DATE)
                        ) THEN TRUE
                        ELSE FALSE
                    END AS otm
                FROM corporate_investor i
                INNER JOIN (
                    SELECT DISTINCT dim1.investor_uuid, dim1.folio_number
                    FROM distributor_investor_mapping dim1
                    INNER JOIN sphmf.customer_master cm_base
                        ON cm_base.folio_no = dim1.folio_number
                    WHERE dim1.arn_code = %s
                    {dim_where}
                ) dim ON i.uuid = dim.investor_uuid
                LEFT JOIN sphmf.multiple_bank ib
                    ON ib.folio_no = dim.folio_number
                {investor_join}
                WHERE {investor_condition}
                  AND (CASE WHEN %s <> '' THEN LOWER(i.first_name) ILIKE %s ELSE TRUE END)
                ORDER BY i.pan_number, i.created_time DESC
            ) investors
            GROUP BY uuid, first_name, email, mobile_number, pan_number, dob, folio_number
            ORDER BY first_name ASC
            LIMIT %s OFFSET %s
        """
        return sql, params

    def _template_parts(self, template_name: str):
        if template_name == "otm_yes":
            return (
                """
                AND EXISTS (
                    SELECT
                    FROM sphmf.multiple_bank mb1
                    WHERE dim1.folio_number = mb1.folio_no
                      AND mb1.om_umrn IS NOT NULL
                      AND (mb1.cease_dt IS NULL OR mb1.cease_dt < CURRENT_DATE)
                      AND mb1.paymech IN (
                          SELECT DISTINCT pay_mech
                          FROM payout_mechanism
                          WHERE otm_flag IS TRUE AND active_flag IS TRUE
                      )
                )
                """,
                "",
                "TRUE",
                lambda arn: [],
            )
        if template_name == "otm_no":
            return (
                """
                AND NOT EXISTS (
                    SELECT
                    FROM sphmf.multiple_bank mb1
                    WHERE dim1.folio_number = mb1.folio_no
                      AND mb1.om_umrn IS NOT NULL
                      AND (mb1.cease_dt IS NULL OR mb1.cease_dt < CURRENT_DATE)
                      AND mb1.paymech IN (
                          SELECT DISTINCT pay_mech
                          FROM payout_mechanism
                          WHERE otm_flag IS TRUE AND active_flag IS TRUE
                      )
                )
                """,
                "",
                "TRUE",
                lambda arn: [],
            )
        if template_name == "active":
            return (
                "",
                "",
                """
                i.uuid IN (
                    SELECT DISTINCT map.id
                    FROM (
                        SELECT MAX(DATE(pd.l_trxn_date)) AS last_trxn_date, dim.investor_uuid AS id
                        FROM sphmf.customer_schemes pd
                        INNER JOIN distributor_investor_mapping dim
                            ON pd.folio_no = dim.folio_number
                        WHERE dim.arn_code = %s
                        GROUP BY dim.investor_uuid
                    ) map
                    WHERE CURRENT_DATE - last_trxn_date <= 180
                )
                """,
                lambda arn: [arn],
            )
        if template_name == "dormant":
            return (
                "",
                "",
                """
                i.uuid IN (
                    SELECT DISTINCT map.id
                    FROM (
                        SELECT MAX(DATE(pd.l_trxn_date)) AS last_trxn_date, dim.investor_uuid AS id
                        FROM sphmf.customer_schemes pd
                        INNER JOIN distributor_investor_mapping dim
                            ON pd.folio_no = dim.folio_number
                        WHERE dim.arn_code = %s
                        GROUP BY dim.investor_uuid
                    ) map
                    WHERE CURRENT_DATE - last_trxn_date > 180
                )
                """,
                lambda arn: [arn],
            )
        if template_name == "cgf":
            return (
                "",
                "",
                """
                i.uuid IN (
                    SELECT DISTINCT dim.investor_uuid
                    FROM sphmf.customer_schemes pd
                    INNER JOIN distributor_investor_mapping dim
                        ON dim.folio_number = pd.folio_no
                    WHERE dim.arn_code = %s
                      AND pd.sch_code IN (
                          SELECT schcode
                          FROM sphmf.scheme_setup
                          WHERE cgf_flag = 'C' AND plan_type <> 'D'
                      )
                )
                """,
                lambda arn: [arn],
            )
        if template_name == "minor":
            return (
                "",
                "INNER JOIN sphmf.customer_master cm ON cm.folio_no = dim.folio_number",
                "(cm.inv_type = '02' OR cm.inv_type = '26')",
                lambda arn: [],
            )
        if template_name == "cgf_minor":
            return (
                "",
                "INNER JOIN sphmf.customer_master cm ON cm.folio_no = dim.folio_number",
                """
                (
                    i.uuid IN (
                        SELECT DISTINCT dim.investor_uuid
                        FROM sphmf.customer_schemes pd
                        INNER JOIN distributor_investor_mapping dim
                            ON dim.folio_number = pd.folio_no
                        WHERE dim.arn_code = %s
                          AND pd.sch_code IN (
                              SELECT schcode
                              FROM sphmf.scheme_setup
                              WHERE cgf_flag = 'C' AND plan_type <> 'D'
                          )
                    )
                    OR (cm.inv_type = '02' OR cm.inv_type = '26')
                )
                """,
                lambda arn: [arn],
            )
        if template_name == "others":
            return (
                "",
                "INNER JOIN sphmf.customer_master cm ON cm.folio_no = dim.folio_number",
                """
                i.uuid IN (
                    SELECT DISTINCT dim.investor_uuid
                    FROM sphmf.customer_schemes pd
                    INNER JOIN distributor_investor_mapping dim
                        ON dim.folio_number = pd.folio_no
                    WHERE dim.arn_code = %s
                      AND pd.sch_code NOT IN (
                          SELECT schcode
                          FROM sphmf.scheme_setup
                          WHERE cgf_flag = 'C' AND plan_type <> 'D'
                      )
                )
                AND NOT (cm.inv_type = '02' OR cm.inv_type = '26')
                """,
                lambda arn: [arn],
            )
        return ("", "", "TRUE", lambda arn: [])

    def _intersect_and_page(
        self,
        result_sets: list[list[dict[str, Any]]],
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        if not result_sets:
            return []
        uuid_sets = [set(_uuids(rows)) for rows in result_sets]
        common_uuids = set.intersection(*uuid_sets) if uuid_sets else set()
        row_by_uuid = {str(row["uuid"]): row for row in result_sets[0] if row.get("uuid") is not None}
        rows = [row for uuid, row in row_by_uuid.items() if uuid in common_uuids]
        rows.sort(key=lambda row: str(row.get("first_name") or "").lower())
        return rows[offset : offset + limit]


def _uuids(rows: Iterable[dict[str, Any]]) -> Iterable[str]:
    for row in rows:
        if row.get("uuid") is not None:
            yield str(row["uuid"])


def _search_text(name_search: str | None) -> str:
    if not name_search:
        return ""
    return f"%{name_search.lower()}%"
