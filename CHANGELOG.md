# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned

- Package-data based install support for `uv tool`/`pipx` once the runtime layout is stabilized.
- Optional generic Tailscale-only proxy template.

## [0.2.0] - 2026-11-25

Fork of [PriuS2/HermesKanban](https://github.com/PriuS2/HermesKanban). See
[FORK.md](FORK.md) for the deployment notes.

### Added

- Russian interface as a third language, on by default; the header button cycles RU → EN → KO.
- Dark theme as the default; light theme keeps the contrast contract of the spec.
- PWA: manifest, icons, service worker with an offline shell, update banner, and explicit
  `GET /sw.js` / `GET /manifest.webmanifest` routes ahead of the SPA fallback.
- Web-push notifications for `completed`, `crashed`, `timed_out`, `blocked` and failed
  `worker_result` events: VAPID key generation, subscription API, `push.db` store, and a
  systemd timer sender (`scripts/push_notifier.py`).
- Token entry panel on `401`; the token is passed in the URL fragment and stripped from the address.
- `scheduled` status gets its own «Бэклог» column instead of falling into «Ожидают».
- Touch drag: long-press moves a card (HTML5 `dragover` never fires on touch).
- Desktop layout: status lanes fill the viewport (`flex`, 104–520 px) instead of fixed 320 px
  columns, empty statuses become narrow drop targets, cards scroll inside their column.
- Probing scripts: `scripts/probe_desktop.py`, `probe_list.py`, `probe_desktop_behavior.py`,
  `probe_ui.py`, `shot.py` (CDP with `Emulation.setDeviceMetricsOverride`).

### Changed

- Board columns are no longer fixed 320 px: measured width usage went from 39 % to 93 % of a
  1440×900 viewport, column height from 16 653 px to 746 px, card height to 91–110 px.
- Task list on desktop: single-line 40 px rows, 9 columns instead of 11 (run/comment/attachment
  counters share one cell), task title column 169 → 309 px, dates in the UI locale without seconds.
- `?v=` cache token is bumped for every static asset in one place; `tests/test_ui_shell.py` enforces it.

### Fixed

- Dependency lines stay inside the board: edges to cards scrolled out of a column are skipped and
  the overlay redraws on column scroll.
- «К активной» jumps to the first non-empty column when no running/blocked/ready lane exists.
- Empty status label «ЗАБЛОКИРОВАНЫ» no longer breaks into «ЗАБЛОКИРОВАН / Ы»; the «＋» button
  moved into the drop zone.
- Compatibility shim for current Hermes: `kanban_db.connect` / `active_run` are restored in
  `hermes_imports.py` (each request failed with `AttributeError` without it).

## [0.1.0] - 2026-05-05

### Added

- Standalone Hermes KanbanWebUI FastAPI service.
- Trello-style board UI with Korean default UI and English toggle.
- Board CRUD/switching, task creation, bulk creation, filtering, and drag-and-drop status changes.
- Task detail drawer, comments, events, runs, markdown rendering, and Live Run Monitor endpoints.
- Existing Hermes `hermes_cli.kanban_db` integration as the single source of truth.
- Optional header-based token auth.
- Host-header validation and cross-origin mutation blocking for safer localhost/Tailscale usage.
- Start/stop helper scripts and a systemd user-service template.
- Test suite for health/config, board endpoints, task lifecycle, auth, static shell, JavaScript syntax, drag/drop contract, Live Run Monitor, and CLI parity registry.

### Fixed

- Restored static JavaScript module loading by fixing the markdown newline replacement regex.
- Added static module cache-busting after the browser-facing JavaScript fix.

### Security

- Removed query-string token authentication.
- Prevented stored XSS in board select rendering.
- Added dependency-aware lifecycle handling for status updates.
- Rejected unknown Host headers and cross-site mutating browser requests.

[Unreleased]: https://github.com/r1290z/hermes-kanban-webui/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/r1290z/hermes-kanban-webui/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/PriuS2/HermesKanban/releases/tag/v0.1.0
