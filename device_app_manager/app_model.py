class AppModel(object):

    def __init__(self, name=None, app_type=None, state=0,
                 docker_image_name=None, docker_container_id=None,
                 docker_container_name=None, app_info=None,
                 init_params=None, scheduler_params=None, ui=None):
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
            'ui': self.ui
        }
        return _d

