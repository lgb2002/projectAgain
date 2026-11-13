"""Bounded private-object operations. No public URLs, no user-controlled paths.

Production: Replit App Storage bucket via official SDK. Development/test only:
private local directory OUTSIDE the frontend static assets. Never store raw source
archives inside React public/ or dist/.
"""
import os
from pathlib import Path


class StorageUnavailable(RuntimeError):
    pass


def storage_kind():
    kind = os.getenv('PRIVATE_STORAGE_BACKEND', 'local' if os.getenv('APP_ENV','development') != 'production' else 'replit')
    if kind not in ('replit', 'local', 's3'):
        raise StorageUnavailable('지원하지 않는 저장소 유형입니다.')
    if os.getenv('APP_ENV') == 'production' and kind == 'local':
        raise StorageUnavailable('운영 환경에서 로컬 파일 저장소는 사용할 수 없습니다.')
    return kind


def _local_path(key):
    if not key.startswith('private/') or '..' in key or '\\' in key:
        raise StorageUnavailable('안전하지 않은 저장소 키입니다.')
    base = Path(os.getenv('PRIVATE_STORAGE_DIR', '/tmp/micro_asset_private_files')).resolve()
    target = (base / key).resolve()
    if not target.is_relative_to(base):
        raise StorageUnavailable('안전하지 않은 저장소 경로입니다.')
    return target


def _replit():
    try:
        from replit.object_storage import Client
    except ImportError as exc:
        raise StorageUnavailable('replit-object-storage-python SDK가 설치되지 않았습니다.') from exc
    try:
        bucket = os.getenv('REPLIT_STORAGE_BUCKET_ID') or None
        return Client(bucket_id=bucket)
    except Exception as exc:
        raise StorageUnavailable('App Storage 연결에 실패했습니다.') from exc


def _validate_key(key):
    if not isinstance(key, str) or not key.startswith('private/') or '..' in key or '\\' in key or '//' in key or len(key) > 500:
        raise StorageUnavailable('안전하지 않은 저장소 키입니다.')


def _s3():
    try:
        import boto3
        from botocore.config import Config
        bucket = os.environ['S3_BUCKET']
        if not bucket:
            raise ValueError('missing bucket')
        client = boto3.client('s3', endpoint_url=os.getenv('S3_ENDPOINT_URL') or None,
                              region_name=os.getenv('S3_REGION', 'auto'),
                              config=Config(signature_version='s3v4'))
        return client, bucket
    except Exception as exc:
        raise StorageUnavailable('S3 비공개 저장소 설정 오류') from exc


def presign_put(key, *, content_type='application/zip', expires=300):
    _validate_key(key)
    if storage_kind() != 's3':
        raise StorageUnavailable('직접 업로드는 S3 저장소가 필요합니다.')
    client, bucket = _s3()
    return client.generate_presigned_url('put_object', Params={'Bucket': bucket, 'Key': key,
        'ContentType': content_type}, ExpiresIn=expires)


def presign_get(key, *, expires=60):
    _validate_key(key)
    if storage_kind() != 's3':
        raise StorageUnavailable('직접 다운로드는 S3 저장소가 필요합니다.')
    client, bucket = _s3()
    return client.generate_presigned_url('get_object', Params={'Bucket': bucket, 'Key': key}, ExpiresIn=expires)


def object_size(key):
    _validate_key(key)
    client, bucket = _s3()
    return int(client.head_object(Bucket=bucket, Key=key)['ContentLength'])


def upload(key, content):
    _validate_key(key)
    if storage_kind() == 'replit':
        try: _replit().upload_from_bytes(key, content)
        except Exception as exc: raise StorageUnavailable('App Storage 업로드 실패') from exc
    elif storage_kind() == 's3':
        try:
            client, bucket = _s3()
            client.put_object(Bucket=bucket, Key=key, Body=content)
        except Exception as exc:
            raise StorageUnavailable('S3 업로드 실패') from exc
    else:
        path = _local_path(key)
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        # Create exclusive files and prevent accidental overwrite.
        with path.open('xb') as out:
            out.write(content)
        path.chmod(0o600)


def download(key):
    _validate_key(key)
    if storage_kind() == 'replit':
        try: return _replit().download_as_bytes(key)
        except Exception as exc: raise StorageUnavailable('App Storage 다운로드 실패') from exc
    if storage_kind() == 's3':
        try:
            client, bucket = _s3()
            return client.get_object(Bucket=bucket, Key=key)['Body'].read()
        except Exception as exc:
            raise StorageUnavailable('S3 다운로드 실패') from exc
    path = _local_path(key)
    return path.read_bytes()


def delete(key):
    _validate_key(key)
    if storage_kind() == 'replit':
        try: _replit().delete(key, ignore_not_found=True)
        except Exception as exc: raise StorageUnavailable('App Storage 삭제 실패') from exc
    elif storage_kind() == 's3':
        try:
            client, bucket = _s3()
            client.delete_object(Bucket=bucket, Key=key)
        except Exception as exc:
            raise StorageUnavailable('S3 삭제 실패') from exc
    else:
        _local_path(key).unlink(missing_ok=True)
