# Changelog

## V0.4 — Script Writer + Project Cast

- Optional opt-in OpenAI API screenplay writer with batched shots, validation and review approval.
- Server-side-only API key and explicit charged-call confirmation; no automatic AI calls on page load.
- Per-project character metadata and uploaded reference images with V0.3 snapshot migration.
- Dynamic mock Node Editor references only current project characters.
- React deployed bundle and editable React Flow source updated for V0.4.
- Fixed Docker `COPY assets` empty-folder error by creating directory during build.
- Added offline integration tests and updated GitHub/Render deployment instructions.

**Not implemented:** real AI image/video generation, Vietnamese synthesized voices, TobyFlow live integration, durable storage on Render Free, API billing accounting.
