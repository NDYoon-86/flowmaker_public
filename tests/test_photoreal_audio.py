import json
import subprocess
import pytest
from flowmaker import style,sfx
from flowmaker.project import Project


def test_full_photoreal_mode_preserves_prompt_validation():
    cut={'n':1,'len':8,'kind':'real','prompt':'A wooden beam gently moves on a stone support.'+style.real_tail()}
    assert style.check([cut],mode='photoreal')==[]
    assert any('실사 비중' in v for v in style.check([cut]))
    cut['prompt']='bad tail'
    assert any('꼬리' in v for v in style.check([cut],mode='photoreal'))


def test_photoreal_rejects_clay():
    cut={'n':1,'len':8,'kind':'diag','prompt':'A clay lever gently moves.'+style.diag_tail()}
    assert any('전체 실사' in v for v in style.check([cut],mode='photoreal'))


def test_local_soundtrack_effects_and_import(tmp_path):
    p=Project(tmp_path);p.script.write_text('테스트.',encoding='utf-8')
    sfx.music(p,'ambient',seconds=1)
    assert p.bgm.stat().st_size>0
    p.sfx_path.write_text(json.dumps([{'name':'chime','preset':'chime','sentence':1,'duration':.2,'volume':.2}]),encoding='utf-8')
    assert sfx.generate(p)
    effect=p.build/'sfx/chime.mp3'
    assert effect.stat().st_size>0
    sfx.attach(p,effect,'sfx','imported',1,.1,.3)
    plan=json.loads(p.sfx_path.read_text(encoding='utf-8'))
    assert plan[-1]['name']=='imported' and plan[-1]['offset']==.1
    result=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',str(p.bgm)],capture_output=True,text=True,check=True)
    assert 1<=float(result.stdout)<1.2


@pytest.mark.parametrize('name',['../outside','a/b',''])
def test_audio_import_rejects_unsafe_names(tmp_path,name):
    p=Project(tmp_path);p.script.write_text('테스트.',encoding='utf-8')
    source=tmp_path/'input.wav';source.write_bytes(b'placeholder')
    with pytest.raises(SystemExit,match='음원 이름'):sfx.attach(p,source,'sfx',name)


def test_modern_drama_tail_allows_visible_faces():
    cut={'n':1,'len':8,'kind':'hist','prompt':'A father wears a navy jacket, smiles at his family.'+style.drama_tail()}
    assert 'Faces remain visible' in cut['prompt']
    assert style.check([cut],mode='photoreal')==[]
