from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CATEGORIES = Literal['web_app', 'saas', 'desktop_tool', 'ai_agent', 'mobile_app', 'game', 'module', 'content_asset', 'revenue_site']
LIFECYCLES = Literal['UNLAUNCHED', 'IN_DEVELOPMENT', 'DISCONTINUED', 'FAILED_COMMERCIALIZATION', 'OPERATING_NO_REVENUE', 'OPERATING_REVENUE', 'ASSET_ONLY']
RIGHTS = Literal['FULL_IP_ASSIGNMENT', 'EXCLUSIVE_LICENSE', 'NON_EXCLUSIVE_LICENSE', 'ASSET_TRANSFER_ONLY', 'BUSINESS_TRANSFER_REVIEW_REQUIRED']

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Register(Strict):
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=12, max_length=128)

    @field_validator('email')
    @classmethod
    def clean_email(cls, email):
        email = email.strip().lower()
        if '@' not in email or '.' not in email.rsplit('@', 1)[-1]:
            raise ValueError('유효한 이메일을 입력하세요.')
        return email


class Login(Strict):
    email: str
    password: str


class ListingCreate(Strict):
    import_id: str | None = Field(default=None, min_length=36, max_length=36)
    title: str = Field(min_length=2, max_length=120)
    description: str = Field(min_length=30, max_length=25000)
    category: CATEGORIES
    lifecycle_status: LIFECYCLES
    sale_rights_type: RIGHTS
    inventory_mode: Literal['ONE_TIME', 'REPEAT_LICENSE'] = 'ONE_TIME'
    price_krw: int = Field(gt=0, le=1_000_000_000)
    tech_stack: list[str] = Field(default_factory=list, max_length=30)
    included_assets: list[str] = Field(min_length=1, max_length=50)
    excluded_assets: list[str] = Field(default_factory=list, max_length=50)
    known_defects: list[str] = Field(default_factory=list, max_length=50)
    required_services: list[str] = Field(default_factory=list, max_length=30)
    monthly_cost_estimate_krw: int | None = Field(default=None, ge=0)
    handover_days_estimate: int | None = Field(default=None, ge=0, le=365)
    seller_support_days: int | None = Field(default=None, ge=0, le=365)
    has_revenue: bool = False
    revenue_krw_claimed: int | None = Field(default=None, ge=0)
    rights_attested: bool = False
    is_demo: bool = False

    @model_validator(mode='after')
    def consistency(self):
        if self.inventory_mode == 'REPEAT_LICENSE' and self.sale_rights_type != 'NON_EXCLUSIVE_LICENSE':
            raise ValueError('반복 판매는 비독점 사용권 매물만 가능합니다.')
        if self.lifecycle_status == 'OPERATING_REVENUE' and not self.has_revenue:
            raise ValueError('매출 발생 상태와 매출 유무가 일치하지 않습니다.')
        if self.has_revenue is False and self.revenue_krw_claimed not in (None, 0):
            raise ValueError('매출이 없는 매물에 양수 매출을 기입할 수 없습니다.')
        return self


class ListingPatch(Strict):
    expected_version: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, min_length=30, max_length=25000)
    category: CATEGORIES | None = None
    lifecycle_status: LIFECYCLES | None = None
    sale_rights_type: RIGHTS | None = None
    price_krw: int | None = Field(default=None, gt=0, le=1_000_000_000)
    tech_stack: list[str] | None = None
    included_assets: list[str] | None = None
    excluded_assets: list[str] | None = None
    known_defects: list[str] | None = None
    required_services: list[str] | None = None
    monthly_cost_estimate_krw: int | None = Field(default=None, ge=0)
    handover_days_estimate: int | None = Field(default=None, ge=0)
    seller_support_days: int | None = Field(default=None, ge=0)
    rights_attested: bool | None = None
    status: Literal['DRAFT', 'PENDING_REVIEW', 'ACTIVE', 'PAUSED'] | None = None


