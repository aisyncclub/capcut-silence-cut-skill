#!/usr/bin/env python3
"""
CapCut draft_info.json 추가 무음 컷 스크립트
- Track[0] 세그먼트 내부 무음을 silencedetect로 감지
- 각 세그먼트를 무음 기준으로 분할, 무음 부분 제거
- 이후 target_timerange 전부 앞으로 shift, Track[1] outro도 shift
"""

import argparse
import array
import copy
import json
import math
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path


def detect_silence(video_path, min_duration=1.0, threshold=-35):
    cmd = ["ffmpeg", "-i", video_path,
           "-af", f"silencedetect=noise={threshold}dB:d={min_duration}",
           "-f", "null", "-"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", r.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r.stderr)]
    return list(zip(starts, ends))  # in source-video seconds


def format_ts(seconds):
    seconds = max(0, seconds)
    total_ms = int(round(seconds * 1000))
    ms = total_ms % 1000
    total_s = total_ms // 1000
    s = total_s % 60
    total_m = total_s // 60
    m = total_m % 60
    h = total_m // 60
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"
    return f"{m:02d}:{s:02d}.{ms:03d}"


def detect_clap_candidates(video_path, max_candidates=30, min_gap=0.6):
    """Detect sharp, isolated audio transients that may be clap edit markers."""
    sample_rate = 16000
    window = int(sample_rate * 0.02)
    cmd = [
        "ffmpeg", "-v", "error", "-i", video_path,
        "-vn", "-ac", "1", "-ar", str(sample_rate), "-f", "s16le", "-"
    ]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0 or not r.stdout:
        return []

    samples = array.array("h")
    samples.frombytes(r.stdout)
    if not samples:
        return []

    frames = []
    for start in range(0, len(samples) - window + 1, window):
        chunk = samples[start:start + window]
        peak = max(abs(x) for x in chunk) / 32768.0
        rms = math.sqrt(sum(x * x for x in chunk) / len(chunk)) / 32768.0
        frames.append({
            "time": (start + window / 2) / sample_rate,
            "peak": peak,
            "rms": rms,
        })
    if len(frames) < 3:
        return []

    rms_values = sorted(f["rms"] for f in frames)
    median_rms = rms_values[len(rms_values) // 2] or 1e-6
    raw = []
    for i in range(1, len(frames) - 1):
        prev_f, cur, next_f = frames[i - 1], frames[i], frames[i + 1]
        is_local_peak = cur["peak"] >= prev_f["peak"] and cur["peak"] >= next_f["peak"]
        transient_ratio = cur["rms"] / max(median_rms, 1e-6)
        if is_local_peak and cur["peak"] >= 0.55 and transient_ratio >= 8:
            score = cur["peak"] * transient_ratio
            confidence = "높음" if cur["peak"] >= 0.78 and transient_ratio >= 12 else "확인 필요"
            raw.append({
                "time": cur["time"],
                "peak": cur["peak"],
                "ratio": transient_ratio,
                "score": score,
                "confidence": confidence,
            })

    raw.sort(key=lambda x: x["score"], reverse=True)
    selected = []
    for cand in raw:
        if all(abs(cand["time"] - kept["time"]) >= min_gap for kept in selected):
            selected.append(cand)
        if len(selected) >= max_candidates:
            break
    selected.sort(key=lambda x: x["time"])
    return selected


def nearest_cut_boundary(time_sec, silences_cc, padding):
    boundaries = []
    for start, end in silences_cc:
        boundaries.extend([start + padding, end - padding])
    if not boundaries:
        return None
    nearest = min(boundaries, key=lambda x: abs(x - time_sec))
    return nearest, time_sec - nearest


def export_clap_clip(video_path, out_path, center_time, clip_padding):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    start = max(0, center_time - clip_padding)
    duration = clip_padding * 2
    cmd = [
        "ffmpeg", "-v", "error", "-y", "-ss", f"{start:.3f}",
        "-i", video_path, "-t", f"{duration:.3f}", "-vn", "-ac", "1",
        str(out_path)
    ]
    subprocess.run(cmd, check=False)


def report_clap_candidates(args, candidates, src_to_cc_offset_us, silences_cc):
    report_dir = Path(args.report_dir or Path.cwd() / "capcut_reports" / args.project)
    report_dir.mkdir(parents=True, exist_ok=True)
    print()
    print("👏 박수 후보")
    if not candidates:
        print("   후보 없음")
        return
    for idx, cand in enumerate(candidates, start=1):
        timeline_time = cand["time"] + src_to_cc_offset_us / 1e6
        boundary = nearest_cut_boundary(timeline_time, silences_cc, args.padding)
        if boundary:
            _, delta = boundary
            boundary_text = f"컷 경계 {delta:+.2f}s"
        else:
            boundary_text = "컷 경계 없음"
        clip_path = report_dir / f"clap_{idx:02d}_{format_ts(timeline_time).replace(':', '-')}.wav"
        export_clap_clip(args.source, clip_path, cand["time"], args.clap_clip_padding)
        print(
            f"   - {format_ts(timeline_time)} / {cand['confidence']} / "
            f"{boundary_text} / peak={cand['peak']:.2f} / 확인 클립: {clip_path}"
        )


def plan_segment_cuts(seg, silences_cc, padding, min_keep=0.2):
    """
    seg의 source_timerange 내부에 들어가는 silences_cc(무음, 복합클립시간)를
    padding 적용 후 제거. 남는 구간 리스트 반환.
    각 반환: (new_source_start_us, new_source_dur_us)
    """
    src_start = seg['source_timerange']['start']  # us
    src_dur = seg['source_timerange']['duration']
    src_end = src_start + src_dur

    # cut regions in us (padding 적용)
    cuts = []
    for ss, se in silences_cc:
        ss_us = int(ss * 1e6)
        se_us = int(se * 1e6)
        # overlap with [src_start, src_end]
        lo = max(src_start, ss_us)
        hi = min(src_end, se_us)
        if hi <= lo:
            continue
        # padding: 무음 양 끝에서 padding만큼 남기고 자름
        pad = int(padding * 1e6)
        cut_lo = lo + pad
        cut_hi = hi - pad
        if cut_hi - cut_lo < int(0.05 * 1e6):  # 50ms 이하는 자를 의미 없음
            continue
        cuts.append((cut_lo, cut_hi))

    if not cuts:
        return [(src_start, src_dur)]

    # 겹치는 cut 병합
    cuts.sort()
    merged = [cuts[0]]
    for a, b in cuts[1:]:
        if a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))

    # keep regions
    keeps = []
    cursor = src_start
    for a, b in merged:
        if a > cursor:
            keeps.append((cursor, a - cursor))
        cursor = b
    if cursor < src_end:
        keeps.append((cursor, src_end - cursor))

    # 너무 짧은 조각 제거 (최소 min_keep)
    min_us = int(min_keep * 1e6)
    keeps = [(s, d) for s, d in keeps if d >= min_us]
    return keeps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--project', required=True, help='CapCut 프로젝트 폴더 (e.g. 0421)')
    ap.add_argument('--source', required=True, help='메인 소스 비디오 경로')
    ap.add_argument('--silence-duration', type=float, default=0.8, help='무음 컷 기준 초. 추천 선택지: 0.6, 0.8, 1.0 (default: 0.8)')
    ap.add_argument('--silence-threshold', type=int, default=-35, help='무음 판정 dB (default: -35)')
    ap.add_argument('--padding', type=float, default=0.15, help='컷 경계 앞뒤 여백 초 (default: 0.15)')
    ap.add_argument('--dry-run', action='store_true', help='실제 변경 없이 계획만 출력')
    ap.add_argument('--report-claps', action='store_true', help='박수/클랩 편집점 후보를 보고하고 확인 클립 생성')
    ap.add_argument('--clap-max-candidates', type=int, default=30)
    ap.add_argument('--clap-min-gap', type=float, default=0.6)
    ap.add_argument('--clap-clip-padding', type=float, default=0.75)
    ap.add_argument('--report-dir', help='박수 후보 확인 클립 출력 폴더')
    args = ap.parse_args()

    base = os.path.expanduser(f'~/Movies/CapCut/User Data/Projects/com.lveditor.draft/{args.project}')
    draft_path = os.path.join(base, 'draft_info.json')
    if not os.path.exists(draft_path):
        print(f'not found: {draft_path}', file=sys.stderr)
        sys.exit(1)

    with open(draft_path) as f:
        d = json.load(f)

    # 복합클립 → 원본 mp4 offset 계산
    sub = d['materials']['drafts'][0]['draft']
    sub_seg0 = sub['tracks'][0]['segments'][0]
    # compound_time = src_time - (sub_src_start - sub_tgt_start)
    src_to_cc_offset_us = sub_seg0['target_timerange']['start'] - sub_seg0['source_timerange']['start']

    # silencedetect
    print(f'🔍 silencedetect: {args.source}')
    print(f'   min_duration={args.silence_duration}s threshold={args.silence_threshold}dB')
    sils_src = detect_silence(args.source, args.silence_duration, args.silence_threshold)
    print(f'   → {len(sils_src)}개 무음 구간 (원본 기준)')
    # convert to compound-clip time
    sils_cc = [(s + src_to_cc_offset_us/1e6, e + src_to_cc_offset_us/1e6) for s, e in sils_src]

    if args.report_claps:
        candidates = detect_clap_candidates(
            args.source,
            max_candidates=args.clap_max_candidates,
            min_gap=args.clap_min_gap,
        )
        report_clap_candidates(args, candidates, src_to_cc_offset_us, sils_cc)

    # Track[0] 처리
    track0 = d['tracks'][0]
    old_segs = track0['segments']
    new_segs = []
    cut_count = 0

    for seg in old_segs:
        keeps = plan_segment_cuts(seg, sils_cc, args.padding)
        if len(keeps) == 1 and keeps[0][0] == seg['source_timerange']['start'] \
                and keeps[0][1] == seg['source_timerange']['duration']:
            new_segs.append(seg)
            continue
        cut_count += len(keeps)
        for i, (s, dur) in enumerate(keeps):
            piece = copy.deepcopy(seg)
            piece['id'] = str(uuid.uuid4()).upper()
            piece['source_timerange']['start'] = s
            piece['source_timerange']['duration'] = dur
            # target_timerange 나중에 재계산
            new_segs.append(piece)

    # target_timerange 재계산 (앞에서부터 누적)
    cursor = 0
    for s in new_segs:
        dur = s['source_timerange']['duration']
        s['target_timerange']['start'] = cursor
        s['target_timerange']['duration'] = dur
        cursor += dur

    new_total_us = cursor
    old_total_us = d['duration']

    print()
    print(f'📊 결과')
    print(f'   기존 세그먼트: {len(old_segs)} → 신규: {len(new_segs)}')
    print(f'   기존 길이: {old_total_us/1e6:.2f}s → 신규: {new_total_us/1e6:.2f}s')
    print(f'   제거량: {(old_total_us - new_total_us)/1e6:.2f}s')

    # Track[1] 외 다른 트랙(outro 등) target shift
    for ti, t in enumerate(d['tracks']):
        if ti == 0:
            continue
        for s in t.get('segments', []):
            # outro는 원본 끝에 있었음. 새 총 길이 - (기존 총 길이 - 기존 target.start)
            old_end_offset = old_total_us - s['target_timerange']['start']
            s['target_timerange']['start'] = new_total_us - old_end_offset
        print(f'   Track[{ti}] ({t.get("type")}) {len(t.get("segments",[]))}개 segment shift 완료')

    # 업데이트
    track0['segments'] = new_segs
    d['duration'] = new_total_us
    import time
    d['update_time'] = int(time.time())

    if args.dry_run:
        print('\n💤 dry-run: 파일 변경 없음')
        return

    # 원자적 쓰기
    tmp = draft_path + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(d, f, ensure_ascii=False, separators=(',', ':'))
    os.replace(tmp, draft_path)
    print(f'\n✅ 저장: {draft_path}')


if __name__ == '__main__':
    main()
