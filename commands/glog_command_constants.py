from __future__ import annotations


MIN_POLL_INTERVAL_SECONDS = 30


class GlogSubCommand:
    HELP = "help"
    STATUS = "status"
    LIST = "list"
    PLUGIN = "plugin"
    ENABLE = "enable"
    DISABLE = "disable"
    PUSH = "push"
    BIND = "bind"
    UNBIND = "unbind"
    ROLLBACK = "rollback"
    RECALL = "recall"
    EVENT = "event"
    AVATAR = "avatar"
    MEMBER = "member"


class SwitchValue:
    ON = "on"
    OFF = "off"


class PushAction:
    ENABLE = "enable"
    DISABLE = "disable"


class AvatarAction:
    PROBE = "probe"
    STATUS = "status"
    CHECK = "check"
    INTERVAL = "interval"


class MemberAction:
    CHECK = "check"
    STATUS = "status"
    POLL = "poll"
    INTERVAL = "interval"


class RollbackTarget:
    AVATAR = "avatar"
    GROUP_NAME = "group_name"


ALL_SWITCH_VALUES = {SwitchValue.ON, SwitchValue.OFF}
ALL_PUSH_ACTIONS = {PushAction.ENABLE, PushAction.DISABLE}
ALL_AVATAR_ACTIONS = {
    AvatarAction.PROBE,
    AvatarAction.STATUS,
    AvatarAction.CHECK,
    AvatarAction.INTERVAL,
}
ALL_MEMBER_ACTIONS = {
    MemberAction.CHECK,
    MemberAction.STATUS,
    MemberAction.POLL,
    MemberAction.INTERVAL,
}
ALL_ROLLBACK_TARGETS = {RollbackTarget.AVATAR, RollbackTarget.GROUP_NAME}

EVENT_SWITCH_ALIASES = {
    "bot_kick_member": "bot_kick_member",
    "kick": "bot_kick_member",
    "bot-kick": "bot_kick_member",
    "bot_ban_member": "bot_ban_member",
    "ban": "bot_ban_member",
    "bot-ban": "bot_ban_member",
    "bot_recall_own_message": "bot_recall_own_message",
    "recall-own": "bot_recall_own_message",
    "recall_own": "bot_recall_own_message",
    "bot_recall_other_message": "bot_recall_other_message",
    "recall-other": "bot_recall_other_message",
    "recall_other": "bot_recall_other_message",
}

SELF_OPERATION_EVENT_SWITCHES = {
    "bot_kick_member",
    "bot_ban_member",
    "bot_recall_own_message",
    "bot_recall_other_message",
}


HELP_TEXT = "\n".join(
    [
        "/glog status [group_id] - show status",
        "/glog enable [group_id] - enable current or target source group",
        "/glog disable [group_id] - disable current or target source group",
        "/glog push enable <group_id> - register a push group",
        "/glog push disable <group_id> - disable a push group",
        "/glog bind <push_group_id> - bind current source group to a push group",
        "/glog bind <source_group_id> <push_group_id> - bind as global admin",
        "/glog unbind <push_group_id> - unbind current source group",
        "/glog rollback avatar on|off [group_id] - toggle avatar rollback",
        "/glog rollback group_name on|off [group_id] - toggle group name rollback",
        "/glog recall on|off [group_id] - toggle recalled message content",
        "/glog event <kick|ban|recall-own|recall-other> on|off [group_id] - toggle bot self-operation logs",
        "/glog event status [group_id] - show bot self-operation log switches",
        "/glog avatar probe [group_id] - probe avatar-related fields",
        "/glog avatar check [group_id] - run avatar hash detection now",
        "/glog avatar interval <seconds> - set avatar hash poll interval",
        "/glog avatar status [group_id] - show avatar hash state and probe",
        "/glog member check [group_id] - scan member profiles now",
        "/glog member poll on|off [group_id] - toggle member snapshot polling",
        "/glog member interval <seconds> - set member poll interval",
        "/glog member status [group_id] - show member profile snapshot state",
        "/glog plugin on|off - global plugin switch",
        "/glog list - show all monitored and push groups",
        "/glog help - show this help text",
    ]
)
