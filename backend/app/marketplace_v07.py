"""ProjectAgain v0.7: seller-confirmed public showcase, non-executing takeover checklist,
public/private listing questions, and notification preferences.
"""
from datetime import timedelta
import hashlib
from io import BytesIO
from ipaddress import ip_address
import os
import re
from urllib.parse import urlsplit
from uuid import uuid4
from fastapi import APIRouter, Depends, File, Request, UploadFile, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from PIL import Image, ImageOps, UnidentifiedImageError
from .db import get_db
from .models import Listing, Notification, ListingSourceSummary, ProjectImport, now
from .marketplace_models import ListingMedia, ListingShowcase, ListingInquiry, NotificationPreference
from .security import human, auth_context
from .private_storage import upload as store_upload, download as store_download, delete as store_delete, StorageUnavailable
from .notifications_v07 import notify, email_configured
from .main import must_listing, listing_detail, fail, audit, view, output, admin_only

router=APIRouter(prefix='/api/v1', tags=['ProjectAgain v0.7'])
MAX_IMAGE = 4 * 1024 * 1024
MAX_PIXELS = 14_000_000
MAX_MEDIA = 8


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


def safe_https_url(raw: str | None, video: bool=False) -> str | None:
    if raw is None or not raw.strip():return None
    url=raw.strip()
    if len(url)>700 or any(ord(c)<32 for c in url):raise ValueError('주소 형식을 확인하세요.')
    try: u=urlsplit(url)
    except ValueError as exc: raise ValueError('주소 형식을 확인하세요.') from exc
    host=(u.hostname or '').lower().rstrip('.')
    try: port=u.port
    except ValueError as exc:raise ValueError('주소의 포트 형식을 확인하세요.') from exc
    if u.scheme!='https' or not host or u.username or u.password or port not in (None,443):
        raise ValueError('외부 링크는 사용자 정보가 없는 HTTPS 주소만 허용됩니다.')
    if host=='localhost' or host.endswith(('.localhost','.local','.internal')) or '.' not in host:
        raise ValueError('공개된 외부 서비스의 HTTPS 주소만 허용됩니다.')
    try: ip_address(host)
    except ValueError: pass
    else: raise ValueError('IP 주소는 허용되지 않습니다.')
    if video and host not in ('youtu.be','youtube.com','www.youtube.com','m.youtube.com','vimeo.com','www.vimeo.com'):
        raise ValueError('시연 영상 링크는 YouTube 또는 Vimeo만 지원합니다.')
    return url


class ShowcaseInput(Strict):
    demo_url: str | None = Field(default=None,max_length=700)
    video_url: str | None = Field(default=None,max_length=700)
    highlights: list[str] = Field(default_factory=list,max_length=8)

    @field_validator('demo_url')
    @classmethod
    def check_demo(cls,v):return safe_https_url(v)

    @field_validator('video_url')
    @classmethod
    def check_video(cls,v):return safe_https_url(v,True)

    @field_validator('highlights')
    @classmethod
    def check_highlights(cls,values):
        if any(not x.strip() or len(x)>130 for x in values):raise ValueError('기능 소개는 1~130자씩 입력하세요.')
        return [x.strip() for x in values]


class MediaUpdate(Strict):
    caption: str = Field(default='',max_length=140)
    set_cover: bool = False


class InquiryCreate(Strict):
    question: str = Field(min_length=10,max_length=1500)
    visibility: str = Field(default='PUBLIC',pattern='^(PUBLIC|PRIVATE)$')


class InquiryAnswer(Strict):
    answer: str = Field(min_length=2,max_length=2000)


class EmailPreference(Strict):
    email_enabled: bool


def visible_listing(db, listing_id, request, include_demo=False):
    return listing_detail(listing_id,include_demo=include_demo,db=db,request=request)


