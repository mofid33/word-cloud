# Phase 13 — Visualization

Status: IMPLEMENTED — AWAITING_TARGET_VERIFICATION
Date: 2026-10-01

## Scope implemented

- Persian-aware WordCloud rendering from persisted final keywords only.
- Final score drives visualization weight; rank provides deterministic ordering.
- Explicit Arabic/Persian shaping with arabic-reshaper and bidi visual ordering.
- ZWNJ, multi-token Persian phrases, mixed Persian/Latin text, digits and punctuation are covered by rendering tests.
- Deterministic WordCloud layout through a fixed configuration seed.
- Real PNG output.
- Real UTF-8 SVG output with XML escaping and no raw HTML injection.
- Thin VisualizationController discovered by the existing WebService convention.
- Route: GET /api/v1/visualization/{analysis_id}?format=png|svg
- Repository query dedicated to visualization loads only the analysis row and final keywords; documents and topics are configured with raiseload.
- SOLDIER_CONCERN visualization never re-reads or re-analyzes raw text.
- No visualization binary or SVG content is persisted in the structured analysis result.
- No new SQLAlchemy model or Alembic migration is required.

## Configuration

Both development and production configuration contain the same keys:

- visualization.width = 1200
- visualization.height = 675
- visualization.maximum_words = 100
- visualization.background = #FFFFFF
- visualization.font_family = DejaVu Sans
- visualization.font_path = @matplotlib/DejaVuSans.ttf
- visualization.random_seed = 42

The @matplotlib token resolves the font shipped with the installed Matplotlib package instead of relying on a developer-specific Windows/Linux font path. Startup fails deterministically when the configured font cannot be resolved or opened.

## Dependency selection

- wordcloud 1.9.6: WordCloud layout and PNG rendering.
- arabic-reshaper 3.0.1: Arabic/Persian glyph shaping.
- python-bidi 0.6.11: bidi visual ordering.
- Pillow and Matplotlib are declared directly because Phase 13 imports them directly.

No font binary is added to this repository.

## API behavior

- completed + png -> 200 image/png
- completed + svg -> 200 image/svg+xml
- unknown analysis -> 404 analysis_not_found
- pending/processing -> 409 analysis_visualization_not_ready
- failed -> 409 analysis_failed
- completed with no positive finite final-score keywords -> 409 analysis_visualization_empty
- unsupported format -> 422 unsupported_visualization_format

## Determinism contract

With the same persisted analysis keywords, configuration, renderer/library versions, font and random seed:

- keyword selection/order is deterministic;
- WordCloud random state is deterministic;
- PNG bytes are expected to be deterministic and are covered by a byte-equality rendering test;
- SVG element ordering/content is deterministic and covered by byte-equality tests.

## Verification state

Repository implementation and tests are committed, but Phase 13 is intentionally not marked complete until the target Windows environment runs dependency installation, compile, PostgreSQL integration tests, discovery/runtime smoke, rendering benchmark and full regression.
