"""Always-available, public-safe, evidence-based takeover report.

Never runs imported projects and never promises deployability or transfer rights.
"""
from datetime import datetime
from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base
from .models import now


class ListingReadinessReport(Base):
    __tablename__ = 'listing_readiness_reports'
    listing_id: Mapped[str] = mapped_column(ForeignKey('listings.id'), primary_key=True)
    report: Mapped[dict] = mapped_column(JSON, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now)
    report_version: Mapped[str] = mapped_column(String(24), nullable=False, default='readiness-v3')


BASE_CHECKS = (
    ('RIGHTS', '판매 권리 및 제3자 권리', 'sale_rights_type', 'rights_attested'),
    ('INCLUDED_ASSETS', '포함·제외 자산 구분', 'included_assets', 'excluded_assets'),
    ('KNOWN_DEFECTS', '알려진 결함 및 제한', 'known_defects', None),
    ('SERVICES', '외부 서비스·접근권·유지비용', 'required_services', 'monthly_cost_estimate_krw'),
    ('HANDOVER', '인수 일정 및 기술 지원', 'handover_days_estimate', 'seller_support_days'),
)


def make_report(listing, analysis=None):
    """Only seller declarations, safe file-level evidence and pinned CI metadata."""
    analysis = analysis or {}
    source = bool(analysis.get('file_count'))
    checks = []
    for key, title, first, second in BASE_CHECKS:
        val = getattr(listing, first, None)
        alt = getattr(listing, second, None) if second else None
        supplied = bool(val is not None and (val != [] and val != ''))
        if key == 'KNOWN_DEFECTS':
            supplied = bool(val)  # empty default != independently verified claim of no defects
        if key == 'RIGHTS': supplied = bool(val and alt)
        if key == 'INCLUDED_ASSETS':supplied = bool(val)
        if key == 'SERVICES':supplied = bool(val) or alt is not None
        if key == 'HANDOVER':supplied = val is not None
        checks.append({'key':key,'title':title,'status':'DECLARED' if supplied else 'NEEDS_INPUT',
                       'basis':'판매자 입력 (독립 검증 아님)' if supplied else '판매자 확인 필요',
                       'action':{
                           'RIGHTS':'권리 보유 근거, 제3자 라이선스 및 이전 범위를 확인하세요.',
                           'INCLUDED_ASSETS':'제공할 소스, 도메인, 데이터, 디자인 및 제외 항목을 명시하세요.',
                           'KNOWN_DEFECTS':'알려진 결함이 없는 경우에도 테스트와 실제 동작을 직접 점검하세요.',
                           'SERVICES':'운영 비용, 계정 이전 가능성, API 키 재발급 계획을 확인하세요.',
                           'HANDOVER':'인수 자료 전달 방식과 지원 범위·기간을 합의하세요.',
                       }[key]})
    for item in analysis.get('takeover_checks', [])[:15]:
        checks.append({'key':'SOURCE_'+str(item.get('key',''))[:40],
                       'title':str(item.get('label',''))[:110],
                       'status':'FILE_FOUND' if item.get('status')=='FOUND' else 'NOT_OBSERVED',
                       'basis':'파일·설정의 존재만 확인' if item.get('status')=='FOUND' else '파일에서 확인되지 않음',
                       'action':str(item.get('detail',''))[:400]})
    if not source:
        checks.append({'key':'SOURCE_NOT_PROVIDED','title':'분석용 소스 파일',
                       'status':'NOT_OBSERVED','basis':'등록된 분석용 ZIP/GitHub 소스 없음',
                       'action':'소스 분석 없이도 보고서는 제공됩니다. 판매자에게 검증 가능한 코드·실행 정보를 요청하세요.'})
    ci = analysis.get('ci_evidence') or {'status':'NOT_AVAILABLE','origin':'GITHUB_ACTIONS','runs_checked':0}
    # Fixed bounded fields; never expose repository identifiers, URLs, CI logs or private paths.
    ci = {'status':ci.get('status','NOT_AVAILABLE'), 'origin':'GITHUB_ACTIONS',
          'runs_checked':int(ci.get('runs_checked',0)), 'observed_sha_match':bool(ci.get('observed_sha_match',False))}
    if ci['status'] not in ('OBSERVED_SUCCESS','OBSERVED_FAILURE','OBSERVED_IN_PROGRESS','NOT_AVAILABLE','QUERY_FAILED'):
        ci['status']='NOT_AVAILABLE'
    next_actions=[x['action'] for x in checks if x['status'] in ('NEEDS_INPUT','NOT_OBSERVED')][:8]
    if not next_actions:next_actions=['핵심 기능의 실제 실행, 배포, 접근 권한, 소유권을 독립 검증하세요.']
    return {'report_version':'readiness-v3','scope':'인수 준비를 위한 정보·증빙 체크리스트 (거래·실행·권리 보증 아님)',
            'evidence_source':'SOURCE_STATIC_AND_GITHUB_CI' if source else 'SELLER_DECLARATIONS_ONLY',
            'source_analyzed':source, 'source_analysis_version':analysis.get('analysis_version'),
            'source_warnings':list(analysis.get('warnings') or [])[:25],
            'file_count':int(analysis.get('file_count',0)),
            'tech_stack':list(analysis.get('tech_stack') or [])[:25],
            'ci_evidence':ci, 'checks':checks,
            'next_actions':next_actions,'readiness_status':'INDEPENDENT_REVIEW_REQUIRED',
            'code_executed_by_platform':False,'rights_verified':False,
            'runtime_verified_by_platform':False,
            'notes':'CI는 GitHub가 기록한 특정 커밋의 결과이며 이 플랫폼의 재현 테스트가 아닙니다. FILE_FOUND/DECLARED는 실제 정상 동작을 증명하지 않습니다.'}


def save_report(db, listing, analysis=None):
    report = make_report(listing, analysis)
    row = db.get(ListingReadinessReport, listing.id)
    if row is None:
        row = ListingReadinessReport(listing_id=listing.id, report=report)
        db.add(row)
    else:
        row.report = report
        row.generated_at = now()
    return row


def current_report(db, listing):
    """Fallback for unmigrated legacy instances: GET never lacks a report."""
    from .models import ListingSourceSummary
    source = db.get(ListingSourceSummary, listing.id)
    row = db.get(ListingReadinessReport, listing.id)
    if row is None:
        return make_report(listing, source.analysis if source else None)
    return row.report
