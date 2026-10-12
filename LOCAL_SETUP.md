# Vertex AI용 Flowmaker 설치본

저장소를 복제한 디렉터리에서 설치하고 실행합니다.
`bash install.sh`는 Python 가상환경, Pillow, Playwright Chromium, ffmpeg 및 Pretendard 폰트를 준비합니다.
설치 후 `.env`의 `GOOGLE_CLOUD_PROJECT`를 실제 프로젝트 ID로 변경하세요.

## 원본 분석 및 변경

원본은 건축·공학 쇼츠의 대본, 컷 검사, Flow 브라우저 제출·회수, ElevenLabs 더빙 및 타임스탬프,
자막·효과음·ffmpeg 조립을 제공하는 Python CLI입니다. 웹 앱이나 GUI는 아닙니다.

이 설치본은 다음 경로를 사용합니다.

- 영상 `submit`/`collect`: Vertex AI Omni 1.1, 720p, 9:16. submit이 순차 생성 후 직접 저장합니다.
- 음성 `tts`: Vertex AI `gemini-3.8-flash-tts`, 기본 목소리 Kore. ADC 인증을 사용합니다.
- 같은 목소리와 스타일로 문장별 생성하고 로컬 WAV 캐시를 재사용합니다. 톤이 문장 사이에서 다소 달라질 수 있습니다.
- 문장 경계는 WAV 실측 시간이며, 글자별 시간은 문장 내부 보간입니다. 단어 단위 강제 정렬은 아닙니다.
- 출력은 기존 `narration_raw.mp3`, `alignment.json` 규약을 유지하므로 timing/subs/assemble을 사용할 수 있습니다.
- 효과음·음악은 외부 API 대신 원본 로컬 합성 또는 저작권 확인된 파일을 사용합니다.
- Flow 웹 로그인과 ElevenLabs 키는 필요 없습니다. 원본 flow_driver는 참고 코드 및 기존 순수 로직 테스트용으로 남아 있습니다.

## 실행

```bash
cd flowmaker_public
.venv/bin/python -m flowmaker doctor
export VIDEO_STYLE=mixed  # 원본 점토 예시를 사용할 때
.venv/bin/python -m flowmaker new bridge --from drawbridge
.venv/bin/python -m flowmaker tts bridge
.venv/bin/python -m flowmaker timing bridge --target 100
.venv/bin/python -m flowmaker sync-need bridge
.venv/bin/python -m flowmaker check bridge
.venv/bin/python -m flowmaker submit bridge 8
.venv/bin/python -m flowmaker collect bridge 8
.venv/bin/python -m flowmaker subs bridge
.venv/bin/python -m flowmaker assemble bridge
```

로컬 전역 `flowmaker` 실행기는 이 설치본과 가상환경을 사용하도록 설정할 수 있습니다.
기본 설치 스크립트는 전역 실행기를 만들지 않습니다.
`.env`에 프로젝트 및 모델이 설정되어 있습니다. 인증 토큰은 저장소에 저장하지 않습니다.

## 무료 크레딧 관문

유료 호출은 `~/.flowmaker/credit-check.json`이 없거나 15분 이상 지났으면 차단됩니다.
이는 에이전트가 실시간 결제 화면과 공식 단가를 확인한 후 작성하는 검토 기록입니다.
실시간 조회 자동화나 클라우드 전체의 강제 지출 한도가 아닙니다.

기록 스키마:

```json
{
  "project": "your-google-cloud-project",
  "free_trial_active": true,
  "eligible": true,
  "checked_at": "<현재 확인 시각, timezone 포함 ISO8601>",
  "expires_at": "<콘솔에서 확인한 만료 시각, timezone 포함 ISO8601>",
  "original_krw": 407626,
  "remaining_krw": "<현재 콘솔 잔액 숫자>",
  "unreconciled_krw": "<모든 미반영 요청의 보수적 비용 예약 합계 숫자>",
  "models": {
    "gemini-3.8-flash-tts": {
      "max_cost_per_request_krw": "<입력 및 최대 출력 전체를 포함한 비용 상한 숫자>",
      "pricing_source": "<공식 단가 HTTPS URL>",
      "scope": "entire_request"
    }
  }
}
```

위 예시는 템플릿입니다. 확인하지 않은 값을 채워 실행하지 마세요. 영상 모델도 같은 방식으로
검토 항목을 추가해야 합니다. 에이전트는 요청의 최대 길이·토큰·해상도·환율을 포함해 상한을 산정합니다.
각 요청 전에 비용을 예약하고 최초 크레딧의 10%를 남깁니다. 실패·타임아웃도 결제 대조 전에는
예약을 유지합니다. 대조 시 새 잔액에 이미 반영된 예약만 해제해야 하며 외부 프로젝트의 사용량도 확인합니다.
한 번에 한 요청만 허용하고 자동 재시도하지 않습니다. 프로세스 강제 종료 시 lock 파일은
실행 중인 작업과 비용 상태를 확인한 후에만 제거합니다.

검증은 합성 WAV/가짜 API 응답으로 음성 디코딩, 문장 타이밍, 캐시, 비용 차단과 기존 조립을 확인합니다.
설치 자체에는 과금 API 호출이 필요하지 않습니다. 실제 TTS 출력 품질은 별도 크레딧 검토 후 확인해야 합니다.

## 전체 실사와 음악·효과음

기본 `VIDEO_STYLE=photoreal`은 전체 컷을 real/hist 실사로 구성하며 원본의 실사 비중 제한을 적용하지 않습니다.
프롬프트 꼬리·숫자·구성 요소 검사 등은 유지합니다. 원본 점토 예시는 `VIDEO_STYLE=mixed`로 실행합니다.

```bash
flowmaker music myproject ambient --seconds 100  # 잔잔한 원본 합성 배경음악
flowmaker music myproject pulse --seconds 100    # 리듬이 있는 합성 배경음악
flowmaker audio myproject /absolute/path/music.wav --kind bgm
flowmaker audio myproject /absolute/path/effect.wav --kind sfx --name lever --sentence 1 --offset 2 --volume 0.3
flowmaker sfx myproject
flowmaker assemble myproject
```

`music`은 자유형 AI 작곡이 아닌 ambient/pulse 프리셋 합성입니다. API 비용이 없으며 생성한 파형은
외부 음원에서 복제하지 않습니다. `sfx.json`에 `preset: chime` 또는 `preset: whoosh`와 `duration`을
넣으면 효과음도 로컬에서 합성합니다. 가져온 음원은 사용자가 사용 권리를 확인해야 합니다.
기존 조립기는 음악을 더빙에 맞춰 자동으로 줄이고, 효과음을 지정 문장과 offset에 배치합니다.
