# 待办事项与技术债演进计划 (TODO / ARCHITECTURE)

更新日期: 2026-04-09

## 当前实施进度

### 已完成
- [x] 阶段 1：头像状态机与重试机制规范化。已引入 `avatar_guard_models.py`，用枚举替代头像状态魔法字符串，并将回滚校验重试改为可注入策略。
- [x] 阶段 2：头像抓取接口异步化。`fetch_group_avatar_hash` 已改为原生异步实现，并通过 `aiohttp` 执行头像抓取。
- [x] 高频状态持久化已从零散 JSON 覆写迁移到 SQLite Repository，保留了旧数据迁移路径。
- [x] 命令层、轮询调度、头像防护、群名防护、成员资料比对等主业务已从 `main.py` 拆出独立服务。
- [x] 阶段 10 / 子项 1：已引入 `group_task_coordinator.py`，将按群粒度的头像、群名、成员资料锁从 `main.py` 剥离。
- [x] 阶段 10 / 子项 2：已引入 `message_recall_service.py`，将消息缓存、撤回命中与撤回日志调度从 `main.py` 剥离。

### 当前主线
- [ ] 阶段 10：核心事件转接与锁分离。
  这是当前唯一的主线重构阶段，目标是继续收缩 `main.py`，清理剩余事件编排、撤回流程和锁协调逻辑。

## 阶段 10：核心事件转接与锁分离

目标：
- 让 `main.py` 仅保留 IoC 装配、AstrBot 事件入口和薄回调，不再承载具体业务流。

待实施项：
- [x] 提取并发锁管理：将 `_avatar_group_locks`、`_group_name_locks`、`_member_profile_locks` 从 `main.py` 剥离到 `group_task_coordinator.py`，统一管理按群粒度的运行时锁。
- [x] 剥离撤回缓存调度：围绕 `GroupMessageCache` 建立 `message_recall_service.py`，负责消息缓存、撤回事件命中与撤回日志调度。
- [ ] 切分 notice 事件流：创建 `notice_event_handler.py`，承接 `on_raw_notice` 中的解析、路由与事件分发，消除主入口中的 notice 分支扩张。
- [ ] 切分被动消息事件流：创建 `passive_message_handler.py`，承接 `on_group_message` 中的消息缓存和成员资料被动更新逻辑。
- [ ] 聚合权限与公共解析工具：将 `_can_manage_source_group`、`_can_query_group_metadata`、`_current_group_id`、`_resolve_bind_args` 等边界辅助逻辑继续回收到更清晰的工具模块。

验收标准：
- `main.py` 不再直接维护分组锁字典。
- `on_raw_notice` 不再直接展开 `group_recall`、`notify.group_name` 等业务分支。
- 撤回日志链路从主入口抽离后，行为与现有逻辑保持一致。
- 新增 notice 事件时，优先通过 handler / dispatch table 扩展，而不是继续增长主入口的条件分支。

## 已知阻塞与后续排期

- [ ] SQLite 数据层原生异步化：需在获得许可引入 `aiosqlite` 后实施。当前 `persistence.py` 仍通过 `asyncio.to_thread` 调用同步 `sqlite3` Repository。
- [ ] 头像回滚兼容性问题：需继续排查框架 `set_group_portrait` 对本地 `file:///` 基线图片路径的拒绝问题，避免轮询回滚路径出现挂起或失败。
