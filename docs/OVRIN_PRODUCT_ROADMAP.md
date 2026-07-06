# Ovrin Product Roadmap

Ovrin is a privacy-first AI regression testing and debugging platform for speech, voice, and agent systems.

The product is designed for engineering teams that need to test model or pipeline changes before they affect users. Ovrin helps teams detect regressions, compare runs, open debug cases, and investigate failures without forcing sensitive transcripts, audio, model outputs, or private repository data into a cloud system.

## Product vision

Ovrin should become a launch-ready platform for testing and debugging:

- STT / ASR systems
- transcription pipelines
- TTS systems
- diarization pipelines
- authorized voice cloning workflows
- voice agents
- chatbots and text agents
- AI regression workflows connected to CI/CD

The long-term goal is:

> Give teams full debugging power while letting them control where sensitive data is processed.

## Core workflow

Ovrin should support this complete workflow:

```text
Project
→ Dataset
→ Test case
→ Evaluation run
→ Evaluation result
→ Run comparison
→ Debug case
→ Debug workspace
→ AI-assisted investigation
