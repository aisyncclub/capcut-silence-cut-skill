# CapCut Silence Cut Skill

Claude/Codex에서 CapCut Mac 프로젝트의 무음 구간을 안전하게 컷편집하기 위한 스킬입니다.

이 스킬은 `draft_info.json`을 직접 편집하므로 항상 dry-run, 전체 백업, CapCut 종료 확인을 먼저 수행하도록 설계되어 있습니다.

## 핵심 동작

- CapCut 프로젝트의 무음 구간 감지
- `tracks[0].segments` 분할 및 타임라인 당김
- 후반부 트랙 위치 보정
- 전체 프로젝트 백업
- dry-run 리포트
- 박수/클랩/피크 후보 리포트

## 시작 시 필수 질문

스킬을 시작하면 가장 먼저 무음 컷 기준을 선택해야 합니다.

```text
무음 구간을 몇 초 이상부터 자를까요?
1) 0.6초 - 빠르게 촘촘히 자름, 말 사이 짧은 공백도 많이 제거
2) 0.8초 - 추천, 자연스러운 유튜브/강의 편집 균형
3) 1.0초 - 보수적, 긴 침묵만 제거
```

추천 기본값은 `0.8초`입니다.

## Claude Code 설치

```bash
mkdir -p ~/.claude/skills
git clone https://github.com/aisyncclub/capcut-silence-cut-skill.git ~/.claude/skills/capcut-silence-cut
```

Claude Code를 재시작한 뒤 다음처럼 호출합니다.

```text
캡컷 무음 편집 스킬로 0503 프로젝트 무음 제거해줘
```

## Codex 설치

```bash
mkdir -p ~/.codex/skills
git clone https://github.com/aisyncclub/capcut-silence-cut-skill.git ~/.codex/skills/capcut-silence-cut
```

Codex를 재시작한 뒤 사용합니다.

## 사전 조건

- macOS
- CapCut desktop
- Python 3.9+
- FFmpeg

FFmpeg가 없다면:

```bash
brew install ffmpeg
```

## 직접 실행 예시

먼저 dry-run:

```bash
python3 scripts/capcut_silence_cut.py \
  --project 0503 \
  --source "/path/to/source.mp4" \
  --silence-duration 0.8 \
  --silence-threshold -35 \
  --padding 0.15 \
  --dry-run
```

박수 후보 리포트 포함:

```bash
python3 scripts/capcut_silence_cut.py \
  --project 0503 \
  --source "/path/to/source.mp4" \
  --silence-duration 0.8 \
  --silence-threshold -35 \
  --padding 0.15 \
  --report-claps \
  --report-dir "capcut_reports/0503" \
  --dry-run
```

적용은 dry-run 결과를 확인한 뒤 `--dry-run`을 제거해서 실행합니다.

## 안전 원칙

- CapCut이 켜져 있으면 적용하지 않습니다.
- `draft_info.json`만이 아니라 프로젝트 폴더 전체를 백업합니다.
- 박수 후보는 자동 컷 기준이 아니라 검토용 마커입니다.
- 사용자가 승인하기 전에는 실제 적용하지 않습니다.

