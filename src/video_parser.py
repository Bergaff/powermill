"""
Парсер видеоуроков: видео -> аудио (ffmpeg) -> текст (faster-whisper).

Все файлы и кэш — только диск E (см. config.py).
"""
import subprocess
from pathlib import Path

from tqdm import tqdm

from config import OUTPUT_DIR, VIDEO_DIR, WHISPER_MODEL


def download_youtube(url: str, output_name: str | None = None) -> None:
    """Скачивает аудио с YouTube в data/videos (диск E)."""
    output_path = VIDEO_DIR / (f"{output_name}.%(ext)s" if output_name else "%(title)s.%(ext)s")
    cmd = [
        "yt-dlp",
        "-f", "bestaudio/best",
        "-x", "--audio-format", "mp3",
        "-o", str(output_path),
        url,
    ]
    subprocess.run(cmd, check=True)
    print(f"✅ Скачано: {url}")


def fix_powermill_terms(text: str) -> str:
    """Исправляет типичные ошибки Whisper в терминалах PowerMill/ЧПУ."""
    replacements = {
        "повер мил": "PowerMill",
        "повермил": "PowerMill",
        "пауэр мил": "PowerMill",
        "пауэрмил": "PowerMill",
        "пи эм эль": "PML",
        "пмл": "PML",
        "рафинг": "roughing",
        "финишинг": "finishing",
        "баундари": "boundary",
        "баундри": "boundary",
        "лид ин": "lead-in",
        "лид аут": "lead-out",
        "эн си": "NC",
        "джи код": "G-код",
    }
    for wrong, correct in replacements.items():
        text = text.replace(wrong, correct)
    return text


def transcribe_audio(audio_path: Path, language: str = "ru") -> str:
    """Транскрибирует аудиофайл через faster-whisper (локально)."""
    from faster_whisper import WhisperModel

    print(f"🎙️ Загрузка модели Whisper ({WHISPER_MODEL})...")
    model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")

    print(f"🎙️ Транскрипция: {audio_path.name}")
    segments, _info = model.transcribe(
        str(audio_path),
        language=language,
        beam_size=5,
        vad_filter=True,  # фильтр тишины — ускоряет в 2–3 раза
    )

    lines = []
    for seg in segments:
        minutes = int(seg.start // 60)
        seconds = int(seg.start % 60)
        lines.append(f"[{minutes:02d}:{seconds:02d}] {seg.text.strip()}")

    return fix_powermill_terms("\n".join(lines))


def parse_all_videos() -> list[dict]:
    """Транскрибирует всё из data/videos (диск E)."""
    video_files = (
        sorted(VIDEO_DIR.glob("*.mp4"))
        + sorted(VIDEO_DIR.glob("*.mp3"))
        + sorted(VIDEO_DIR.glob("*.wav"))
        + sorted(VIDEO_DIR.glob("*.mkv"))
    )
    if not video_files:
        print(f"⚠️ Нет видео в {VIDEO_DIR} — пропускаем этап.")
        return []

    print(f"🎬 Найдено {len(video_files)} видеофайлов")
    all_transcripts = []

    for video_path in tqdm(video_files, desc="Транскрипция"):
        try:
            if video_path.suffix in {".mp4", ".mkv", ".avi"}:
                audio_path = video_path.with_suffix(".mp3")
                if not audio_path.exists():
                    subprocess.run(
                        [
                            "ffmpeg", "-y", "-i", str(video_path),
                            "-vn", "-acodec", "libmp3lame", "-q:a", "2",
                            str(audio_path),
                        ],
                        check=True,
                        capture_output=True,
                    )
            else:
                audio_path = video_path

            text = transcribe_audio(audio_path)
            all_transcripts.append({
                "source": video_path.name,
                "text": text,
                "chars": len(text),
            })

            out_file = OUTPUT_DIR / f"{video_path.stem}_transcript.txt"
            out_file.write_text(text, encoding="utf-8")
            print(f"  ✅ {video_path.name}: {len(text)} символов")

        except Exception as e:
            print(f"  ❌ {video_path.name}: {e}")

    print(f"\n✅ Транскрибировано {len(all_transcripts)} видео")
    return all_transcripts


if __name__ == "__main__":
    parse_all_videos()
