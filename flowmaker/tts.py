"""Gemini TTS dubbing: measured sentence boundaries, interpolated character times."""
from __future__ import annotations
import base64
import hashlib
import io
import json
import subprocess
import wave
from . import env, vertex
from .project import Project

MODEL = 'gemini-3.8-flash-tts'
DEFAULT_VOICE = 'Kore'


def decode_audio(response):
    parts = [p for c in response.get('candidates',[]) for p in c.get('content',{}).get('parts',[])]
    items = [p['inlineData'] for p in parts if p.get('inlineData',{}).get('mimeType','').startswith('audio/')]
    if len(items) != 1:
        raise SystemExit('TTS 응답에 단일 음성이 없다. 자동 재시도하지 않는다')
    item = items[0]
    audio = base64.b64decode(item['data'], validate=True)
    if audio.startswith(b'RIFF'):
        with wave.open(io.BytesIO(audio),'rb') as w:
            if w.getnchannels()!=1 or w.getsampwidth()!=2 or w.getnframes()==0:
                raise SystemExit('TTS WAV는 비어 있지 않은 16-bit mono여야 한다')
            return w.readframes(w.getnframes()), w.getframerate()
    mime = item['mimeType']
    if not mime.startswith('audio/L16') or not audio or len(audio)%2:
        raise SystemExit(f'지원하지 않는 TTS 오디오 형식: {mime}')
    rate = next((int(v.split('=',1)[1]) for v in mime.split(';') if v.strip().startswith('rate=')),24000)
    if rate <= 0:
        raise SystemExit('잘못된 TTS 샘플레이트')
    return audio, rate


def synthesize(project: Project):
    model = env.get('TTS_MODEL', MODEL)
    if model != MODEL:
        raise SystemExit(f'음성 모델은 {MODEL}만 사용한다. TTS_MODEL 설정을 확인하라')
    voice = env.get('TTS_VOICE',DEFAULT_VOICE)
    style = env.get('TTS_STYLE','Clear natural Korean documentary narration, consistent calm delivery')
    lines = project.lines(project.script)
    if not lines:
        raise SystemExit('대본이 비어 있다')
    cache = project.build / 'tts'; cache.mkdir(parents=True,exist_ok=True)
    voice_path = project.dir / 'voices.json'
    voices = json.loads(voice_path.read_text(encoding='utf-8')) if voice_path.exists() else {}
    frames, chars, starts, ends, pos, rate = [],[],[],[],0.0,None
    for line_number, text in enumerate(lines, 1):
        settings = voices.get(str(line_number), {})
        voice = settings.get('voice', env.get('TTS_VOICE', DEFAULT_VOICE))
        style = settings.get('style', env.get('TTS_STYLE', 'Clear natural Korean documentary narration, consistent calm delivery'))
        digest = hashlib.sha256(json.dumps([vertex.project_id(),model,voice,style,text]).encode()).hexdigest()
        saved = cache / f'{digest}.wav'
        if saved.exists():
            with wave.open(str(saved),'rb') as w:
                if w.getnchannels()!=1 or w.getsampwidth()!=2:
                    raise SystemExit('캐시 WAV 형식 오류')
                pcm, sample_rate = w.readframes(w.getnframes()),w.getframerate()
        else:
            result = vertex.request('v1/projects/{project}/locations/global/publishers/google/models/'+model+':generateContent',
                {'contents':[{'role':'user','parts':[{'text':text,'speechMetadata':{'style':style}}]}],
                 'generationConfig':{'responseModalities':['AUDIO'],'speechConfig':{'voiceConfig':{'voice':voice}}}},model)
            pcm, sample_rate = decode_audio(result)
            with wave.open(str(saved),'wb') as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(sample_rate); w.writeframes(pcm)
        if rate is not None and rate!=sample_rate:
            raise SystemExit('문장별 샘플레이트가 다르다. 자동 재시도하지 않는다')
        rate = sample_rate
        duration = len(pcm)/(rate*2)
        if duration<=0:
            raise SystemExit('TTS 오디오가 비어 있다')
        if chars:
            chars.append(' '); starts.append(pos); ends.append(pos)
        for i,char in enumerate(text):
            chars.append(char); starts.append(pos+duration*i/len(text)); ends.append(pos+duration*(i+1)/len(text))
        pos+=duration; frames.append(pcm)
    combined = cache / 'combined.wav'
    with wave.open(str(combined),'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(b''.join(frames))
    subprocess.run(['ffmpeg','-v','error','-i',str(combined),'-c:a','libmp3lame','-b:a','128k',str(project.narration_raw),'-y'],check=True)
    alignment = {'characters':chars,'character_start_times_seconds':starts,'character_end_times_seconds':ends,
                 'source':'gemini_sentence_audio','character_timing':'interpolated','model':model,'default_voice':env.get('TTS_VOICE',DEFAULT_VOICE),'voices_by_line':voices}
    project.alignment.write_text(json.dumps(alignment,ensure_ascii=False),encoding='utf-8')
    print(f'더빙 저장 · {model} · {len(lines)}문장 · {pos:.2f}초 (글자 타이밍은 추정값)')
    return {'chars':len(chars),'seconds':pos,'model':model}
