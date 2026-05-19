from app.agents.tools import parse_with_context
from app.core.settings import Settings
from app.db.postgres import DatabaseNotConfiguredError, PostgresClient
from app.models.chat import ChatRequest, ChatResponse, PageMeta
from app.models.search_plan import InvestorTab
from app.services.audit import AuditLogger
from app.services.individual_executor import IndividualInvestorExecutor
from app.services.non_individual_executor import NonIndividualInvestorExecutor
from app.services.result_formatter import format_rows_for_chat


class ChatService:
    def __init__(self, db: PostgresClient, settings: Settings) -> None:
        self._db = db
        self._settings = settings
        self._audit = AuditLogger()
        self._individual_executor = IndividualInvestorExecutor(db)
        self._non_individual_executor = NonIndividualInvestorExecutor(db, settings)

    def handle(self, request: ChatRequest) -> ChatResponse:
        limit = request.page_limit or self._settings.default_page_limit
        offset = request.page_offset or 0
        parsed = parse_with_context(request.message, request.messages, limit, offset)
        plan = parsed["plan"]
        validation = parsed["validation"]

        self._audit.log_event(
            "search_plan",
            {
                "investor_tab": plan.investor_tab.value,
                "validation_status": validation.status,
                "arn_code": request.arn_code or self._settings.default_dev_arn,
            },
        )

        if not validation.can_execute:
            return ChatResponse(
                reply=validation.message or "I need more information before searching.",
                needs_clarification=validation.status == "clarification",
                status=validation.status,
            )

        arn_code = request.arn_code or self._settings.default_dev_arn
        try:
            rows = self._execute(plan, arn_code)
        except DatabaseNotConfiguredError as exc:
            return ChatResponse(reply=str(exc), status="error")

        return ChatResponse(
            reply=format_rows_for_chat(rows, plan.page_limit, plan.page_offset),
            rows=rows,
            count=len(rows),
            page=PageMeta(limit=plan.page_limit, offset=plan.page_offset),
        )

    def _execute(self, plan, arn_code: str):
        if plan.investor_tab == InvestorTab.INDIVIDUAL:
            return self._individual_executor.execute(plan, arn_code)
        if plan.investor_tab == InvestorTab.NON_INDIVIDUAL:
            return self._non_individual_executor.execute(plan, arn_code)
        return []
