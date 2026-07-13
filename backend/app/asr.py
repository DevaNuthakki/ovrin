from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TranscriptionResult:
    transcript: str
    provider: str
    model_name: str


class TranscriptionError(Exception):
    pass


def transcribe_audio(audio_path: str | Path, model_name: str | None = None) -> TranscriptionResult:
    audio_file = Path(audio_path)

    if not audio_file.exists():
        raise TranscriptionError(f"Audio file not found: {audio_file}")

    if audio_file.stat().st_size == 0:
        raise TranscriptionError(f"Audio file is empty: {audio_file}")

    # Foundation placeholder:
    # This keeps the Ovrin pipeline working without adding heavy local model
    # dependencies yet. Later, this function can be swapped to Whisper,
    # WhisperX, a private runner, or a hosted ASR provider.
    transcript = (
        "mock asr transcript generated from "
        f"{audio_file.stem.replace('-', ' ').replace('_', ' ')}"
    )

    return TranscriptionResult(
        transcript=transcript,
        provider="mock_local",
        model_name=model_name or "mock-asr-foundation",
    )
