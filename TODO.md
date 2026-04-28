# 待办事项与技术债演进计划 (TODO / ARCHITECTURE)

更新日期: 2026-04-28

## 当前实施进度

### 已完成
- [x] 阶段 1：头像状态机与重试机制规范化。已引入 `avatar_guard_models.py`，用枚举替代头像状态魔法字符串，并将回滚校验重试改为可注入策略。
- [x] 阶段 2：头像抓取接口异步化。`fetch_group_avatar_hash` 已改为原生异步实现，并通过 `aiohttp` 执行头像抓取。
- [x] 高频状态持久化已从零散 JSON 覆写迁移到 SQLite Repository，保留了旧数据迁移路径。
- [x] 命令层、轮询调度、头像防护、群名防护、成员资料比对等主业务已从 `main.py` 拆出独立服务。
- [x] 阶段 10 / 子项 1：已引入 `group_task_coordinator.py`，将按群粒度的头像、群名、成员资料锁从 `main.py` 剥离。
- [x] 阶段 10 / 子项 2：已引入 `message_recall_service.py`，将消息缓存、撤回命中与撤回日志调度从 `main.py` 剥离。
- [x] 阶段 10 / 子项 3：已引入 `notice_event_handler.py`，将 `on_raw_notice` 中的解析、路由与业务分发从 `main.py` 剥离。
- [x] 阶段 10 / 子项 4：已引入 `passive_message_handler.py`，将 `on_group_message` 中的消息缓存与被动成员资料更新从 `main.py` 剥离。
- [x] 阶段 10 / 子项 5：已引入 `group_context_service.py`，将群上下文解析、bind 参数解析与权限边界判断从 `main.py` 剥离。

### 当前主线
- [x] 阶段 10：核心事件转接与锁分离。
  主线重构已完成，`main.py` 已收缩为 IoC 装配、AstrBot 事件入口与薄回调。

## 阶段 10：核心事件转接与锁分离

目标：
- 让 `main.py` 仅保留 IoC 装配、AstrBot 事件入口和薄回调，不再承载具体业务流。

待实施项：
- [x] 提取并发锁管理：将 `_avatar_group_locks`、`_group_name_locks`、`_member_profile_locks` 从 `main.py` 剥离到 `group_task_coordinator.py`，统一管理按群粒度的运行时锁。
- [x] 剥离撤回缓存调度：围绕 `GroupMessageCache` 建立 `message_recall_service.py`，负责消息缓存、撤回事件命中与撤回日志调度。
- [x] 切分 notice 事件流：创建 `notice_event_handler.py`，承接 `on_raw_notice` 中的解析、路由与事件分发，消除主入口中的 notice 分支扩张。
- [x] 切分被动消息事件流：创建 `passive_message_handler.py`，承接 `on_group_message` 中的消息缓存和成员资料被动更新逻辑。
- [x] 聚合权限与公共解析工具：将 `_can_manage_source_group`、`_can_query_group_metadata`、`_current_group_id`、`_resolve_bind_args` 等边界辅助逻辑回收到 `group_context_service.py`。

验收标准：
- `main.py` 不再直接维护分组锁字典。
- `on_raw_notice` 不再直接展开 `group_recall`、`notify.group_name` 等业务分支。
- 撤回日志链路从主入口抽离后，行为与现有逻辑保持一致。
- 新增 notice 事件时，优先通过 handler / dispatch table 扩展，而不是继续增长主入口的条件分支。

## 阶段 11：状态链路稳定性与防腐层收口

目标：
- 首要优化目的：提升状态型后台链路在并发、异常、热重载和 AstrBot 宿主约束下的稳定性、可预测性与可诊断性。
- 优先处理 AstrBot 数据目录合规、主入口反向依赖清理与高频状态读写，再处理头像回滚链路、Bot API 防腐层和模型校验，不在当前阶段继续扩张新的抽象层。

