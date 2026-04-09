# Changelog

All notable changes to the `astrbot_plugin_group_event_log` codebase will be documented in this file.

## [Unreleased]
### Changed
- **Optimization Roadmap**: Consolidated the latest architecture conclusions into `TODO.md`, defining Phase 11 around state-path stability, native async SQLite migration, avatar rollback diagnostics, Bot API anti-corruption hardening, and deferring internal Event Bus work.

### Refactored
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
- **Test Coverage**: Added integration test suites: `test_persistence.py`, `test_services.py`, `test_avatar_guard_service.py`, `test_member_profile_service.py`, `test_polling_scheduler.py`, `test_glog_command_handler.py`, and `test_avatar_hash.py`.
