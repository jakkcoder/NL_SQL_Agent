from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMConfig(BaseModel):
    """Configuration for LLM calls (Google Gemini or AWS Bedrock via LiteLLM)."""

    provider: str
    model: str
    bedrock_model_id: str | None = None
    google_api_key: SecretStr | None = None
    google_cloud_project: str | None = None
    google_cloud_location: str
    google_genai_use_vertexai: bool
    request_timeout_seconds: int
    temperature: float
    max_output_tokens: int | None = None

    @property
    def uses_bedrock(self) -> bool:
        return self.provider.lower() in {"bedrock", "aws-bedrock", "aws_bedrock"}


class AWSConfig(BaseModel):
    """AWS runtime configuration.

    Keep credential values in environment variables or an injected secret
    manager. Do not commit real values to source control.
    """

    region: str
    access_key_id: SecretStr | None = None
    secret_access_key: SecretStr | None = None
    session_token: SecretStr | None = None
    profile: str | None = None
    role_arn: str | None = None
    secrets_manager_prefix: str | None = None


class DatabaseConfig(BaseModel):
    """Resolved database connection settings for one environment."""

    url: SecretStr | None = None
    statement_timeout_ms: int
    pool_min_size: int
    pool_max_size: int
    connect_timeout_seconds: int = 5
    pool_timeout_seconds: int = 10
    environment: str = "dev"


class SearchConfig(BaseModel):
    default_dev_arn: str
    default_page_limit: int
    max_intersection_rows: int


class SecurityConfig(BaseModel):
    allowed_origins: list[str]


class RuntimeConfig(BaseModel):
    environment: str
    log_level: str
    service_name: str

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}

    @property
    def is_development(self) -> bool:
        return self.environment.lower() in {"local", "development", "dev"}