待实施项：
- [x] 优先级 0：持久化目录迁移到 AstrBot 根目录 `data/astrbot_plugin_group_event_log`。已切换运行时数据落盘位置，并补齐旧插件目录到新根目录的数据兼容迁移路径。
- [x] 优先级 1：去回调化与主入口反向依赖清理。已移除 `main.py` 传入子服务的 `lambda` 与私有方法 callback，改为显式运行时状态、配置存取与群操作服务编排。
- [x] 优先级 1：SQLite 数据层原生异步化。已引入 `aiosqlite`，并将 `ConfigPersistence` / `SQLiteStateRepository` 的数据库 I/O 改为原生 async 接口，移除数据库路径上的 `asyncio.to_thread + sqlite3` 组合。
- [x] 优先级 1：保留并验证 SQLite 的 WAL、`busy_timeout`、初始化迁移与目录迁移语义。异步化后已保持 `WAL` / `busy_timeout` 配置、旧 JSON / 旧 SQLite 迁移链路与运行时目录迁移语义，并补充并发初始化回归测试。
- [x] 优先级 1：热重载后台任务生命周期硬化。`main.py` 已登记初始化任务，补齐 `terminate()` 主动置停、取消、等待并清理后台任务集合，降低重载后旧实例延迟轮询风险。
- [x] 优先级 2：头像回滚兼容性与诊断增强。已补充 `set_group_portrait` 的多候选输入尝试链路，覆盖原始本地路径、规范化本地路径与 `file:///` URI，并在真实群头像变更回滚场景下完成运行验收。
- [x] 优先级 2：补强头像回滚链路日志上下文。已区分基线路径缺失、路径不可读 / 已失效、API 调用失败、回滚后哈希校验失败四类原因，并将诊断信息写入命令输出、推送日志与持久化状态。
- [ ] 优先级 3：强化 `BotApiService` 防腐边界，继续收口 OneBot / NapCat 私有 payload 与参数差异，优先补齐标准化返回结构、错误语义和内部 typed DTO，避免宿主协议细节向业务服务扩散。
- [ ] 优先级 4：轻量模型校验增强。优先在现有 `dataclass` 结构上补齐配置边界校验、坏数据兜底和字段归一化；仅当配置复杂度继续明显上升时，再单独评估 `pydantic` 等新增依赖。
- [ ] 延后项：内部 Event Bus / Pub-Sub。当前显式依赖注入仍然可追踪，暂不引入事件总线掩盖调用链；仅在后续出现明确的跨服务广播场景或构造依赖失控时再单独立项。

验收标准：
- 插件运行时数据落盘位置已切换到 AstrBot 根目录 `data/astrbot_plugin_group_event_log`，且历史状态可从旧插件目录数据平滑迁移，不因插件更新或重装而丢失。
- `main.py` 不再通过 callback / lambda 让子服务反向依赖主入口私有方法；主入口仅负责装配、事件入口和显式编排。
- `persistence.py` 与 `sqlite_repository.py` 完成异步改造后，初始化、轮询与配置保存行为保持现有语义一致，且无新增高频锁库异常。
- 头像回滚失败时，日志能够明确区分路径格式问题、目录迁移后路径失效、宿主 API 报错与回滚后校验失败，不再只暴露笼统失败信息。
- `BotApiService` 新增适配能力后，业务服务不再继续散落宿主专属参数结构或错误分支。
- 配置与状态模型在遇到缺字段、脏字段或历史损坏数据时，不得导致插件初始化主流程崩溃。
- 在 AstrBot 控制台重复热重载后，不得出现僵尸轮询任务重复执行；旧实例必须稳定失活，新实例必须独占运行时令牌。

## 阶段 12：AstrBot 边界与运行时中枢降耦

目标：
- 将 AstrBot 框架对象限制在入口 / 适配层，命令层与业务层优先接收原生 context / result。
- 收口 OneBot / NapCat 平台 API 差异，减少 `dict[str, object]`、`Any` 与裸 `bot.api.call_action` 向业务服务扩散。
- 拆薄 `GroupRuntimeService`，避免其继续聚合命令展示、轮询编排、锁内业务和状态路径输出。

并行执行边界：
- [ ] 子任务 A：命令层脱水。写入范围限制在 `commands/` 与命令相关测试；引入原生 `CommandContext` / `CommandResult`，逐步移除命令服务中的 `AstrMessageEvent` / `MessageEventResult` 直接依赖。
- [ ] 子任务 B：平台 API 防腐。写入范围限制在 `platforms/`、`services/bot_api_service.py` 与 Bot API 相关测试；优先为群信息、成员列表、群名设置、头像回滚补 typed result，降低宿主协议细节泄漏。
- [ ] 子任务 C：运行时中枢瘦身。写入范围限制在 `runtime/`、必要的新展示 / summary 模块与 runtime 相关测试；把命令展示文案和状态路径展示从 `GroupRuntimeService` 拆出，保留运行时编排职责。

集成规则：
- 三个子任务不得回滚 `main.py` 的生命周期修复与 `test_main_lifecycle.py`。
- 若某子任务必须触碰其他子任务写入范围，先停下并汇报冲突点，不自行跨界重构。
- 集成顺序优先为命令层脱水、平台 API 防腐、运行时中枢瘦身；若出现接口冲突，以能保持现有 65 个单元测试通过的最小改动为准。

验收标准：
- `main.py` 仍只承担装配、AstrBot 事件入口、标准响应回装与生命周期释放。
- 命令服务不再直接依赖 AstrBot 事件对象和响应对象，或仅保留明确标注的最外层 adapter。
- 平台 API 适配层返回明确 typed result，业务服务不继续新增裸 `bot.api.call_action` 或无结构 `dict[str, object]` 分支。
- `GroupRuntimeService` 的职责收敛为运行时编排，不再承载大段命令展示文案。
- 完整插件单元测试保持通过；若 Ruff 不可用，需明确记录环境缺失。
