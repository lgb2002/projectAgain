"""Manual local administrator setup. Never seed a production default password."""
import os
from sqlalchemy import select
from .db import SessionLocal
from .models import User
from .security import hash_password

def admin():
    email=os.environ.get('ADMIN_EMAIL','').lower().strip()
    password=os.environ.get('ADMIN_PASSWORD','')
    if not email or len(password)<12:raise SystemExit('Set ADMIN_EMAIL and ADMIN_PASSWORD (at least 12 chars) in environment')
    with SessionLocal() as db:
        user=db.scalar(select(User).where(User.email==email))
        if user:
            user.role='ADMIN'
            if os.environ.get('ADMIN_RESET_PASSWORD')=='1':user.password_hash=hash_password(password)
        else:
            user=User(email=email,password_hash=hash_password(password),role='ADMIN')
            db.add(user)
        db.commit()
        print('Admin account configured:',email)

if __name__=='__main__':admin()
