"""ADC REST transport and fail-closed, manually reviewed free-credit gate."""
from __future__ import annotations
import datetime as dt
import json
import math
import os
import subprocess
import urllib.error
import urllib.request
import uuid
from contextlib import contextmanager
from . import env


def project_id():
    return env.require('GOOGLE_CLOUD_PROJECT', 'Vertex AI 프로젝트를 설정하라')


@contextmanager
def credit_reservation(model):
    home = env.home()
    path, lock = home / 'credit-check.json', home / 'credit-check.lock'
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise SystemExit('다른 유료 작업이 진행 중이다. 자동 재시도하지 않는다')
    os.close(fd)
    try:
        if not path.exists():
            raise SystemExit('무료 크레딧 확인 기록이 없다. 에이전트가 실시간 잔액·단가를 확인해야 한다')
        try:
            r = json.loads(path.read_text(encoding='utf-8'))
            now = dt.datetime.now(dt.timezone.utc)
            age = (now - dt.datetime.fromisoformat(r['checked_at'])).total_seconds()
            cap = float(r['models'][model]['max_cost_per_request_krw'])
            available = float(r['remaining_krw']) - float(r['unreconciled_krw'])
            reserve = float(r['original_krw']) * .1
            valid = (r['project'] == project_id() and r['free_trial_active'] is True and r['eligible'] is True
                     and 0 <= age <= 900 and now < dt.datetime.fromisoformat(r['expires_at'])
                     and r['models'][model]['pricing_source'].startswith('https://')
                     and r['models'][model]['scope'] == 'entire_request')
        except (KeyError, ValueError, TypeError, OverflowError):
            raise SystemExit('크레딧 확인 기록이 불완전하다. 잔액·만료일·모델 단가를 다시 확인하라')
        if not valid or not all(math.isfinite(x) for x in (cap, available, reserve)) or cap <= 0 or reserve <= 0 or available - cap < reserve:
            raise SystemExit('무료 크레딧 확인 만료 또는 안전 잔액 부족. 유료 호출 중단')
        entry = {'id':str(uuid.uuid4()), 'model':model, 'reserved_krw':cap, 'status':'pending', 'created_at':now.isoformat()}
        r['unreconciled_krw'] = float(r['unreconciled_krw']) + cap
        r.setdefault('reservations', []).append(entry)
        path.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding='utf-8'); path.chmod(0o600)
        try:
            yield entry
        except BaseException:
            entry['status'] = 'unknown_or_failed'
            raise
        else:
            entry['status'] = 'completed_unreconciled'
        finally:
            path.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding='utf-8')
            print(f'비용 상한 예약 ₩{cap:,.2f} · 유효 잔액 ₩{available-cap:,.2f} (실제 차감 확인 대기)')
    finally:
        lock.unlink(missing_ok=True)


def request(path, body, model):
    project = project_id()
    if env.get('GOOGLE_CLOUD_LOCATION', 'global') != 'global':
        raise SystemExit('이 모델은 global 위치를 사용해야 한다')
    try:
        token = subprocess.run(['gcloud','auth','application-default','print-access-token'], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        raise SystemExit('ADC 인증 실패. gcloud auth application-default login 으로 인증하라')
    if not token:
        raise SystemExit('ADC 액세스 토큰이 비어 있다')
    req = urllib.request.Request('https://aiplatform.googleapis.com/' + path.format(project=project), data=json.dumps(body).encode(), headers={'Authorization':'Bearer '+token, 'Content-Type':'application/json'})
    with credit_reservation(model) as entry:
        try:
            with urllib.request.urlopen(req, timeout=600) as response:
                result = json.load(response)
        except urllib.error.HTTPError as e:
            raise SystemExit(f'Vertex AI 오류 {e.code}: {e.read().decode(errors="replace")[:500]}')
        entry['usage'] = result.get('usageMetadata', result.get('usage', {}))
        return result
