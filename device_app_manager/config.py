from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals
)

class Config(object):
    __slots__ = [
        "deployent_basedir",
        "app_deploy_rpc_name",
        "app_kill_rpc_name",
        "isalive_rpc_name",
        "heartbeat_topic",
        "connected_event",
        "disconnected_event",
        "platform_port",
        "platform_host",
        "platform_vhost"
    ]
    def __init__(self, *args, **kwargs):
        pass