class PreferencesIn(Strict):
    min_budget_krw: int = Field(default=0, ge=0)
    max_budget_krw: int = Field(default=1_000_000, ge=0)
    skill_level: Literal['NONE','BASIC','INTERMEDIATE','ADVANCED'] = 'BASIC'
    objectives: list[str] = Field(default_factory=list)
    preferred_tech_stack: list[str] = Field(default_factory=list)
    max_monthly_cost_krw: int | None = Field(default=None, ge=0)
    risk_tolerance: Literal['LOW','MEDIUM','HIGH'] = 'MEDIUM'

    @model_validator(mode='after')
    def budget(self):
        if self.max_budget_krw < self.min_budget_krw:
            raise ValueError('최대 예산은 최소 예산 이상이어야 합니다.')
        return self


class OfferCreate(Strict):
    listing_id: str
    offered_price_krw: int = Field(gt=0, le=1_000_000_000)
    terms: dict = Field(default_factory=dict)
    expires_at: datetime
    is_demo: Literal[True] = True


class Counter(Strict):
    offered_price_krw: int = Field(gt=0, le=1_000_000_000)
    terms: dict = Field(default_factory=dict)
    expires_at: datetime
    expected_version: int = Field(ge=1)


class Version(Strict):
    expected_version: int = Field(ge=1)


class Transition(Version):
    status: Literal['HANDOVER_IN_PROGRESS','HANDOVER_REVIEW','DEMO_COMPLETED','DISPUTED','CANCELLED']


class CheckCreate(Strict):
    check_key: str = Field(min_length=2, max_length=100)
    description: str = Field(default='', max_length=1500)
    result: Literal['SELLER_SUBMITTED','AGENT_CHECKED','BUYER_CONFIRMED','NEEDS_FIX','NOT_TESTED'] = 'NOT_TESTED'
    evidence_refs: list[str] = Field(default_factory=list)
    remarks: str | None = None


class CheckPatch(Strict):
    result: Literal['SELLER_SUBMITTED','AGENT_CHECKED','BUYER_CONFIRMED','NEEDS_FIX','NOT_TESTED']
    expected_version: int
    evidence_refs: list[str] = Field(default_factory=list)
    remarks: str | None = None


class InspectionCreate(Strict):
    report_type: Literal['STATIC','EXECUTION','HANDOVER','LEGAL_CHECKLIST']
    verdict: Literal['NOT_TESTED','UNVERIFIED','PASS','PARTIAL','FAIL']
    findings: list[dict] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    source_version_sha256: str | None = None
    agent_job_id: str | None = None


class AgentActionCreate(Strict):
    action_type: Literal['SUBMIT_OFFER','COUNTER_OFFER','RECORD_HANDOVER_CHECK','REQUEST_SELLER_FIX','SUGGEST_LISTING_UPDATE']
    resource_id: str
    proposed_payload: dict
    payload_sha256: str = Field(min_length=64, max_length=64)
    expires_at: datetime


class AgentListingSuggestion(Strict):
    """Changes proposed by an external agent; never grants it control of rights, money or status."""
    expected_version: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, min_length=30, max_length=25000)

    @model_validator(mode='after')
    def require_content(self):
        if self.title is None and self.description is None:
            raise ValueError('제안할 제목이나 설명을 입력하세요.')
        return self


class GrantCreate(Strict):
    scopes: list[Literal['listing:read','inspection:read','inspection:write','buyer_profile:read','offer:read','offer:draft','offer:execute','transaction:read','handover:read','handover:report','handover:draft','handover:execute','asset:inspect','listing:draft','listing:execute']] = Field(min_length=1)
    expires_in_hours: int = Field(default=12, ge=1, le=24)


class ReportCreate(Strict):
    listing_id: str
    reason_code: Literal['SUSPECTED_IP_VIOLATION','MISLEADING','UNSAFE_FILE','PERSONAL_DATA','OTHER']
    description: str = Field(default='', max_length=3000)
