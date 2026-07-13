from pathlib import Path

from app.speech import TranscriptionError, TranscriptionResult, get_asr_provider


def transcribe_audio(
    audio_path: str | Path,
    model_name: str | None = None,
) -> TranscriptionResult:
    return get_asr_provider().transcribe(
        audio_path=audio_path,
        model_name=model_name,
    )