def owner_mutable(db, listing_id, ctx):
    listing=must_listing(db,listing_id)
    if listing.seller_id != ctx['user'].id or ctx['kind']!='session': fail(404,'매물을 찾을 수 없습니다.')
    if listing.status in ('RESERVED','CLOSED','REMOVED'):fail(409,'이 상태에서는 수정할 수 없습니다.')
    return listing


def changed(db,listing,ctx,action):
    # Changed public claims or gallery must be re-moderated. Pending review returns to draft.
    if listing.status=='ACTIVE':listing.status='PENDING_REVIEW'
    elif listing.status=='PENDING_REVIEW':listing.status='DRAFT'
    listing.version+=1
    audit(db,ctx,action,'listing',listing.id,new={'status':listing.status,'version':listing.version},demo=listing.is_demo)


def media_view(row,listing):
    return {'id':row.id,'caption':row.caption,'width':row.width,'height':row.height,
            'position':row.position, 'url':f'/api/v1/listings/{listing.id}/media/{row.id}/image'+('?demo=1' if listing.is_demo else '')}


@router.post('/listings/{listing_id}/source-summary/reanalyze')
def reanalyze_source(listing_id:str,db:Session=Depends(get_db),ctx=Depends(human)):
    """Upgrade older v0.6 source snapshots without GitHub access or source execution."""
    listing=owner_mutable(db,listing_id,ctx)
    summary=db.get(ListingSourceSummary,listing_id)
    if not summary:fail(404,'연결된 소스가 없습니다. GitHub 또는 ZIP으로 먼저 등록하세요.')
    source=db.get(ProjectImport,summary.import_id)
    if not source or source.user_id!=ctx['user'].id or source.listing_id!=listing_id:
        fail(404,'접근할 수 없는 소스입니다.')
    try: blob=store_download(source.object_key)
    except (StorageUnavailable,OSError):fail(503,'등록된 소스 파일에 접근할 수 없습니다.')
    if hashlib.sha256(blob).hexdigest()!=source.checksum_sha256:
        fail(409,'소스 파일의 무결성을 확인하지 못했습니다.')
    from .project_analyzer import analyze_archive, public_analysis
    from .static_screen import screen, RejectedFile
    try:
        screen(source.filename,blob)
        result=analyze_archive(blob,'등록된 프로젝트')
    except (RejectedFile,ValueError,OSError):fail(422,'이 파일을 안전하게 재분석할 수 없습니다.')
    # Preserve previously observed pinned CI metadata; reanalysis never reruns or asserts CI.
    if source.analysis.get('ci_evidence'):
        result['ci_evidence']=source.analysis['ci_evidence']
    source.analysis=result
    summary.analysis=public_analysis(result)
    from .readiness_report import save_report
    save_report(db, listing, summary.analysis)
    changed(db,listing,ctx,'source_summary.reanalyze')
    db.commit()
    return {'analysis':summary.analysis,'listing_status':listing.status,
            'source_archive_visibility':'PRIVATE_REVIEW_ONLY'}


@router.get('/listings/{listing_id}/showcase')
def get_showcase(listing_id:str,request:Request,include_demo:bool=False,db:Session=Depends(get_db)):
    visible_listing(db,listing_id,request,include_demo)
    listing=db.get(Listing,listing_id)
    summary=db.get(ListingShowcase,listing_id)
    media=db.scalars(select(ListingMedia).where(ListingMedia.listing_id==listing_id).order_by(ListingMedia.position,ListingMedia.created_at)).all()
    return {'demo_url':summary.demo_url if summary else None,
            'video_url':summary.video_url if summary else None,
            'highlights':summary.highlights if summary else [],
            'media':[media_view(m,listing) for m in media],
            'seller_provided':True,'demo_not_verified':True}


