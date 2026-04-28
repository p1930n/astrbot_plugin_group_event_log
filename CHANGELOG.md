# Changelog

All notable changes to the `astrbot_plugin_group_event_log` codebase will be documented in this file.

## [Unreleased]
### Changed
- **Hot-Reload Lifecycle**: Registered the initialization task with the plugin background-task tracker and added `terminate()` cleanup to stop runtime loops, cancel pending tasks, await shutdown, and log non-cancellation task failures.
- **Optimization Roadmap**: Consolidated the latest architecture conclusions into `TODO.md`, defining Phase 11 around state-path stability, native async SQLite migration, avatar rollback diagnostics, Bot API anti-corruption hardening, and deferring internal Event Bus work.
- **AstrBot Compliance Roadmap**: Updated Phase 11 in `TODO.md` to prioritize AstrBot root data-directory migration, callback removal from service orchestration, and hot-reload task lifecycle guarantees before deeper persistence and adapter refactors.
- **Runtime Data Root**: Moved plugin runtime state to AstrBot root `data/astrbot_plugin_group_event_log`, added compatibility migration for legacy plugin-local SQLite / probe / baseline files, and updated status output paths to point at the new runtime store.
- **Runtime Orchestration Boundary**: Replaced `main.py` callback and lambda wiring with explicit runtime state, runtime session, runtime config, and group runtime services so scheduling, notice routing, passive profile updates, and glog commands no longer reverse-call plugin private methods.
- **Native Async SQLite**: Added `aiosqlite`, converted `ConfigPersistence` and `SQLiteStateRepository` database I/O to native async operations, preserved `WAL` / `busy_timeout` and legacy migration semantics, and extended persistence tests to cover concurrent initialization.
- **Avatar Rollback Diagnostics**: Expanded `set_group_portrait` rollback input candidates, classified rollback failures into path-missing / unreadable-path / API-rejected / verify-failed cases, and surfaced applied-input plus attempted-input diagnostics in command output, persisted state, and dispatched logs.

### Refactored
- **Glog Event Switch Layer**: Extracted bot self-operation event switch command handling into `glog_event_service.py`, keeping `glog_config_service.py` focused on general plugin and group configuration commands.
- **State Persistence**: Migrated high-frequency runtime state (avatar hash, group name guard, member profiles) from scattered JSON writes to SQLite.
- **Service Domain Extraction**: Extracted `BotApiService`, `LogDispatchService`, `GroupNameGuardService`, `AvatarGuardService`, and `MemberProfileService` from `main.py` to eliminate God Object patterns.
- **Glog Command Layer**: Refactored command dispatch, splitting config and group logic (`glog_config_service`, `glog_group_service`, `glog_command_handler`).
- **Polling Extraction**: Moved avatar and member profile loops into `PollingSchedulerService`, adding bot readiness guards to prevent startup race conditions.
- **Avatar Hash Fetch Async**: Rewrote `fetch_group_avatar_hash` natively to use `aiohttp`, replacing `asyncio.to_thread` usage. Added graceful error fallback when `aiohttp` is missing.
- **Group Task Coordination**: Added `group_task_coordinator.py` to centralize per-group avatar, group-name, and member-profile locks, removing lock dictionaries from `main.py`.
- **Message Recall Flow**: Added `message_recall_service.py` to encapsulate message caching, recall hit lookup, and recall log dispatch from `main.py`.
- **Notice Event Flow**: Added `notice_event_handler.py` to encapsulate notice parsing, config gating, recall routing, and group-name rollback dispatch from `main.py`.
- **Passive Message Flow**: Added `passive_message_handler.py` to encapsulate group-message cache writes and passive member-profile routing from `main.py`.
- **Group Context Extraction**: Added `group_context_service.py` to encapsulate current-group resolution, bind-argument parsing, and source-group permission checks from `main.py`.

### Added
- **Lifecycle Test Coverage**: Added `test_main_lifecycle.py` to verify plugin termination cancels registered background tasks and clears runtime task state without requiring a real AstrBot runtime.
- **Bot Self-Operation Event Switches**: Added per-source-group switches for bot kick, bot mute / unmute, bot recall-own-message, and bot recall-other-message notice logs, configurable through `/glog event ...`.
- **WebUI Default Event Policy**: Added `_conf_schema.json` defaults for new groups so WebUI can control the initial bot self-operation event switch policy while existing groups remain isolated through persisted group config.
- **Test Coverage**: Added integration test suites: `test_persistence.py`, `test_services.py`, `test_avatar_guard_service.py`, `test_member_profile_service.py`, `test_polling_scheduler.py`, `test_glog_command_handler.py`, and `test_avatar_hash.py`.
