"""Synchronous Vertex Omni generation; preserves existing clip filenames."""
import base64
import json
from . import env, vertex
from .project import Project

MODEL = 'gemini-omni-1.1-flash-preview'


def submit(project: Project, length: int, only=None, headless=False):
    from .cli import cmd_check
    from argparse import Namespace
    cmd_check(Namespace(project=str(project.dir)))
    if env.get('VERTEX_AI_VIDEO_MODEL',MODEL)!=MODEL:
        raise SystemExit(f'영상 모델은 {MODEL}만 사용한다')
    targets=[c for c in project.load_cuts() if c['len']==length and (c['n'] in only if only is not None else not c['done'])]
    project.clips.mkdir(parents=True,exist_ok=True); project.build.mkdir(parents=True,exist_ok=True)
    meta=project.build/f'submit_{length}s.json'
    for c in targets:
        response=vertex.request('v1beta1/projects/{project}/locations/global/interactions',
            {'model':MODEL,'background':False,'store':False,'stream':False,
             'input':[{'type':'text','text':c['prompt']}],
             'response_format':[{'type':'video','resolution':'720p','duration':f'{length}s','aspect_ratio':'9:16'}],
             'generation_config':{'video_config':{'task':'text_to_video'}}},MODEL)
        videos=[p for s in response.get('steps',[]) for p in s.get('content',[]) if p.get('type')=='video']
        if response.get('status')!='completed' or len(videos)!=1 or not videos[0].get('data'):
            raise SystemExit('영상 완료 응답이 없다. 비용을 확인하기 전에는 재시도하지 않는다')
        data=base64.b64decode(videos[0]['data'],validate=True)
        if not data:
            raise SystemExit('영상 응답이 비어 있다')
        temp=project.clip(c['n']).with_suffix('.tmp'); temp.write_bytes(data); temp.replace(project.clip(c['n']))
        (project.build/f'vertex_C{c["n"]:02d}.json').write_text(json.dumps({'model':MODEL,'usage':response.get('usage'),'seconds':length}),encoding='utf-8')
        print(f'C{c["n"]:02d} Vertex AI 생성 완료')
    meta.write_text(json.dumps({'provider':'vertex','order':[c['n'] for c in targets]}),encoding='utf-8')
    return meta


def collect(project: Project, length: int, headless=False):
    meta=project.build/f'submit_{length}s.json'
    if not meta.exists():
        raise SystemExit('먼저 submit을 실행하라')
    data=json.loads(meta.read_text(encoding='utf-8'))
    if data.get('provider')!='vertex':
        raise SystemExit('이 기록은 Vertex AI 생성 기록이 아니다')
    order=data['order']
    if any(not project.clip(n).exists() for n in order):
        raise SystemExit('완료 클립이 누락됐다. 비용 확인 후 복구하라')
    print(f'{len(order)}컷은 submit 단계에서 이미 로컬 저장됐다')
    return len(order)
