---
description: CapCut 프로젝트의 무음 구간을 안전 백업 후 자동 컷편집하고, 박수/피크 후보와 컷 리포트를 생성합니다.
argument-hint: CapCut 프로젝트 ID와 옵션
allowed-tools: Read, Write, Edit, Glob, Grep, Bash
user-invocable: true
---

# CapCut 추가 무음 컷 스킬

이미 CapCut에서 편집 중이거나 완료한 프로젝트에, **원본 영상 기준 무음 구간**을 찾아 추가로 잘라냅니다. `draft_info.json`의 `tracks[0].segments`를 분할하고 이후 세그먼트의 `target_timerange`를 전부 앞으로 당깁니다. Track[1+]의 segment들(outro 등)도 새 총 길이에 맞춰 shift됩니다.

## 사전 조건

- macOS + CapCut 데스크톱 설치
- 프로젝트 위치: `~/Movies/CapCut/User Data/Projects/com.lveditor.draft/<project_id>/draft_info.json`
- 작업 스크립트: `{{SCRIPTS_DIR}}/capcut_silence_cut.py`
- FFmpeg 설치

## 실행 절차

### Step 0: 시작 질문 (무음 구간 세팅 필수)

이 스킬을 시작하면 **가장 먼저** 무음 구간 기준을 물어보세요. 사용자가 프로젝트 ID나 영상 경로를 이미 말했더라도 이 질문은 생략하지 않습니다.

반드시 아래 선택지로 묻습니다:

```text
무음 구간을 몇 초 이상부터 자를까요?
1) 0.6초 - 빠르게 촘촘히 자름, 말 사이 짧은 공백도 많이 제거
2) 0.8초 - 추천, 자연스러운 유튜브/강의 편집 균형
3) 1.0초 - 보수적, 긴 침묵만 제거
```

선택값 매핑:

| 선택 | `--silence-duration` | 사용 상황 |
|---|---:|---|
| `0.6` | `0.6` | 빠른 숏폼/템포감 있는 편집 |
| `0.8` | `0.8` | 추천 기본값, 일반 유튜브/강의 |
| `1` / `1.0` | `1.0` | 보수적 롱폼/강의 |

사용자가 "추천", "기본", "알아서"라고 답하면 `0.8`을 사용합니다.
사용자가 다른 값을 요구하면 적용 가능하지만, 먼저 위 세 선택지 밖의 커스텀값임을 확인합니다.

### Step 1: 파라미터 인터뷰

사용자에게 반드시 아래 3가지를 물어보세요. 대답 없이 진행 금지.

1. **프로젝트 ID** — `~/Movies/CapCut/User Data/Projects/com.lveditor.draft/` 하위 폴더명 (예: `0421`).
   - 후보 리스트를 `ls`로 먼저 보여주고 선택받는 편이 편함.
2. **메인 소스 영상 경로** — silencedetect 대상이 될 원본 비디오 파일.
   - 확실치 않으면 `draft_info.json`의 `materials.drafts[0].draft.materials.videos[]`에서 `has_audio=true`인 항목의 `path`를 읽어 후보를 보여주세요.
3. **무음 기준/여백 파라미터** — Step 0에서 받은 값을 사용하고, 여백만 아래 질문으로 확인:
   - "컷 경계에 얼마나 여백을 남길까요? **(표준: 0.15초)**"
   - 사용자가 "표준/기본/그대로" 류의 답을 하면 `--silence-duration 0.8 --silence-threshold -35 --padding 0.15` 사용.
   - `--silence-threshold`는 필요할 때만 추가로 질문 (보통 -35dB 고정).
4. **박수 편집점 체크 여부** — 사용자가 강의/촬영 컷편집에서 "박수", "클랩", "편집점", "싱크 포인트"를 언급하면 박수 소리를 편집점 후보로 별도 체크합니다.
   - 박수 후보는 자동 컷 적용 대상이 아니라 **검토용 마커**로 취급합니다.
   - 후보 타임스탬프, 주변 무음 여부, 컷 적용 영향 여부를 dry-run 결과와 함께 이 대화에 요약해서 올립니다.
   - 가능하면 후보별 0.8~1.5초 전후의 짧은 오디오/영상 확인 클립을 `capcut_reports/<PROJECT_ID>/`에 내보내고 경로를 함께 제공합니다.

### Step 2: 안전 체크

반드시 순서대로:

1. **CapCut 프로세스 종료 확인** —
   ```bash
   pgrep -lf "CapCut.app/Contents/MacOS/CapCut" | grep -v Helper
   ```
   결과 있으면 사용자에게 "CapCut을 저장 후 완전 종료(Cmd+Q)해주세요"라고 안내하고 중단.

2. **전체 폴더 백업** — `draft_info.json`만 백업하지 말고 **폴더 전체** 백업 (연관 캐시/썸네일 때문):
   ```bash
   TS=$(date +%Y%m%d_%H%M%S)
   SRC="$HOME/Movies/CapCut/User Data/Projects/com.lveditor.draft/<PROJECT_ID>"
   DST="$HOME/devmin/youtube_editor/capcut_backup/<PROJECT_ID>_$TS"
   mkdir -p "$HOME/devmin/youtube_editor/capcut_backup"
   cp -R "$SRC" "$DST"
   ```
   백업 경로를 사용자에게 알려주세요. 프로젝트는 수 GB일 수 있습니다.

