"""Local 9:16 video assembly, Windows narration and burned captions."""
import json
import os
import shutil
import subprocess
import textwrap
import wave
from pathlib import Path


def ffmpeg_path():
    custom = Path(__file__).resolve().parent.parent / 'tools' / 'ffmpeg.exe'
    if custom.is_file():
        return str(custom)
    binary = shutil.which('ffmpeg')
    if binary:
        return binary
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError):
        raise RuntimeError('FFmpeg fehlt. Bitte EINRICHTEN.bat ausführen.') from None


def run_ffmpeg(args, folder, timeout=600):
    process = subprocess.run([ffmpeg_path(), '-hide_banner', '-loglevel', 'error', '-nostdin', '-y'] + args,
                             cwd=folder, capture_output=True, timeout=timeout,
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if process.returncode:
        message = process.stderr.decode('utf-8', errors='replace')[-1200:]
        raise RuntimeError('Videoschnitt fehlgeschlagen: ' + message)


def check_ffmpeg():
    result = subprocess.run([ffmpeg_path(), '-hide_banner', '-filters'], capture_output=True, timeout=20,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode or b'subtitles' not in result.stdout:
        raise RuntimeError('FFmpeg benötigt den subtitles-Filter (libass). Vollständigen FFmpeg-Build verwenden.')
    return ffmpeg_path()


def windows_narration(text, path):
    if os.name != 'nt':
        raise RuntimeError('Sprecherstimme hier nur unter Windows verfügbar. Option deaktivieren oder WAV-Dateien extern vorbereiten.')
    script = (
        '[Console]::InputEncoding=[System.Text.Encoding]::UTF8; $ErrorActionPreference="Stop"; '
        '$p=ConvertFrom-Json ([Console]::In.ReadToEnd()); Add-Type -AssemblyName System.Speech; '
        '$s=New-Object System.Speech.Synthesis.SpeechSynthesizer; '
        'try {$s.SelectVoiceByHints([System.Speech.Synthesis.VoiceGender]::NotSet,'
        '[System.Speech.Synthesis.VoiceAge]::NotSet,0,[System.Globalization.CultureInfo]::GetCultureInfo("de-DE"))} catch {}; '
        'try {$s.SetOutputToWaveFile($p.path); $s.Speak($p.text)} finally {$s.Dispose()}'
    )
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
        input=json.dumps({'text': text, 'path': str(Path(path).resolve())}).encode('utf-8'),
        capture_output=True, timeout=120, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode or not Path(path).exists():
        raise RuntimeError('Windows konnte keine Sprecherdatei erzeugen. Sprachstimme prüfen oder Sprecherstimme deaktivieren.')


def timestamp(seconds, ass=False):
    units = int(round(seconds * (100 if ass else 1000)))
    div = 100 if ass else 1000
    hour, rest = divmod(units, 3600 * div)
    minute, rest = divmod(rest, 60 * div)
    second, fraction = divmod(rest, div)
    return f'{hour}:{minute:02}:{second:02}.{fraction:02}' if ass else f'{hour:02}:{minute:02}:{second:02},{fraction:03}'


def subtitle_ass(text, duration):
    # Remove ASS control syntax from model/user text; captions are plain text.
    clean = text.replace('\\', '／').replace('{', '(').replace('}', ')').replace('\n', ' ').replace('\r', ' ')
    wrapped = '\\N'.join(textwrap.wrap(clean, 30))
    return (
        '[Script Info]\nScriptType: v4.00+\nPlayResX: 720\nPlayResY: 1280\n'
        '[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, '
        'Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, '
        'Alignment, MarginL, MarginR, MarginV, Encoding\n'
        'Style: Default,Arial,42,&H00FFFFFF,&H000000FF,&H00121926,&H80000000,-1,0,0,0,100,100,0,0,1,3,1,2,55,55,220,1\n'
        '[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n'
        f'Dialogue: 0,0:00:00.00,{timestamp(duration,True)},Default,,0,0,0,,{wrapped}\n'
    )


def render(projects, ident, preview=False, voice=True, music=None, notify=lambda text: None):
    check_ffmpeg()
    plan = projects.load(ident)
    folder = projects.folder(ident)
    output = folder / ('vorschau' if preview else 'export')
    output.mkdir(exist_ok=True)
    subtitles = []
    elapsed = 0.0
    for number, scene in enumerate(plan['scenes']):
        notify(f'{"Vorschau" if preview else "Schnitt"}: Szene {number+1}/{len(plan["scenes"])}')
        duration = float(scene['duration'])
        voice_name = f'voice_{number:02d}.wav'
        if voice:
            windows_narration(scene['narration'], output / voice_name)
            with wave.open(str(output / voice_name), 'rb') as wav:
                duration = max(duration, wav.getnframes() / wav.getframerate() + 0.2)
            if duration > 12:
                raise ValueError('Sprechertext dauert zu lange. Plan kürzen und neues Projekt erzeugen.')
        ass_name = f'sub_{number:02d}.ass'
        (output / ass_name).write_text(subtitle_ass(scene['narration'], duration), encoding='utf-8')
        if preview:
            color = ['0x12283d', '0x183c48', '0x243049', '0x174546'][number % 4]
            inputs = ['-f', 'lavfi', '-i', f'color=c={color}:s=720x1280:r=30:d={duration}']
        else:
            clip = folder / f'clip_{number:02d}.mp4'
            if not clip.exists():
                raise ValueError(f'Videoclip für Szene {number+1} fehlt. Erst Runway-Erzeugung abschließen.')
            inputs = ['-i', str(clip.resolve())]
        inputs += ['-i', voice_name] if voice else ['-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo']
        filters = (f'scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,setsar=1,fps=30,'
                   f'tpad=stop_mode=clone:stop_duration=12,trim=duration={duration},subtitles={ass_name}')
        run_ffmpeg(inputs + ['-map', '0:v:0', '-map', '1:a:0', '-vf', filters,
                   '-af', 'apad', '-t', str(duration), '-c:v', 'libx264', '-preset', 'veryfast',
                   '-crf', '21', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-ar', '48000', '-ac', '2',
                   f'segment_{number:02d}.mp4'], output)
        subtitles.append(f'{number+1}\n{timestamp(elapsed)} --> {timestamp(elapsed+duration)}\n{scene["narration"]}\n')
        elapsed += duration
    (output / 'concat.txt').write_text(''.join(f"file 'segment_{n:02d}.mp4'\n" for n in range(len(plan['scenes']))), encoding='utf-8')
    run_ffmpeg(['-f', 'concat', '-safe', '1', '-i', 'concat.txt', '-c', 'copy', '-movflags', '+faststart', 'joined.mp4'], output)
    if music:
        music = Path(music).resolve()
        if not music.is_file() or music.suffix.lower() not in ('.wav', '.mp3', '.m4a', '.ogg'):
            raise ValueError('Bitte eine vorhandene eigene Audiodatei wählen.')
        run_ffmpeg(['-i', 'joined.mp4', '-stream_loop', '-1', '-i', str(music), '-filter_complex',
                    '[1:a]volume=0.08[m];[0:a][m]amix=inputs=2:duration=first:normalize=0[a]',
                    '-map', '0:v:0', '-map', '[a]', '-c:v', 'copy', '-c:a', 'aac', '-t', str(elapsed),
                    '-movflags', '+faststart', 'final.tmp.mp4'], output)
    else:
        shutil.copyfile(output / 'joined.mp4', output / 'final.tmp.mp4')
    (output / 'final.tmp.mp4').replace(output / 'final.mp4')
    (output / 'untertitel.srt').write_text('\n'.join(subtitles), encoding='utf-8')
    (output / 'caption.txt').write_text(plan['caption'], encoding='utf-8')
    (output / 'szenenplan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding='utf-8')
    (output / 'render_info.json').write_text(json.dumps({'duration': elapsed}), encoding='utf-8')
    return output / 'final.mp4'
