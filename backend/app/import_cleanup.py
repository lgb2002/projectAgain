"""Run periodically: python -m app.import_cleanup

Delete expired, UNATTACHED temporary source objects. Never delete attached files.
No data is deleted unless an import expired and remained in STAGED status.
"""
from datetime import timezone
from sqlalchemy import select
from .db import SessionLocal
from .models import ProjectImport, now
from .private_storage import delete as store_delete


def cleanup(limit=200):
    removed=0; errors=0
    with SessionLocal() as db:
        rows=db.scalars(select(ProjectImport).where(
            ProjectImport.status=='STAGED', ProjectImport.listing_id.is_(None),
            ProjectImport.expires_at < now()).order_by(ProjectImport.expires_at.asc())
            .limit(limit).with_for_update(skip_locked=True)).all()
        for row in rows:
            try:
                store_delete(row.object_key)
                row.status='EXPIRED'
                db.commit()
                removed+=1
            except Exception:
                db.rollback()
                errors+=1
    return {'expired_cleaned':removed,'storage_errors':errors}


if __name__=='__main__':
    print(cleanup())
