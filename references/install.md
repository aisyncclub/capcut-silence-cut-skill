# capcut-silence-cut 설치 가이드

## 사전 조건
- macOS (Apple Silicon 권장)
- Python 3.9+, ffmpeg
- Claude Code CLI

## Claude Code 설치

```bash
mkdir -p ~/.claude/skills
git clone https://github.com/aisyncclub/capcut-silence-cut-skill.git ~/.claude/skills/capcut-silence-cut
```

Claude Code를 재시작합니다.

## Codex 설치

```bash
mkdir -p ~/.codex/skills
git clone https://github.com/aisyncclub/capcut-silence-cut-skill.git ~/.codex/skills/capcut-silence-cut
```

Codex를 재시작합니다.

## FFmpeg 설치

```bash
brew install ffmpeg
```

## 시작 시 필수 질문

스킬 실행 시 에이전트는 먼저 아래 질문을 해야 합니다.

```text
무음 구간을 몇 초 이상부터 자를까요?
1) 0.6초 - 빠르게 촘촘히 자름
2) 0.8초 - 추천 기본값
3) 1.0초 - 보수적 컷
```

사용자가 "추천", "기본", "알아서"라고 하면 `0.8`을 사용합니다.

## 직접 실행 확인

```bash
python3 scripts/capcut_silence_cut.py --help
python3 -m py_compile scripts/capcut_silence_cut.py
```
