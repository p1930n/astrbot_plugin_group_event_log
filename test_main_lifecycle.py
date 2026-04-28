import asyncio
import importlib
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace


def _install_astrbot_stubs() -> None:
    astrbot_module = types.ModuleType("astrbot")
    api_module = types.ModuleType("astrbot.api")
    event_module = types.ModuleType("astrbot.api.event")
    filter_module = types.ModuleType("astrbot.api.event.filter")
    star_module = types.ModuleType("astrbot.api.star")

    class FakeMessageEventResult:
        def __init__(self) -> None:
            self.message_text = ""

        def message(self, text: str) -> "FakeMessageEventResult":
            self.message_text = text
            return self

    class FakeEventMessageType:
        GROUP_MESSAGE = "group_message"
        ALL = "all"

    class FakeStar:
        def __init__(self, context: object) -> None:
            self.context = context

    def identity_decorator(*args: object, **kwargs: object):
        del args
        del kwargs

        def decorator(func):
            return func

        return decorator

    def register(*args: object, **kwargs: object):
        del args
        del kwargs

        def decorator(cls):
            return cls

        return decorator

    filter_module.command = identity_decorator
    filter_module.event_message_type = identity_decorator
    filter_module.EventMessageType = FakeEventMessageType
    filter_module.PlatformAdapterType = SimpleNamespace(AIOCQHTTP="aiocqhttp")

    event_module.AstrMessageEvent = object
    event_module.MessageEventResult = FakeMessageEventResult

    star_module.Context = object
    star_module.Star = FakeStar
    star_module.register = register

    api_module.logger = SimpleNamespace(
        info=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
    )

    sys.modules.setdefault("astrbot", astrbot_module)
    sys.modules.setdefault("astrbot.api", api_module)
    sys.modules.setdefault("astrbot.api.event", event_module)
    sys.modules.setdefault("astrbot.api.event.filter", filter_module)
    sys.modules.setdefault("astrbot.api.star", star_module)


_install_astrbot_stubs()
PLUGIN_PARENT = Path(__file__).resolve().parents[1]
if str(PLUGIN_PARENT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_PARENT))

plugin_main = importlib.import_module("astrbot_plugin_group_event_log.main")


class MainLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_terminate_cancels_registered_background_tasks(self) -> None:
        plugin = plugin_main.GroupEventLogPlugin.__new__(plugin_main.GroupEventLogPlugin)
        plugin._runtime_state = SimpleNamespace(is_running=True)
        plugin._background_tasks = set()
        started = asyncio.Event()
        cancelled = asyncio.Event()

        async def worker() -> None:
            started.set()
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                cancelled.set()
                raise

        plugin._register_task(asyncio.create_task(worker()))
        await started.wait()

        await plugin.terminate()

        self.assertFalse(plugin._runtime_state.is_running)
        self.assertTrue(cancelled.is_set())
        self.assertEqual(plugin._background_tasks, set())


if __name__ == "__main__":
    unittest.main()
