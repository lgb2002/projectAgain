"""Use via: python -m app.email_worker --once (or --loop as separate Replit worker)."""
import argparse
import time
from .db import SessionLocal
from .notifications_v07 import send_due
from .privacy import cleanup_objects

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--once',action='store_true')
    p.add_argument('--loop',action='store_true')
    args=p.parse_args()
    if not (args.once or args.loop): p.error('choose --once or --loop')
    while True:
        with SessionLocal() as db:
            result=send_due(db)
            cleanup=cleanup_objects(db)
        print('Email outbox:',result,'Privacy deletion:',cleanup,flush=True)
        if args.once: return
        time.sleep(60)

if __name__=='__main__':main()