@router.put('/listings/{listing_id}/showcase')
def save_showcase(listing_id:str,data:ShowcaseInput,db:Session=Depends(get_db),ctx=Depends(human)):
    listing=owner_mutable(db,listing_id,ctx)
    row=db.get(ListingShowcase,listing_id)
    if not row:
        row=ListingShowcase(listing_id=listing_id)
        db.add(row)
    row.demo_url=data.demo_url
    row.video_url=data.video_url
    row.highlights=data.highlights
    changed(db,listing,ctx,'showcase.update')
    db.commit()
    return {'ok':True,'listing_status':listing.status,'listing_version':listing.version}


def normalized_image(content):
    try:
        with Image.open(BytesIO(content)) as image:
            if image.format not in ('PNG','JPEG','WEBP') or image.width*image.height>MAX_PIXELS:
                fail(422,'지원하지 않는 형식이거나 너무 큰 이미지입니다.')
            image=ImageOps.exif_transpose(image)
            image.thumbnail((1920,1440))
            rgb=image.convert('RGB')
            out=BytesIO()
            rgb.save(out,format='WEBP',quality=84,method=4)
            return out.getvalue(),rgb.width,rgb.height
    except (Image.DecompressionBombError,Image.DecompressionBombWarning,UnidentifiedImageError,OSError,ValueError):
        fail(422,'유효한 PNG, JPEG 또는 WebP 이미지만 등록할 수 있습니다.')


@router.post('/listings/{listing_id}/media',status_code=201)
async def upload_media(listing_id:str,file:UploadFile=File(...),db:Session=Depends(get_db),ctx=Depends(human)):
    listing=owner_mutable(db,listing_id,ctx)
    count=db.scalar(select(func.count(ListingMedia.id)).where(ListingMedia.listing_id==listing_id)) or 0
    if count>=MAX_MEDIA:fail(422,'이미지는 매물당 최대 8장입니다.')
    seller_media=db.scalar(select(func.count(ListingMedia.id)).join(Listing,Listing.id==ListingMedia.listing_id).where(Listing.seller_id==ctx['user'].id)) or 0
    if seller_media>=80:fail(429,'계정당 미리보기 이미지 한도에 도달했습니다.')
    blob=await file.read(MAX_IMAGE+1)
    if not blob or len(blob)>MAX_IMAGE:fail(422,'이미지는 4MB 이하로 등록하세요.')
    webp,width,height=normalized_image(blob)
    key=f'private/showcases/{listing_id}/{uuid4().hex}.webp'
    try:store_upload(key,webp)
    except (StorageUnavailable,OSError):fail(503,'이미지 보관에 실패했습니다.')
    row=ListingMedia(listing_id=listing_id,object_key=key,mime='image/webp',width=width,height=height,position=count)
    try:
        db.add(row)
        changed(db,listing,ctx,'showcase.image.add')
        db.commit()
    except Exception:
        db.rollback()
        try:store_delete(key)
        except StorageUnavailable:pass
        raise
    return {'item':media_view(row,listing),'listing_status':listing.status}


@router.get('/listings/{listing_id}/media/{media_id}/image')
def image_bytes(listing_id:str,media_id:str,request:Request,demo:bool=False,db:Session=Depends(get_db)):
    visible_listing(db,listing_id,request,include_demo=demo)
    media=db.get(ListingMedia,media_id)
    if not media or media.listing_id!=listing_id:fail(404,'이미지를 찾을 수 없습니다.')
    try: blob=store_download(media.object_key)
    except (StorageUnavailable,OSError):fail(503,'이미지에 접근할 수 없습니다.')
    return Response(content=blob,media_type='image/webp',headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})


@router.patch('/listings/{listing_id}/media/{media_id}')
def update_media(listing_id:str,media_id:str,data:MediaUpdate,db:Session=Depends(get_db),ctx=Depends(human)):
    listing=owner_mutable(db,listing_id,ctx)
    row=db.get(ListingMedia,media_id)
    if not row or row.listing_id!=listing_id:fail(404,'이미지가 없습니다.')
    row.caption=data.caption.strip()
    if data.set_cover:
        first=db.scalar(select(ListingMedia).where(ListingMedia.listing_id==listing_id).order_by(ListingMedia.position,ListingMedia.created_at).limit(1))
        if first and first.id!=row.id:
            row.position,first.position=first.position,row.position
    changed(db,listing,ctx,'showcase.image.update')
    db.commit()
    return {'item':media_view(row,listing),'listing_status':listing.status}