class AppConfig(BaseSettings):
    """Central application configuration loaded from environment variables."""

    environment: str = Field(default="local", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    service_name: str = Field(default="nl-sql-agent", alias="SERVICE_NAME")

    dev_database_url: SecretStr | None = Field(default=None, alias="DEV_DATABASE_URL")
    dev_db_statement_timeout_ms: int = Field(default=15000, alias="DEV_DB_STATEMENT_TIMEOUT_MS")
    dev_db_pool_min_size: int = Field(default=1, alias="DEV_DB_POOL_MIN_SIZE")
    dev_db_pool_max_size: int = Field(default=4, alias="DEV_DB_POOL_MAX_SIZE")
    dev_db_connect_timeout_seconds: int = Field(default=5, alias="DEV_DB_CONNECT_TIMEOUT_SECONDS")
    dev_db_pool_timeout_seconds: int = Field(default=10, alias="DEV_DB_POOL_TIMEOUT_SECONDS")

    prod_database_url: SecretStr | None = Field(default=None, alias="PROD_DATABASE_URL")
    prod_db_statement_timeout_ms: int = Field(default=15000, alias="PROD_DB_STATEMENT_TIMEOUT_MS")
    prod_db_pool_min_size: int = Field(default=2, alias="PROD_DB_POOL_MIN_SIZE")
    prod_db_pool_max_size: int = Field(default=10, alias="PROD_DB_POOL_MAX_SIZE")
    prod_db_connect_timeout_seconds: int = Field(default=5, alias="PROD_DB_CONNECT_TIMEOUT_SECONDS")
    prod_db_pool_timeout_seconds: int = Field(default=10, alias="PROD_DB_POOL_TIMEOUT_SECONDS")

    default_dev_arn: str = Field(default="ARN-0411", alias="DEFAULT_DEV_ARN")
    default_page_limit: int = Field(default=25, alias="DEFAULT_PAGE_LIMIT")
    max_intersection_rows: int = Field(default=5000, alias="MAX_INTERSECTION_ROWS")

    dynamic_investor_sql_enabled: bool = Field(default=False, alias="DYNAMIC_INVESTOR_SQL_ENABLED")
    dynamic_sql_llm_model: str | None = Field(default=None, alias="DYNAMIC_SQL_LLM_MODEL")
    router_llm_model: str | None = Field(default=None, alias="ROUTER_LLM_MODEL")
    query_generator_llm_model: str | None = Field(default=None, alias="QUERY_GENERATOR_LLM_MODEL")
    query_generator_max_output_tokens: int | None = Field(default=None, alias="QUERY_GENERATOR_MAX_OUTPUT_TOKENS")
    query_generator_catalog_max_chars: int = Field(default=200_000, alias="QUERY_GENERATOR_CATALOG_MAX_CHARS")
    query_generator_schema_contract_max_chars: int = Field(
        default=120_000,
        alias="QUERY_GENERATOR_SCHEMA_CONTRACT_MAX_CHARS",
    )
    query_generator_guide_only: bool = Field(
        default=True,
        alias="QUERY_GENERATOR_GUIDE_ONLY",
    )

    llm_provider: str = Field(default="bedrock", alias="LLM_PROVIDER")
    # Root ADK agent (routing + tool calls): prefer a small/fast Bedrock model.
    bedrock_model_id: str = Field(
        default="anthropic.claude-3-haiku-20240307-v1:0",
        alias="BEDROCK_MODEL_ID",
    )
    bedrock_root_model_id: str | None = Field(default=None, alias="BEDROCK_ROOT_MODEL_ID")
    # Catalog SQL generator (large filter_catalog_json in one shot): large-context Bedrock model.
    bedrock_query_generator_model_id: str = Field(
        default="anthropic.claude-3-sonnet-20240229-v1:0",
        alias="BEDROCK_QUERY_GENERATOR_MODEL_ID",
    )
    google_api_key: SecretStr | None = Field(default=None, alias="GOOGLE_API_KEY")
    google_adk_model: str = Field(default="gemini-2.0-flash", alias="GOOGLE_ADK_MODEL")
    google_cloud_project: str | None = Field(default=None, alias="GOOGLE_CLOUD_PROJECT")
    google_cloud_location: str = Field(default="us-central1", alias="GOOGLE_CLOUD_LOCATION")
    google_genai_use_vertexai: bool = Field(default=False, alias="GOOGLE_GENAI_USE_VERTEXAI")
    llm_request_timeout_seconds: int = Field(default=60, alias="LLM_REQUEST_TIMEOUT_SECONDS")
    llm_temperature: float = Field(default=0.0, alias="LLM_TEMPERATURE")
    llm_max_output_tokens: int | None = Field(default=None, alias="LLM_MAX_OUTPUT_TOKENS")

    aws_region: str = Field(default="ap-south-1", alias="AWS_REGION")
    aws_access_key_id: SecretStr | None = Field(default=None, alias="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: SecretStr | None = Field(default=None, alias="AWS_SECRET_ACCESS_KEY")
    aws_session_token: SecretStr | None = Field(default=None, alias="AWS_SESSION_TOKEN")
    aws_profile: str | None = Field(default=None, alias="AWS_PROFILE")
    aws_role_arn: str | None = Field(default=None, alias="AWS_ROLE_ARN")
    aws_secrets_manager_prefix: str | None = Field(default=None, alias="AWS_SECRETS_MANAGER_PREFIX")

    filter_catalog_path: str | None = Field(default=None, alias="FILTER_CATALOG_PATH")
    filter_catalog_sqlite_path: str | None = Field(default=None, alias="FILTER_CATALOG_SQLITE_PATH")
    dev_local_sqlite_mirror: str | None = Field(default=None, alias="DEV_LOCAL_SQLITE_MIRROR")
    dev_investor_search_use_sqlite: bool = Field(default=False, alias="DEV_INVESTOR_SEARCH_USE_SQLITE")
    adk_web_ui: bool | None = Field(default=None, alias="ADK_WEB_UI")

    allowed_origins: str = Field(
        default="http://localhost:8000,http://localhost:3000,http://127.0.0.1:5500,null",
        alias="ALLOWED_ORIGINS",
    )

    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @field_validator("default_dev_arn", mode="after")
    @classmethod
    def normalize_default_dev_arn(cls, value: str) -> str:
        """Distributor scope for dev/local runs; keep a single safe default when unset or blank."""

        s = (value or "").strip()
        return s or "ARN-0411"

    @field_validator(
        "dev_database_url",
        "prod_database_url",
        "google_api_key",
        "google_cloud_project",
        "aws_access_key_id",
        "aws_secret_access_key",
        "aws_session_token",
        "aws_profile",
        "aws_role_arn",
        "aws_secrets_manager_prefix",
        "llm_max_output_tokens",
        "dynamic_sql_llm_model",
        "router_llm_model",
        "query_generator_llm_model",
        "query_generator_max_output_tokens",
        "bedrock_root_model_id",
        "filter_catalog_sqlite_path",
        "dev_local_sqlite_mirror",
        mode="before",
    )
    @classmethod
    def empty_string_as_none(cls, value):
        if value == "":
            return None
        return value

    @property
    def runtime(self) -> RuntimeConfig:
        return RuntimeConfig(
            environment=self.environment,
            log_level=self.log_level,
            service_name=self.service_name,
        )

    @property
    def serve_adk_web_ui(self) -> bool:
        """Serve ADK chat UI at /dev-ui (and redirect / → /dev-ui/) when True."""

        if self.adk_web_ui is not None:
            return self.adk_web_ui
        return self.runtime.is_development

    @property
    def dev_database(self) -> DatabaseConfig:
        return DatabaseConfig(
            url=self.dev_database_url,
            statement_timeout_ms=self.dev_db_statement_timeout_ms,
            pool_min_size=self.dev_db_pool_min_size,
            pool_max_size=self.dev_db_pool_max_size,
            connect_timeout_seconds=self.dev_db_connect_timeout_seconds,
            pool_timeout_seconds=self.dev_db_pool_timeout_seconds,
            environment="dev",
        )

    @property
    def prod_database(self) -> DatabaseConfig:
        return DatabaseConfig(
            url=self.prod_database_url,
            statement_timeout_ms=self.prod_db_statement_timeout_ms,
            pool_min_size=self.prod_db_pool_min_size,
            pool_max_size=self.prod_db_pool_max_size,
            connect_timeout_seconds=self.prod_db_connect_timeout_seconds,
            pool_timeout_seconds=self.prod_db_pool_timeout_seconds,
            environment="prod",
        )

    @property
    def database(self) -> DatabaseConfig:
        """Active database config selected from APP_ENV."""
        if self.runtime.is_production:
            return self.prod_database
        return self.dev_database

    @property
    def search(self) -> SearchConfig:
        return SearchConfig(
            default_dev_arn=self.default_dev_arn,
            default_page_limit=self.default_page_limit,
            max_intersection_rows=self.max_intersection_rows,
        )

    @property
    def bedrock_root_model_id_resolved(self) -> str:
        """Bedrock model id for the ADK root agent (small/fast)."""

        raw = (self.bedrock_root_model_id or self.bedrock_model_id or "").strip()
        return raw or "anthropic.claude-3-haiku-20240307-v1:0"

    @property
    def bedrock_query_generator_model_id_resolved(self) -> str:
        """Bedrock model id for ``run_catalog_sql_generator_llm`` (large context)."""

        return (self.bedrock_query_generator_model_id or "").strip() or (
            "anthropic.claude-3-sonnet-20240229-v1:0"
        )

    @property
    def llm(self) -> LLMConfig:
        """Root ADK agent LLM (greeting vs tool routing)."""

        if self.llm_provider.lower() in {"bedrock", "aws-bedrock", "aws_bedrock"}:
            model = f"bedrock/{self.bedrock_root_model_id_resolved}"
            bedrock_id = self.bedrock_root_model_id_resolved
        else:
            model = self.google_adk_model
            bedrock_id = self.bedrock_model_id

        return LLMConfig(
            provider=self.llm_provider,
            model=model,
            bedrock_model_id=bedrock_id,
            google_api_key=self.google_api_key,
            google_cloud_project=self.google_cloud_project,
            google_cloud_location=self.google_cloud_location,
            google_genai_use_vertexai=self.google_genai_use_vertexai,
            request_timeout_seconds=self.llm_request_timeout_seconds,
            temperature=self.llm_temperature,
            max_output_tokens=self.llm_max_output_tokens,
        )

    @property
    def aws(self) -> AWSConfig:
        return AWSConfig(
            region=self.aws_region,
            access_key_id=self.aws_access_key_id,
            secret_access_key=self.aws_secret_access_key,
            session_token=self.aws_session_token,
            profile=self.aws_profile,
            role_arn=self.aws_role_arn,
            secrets_manager_prefix=self.aws_secrets_manager_prefix,
        )

    @property
    def security(self) -> SecurityConfig:
        return SecurityConfig(allowed_origins=self.cors_origins)

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    @property
    def database_url_value(self) -> str | None:
        active = self.database.url
        return active.get_secret_value() if active else None

    @property
    def dev_local_sqlite_mirror_file_url(self) -> str | None:
        """``sqlite:///...`` when ``DEV_LOCAL_SQLITE_MIRROR`` points at an existing file in dev."""

        if not self.runtime.is_development:
            return None
        raw = (self.dev_local_sqlite_mirror or "").strip()
        if not raw:
            return None
        path = Path(raw)
        if not path.is_absolute():
            backend_root = Path(__file__).resolve().parents[2]
            path = backend_root / path
        if path.is_file():
            return f"sqlite:///{path.resolve()}"
        return None

    @property
    def dev_use_sqlite_investor_search(self) -> bool:
        """Run default Individual list queries on the SQLite mirror (development only)."""

        if not self.runtime.is_development:
            return False
        if not self.dev_investor_search_use_sqlite:
            return False
        return self.dev_local_sqlite_mirror_file_url is not None

    @property
    def filter_catalog_refresh_database_url(self) -> str | None:
        """PostgreSQL warehouse URL or ``sqlite:///...`` for filter catalog merge only."""

        mirror = self.dev_local_sqlite_mirror_file_url
        if mirror:
            return mirror
        raw = (self.filter_catalog_sqlite_path or "").strip()
        if raw:
            path = Path(raw)
            if not path.is_absolute():
                backend_root = Path(__file__).resolve().parents[2]
                path = backend_root / path
            if path.is_file():
                return f"sqlite:///{path.resolve()}"
        return self.database_url_value

    @property
    def dynamic_sql_llm_model_resolved(self) -> str:
        """Model id for dynamic SQL ReAct engine (LiteLLM format, e.g. bedrock/...)."""

        if self.dynamic_sql_llm_model and self.dynamic_sql_llm_model.strip():
            raw = self.dynamic_sql_llm_model.strip()
            if self.llm_provider.lower() in {"bedrock", "aws-bedrock", "aws_bedrock"} and not raw.startswith(
                "bedrock/"
            ):
                return f"bedrock/{raw}"
            return raw
        return self.llm.model

    def _optional_litellm_model(self, raw: str | None, *, fallback: str) -> str:
        if raw and str(raw).strip():
            rid = str(raw).strip()
            if self.llm_provider.lower() in {"bedrock", "aws-bedrock", "aws_bedrock"} and not rid.startswith(
                "bedrock/"
            ):
                return f"bedrock/{rid}"
            return rid
        return fallback

    @property
    def router_llm_model_resolved(self) -> str:
        """Small classifier model (LiteLLM id); defaults to main ``llm`` model."""

        return self._optional_litellm_model(self.router_llm_model, fallback=self.llm.model)

    @property
    def query_generator_llm_model_resolved(self) -> str:
        """Large-context catalog SQL author (LiteLLM id).

        Resolution order:
        1. ``QUERY_GENERATOR_LLM_MODEL`` if set
        2. ``BEDROCK_QUERY_GENERATOR_MODEL_ID`` when ``LLM_PROVIDER`` is Bedrock
        3. ``DYNAMIC_SQL_LLM_MODEL`` / root ``llm`` model (non-Bedrock or legacy override)
        """

        if self.query_generator_llm_model and self.query_generator_llm_model.strip():
            return self._optional_litellm_model(
                self.query_generator_llm_model,
                fallback=self.llm.model,
            )
        if self.llm_provider.lower() in {"bedrock", "aws-bedrock", "aws_bedrock"}:
            return f"bedrock/{self.bedrock_query_generator_model_id_resolved}"
        return self._optional_litellm_model(
            self.dynamic_sql_llm_model,
            fallback=self.llm.model,
        )

    @property
    def query_generator_max_output_tokens_resolved(self) -> int | None:
        if self.query_generator_max_output_tokens is not None:
            return self.query_generator_max_output_tokens
        return self.llm_max_output_tokens

    @property
    def dev_database_url_value(self) -> str | None:
        return self.dev_database_url.get_secret_value() if self.dev_database_url else None

    @property
    def prod_database_url_value(self) -> str | None:
        return self.prod_database_url.get_secret_value() if self.prod_database_url else None

    def production_missing_values(self) -> list[str]:
        """Return required values missing for a production deployment."""

        if not self.runtime.is_production:
            return []

        required = {
            "PROD_DATABASE_URL": self.prod_database_url_value,
            "ALLOWED_ORIGINS": self.allowed_origins,
        }
        if self.llm_provider.lower() in {"bedrock", "aws-bedrock", "aws_bedrock"}:
            has_aws_credentials = bool(
                self.aws_access_key_id_value and self.aws_secret_access_key_value
            ) or bool(self.aws_profile) or bool(self.aws.role_arn)
            required["AWS credentials (keys or profile)"] = has_aws_credentials
            required["BEDROCK_MODEL_ID"] = self.bedrock_model_id
        else:
            required["GOOGLE_API_KEY or GOOGLE_GENAI_USE_VERTEXAI=true"] = (
                self.google_api_key_value or self.google_genai_use_vertexai
            )
        return [name for name, value in required.items() if not _has_real_value(value)]

    @property
    def google_api_key_value(self) -> str | None:
        return self.google_api_key.get_secret_value() if self.google_api_key else None

    @property
    def aws_access_key_id_value(self) -> str | None:
        return self.aws_access_key_id.get_secret_value() if self.aws_access_key_id else None

    @property
    def aws_secret_access_key_value(self) -> str | None:
        return (
            self.aws_secret_access_key.get_secret_value()
            if self.aws_secret_access_key
            else None
        )


@lru_cache
def get_config() -> AppConfig:
    return AppConfig()


def apply_runtime_env(config: AppConfig | None = None) -> None:
    """Export config values to process env for LiteLLM/Boto3 SDKs."""

    import os

    config = config or get_config()

    if config.google_api_key_value:
        os.environ["GOOGLE_API_KEY"] = config.google_api_key_value

    aws = config.aws
    os.environ["AWS_REGION"] = aws.region
    os.environ["AWS_DEFAULT_REGION"] = aws.region
    os.environ["AWS_REGION_NAME"] = aws.region

    # Do not export placeholder .env values — they override ~/.aws/credentials from `aws configure`.
    for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_PROFILE"):
        os.environ.pop(key, None)

    access_key = aws.access_key_id.get_secret_value() if aws.access_key_id else None
    secret_key = aws.secret_access_key.get_secret_value() if aws.secret_access_key else None
    session_token = aws.session_token.get_secret_value() if aws.session_token else None

    if _has_real_value(access_key):
        os.environ["AWS_ACCESS_KEY_ID"] = access_key
    if _has_real_value(secret_key):
        os.environ["AWS_SECRET_ACCESS_KEY"] = secret_key
    if _has_real_value(session_token):
        os.environ["AWS_SESSION_TOKEN"] = session_token
    if _has_real_value(aws.profile):
        os.environ["AWS_PROFILE"] = aws.profile


def get_settings() -> AppConfig:
    """Backward-compatible alias for modules that expect get_settings()."""

    return get_config()


def _has_real_value(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if not isinstance(value, str):
        return bool(value)
    normalized = value.strip().lower()
    return bool(normalized) and not normalized.startswith("replace-with")
