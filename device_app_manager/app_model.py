from typing import Dict


class AppModel(object):

    def __init__(self,
                 name: str = None,
                 app_type: str = None,
                 state: int = 0,
                 docker_image_name: str = None,
                 docker_container_id: str = None,
                 docker_container_name: str = None,
                 app_info: Dict = None,
                 init_params: Dict = None,
                 scheduler_params: Dict = None,
                 ui: Dict = None,
                 voice_command_params: Dict = None):
        self.name = name
        self.app_type = app_type
        self.state = state
        self.docker_image_name = docker_image_name
        self.docker_container_id = docker_container_id
        self.docker_container_name = docker_container_name
        self.created_at = -1
        self.updated_at = -1
        self.info = app_info
        self.init_params = init_params
        self.scheduler_params = scheduler_params
        self.ui = ui
        self.voice_commands = voice_command_params

    @property
    def docker(self):
        return {
            'image': {
                'name': self.docker_image_name
            },
            'container': {
                'name': self.docker_container_name,
                'id': self.docker_container_id
            }
        }

    def serialize(self):
        _d = {
            'name': self.name,
            'type': self.app_type,
            'state': self.state,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'docker': {
                'image': {
                    'name': self.docker_image_name
                },
                'container': {
                    'name': self.docker_container_name,
                    'id': self.docker_container_id
                }
            },
            'info': self.info,
            'init_params': self.init_params,
            'scheduling': self.scheduler_params,
            'voice_commands': self.voice_commands,
            'ui': self.ui
        }
        return _d