@router.delete('/listings/{listing_id}/media/{media_id}')
def remove_media(listing_id:str,media_id:str,db:Session=Depends(get_db),ctx=Depends(human)):
    listing=owner_mutable(db,listing_id,ctx)
    row=db.get(ListingMedia,media_id)
    if not row or row.listing_id!=listing_id:fail(404,'이미지가 없습니다.')
    key=row.object_key
    db.delete(row)
    changed(db,listing,ctx,'showcase.image.remove')
    db.commit()
    try:store_delete(key)
    except (StorageUnavailable,OSError):pass  # Orphan is not exposed; cleanup job can retry.
    return {'ok':True,'listing_status':listing.status}


def inquiry_view(row,author=False):
    return {'id':row.id,'listing_id':row.listing_id,'question':row.question,'visibility':row.visibility,
            'answer':row.answer,'created_at':output(row.created_at),'answered_at':output(row.answered_at),
            'is_mine':bool(author)}


def optional_user(request, db):
    try:
        ctx=auth_context(request,db)
        return ctx['user'] if ctx['kind']=='session' else None
    except HTTPException: return None


@router.get('/listings/{listing_id}/inquiries')
def listing_inquiries(listing_id:str,request:Request,include_demo:bool=False,db:Session=Depends(get_db)):
    visible_listing(db,listing_id,request,include_demo)
    listing=db.get(Listing,listing_id)
    user=optional_user(request,db)
    rows=db.scalars(select(ListingInquiry).where(ListingInquiry.listing_id==listing_id,
              ListingInquiry.hidden_at.is_(None)).order_by(ListingInquiry.created_at.desc()).limit(100)).all()
    permitted=[r for r in rows if r.visibility=='PUBLIC' or (user and user.id in (r.buyer_id,r.seller_id)) or (user and user.role=='ADMIN')]
    return {'items':[inquiry_view(r,user is not None and user.id==r.buyer_id) for r in permitted]}


CONTACT=re.compile(r'(?:[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}|https?://|(?:\+?82[-\s]?)?01[016789][-\s]?\d{3,4}[-\s]?\d{4})',re.I)


@router.post('/listings/{listing_id}/inquiries',status_code=201)
def ask_inquiry(listing_id:str,data:InquiryCreate,db:Session=Depends(get_db),ctx=Depends(human)):
    listing=must_listing(db,listing_id)
    if listing.status!='ACTIVE':fail(409,'공개된 매물에만 문의할 수 있습니다.')
    if ctx['user'].id==listing.seller_id:fail(422,'자신의 매물에는 문의할 수 없습니다.')
    question=data.question.strip()
    if len(question)<10 or CONTACT.search(question):fail(422,'문의 내용에서 연락처와 외부 링크를 제거해 주세요.')
    after=now()-timedelta(hours=24)
    count=db.scalar(select(func.count(ListingInquiry.id)).where(ListingInquiry.buyer_id==ctx['user'].id,ListingInquiry.created_at>after)) or 0
    if count>=12:fail(429,'하루 문의 한도를 초과했습니다.')
    recent=db.scalar(select(ListingInquiry.id).where(ListingInquiry.buyer_id==ctx['user'].id,
                   ListingInquiry.listing_id==listing_id,ListingInquiry.created_at>now()-timedelta(seconds=30)).limit(1))
    if recent:fail(429,'잠시 후 다시 문의해 주세요.')
    row=ListingInquiry(listing_id=listing_id,buyer_id=ctx['user'].id,seller_id=listing.seller_id,
                       visibility=data.visibility,question=question)
    db.add(row)
    db.flush()
    notify(db,listing.seller_id,'INQUIRY_RECEIVED','프로젝트에 새로운 구매 문의가 도착했습니다.','inquiry',row.id)
    audit(db,ctx,'inquiry.create','inquiry',row.id,new={'visibility':row.visibility},demo=listing.is_demo)
    db.commit()
    return inquiry_view(row,True)


