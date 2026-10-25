"""Optional entirely local Whisper captions for OBS gameplay shorts.

Requires faster-whisper and a cached model, installed by the owner.
Never downloads models while JARVIS is streaming.
"""
from __future__ import annotations

import functools
import subprocess
from pathlib import Path

from .core.media import ffmpeg_path


def ass_time(seconds):
    centis = max(0, int(round(float(seconds) * 100)))
    hh, rem = divmod(centis, 360000)
    mm, rem = divmod(rem, 6000)
    ss, ff = divmod(rem, 100)
    return f"{hh}:{mm:02}:{ss:02}.{ff:02}"


def safe_line(value):
    return str(value).replace("\\", "／").replace("{", "(").replace("}", ")").replace("\n", " ").strip()


def ass_captions(segments, width=720, height=1280):
    """ASS dialogue with speech-timed short groups, suitable for portrait video."""
    head = (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {width}\nPlayResY: {height}\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, "
        "Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default,Arial,50,&H00FFFFFF,&H000000FF,&H00080814,&H98080814,"
        "-1,0,0,0,100,100,0,0,1,3,1,2,55,55,180,1\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    lines = []
    for segment in segments:
        words = segment.words or []
        chunks = [words[n:n+4] for n in range(0, len(words), 4)] if words else []
        if chunks:
            for chunk in chunks:
                start, end = chunk[0].start, chunk[-1].end
                text = safe_line("".join(w.word for w in chunk))
                if text and end > start:
                    lines.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Default,,0,0,0,,{text}\n")
        elif segment.text and segment.end > segment.start:
            text = safe_line(segment.text)
            if text:
                lines.append(f"Dialogue: 0,{ass_time(segment.start)},{ass_time(segment.end)},Default,,0,0,0,,{text}\n")
    return head + "".join(lines), len(lines)


@functools.lru_cache(maxsize=1)
def _model():
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise RuntimeError("Untertitel benötigen faster-whisper (optional installieren).") from None
    try:
        return WhisperModel("small", device="cpu", compute_type="int8",
                            local_files_only=True, cpu_threads=2)
    except Exception as exc:
        raise RuntimeError("Whisper-Modell 'small' nicht lokal verfügbar. "
                           "Modell einmalig vor dem Stream herunterladen.") from exc


def caption_video(video, resolution=720):
    video = Path(video).resolve()
    folder = video.parent
    model = _model()
    segments, _ = model.transcribe(str(video), beam_size=1, word_timestamps=True,
                                   vad_filter=True, condition_on_previous_text=False)
    ass, count = ass_captions(list(segments), width=resolution, height=int(resolution*16/9))
    (folder / "untertitel.ass").write_text(ass, encoding="utf-8")
    if not count:
        raise RuntimeError("Keine verständliche Sprache für Untertitel erkannt.")
    temp = folder / "caption_work.mp4"
    command = [ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
               "-i", str(video), "-vf", "subtitles=untertitel.ass",
               "-c:v", "libx264", "-threads", "2", "-preset", "veryfast", "-crf", "22",
               "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", str(temp)]
    try:
        result = subprocess.run(command, cwd=folder, capture_output=True, timeout=1200,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode or not temp.exists() or not temp.stat().st_size:
            raise RuntimeError("Untertitel konnten nicht eingebrannt werden: "
                               + result.stderr.decode(errors="replace")[-500:])
        temp.replace(video)
    finally:
        temp.unlink(missing_ok=True)
    return count
