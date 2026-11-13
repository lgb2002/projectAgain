"""Strict, human-reviewed V2 negotiation terms and legacy compatibility."""
from datetime import timezone
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from typing import Literal
from .models import Listing

SUPPORT_LIMITS = {0: 0, 7: 3, 14: 5, 30: 10}
SCOPE_CODES = {'SETUP_GUIDANCE', 'EXISTING_FUNCTION_GUIDANCE', 'CODE_STRUCTURE_GUIDANCE'}
RIGHTS = {'FULL_IP_ASSIGNMENT', 'EXCLUSIVE_LICENSE', 'NON_EXCLUSIVE_LICENSE',
          'ASSET_TRANSFER_ONLY', 'BUSINESS_TRANSFER_REVIEW_REQUIRED'}

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')

class SupportTerms(Strict):
    days: Literal[0, 7, 14, 30]
    included_case_limit: int = Field(ge=0, le=30)
    scope_codes: list[Literal['SETUP_GUIDANCE', 'EXISTING_FUNCTION_GUIDANCE', 'CODE_STRUCTURE_GUIDANCE']] = Field(default_factory=list, max_length=3)
    reply_goal_hours: int = Field(default=72, ge=24, le=336)
    is_reply_goal_guaranteed: Literal[False] = False
    exceptions_note: str = Field(default='', max_length=600)

    @model_validator(mode='after')
    def check(self):
        if self.days == 0 and self.included_case_limit != 0:
            raise ValueError('지원 없음은 일반 기술 지원 0건이어야 합니다.')
        if self.days > 0 and self.included_case_limit == 0:
            raise ValueError('지원 기간이 있으면 최소 1건 이상이어야 합니다.')
        if self.days > 0 and not self.scope_codes:
            raise ValueError('지원 범위를 선택해 주세요.')
        if len(self.scope_codes) != len(set(self.scope_codes)):
            raise ValueError('지원 범위 중복은 허용하지 않습니다.')
        return self

class OfferTermsV2(Strict):
    schema_version: Literal[2]
    price_krw: int = Field(gt=0, le=1_000_000_000)
    rights_type: Literal['FULL_IP_ASSIGNMENT', 'EXCLUSIVE_LICENSE', 'NON_EXCLUSIVE_LICENSE',
                         'ASSET_TRANSFER_ONLY', 'BUSINESS_TRANSFER_REVIEW_REQUIRED']
    included_assets: list[str] = Field(min_length=1, max_length=50)
    excluded_assets: list[str] = Field(default_factory=list, max_length=50)
    handover_days: int = Field(ge=0, le=365)
    support: SupportTerms
    buyer_conditions_note: str = Field(default='', max_length=1500)

    @model_validator(mode='after')
    def check(self):
        if len(self.included_assets) != len(set(self.included_assets)) or set(self.included_assets) & set(self.excluded_assets):
            raise ValueError('포함 자산과 제외 자산이 중복되면 안 됩니다.')
        return self


def recommended_support(days):
    days = days if days in SUPPORT_LIMITS else 0
    return {'days': days, 'included_case_limit': SUPPORT_LIMITS[days],
            'scope_codes': ['SETUP_GUIDANCE', 'EXISTING_FUNCTION_GUIDANCE'] if days else [],
            'reply_goal_hours': 72, 'is_reply_goal_guaranteed': False,
            'exceptions_note': '신규 개발, 운영 대행, 구매자 수정분은 기본 지원에서 제외됩니다.'}


def default_terms(listing: Listing, price: int | None = None):
    return {'schema_version': 2, 'price_krw': price if price is not None else listing.price_krw,
            'rights_type': listing.sale_rights_type, 'included_assets': list(listing.included_assets or []),
            'excluded_assets': list(listing.excluded_assets or []),
            'handover_days': listing.handover_days_estimate if listing.handover_days_estimate is not None else 7,
            'support': recommended_support(listing.seller_support_days),
            'buyer_conditions_note': ''}


def validated_terms(terms: dict, price: int, listing: Listing):
    if not isinstance(terms, dict):
        raise HTTPException(422, '거래 조건은 객체 형태여야 합니다.')
    if terms.get('schema_version') != 2:
        # Do not silently invent commitments for pre-v0.12 freeform records.
        return terms
    try:
        value = OfferTermsV2.model_validate(terms)
    except ValidationError as exc:
        raise HTTPException(422, '구조화 조건의 값이나 형식을 확인해 주세요: ' + str(exc.errors(include_url=False)[:2]))
    if value.price_krw != price:
        raise HTTPException(422, '표시 가격과 구조화 조건 가격이 다릅니다.')
    allowed = set(listing.included_assets or [])
    if not set(value.included_assets).issubset(allowed):
        raise HTTPException(422, '포함 자산은 현재 등록된 제공 자산 범위에서만 협상할 수 있습니다.')
    # Exclusions must include those explicitly excluded on the listing.
    if not set(listing.excluded_assets or []).issubset(set(value.excluded_assets)):
        raise HTTPException(422, '매물의 제외 자산을 임의로 포함할 수 없습니다.')
    if value.rights_type == 'BUSINESS_TRANSFER_REVIEW_REQUIRED' and listing.sale_rights_type != value.rights_type:
        raise HTTPException(422, '사업 전체 이전은 별도 권리 검토가 필요한 매물에서만 협의할 수 있습니다.')
    return value.model_dump(mode='json')
