"""Use local audio assets only; external paid SFX/music APIs are disabled."""
import json
from .project import Project


def generate(project: Project) -> bool:
    if not project.sfx_path.exists():
        print('sfx.json 없음 — 효과음 없이 간다'); return True
    plan=json.loads(project.sfx_path.read_text(encoding='utf-8'))
    missing=[s['name'] for s in plan if not (project.build/'sfx'/f'{s["name"]}.mp3').exists()]
    if missing:
        raise SystemExit('외부 효과음 API는 사용하지 않는다. 저작권 확인된 파일을 build/sfx에 넣어라: '+', '.join(missing))
    return True


def music(project: Project, prompt: str, seconds: int = 100):
    raise SystemExit('외부 음악 API는 사용하지 않는다. 저작권 확인된 bgm.mp3를 프로젝트에 넣어라')
