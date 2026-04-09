# 群事件日志插件：深度代码优化与技术债演进计划 (Code Optimization Plan)

**文档受众**: 后续承接该插件开发的 AI Agent 协同者
**当前阶段状态**: 主体解耦已完成，上帝对象（God Class）已拆分。目前 `main.py` 已彻底解耦，流程转交至 `GroupEventOrchestrator`。
**本文档目标**: 专门聚焦代码级别的深度重构与架构性能优化，不涉及直接的产品功能更新。

---

## 优化方向 1：数据持久化原生异步化 (Native Async DB)

**问题背景**:
当前版本在 `persistence.py` 内部使用 `asyncio.to_thread` 对原生的同步 `SQLite3` 指令进行了多线程包裹（见 `sqlite_repository.py`）。虽然起到了非阻塞 IO 的作用，但未完全拥抱异步并发栈。

**实施指导方案**:
1. 引入外部依赖：更新 `requirements.txt` 加入 `aiosqlite`。
2. 重写 `SQLiteStateRepository`：将所有带有 IO 操作的方法（包括 `_connect`, `execute`, `fetchone`）全部改写为 `async def`，彻底去除同步锁阻塞与 `to_thread` 强行跨线程。
3. 获取迭代优化：大数据量查询改为使用 `async for row in cursor` 原生异步游标迭代。

**防腐败原则要求**:
- 改造过程必须保留底层 SQLite 的 WAL 模式，并且切忌因异步滥用导致抛出 `database is locked` 异常。

---

## 优化方向 2：模型反序列化层自动化 (Model / Pydantic Migration)

**问题背景**:
`models.py` 中 `PluginConfig` 和 `SourceGroupConfig` 目前依旧采用手写的 `from_dict` / `to_dict` 字典解析与组装。随着配置项嵌套加深，手动容错判断极度冗余且容易发生 KeyError 遗漏或类型推断失效。

**实施指导方案**:
1. 评估引入 `pydantic v2` 或深度使用 Python 原生 `dataclasses`（配合 `dacite` 等第三方解析库）。
2. 将所有与核心缓存通信的松散数据结构（如 AvatarHashState，ProbeRecord 甚至各类缓存字典）全部强类型化。
3. 严格定义类型校验器，避免被被污染或损坏的 `state.sqlite3` 历史数据冲垮主进程。

**防腐败原则要求**:
- `from_dict` 和 `to_dict` 从此被自动化拦截校验系统接管，坚决不再写纯靠 `isinstance` 试探的野生处理逻辑。

---

## 优化方向 3：依赖传递消除 —— 引入轻量级内部事件总线 (Internal Event Bus)

**问题背景**:
尽管目前的依赖注入（DI）执行得非常标准，但也导致了基础服务（如 `LogDispatchService`）或并发控制器对象（如 `GroupTaskCoordinator`）需要被一层层像糖葫芦一样透传进所有的 `xxxService` 中，导致构造函数异常庞大。

**实施指导方案**:
1. 评估在组件层以上引入轻量级的内部发布/订阅（Pub-Sub）或事件分发机制。
2. 当子服务（如 `AvatarGuardService`）感知到头像重置时，不再直接引用 `self._log_dispatcher`，而是向插件内的 Event Bus `emit` 抛出一个如 `AvatarChangedInternalEvent` 的对象。
3. `LogDispatchService` 从外部集中订阅这些 Event 并发送日志。

**防腐败原则要求**:
- 不可将 Event Bus 作为掩盖参数传递混乱的“垃圾桶”，所有的异步通信必须基于强类型 Object，并且禁止形成复杂的事件派发死循环。

---

## 优化方向 4：跨后端 API 适配防腐层强化 (ACL Layer)

**问题背景**:
当前 `bot_api_service.py` 强依赖于 NapCat/OneBot 系所传递来的私有原生 Payload。在应对未来的星火框架（AstrBot）生态更新、乃至无缝切换宿主框架平台时可能会崩溃。

**实施指导方案**:
1. 在 `BotApiService` 内构建更加严密的 ACL (Anti-Corruption Layer) 防腐层。
2. 彻底屏蔽诸如 `{"group_id": group_id, "no_cache": True}` 等硬编码的第三方协议结构体，面向系统内部重绘标准化接口（例如封装为标准的 `CommandRequest` 入参模式）。
