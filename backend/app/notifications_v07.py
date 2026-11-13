"""Transactional in-app notification + optional SMTP outbox. No mail sent during DB request.
The external worker must be started separately; SMTP is never required for in-app alerts.
"""
import os
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
import smtplib
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import Notification, User, now
from .marketplace_models import NotificationPreference, NotificationEmail


def notify(db: Session, user_id: str, kind: str, title: str, resource_type: str, resource_id: str):
    note = Notification(user_id=user_id, kind=kind, title=title[:200],
                        resource_type=resource_type, resource_id=resource_id)
    db.add(note)
    db.flush()
    pref = db.get(NotificationPreference, user_id)
    if not pref or pref.email_enabled:
        db.add(NotificationEmail(notification_id=note.id, user_id=user_id))
    return note


def email_configured():
    return bool(os.getenv('SMTP_HOST') and os.getenv('SMTP_FROM'))


def _resource_path(note):
    if note.resource_type == 'listing': return f'/listings/{note.resource_id}'
    if note.resource_type == 'inquiry': return '/dashboard?tab=inquiries'
    if note.resource_type == 'offer': return '/dashboard?tab=offers'
    if note.resource_type == 'transaction': return f'/transactions/{note.resource_id}'
    if note.resource_type == 'agent_action': return '/dashboard?tab=agent'
    if note.resource_type == 'listing_asset': return '/operations'
    return '/dashboard?tab=notifications'


def _deliver(recipient: str, note: Notification):
    msg = EmailMessage()
    msg['From'] = os.environ['SMTP_FROM']
    msg['To'] = recipient
    msg['Subject'] = f'[ProjectAgain] {note.title}'
    base = os.environ.get('PUBLIC_BASE_URL','').rstrip('/')
    if not base.startswith('https://'):
        # Only emit links if a legitimate public HTTPS origin is configured.
        base = ''
    msg.set_content(f'{note.title}\n\n{base}{_resource_path(note) if base else ""}\n\n알림 설정은 사이트의 내 활동에서 변경할 수 있습니다.')
    host = os.environ['SMTP_HOST']
    port = int(os.getenv('SMTP_PORT','587'))
    with smtplib.SMTP(host, port, timeout=10) as smtp:
        smtp.ehlo()
        if os.getenv('SMTP_USE_STARTTLS', '1') == '1':
            smtp.starttls()
            smtp.ehlo()
        if os.getenv('SMTP_USERNAME') and os.getenv('SMTP_PASSWORD'):
            smtp.login(os.environ['SMTP_USERNAME'], os.environ['SMTP_PASSWORD'])
        smtp.send_message(msg)


def send_due(db: Session, limit: int = 20):
    """Single batch. PostgreSQL row locks prevent concurrent worker duplicates.
    Still at-least-once in abnormal SMTP/network/commit failures (not exactly once).
    """
    if not email_configured(): return {'configured':False, 'sent':0,'failed':0,'pending':0}
    due = select(NotificationEmail).where(NotificationEmail.status=='PENDING',
              NotificationEmail.next_attempt_at <= now()).order_by(NotificationEmail.created_at).limit(min(limit,100))
    if db.bind.dialect.name == 'postgresql': due=due.with_for_update(skip_locked=True)
    rows = db.scalars(due).all()
    sent = failed = 0
    for row in rows:
        recipient = db.get(User, row.user_id)
        note = db.get(Notification, row.notification_id)
        pref = db.get(NotificationPreference, row.user_id)
        if not recipient or not recipient.is_active or not note or (pref and not pref.email_enabled):
            row.status = 'CANCELLED'
            continue
        try:
            _deliver(recipient.email, note)
        except (OSError, smtplib.SMTPException, KeyError, ValueError):
            row.attempts += 1
            if row.attempts >= 5: row.status = 'FAILED'
            else: row.next_attempt_at = now() + timedelta(minutes=min(240, 2 ** row.attempts))
            row.last_error_code = 'SMTP_DELIVERY_FAILED'  # Never store message or credentials.
            failed += 1
        else:
            row.status = 'SENT'
            row.sent_at = now()
            row.last_error_code = None
            sent += 1
    # Keep row locks until the end of this batch; a second PostgreSQL worker
    # must not acquire other rows from the in-memory selection mid-delivery.
    db.commit()
    return {'configured':True,'sent':sent,'failed':failed,'processed':len(rows)}
