import os
from pathlib import Path

from app.speech.base import TranscriptionError, TranscriptionResult


class FasterWhisperASRProvider:
    provider_name = "faster_whisper"

    def transcribe(
        self,
        audio_path: str | Path,
        model_name: str | None = None,
    ) -> TranscriptionResult:
        audio_file = Path(audio_path)

        if not audio_file.exists():
            raise TranscriptionError(f"Audio file not found: {audio_file}")

        if audio_file.stat().st_size == 0:
            raise TranscriptionError(f"Audio file is empty: {audio_file}")

        try:
            from faster_whisper import WhisperModel
        except ImportError as error:
            raise TranscriptionError(
                "faster-whisper is not installed. "
                "Install it in a compatible Python environment before using "
                "OVRIN_ASR_PROVIDER=faster_whisper."
            ) from error

        selected_model = (
            os.getenv("OVRIN_ASR_MODEL", "").strip()
            or model_name
            or "large-v3-turbo"
        )

        try:
            model = WhisperModel(
                selected_model,
                device="cpu",
                compute_type="int8",
            )
            segments, _info = model.transcribe(str(audio_file), beam_size=5)
            transcript = " ".join(segment.text.strip() for segment in segments).strip()
        except Exception as error:
            raise TranscriptionError(
                f"faster-whisper transcription failed: {error}"
            ) from error

        if not transcript:
            raise TranscriptionError("faster-whisper returned an empty transcript")

        return TranscriptionResult(
            transcript=transcript,
            provider=self.provider_name,
            model_name=selected_model,
        )
