"""Local audio import and original procedural soundtracks. No paid APIs."""
from __future__ import annotations
import array
import json
import math
import random
import re
import subprocess
import wave
from pathlib import Path
from .project import Project

RATE = 24000


def _name(name):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', name):
        raise SystemExit('음원 이름은 영문·숫자·밑줄·하이픈만 사용하라')
    return name


def _encode(dst, samples):
    dst.parent.mkdir(parents=True, exist_ok=True)
    wav=dst.with_suffix('.source.wav')
    values=array.array('h', (int(max(-1,min(1,s))*32767) for s in samples))
    import sys
    if sys.byteorder!='little':values.byteswap()
    with wave.open(str(wav),'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(RATE);w.writeframes(values.tobytes())
    try:
        subprocess.run(['ffmpeg','-v','error','-i',str(wav),'-c:a','libmp3lame','-b:a','128k',str(dst),'-y'],check=True)
    finally:
        wav.unlink(missing_ok=True)


def _effect(preset, seconds):
    if preset not in ('chime','whoosh') or not 0.1<=seconds<=10:
        raise SystemExit('효과음 preset은 chime/whoosh, 길이는 0.1~10초다')
    rng=random.Random(86)
    previous=0.0
    for i in range(int(seconds*RATE)):
        t=i/RATE
        if preset=='chime':
            yield .24*math.exp(-5*t)*min(t/.01,1)*(math.sin(2*math.pi*880*t)+.3*math.sin(2*math.pi*1320*t))
        else:
            previous=.7*previous+.3*rng.uniform(-1,1)
            yield .45*previous*math.sin(math.pi*t/seconds)**2


def generate(project: Project) -> bool:
    if not project.sfx_path.exists():
        print('sfx.json 없음 — 효과음 없이 간다');return True
    for s in json.loads(project.sfx_path.read_text(encoding='utf-8')):
        dst=project.build/'sfx'/f'{_name(s["name"])}.mp3'
        if dst.exists():continue
        if 'preset' not in s:
            raise SystemExit(f'{s["name"]}: audio 명령으로 로컬 파일을 연결하거나 chime/whoosh preset을 지정하라')
        _encode(dst,_effect(s['preset'],float(s.get('duration',1))))
        print(f'효과음 {s["name"]} 생성 완료 (로컬 · API 비용 없음)')
    return True


def music(project: Project, prompt: str, seconds: int = 100):
    if prompt not in ('ambient','pulse') or not 1<=seconds<=600:
        raise SystemExit('로컬 음악 preset은 ambient/pulse, 길이는 1~600초다. 사용자 음악은 audio --kind bgm으로 연결하라')
    frequencies=(130.81,164.81,196.00,261.63)
    def samples():
        for i in range(seconds*RATE):
            t=i/RATE
            fade=min(t/1.2,1,(seconds-t)/1.2)
            pad=sum(math.sin(2*math.pi*f*t+.02*math.sin(t))* .025 for f in frequencies)
            pulse=.05*math.exp(-12*(t%0.5))*math.sin(2*math.pi*65.4*t) if prompt=='pulse' else 0
            yield (pad+pulse)*max(0,fade)
    _encode(project.bgm,samples())
    print(f'로컬 합성 음악 {prompt} · {seconds}초 → {project.bgm.name} (API 비용 없음)')


def attach(project: Project, source, kind, name='effect', sentence=1, offset=0, volume=.35):
    src=Path(source).expanduser().resolve()
    if not src.is_file():raise SystemExit(f'음원 파일이 없다: {src}')
    if kind not in ('bgm','sfx'):raise SystemExit('kind는 bgm 또는 sfx다')
    if not math.isfinite(offset) or offset<0 or not math.isfinite(volume) or not 0<=volume<=1:
        raise SystemExit('offset은 0 이상, volume은 0~1이어야 한다')
    if kind=='sfx' and not 1<=sentence<= (project.n_sentences() or 0):
        raise SystemExit('효과음의 sentence가 대본 범위를 벗어났다')
    name=_name(name)
    dst=project.bgm if kind=='bgm' else project.build/'sfx'/f'{name}.mp3'
    if src==dst.resolve():raise SystemExit('입력 파일과 출력 파일이 같다')
    dst.parent.mkdir(parents=True,exist_ok=True)
    subprocess.run(['ffmpeg','-v','error','-i',str(src),'-vn','-c:a','libmp3lame','-b:a','128k',str(dst),'-y'],check=True)
    if kind=='sfx':
        plan=json.loads(project.sfx_path.read_text(encoding='utf-8')) if project.sfx_path.exists() else []
        plan=[s for s in plan if s['name']!=name]
        plan.append({'name':name,'sentence':sentence,'offset':offset,'volume':volume,'source':'local_file'})
        project.sfx_path.write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'로컬 음원 연결 완료 → {dst}')
