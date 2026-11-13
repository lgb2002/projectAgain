"""Explicitly opt-in, development-only seed listings. Never used in production."""
import secrets
import os
from sqlalchemy import select
from .db import SessionLocal
from .models import User, Listing
from .security import APP_ENV, hash_password

EXAMPLES = [
    ('개인 일정 관리 웹앱 MVP', 'web_app', 'FAILED_COMMERCIALIZATION', 85000,
     'FastAPI와 React로 만든 개인 일정 관리 웹서비스입니다. 기본 일정·태그·완료 표시 기능이 구현됐고, 결제 연동은 개발하지 않았습니다.', ['FastAPI','React','SQLite'], ['웹 프론트엔드 전체 코드','API 서버 코드','기본 설치 문서'], ['배포 계정','실사용자 DB'], ['소셜 로그인 미구현','결제 기능 없음']),
    ('중단된 콘텐츠 요약 AI 에이전트', 'ai_agent', 'DISCONTINUED', 160000,
     '문서와 URL 요약 파이프라인을 Python으로 구성했습니다. 테스트 데이터는 포함하지만 외부 모델 API 키는 제공하지 않습니다.', ['Python','FastAPI','LLM'], ['요약 파이프라인 코드','테스트 스크립트','API 연동 인터페이스'], ['유료 모델 크레딧'], ['요약 길이 자동 최적화 미완성']),
    ('브라우저 CSV 정리 도구', 'desktop_tool', 'ASSET_ONLY', 50000,
     '엑셀 CSV 파일을 합치고 중복 행을 제거하는 소형 유틸리티입니다. 개인용으로 제작되어 별도 과금이나 고객 지원 체계는 없습니다.', ['Python','Pandas'], ['변환 로직 코드','샘플 입력/출력 파일'], ['운영체제별 설치 패키지'], ['대용량 파일에서 메모리 사용량 높음']),
    ('온라인 예약 SaaS 시제품', 'saas', 'UNLAUNCHED', 420000,
     '사업자 예약 캘린더와 관리자 예약 확정 흐름을 구현한 초기 SaaS입니다. 실제 고객과 매출은 없으며 검증되지 않았습니다.', ['TypeScript','PostgreSQL'], ['앱 소스코드','DB 테이블 정의','로컬 실행 안내'], ['기존 클라우드 계정','결제 서비스 계정'], ['결제 연동 없음','이메일 알림 미구현']),
    ('HTML 게임 프로토타입', 'game', 'IN_DEVELOPMENT', 75000,
     '브라우저에서 실행되는 2D 게임의 핵심 루프와 점수 계산만 구현돼 있습니다. 그래픽은 임시 도형으로 구성된 프로토타입입니다.', ['JavaScript','Canvas'], ['게임 로직','임시 테스트 화면'], ['상업용 음원','최종 캐릭터 일러스트'], ['저장 기능 미완성']),
    ('마케팅 데이터 대시보드 템플릿', 'module', 'ASSET_ONLY', 65000,
     '표준 CSV 입력으로 방문자·전환율·매출 그래프를 표시하는 프론트엔드 컴포넌트입니다. 실제 운영 데이터는 제공되지 않습니다.', ['React','TypeScript'], ['UI 컴포넌트 소스','예시 데이터'], ['대시보드 운영 계정'], ['API 실시간 동기화 미구현']),
]

def main():
    if APP_ENV == 'production': raise SystemExit('DEMO seeding forbidden in production')
    with SessionLocal() as db:
        email='demo-seller@invalid.example'
        seller=db.scalar(select(User).where(User.email==email))
        if seller is None:
            seller=User(email=email,password_hash=hash_password(os.getenv('DEMO_SELLER_PASSWORD') or secrets.token_urlsafe(32)))
            db.add(seller);db.flush()
        for title,category,lifecycle,price,desc,tech,included,excluded,defects in EXAMPLES:
            if db.scalar(select(Listing).where(Listing.title==title,Listing.is_demo.is_(True))):continue
            row=Listing(seller_id=seller.id,title=title,description=desc,category=category,
                        lifecycle_status=lifecycle,sale_rights_type='ASSET_TRANSFER_ONLY',
                        price_krw=price,tech_stack=tech,included_assets=included,
                        excluded_assets=excluded,known_defects=defects,required_services=[],
                        monthly_cost_estimate_krw=0,has_revenue=False,
                        rights_attested=True,status='ACTIVE',is_demo=True)
            db.add(row)
        db.commit()
    print('Development DEMO inventory seeded. All sample listings show DEMO labels.')

if __name__ == '__main__':main()
