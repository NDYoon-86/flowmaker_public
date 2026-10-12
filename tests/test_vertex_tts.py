import base64
import datetime as dt
import io
import json
import wave
import pytest
from flowmaker import tts, vertex, env, timing
from flowmaker.project import Project


def audio(seconds):
    out=io.BytesIO()
    with wave.open(out,'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(b'\0\0'*int(24000*seconds))
    return {'candidates':[{'content':{'parts':[{'inlineData':{'mimeType':'audio/wav','data':base64.b64encode(out.getvalue()).decode()}}]}}]}


def test_tts_timing_and_cache(tmp_path,monkeypatch):
    p=Project(tmp_path); p.script.write_text('안녕하세요.\n다리의 원리를 알아봅니다.\n',encoding='utf-8')
    p.subtitles.write_text(p.script.read_text(encoding='utf-8'),encoding='utf-8')
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT','test-project'); monkeypatch.setenv('TTS_MODEL',tts.MODEL)
    calls=[]
    def fake(path,body,model):
        calls.append(body)
        assert 'speechMetadata' in body['contents'][0]['parts'][0]
        assert body['generationConfig']['speechConfig']['voiceConfig']['voice']=='Kore'
        return audio(len(calls))
    monkeypatch.setattr(vertex,'request',fake)
    tts.synthesize(p)
    al=json.loads(p.alignment.read_text(encoding='utf-8'))
    assert ''.join(al['characters'])=='안녕하세요. 다리의 원리를 알아봅니다.'
    assert al['character_end_times_seconds'][-1]==3
    assert al['character_start_times_seconds'][len('안녕하세요. ')]==1
    assert p.narration_raw.stat().st_size>0
    timing.build(p,tempo=1)
    rows=json.loads(p.timing.read_text(encoding='utf-8'))
    assert rows[1]['start']==1 and rows[-1]['end']==3
    tts.synthesize(p)
    assert len(calls)==2  # second run reuses sentence cache, no paid requests


def test_no_audio_does_not_create_alignment(tmp_path,monkeypatch):
    p=Project(tmp_path);p.script.write_text('안녕',encoding='utf-8')
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT','test-project');monkeypatch.setenv('TTS_MODEL',tts.MODEL)
    monkeypatch.setattr(vertex,'request',lambda *a:{'candidates':[]})
    with pytest.raises(SystemExit,match='음성이 없다'): tts.synthesize(p)
    assert not p.alignment.exists()


@pytest.fixture
def review(tmp_path,monkeypatch):
    monkeypatch.setattr(env,'home',lambda:tmp_path)
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT','test-project')
    now=dt.datetime.now(dt.timezone.utc)
    data={'project':'test-project','free_trial_active':True,'eligible':True,'checked_at':now.isoformat(),
          'expires_at':(now+dt.timedelta(days=1)).isoformat(),'remaining_krw':1000,'original_krw':1000,'unreconciled_krw':0,
          'models':{tts.MODEL:{'max_cost_per_request_krw':100,'pricing_source':'https://cloud.google.com/pricing','scope':'entire_request'}}}
    path=tmp_path/'credit-check.json'
    path.write_text(json.dumps(data),encoding='utf-8')
    return path,data


@pytest.mark.parametrize('field,value',[('remaining_krw',150),('unreconciled_krw',850),('eligible',False),('project','wrong'),('remaining_krw',float('nan'))])
def test_credit_gate_rejects_unsafe_reviews(review,field,value):
    path,data=review;data[field]=value;path.write_text(json.dumps(data),encoding='utf-8')
    with pytest.raises(SystemExit):
        with vertex.credit_reservation(tts.MODEL): pytest.fail('gate allowed unsafe call')


def test_credit_gate_rejects_stale_review(review):
    path,data=review;data['checked_at']=(dt.datetime.now(dt.timezone.utc)-dt.timedelta(minutes=16)).isoformat()
    path.write_text(json.dumps(data),encoding='utf-8')
    with pytest.raises(SystemExit):
        with vertex.credit_reservation(tts.MODEL): pytest.fail('stale review accepted')


def test_failure_keeps_cost_reserved_and_unlocks(review):
    path,data=review
    with pytest.raises(TimeoutError):
        with vertex.credit_reservation(tts.MODEL): raise TimeoutError()
    saved=json.loads(path.read_text(encoding='utf-8'))
    assert saved['unreconciled_krw']==100
    assert saved['reservations'][0]['status']=='unknown_or_failed'
    assert not path.with_suffix('.lock').exists()


def test_missing_review_blocks_network(tmp_path,monkeypatch):
    monkeypatch.setattr(env,'home',lambda:tmp_path)
    with pytest.raises(SystemExit,match='확인 기록이 없다'):
        with vertex.credit_reservation(tts.MODEL): pytest.fail()


def test_vertex_video_generation_and_collection(tmp_path,monkeypatch):
    from flowmaker import vertex_video, cli
    p=Project(tmp_path)
    p.script.write_text('다리.',encoding='utf-8')
    p.cuts_path.write_text(json.dumps([{'n':1,'len':4,'kind':'diag','sentences':[1],'prompt':'A detailed clay diagram showing an ancient drawbridge lifting.'}]),encoding='utf-8')
    monkeypatch.setattr(cli,'cmd_check',lambda a:None)
    seen=[]
    def fake(path,body,model):
        seen.append(body)
        assert model==vertex_video.MODEL
        assert body['response_format'][0]=={'type':'video','resolution':'720p','duration':'4s','aspect_ratio':'9:16'}
        return {'status':'completed','steps':[{'content':[{'type':'video','data':base64.b64encode(b'fake-video').decode()}]}]}
    monkeypatch.setattr(vertex,'request',fake)
    vertex_video.submit(p,4)
    assert p.clip(1).read_bytes()==b'fake-video'
    assert vertex_video.collect(p,4)==1
    vertex_video.submit(p,4)
    assert len(seen)==1  # completed clips do not incur another request


def test_invalid_cuts_block_video_before_request(tmp_path,monkeypatch):
    from flowmaker import vertex_video
    p=Project(tmp_path);p.cuts_path.write_text('[]',encoding='utf-8')
    monkeypatch.setattr(vertex,'request',lambda *a:pytest.fail('invalid cuts reached paid API'))
    with pytest.raises(SystemExit,match='검사 실패'):vertex_video.submit(p,4)


def test_voice_map_assigns_distinct_speakers(tmp_path,monkeypatch):
    p=Project(tmp_path);p.script.write_text('아빠 대사.\n엄마 대사.\n',encoding='utf-8')
    p.dir.joinpath('voices.json').write_text(json.dumps({'1':{'voice':'Charon','style':'mature father'},'2':{'voice':'Kore','style':'energetic mother'}}),encoding='utf-8')
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT','test-project');monkeypatch.setenv('TTS_MODEL',tts.MODEL)
    seen=[]
    def fake(path,body,model):
        seen.append((body['generationConfig']['speechConfig']['voiceConfig']['voice'],body['contents'][0]['parts'][0]['speechMetadata']['style']))
        return audio(1)
    monkeypatch.setattr(vertex,'request',fake)
    tts.synthesize(p)
    assert seen==[('Charon','mature father'),('Kore','energetic mother')]


def test_reference_media_selects_reference_task(tmp_path,monkeypatch):
    from flowmaker import vertex_video,cli
    p=Project(tmp_path);p.script.write_text('아빠.',encoding='utf-8')
    (tmp_path/'portrait.png').write_bytes(b'portrait')
    p.cuts_path.write_text(json.dumps([{'n':1,'len':4,'kind':'hist','sentences':[1],'prompt':'A father holding a cream envelope with natural window light.','references':['portrait.png']}]),encoding='utf-8')
    monkeypatch.setattr(cli,'cmd_check',lambda a:None)
    def fake(path,body,model):
        assert body['generation_config']['video_config']['task']=='reference_to_video'
        assert body['input'][0]['mime_type']=='image/png'
        assert base64.b64decode(body['input'][0]['data'])==b'portrait'
        return {'status':'completed','steps':[{'content':[{'type':'video','data':base64.b64encode(b'video').decode()}]}]}
    monkeypatch.setattr(vertex,'request',fake)
    vertex_video.submit(p,4)
