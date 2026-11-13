"""Run independently in Replit shell / scheduled worker; no background tasks in web process."""
from .db import SessionLocal
from .privacy import cleanup_objects

if __name__=='__main__':
    with SessionLocal() as session:
        print(cleanup_objects(session,100))