### Step 3: Dry-run으로 계획 검증

`--dry-run`으로 먼저 실행해서 **기존/신규 세그먼트 수, 제거량, 최종 길이**를 사용자에게 보여주세요:

```bash
python3 {{SCRIPTS_DIR}}/capcut_silence_cut.py \
  --project <PROJECT_ID> \
  --source "<SOURCE_VIDEO_PATH>" \
  --silence-duration <0.6|0.8|1.0> \
  --silence-threshold -35 \
  --padding 0.15 \
  --dry-run
```

박수 편집점 후보까지 체크해야 하면 dry-run에 아래 옵션을 추가합니다:

```bash
python3 {{SCRIPTS_DIR}}/capcut_silence_cut.py \
  --project <PROJECT_ID> \
  --source "<SOURCE_VIDEO_PATH>" \
  --silence-duration <0.6|0.8|1.0> \
  --silence-threshold -35 \
  --padding 0.15 \
  --report-claps \
  --report-dir "capcut_reports/<PROJECT_ID>" \
  --dry-run
```

출력 예:
```
기존 세그먼트: 88 → 신규: 152
기존 길이: 1270.70s → 신규: 1141.15s
제거량: 129.55s
박수 후보:
- 00:03:12.450 / 신뢰도 높음 / 컷 경계 +0.42s / 확인 클립: capcut_reports/<PROJECT_ID>/clap_01_00-03-12.450.wav
```

### Step 3.5: 박수 편집점 후보 보고

박수 체크가 필요한 작업이면 실제 적용 전에 후보를 별도 보고하세요.

- 오디오 피크/트랜지언트가 급격히 튀는 지점을 박수 후보로 잡고, 말소리 피크와 구분이 애매하면 "확인 필요"로 표시합니다.
- 후보가 무음 컷 경계 근처에 있으면 해당 컷이 박수 직전/직후를 과도하게 자르지 않는지 표시합니다.
- 보고 형식:
  ```
  박수 후보:
  - 00:03:12.450 / 신뢰도 높음 / 컷 경계 +0.42s / 확인 클립: <path>
  - 00:07:48.120 / 확인 필요 / 말소리 피크 가능성 / 확인 클립: <path>
  ```
- 사용자가 "박수 기준으로도 잘라줘"라고 명시하지 않는 한, 박수 후보는 타임라인을 자동 변경하지 않습니다.

사용자가 **진행 OK**한 후에만 다음 단계.

### Step 4: 실제 적용

`--dry-run` 플래그 제거 후 재실행. `draft_info.json`이 원자적으로 덮어써집니다.

### Step 5: 검증 안내

사용자에게:
- CapCut을 열어서 프로젝트 확인 (타임라인 길이, 재생 정상 여부, 끊김 위치)
- 문제 있으면 아래 명령으로 백업 폴더의 `draft_info.json`만 원복:
  ```bash
  cp <BACKUP_DIR>/draft_info.json "<PROJECT_DIR>/draft_info.json"
  ```

## 표준 파라미터

사용자가 "추천", "표준으로", "기본값", "그대로", "알아서" 등으로 답할 경우:

| 파라미터 | 표준값 | 의미 |
|---|---|---|
| `--silence-duration` | `0.8` | 0.8초 이상 무음 컷 대상, 자연스러운 기본 추천 |
| `--silence-threshold` | `-35` | 무음 판정 dB |
| `--padding` | `0.15` | 컷 경계 앞뒤 0.15초씩 남김 |

## 주의사항

- **CapCut 비공식 포맷**: CapCut 업데이트 시 스키마가 깨질 수 있음. 실패 시 백업 복원.
- **박수 소리 처리**: 박수는 무음이 아니라 큰 피크라서 `silencedetect`만으로는 편집점 의미를 알 수 없습니다. 박수 후보는 반드시 별도 체크해서 사용자에게 타임스탬프/확인 클립을 올리고, 사용자의 명시적 지시 없이 박수 지점 자체를 자동 컷 기준으로 삼지 마세요.
- **Compound clip 처리**: 메인 편집 대상은 주로 "복합 클립"을 참조하는 parent project의 `tracks[0]`. 이 스킬은 그 레벨에서만 작동 (compound clip 내부는 건드리지 않음).
- **세그먼트 속성 보존**: 스크립트는 원본 세그먼트를 deepcopy해서 각 조각에 동일 효과/키프레임/볼륨/색보정 등을 복사. 각 조각에 새 UUID를 부여.
- **Track[1]+ shift**: outro 같은 후반부 트랙의 segment `target_timerange.start`는 원본 끝에서의 offset을 유지하며 새 총 길이에 맞춰 이동.
- **keyframe 정확도**: 세그먼트를 쪼갤 때 내부 키프레임 타이밍은 원본 기준 그대로 복사됨. 키프레임을 많이 쓴 세그먼트는 시각적으로 어색할 수 있음 — 확인 후 수동 조정 필요.
