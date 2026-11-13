"""Static archive validation only. NOT a malware detector or execution sandbox.

Rejects zip bombs, traversal, symlinks, encrypted archives and likely secret
containers. The result remains QUARANTINED for admin review. Never exec contents.
"""
from io import BytesIO
import os
from pathlib import PurePosixPath
from zipfile import BadZipFile, ZipFile, is_zipfile

MAX_FILE = int(os.getenv('ASSET_MAX_BYTES', str(10*1024*1024)))
MAX_UNPACKED = 100*1024*1024
MAX_ZIP_ITEMS = 4000
EXTENSIONS = ('.zip', '.md', '.txt', '.pdf', '.json')
FORBIDDEN_NAMES = {'.env', '.env.local', '.npmrc', '.pypirc', '.netrc', '.aws', '.git',
                   'id_rsa', 'id_ed25519', 'credentials.json', 'service-account.json'}
SAFE_ENV_TEMPLATES = {'.env.example', '.env.sample', '.env.template', '.env.dist'}


class RejectedFile(ValueError):
    pass


def screen(filename: str, content: bytes) -> dict:
    filename = filename.replace('\\', '/')
    short = filename.rsplit('/', 1)[-1]
    if not short or len(short)>180 or short.startswith('.') or not short.lower().endswith(EXTENSIONS):
        raise RejectedFile('허용된 형식은 ZIP, PDF, MD, TXT, JSON이며 파일 이름을 확인하세요.')
    if not content or len(content) > MAX_FILE:
        raise RejectedFile(f'파일 용량은 1바이트부터 최대 {MAX_FILE // 1024 // 1024}MB까지입니다.')
    if short.lower().endswith('.zip'):
        if not is_zipfile(BytesIO(content)):
            raise RejectedFile('ZIP 파일이 손상됐거나 유효하지 않습니다.')
        try:
            with ZipFile(BytesIO(content)) as z:
                items = z.infolist()
                if len(items)>MAX_ZIP_ITEMS: raise RejectedFile('ZIP 내부 파일 개수가 너무 많습니다.')
                size=0
                for item in items:
                    name = item.filename.replace('\\', '/')
                    p=PurePosixPath(name)
                    if p.is_absolute() or '..' in p.parts or ':' in name or '\x00' in name:
                        raise RejectedFile('ZIP 내부에 잘못된 경로가 포함되어 있습니다.')
                    if any(part.lower() in FORBIDDEN_NAMES or
                           (part.lower().startswith('.env.') and part.lower() not in SAFE_ENV_TEMPLATES)
                           for part in p.parts):
                        raise RejectedFile('ZIP 내부에 비밀 정보 파일이 포함된 것으로 보입니다. 제거 후 다시 제출하세요.')
                    if item.flag_bits & 0x1:
                        raise RejectedFile('암호화된 ZIP은 정적 검증할 수 없습니다.')
                    if ((item.external_attr >> 16) & 0o170000) == 0o120000:
                        raise RejectedFile('ZIP 내부의 심볼릭 링크는 허용하지 않습니다.')
                    size += item.file_size
                    if size > MAX_UNPACKED:
                        raise RejectedFile('ZIP 압축 해제 시 크기가 너무 큽니다.')
                    if item.compress_size>0 and item.file_size>max(1, item.compress_size)*300:
                        raise RejectedFile('비정상적으로 높은 압축 비율입니다.')
                    if item.file_size>0 and item.compress_size==0:
                        raise RejectedFile('압축 정보가 비정상적입니다.')
                # CRC verification: no extracted archive is written to disk.
                for item in items:
                    if not item.is_dir():
                        with z.open(item) as stream:
                            while stream.read(1024 * 1024): pass
        except (BadZipFile, OSError, RuntimeError) as exc:
            raise RejectedFile('ZIP 파일의 무결성 검사에 실패했습니다.') from exc
        return {'kind':'ZIP_STATIC_SCREEN', 'items':len(items), 'uncompressed_bytes':size,
                'malware_scan':'NOT_PERFORMED', 'code_executed':False}
    if short.lower().endswith('.pdf') and not content.startswith(b'%PDF-'):
        raise RejectedFile('PDF 파일 서명이 올바르지 않습니다.')
    if short.lower().endswith(('.md','.txt','.json')):
        try: content.decode('utf-8')
        except UnicodeError as exc: raise RejectedFile('텍스트 파일은 UTF-8 인코딩이어야 합니다.') from exc
    return {'kind':'BASIC_FORMAT_CHECK', 'malware_scan':'NOT_PERFORMED', 'code_executed':False}
