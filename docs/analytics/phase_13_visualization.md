# Phase 13 — Visualization

Status: IMPLEMENTED — AWAITING_TOPIC_VISUALIZATION_VERIFICATION
Date: 2026-10-01

## Scope implemented

- Persian-aware Overall WordCloud rendering from persisted final keywords only.
- Overall WordCloud weight comes from persisted final_score; rank provides deterministic ordering.
- Topic-level WordCloud rendering from persisted AnalysisTopicKeyword links.
- Topic-level WordCloud weight comes from persisted relevance_score; topic-keyword rank provides deterministic ordering.
- Explicit Arabic/Persian shaping with arabic-reshaper and bidi visual ordering.
- ZWNJ, multi-token Persian phrases, mixed Persian/Latin text, digits and punctuation are covered by rendering tests.
- Deterministic WordCloud layout through a fixed configuration seed.
- CPU-bound PNG/SVG rendering is offloaded from the FastAPI event loop via asyncio.to_thread.
- Real PNG output.
- Real UTF-8 SVG output with XML escaping and no raw HTML injection.
- Thin VisualizationController discovered by the existing WebService convention.
- Overall route: GET /api/v1/visualization/{analysis_id}?format=png|svg
- Topic route: GET /api/v1/visualization/{analysis_id}/topics/{topic_id}?format=png|svg
- Overall repository query loads only the analysis row and final keywords; documents and topics are configured with raiseload.
- Topic repository query loads only topics, topic-keyword links and linked persisted keywords; documents and the overall keyword collection are configured with raiseload.
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
- unknown topic -> 404 analysis_topic_not_found
- completed topic with no positive finite relevance-score keywords -> 409 analysis_topic_visualization_empty

## Determinism contract

With the same persisted analysis keywords, configuration, renderer/library versions, font and random seed:

- keyword selection/order is deterministic;
- WordCloud random state is deterministic;
- PNG bytes are expected to be deterministic and are covered by a byte-equality rendering test;
- SVG element ordering/content is deterministic and covered by byte-equality tests.

## Verification state

Target Windows verification received on 2026-10-01 confirms:

- visualization configuration unit tests PASS;
- visualization service unit tests PASS;
- Persian/RTL PNG/SVG renderer tests PASS;
- visualization controller discovery PASS;
- PostgreSQL-backed visualization API integration tests PASS;
- SOLDIER_CONCERN raw marker privacy test PASS;
- runtime OpenAPI smoke exposes `/api/v1/visualization/{analysis_id}`;
- rendering baseline recorded: PNG P50 10375.19 ms, SVG P50 8687.71 ms for 100 words;
- full regression before the event-loop offload fix: `Ran 374 tests ... OK (skipped=8)`.

The performance baseline exposed a production concern: synchronous CPU-bound rendering blocked the async request event loop. The service now offloads renderer execution through `asyncio.to_thread`.

A subsequent full-regression review exposed that the two new visualization unit-test directories lacked `__init__.py`, so `unittest discover -s tests` did not recurse into them even though their focused module runs passed. Package markers have now been added so the full discovery suite includes those tests.

Previous target verification received on 2026-10-01 confirmed:

- `python -m compileall -q src tests` completed without error;
- full test discovery included all existing Phase 13 visualization service and renderer tests;
- event-loop offload regression test PASS;
- regression result before the topic-level correction: `Ran 386 tests in 119.618s — OK (skipped=8)`;
- skipped tests are explicit model/benchmark-gated suites and are not Phase 13 failures.

A subsequent product-contract audit found that SOLDIER_CONCERN requires both Overall WordCloud and Topic-level WordCloud. The topic-level path is now implemented from persisted `AnalysisTopic` / `AnalysisTopicKeyword` data without loading raw documents.

Phase 13 is reopened until target verification confirms compile, focused topic-level unit/API/discovery tests, runtime OpenAPI exposure of the topic route, and full regression. The completion marker must not be restored before those gates pass.
