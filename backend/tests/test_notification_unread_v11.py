"""v0.11: badge count is complete and a single read updates the count.

All tests run against the isolated SQLite database configured in conftest.py.
"""
from app.db import SessionLocal
from app.models import Notification
from test_workflows import people, post


def test_unread_count_not_limited_to_latest_100():
    seller, buyer, stranger, admin = people()
    with SessionLocal() as db:
        for i in range(105):
            db.add(Notification(user_id=seller['id'], kind='TEST', title=f'UX test {i}',
                                resource_type='listing', resource_id='unrelated-test'))
        db.commit()
    result = seller['client'].get('/api/v1/notifications')
    assert result.status_code == 200
    payload = result.json()
    assert len(payload['items']) == 100
    assert payload['unread'] == 105
    assert payload['has_more'] is True
    older = seller['client'].get('/api/v1/notifications?offset=100&limit=100').json()
    assert len(older['items']) == 5 and older['has_more'] is False
    first = payload['items'][0]['id']
    assert post(stranger, f'/notifications/{first}/read', {}).status_code == 404
    assert post(seller, f'/notifications/{first}/read', {}).status_code == 200
    # Reading the same message twice must not consume two unread messages.
    assert post(seller, f'/notifications/{first}/read', {}).status_code == 200
    after = seller['client'].get('/api/v1/notifications').json()
    assert after['unread'] == 104
    assert post(seller, '/notifications/read-all', {}).status_code == 200
    assert seller['client'].get('/api/v1/notifications').json()['unread'] == 0