@router.get('/inquiries/inbox')
def inquiry_inbox(db:Session=Depends(get_db),ctx=Depends(human)):
    uid=ctx['user'].id
    rows=db.scalars(select(ListingInquiry).where((ListingInquiry.buyer_id==uid)|(ListingInquiry.seller_id==uid))
                    .order_by(ListingInquiry.created_at.desc()).limit(150)).all()
    return {'items':[{**inquiry_view(r,r.buyer_id==uid), 'role':'SELLER' if r.seller_id==uid else 'BUYER',
                     'listing_title':db.get(Listing,r.listing_id).title if db.get(Listing,r.listing_id) else '삭제된 매물'} for r in rows]}


@router.post('/inquiries/{inquiry_id}/answer')
def answer_inquiry(inquiry_id:str,data:InquiryAnswer,db:Session=Depends(get_db),ctx=Depends(human)):
    row=db.get(ListingInquiry,inquiry_id)
    if not row or row.seller_id!=ctx['user'].id:fail(404,'문의가 없습니다.')
    listing=db.get(Listing,row.listing_id)
    if row.hidden_at or not listing or listing.status=='REMOVED':fail(409,'답변할 수 없는 문의입니다.')
    answer=data.answer.strip()
    if len(answer)<2 or CONTACT.search(answer):fail(422,'답변 내용에서 연락처와 외부 링크를 제거해 주세요.')
    row.answer=answer
    row.answered_at=now()
    notify(db,row.buyer_id,'INQUIRY_ANSWERED','프로젝트 문의에 판매자 답변이 등록됐습니다.','inquiry',row.id)
    audit(db,ctx,'inquiry.answer','inquiry',row.id,demo=listing.is_demo)
    db.commit()
    return inquiry_view(row)


@router.post('/admin/inquiries/{inquiry_id}/hide')
def admin_hide_inquiry(inquiry_id:str,db:Session=Depends(get_db),ctx=Depends(human)):
    admin_only(ctx)
    row=db.get(ListingInquiry,inquiry_id)
    if not row:fail(404,'문의가 없습니다.')
    row.hidden_at=now()
    audit(db,ctx,'inquiry.hide','inquiry',row.id)
    db.commit()
    return {'ok':True}


@router.get('/notifications/preferences')
def get_notification_preferences(db:Session=Depends(get_db),ctx=Depends(human)):
    pref=db.get(NotificationPreference,ctx['user'].id)
    return {'email_enabled':pref.email_enabled if pref else True,
            'email_delivery_configured':email_configured(),
            'delivery_note':'이메일 발송은 서버의 SMTP 설정과 별도 작업 실행이 필요합니다.'}


@router.put('/notifications/preferences')
def put_notification_preferences(data:EmailPreference,db:Session=Depends(get_db),ctx=Depends(human)):
    pref=db.get(NotificationPreference,ctx['user'].id)
    if not pref:
        pref=NotificationPreference(user_id=ctx['user'].id)
        db.add(pref)
    pref.email_enabled=data.email_enabled
    db.commit()
    return {'email_enabled':pref.email_enabled,'email_delivery_configured':email_configured()}


@router.post('/notifications/read-all')
def read_all_notifications(db:Session=Depends(get_db),ctx=Depends(human)):
    rows=db.scalars(select(Notification).where(Notification.user_id==ctx['user'].id,Notification.read_at.is_(None))).all()
    for row in rows:row.read_at=now()
    db.commit()
    return {'ok':True,'count':len(rows)}
