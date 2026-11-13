# DEMO 매물

개발 시연 매물은 `backend/app/seed_demo.py`에 정의됩니다. 자산·판매 수치·판매자 진위는 모두 가상이며 실제 거래 가능 자산이 아닙니다.

개발 환경에서만 다음 명령으로 추가합니다.

```
cd backend
../.venv/bin/python -m app.seed_demo
```

상용 환경에서는 자동 시드 금지. 화면에 DEMO가 명확히 표시됩니다.
