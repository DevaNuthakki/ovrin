import os

from app.speech.base import ASRProvider
from app.speech.mock_provider import MockASRProvider
from app.speech.faster_whisper_provider import FasterWhisperASRProvider


def get_asr_provider() -> ASRProvider:
    provider_name = os.getenv("OVRIN_ASR_PROVIDER", "mock_local").strip().lower()

    if provider_name in {"mock", "mock_local"}:
        return MockASRProvider()

    if provider_name in {"faster_whisper", "faster-whisper"}:
        return FasterWhisperASRProvider()

    raise ValueError(
        f"Unsupported ASR provider: {provider_name}. "
        "Supported providers: mock_local, faster_whisper"
    )
