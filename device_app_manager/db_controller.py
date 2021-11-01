from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals
)

from redis import Redis, exceptions
from collections import MutableMapping
from pickle import loads, dumps
import json
import time


class RedisConnectionParams(object):
    __slots__ = ['host', 'port', 'db', 'password']

    def __init__(self, **kwargs):
        self.host = 'localhost'
        self.port = 6379
        self.db = 0
        self.password = None

        if 'host' in kwargs:
            self.host = kwargs.pop('host')
        if 'port' in kwargs:
            self.port = kwargs.pop('port')
        if 'db' in kwargs:
            self.db = kwargs.pop('db')
        if 'password' in kwargs:
            self.password = kwargs.pop('password')


class RedisStore(MutableMapping):
    """RedisStore Implementation class.

    Pythonic way of storing and reading from redis db.

    Usage Example:
    --------------
        d = RedisStore('redis://localhost:6379/0')
        d['a'] = {'b': 1, 'c': 10}
        print repr(d.items())

    """

    def __init__(self, engine):
        self._store = Redis.from_url(engine)

    def __getitem__(self, key):
        return loads(self._store[dumps(key)])

    def __setitem__(self, key, value):
        self._store[dumps(key)] = dumps(value)

    def __delitem__(self, key):
        del self._store[dumps(key)]

    def __iter__(self):
        return iter(self.keys())

    def __len__(self):
        return len(self._store.keys())

    def keys(self):
        return [loads(x) for x in self._store.keys()]

    def clear(self):
        self._store.flushdb()

    def save(self):
        self._store.bgsave()


class RedisController(object):
    """Redis Controller implementation class."""
    APP_LIST_NAME = 'appmanager.apps'

    def __init__(self, conn_params, app_list_name=None, auto_save=False):
        """Constructor.

        conn_params (RedisConnectionParams):
        app_list_name (str):
        auto_save (bool):
        """
        self.conn_params = conn_params
        self.auto_save = auto_save

        if app_list_name is not None:
            self.APP_LIST_NAME = app_list_name

        self.redis = Redis(
            host=conn_params.host,
            port=conn_params.port,
            db=conn_params.db,
            password=conn_params.password,
            decode_responses=True,
            charset="utf-8"
        )

    def ping(self):
        """Check if redis is online.

        Returns:
            (bool): True if redis server is online and False otherwise.
        """
        try:
            self.redis.ping()
            return True
        except Exception:
            return False

    def save_db(self):
        """Save database on disk. For persistence purposes."""
        try:
            self.redis.bgsave()
        except exceptions.ResponseError:
            # redis.exceptions.ResponseError:
            # Background save already in progress
            pass

    def get_apps(self):
        """Returns the list of stored applications.

        Returns:
            (list):
        """
        apps = self.redis.lrange(self.APP_LIST_NAME, 0, -1)
        apps = [json.loads(app) for app in apps]
        return apps

    def get_app(self, app_name):
        """Returns a stored application given its name.

        Args:
            app_name (str): The name of the application.

        Returns:
            (dict): A dictionary that includes application information
                as stored in database.
        """
        apps = self.get_apps()
        for _app in apps:
            if _app['name'] == app_name:
                # Exists
                return _app
        raise ValueError('Application does not exist in db.')

    def get_app_type(self, app_name):
        """Returns the type of the application.

        Args:
            app_name (str): The name of the application

        Returns:
            (str): The type of the application
        """
        _app = self.get_app(app_name)
        return _app['type']

    def app_exists(self, app_name):
        """Checks if application exists.

        Args:
            app_name (str): The name of the application

        Returns:
            (str): The type of the application
        """
        apps = self.get_apps()
        for _app in apps:
            if _app['name'] == app_name:
                # Exists
                return True
        return False

    def add_app(self, app):
        """Add a new application to the database.

        Args:
            app (dict): The dictionary representing the application to be
                stored in database.
        """
        ## TODO: Validate somehow the schema of app
        created_at = int(time.time())
        app['created_at'] = created_at
        app['updated_at'] = -1
        self.redis.lpush(
            self.APP_LIST_NAME, json.dumps(app))
        if self.auto_save:
            self.save_db()

    def update_app(self, app):
        """Update an application information in db.

        Args:
            app (dict): The dictionary representing the application to be
                stored in database.
        """
        _app = self.get_app(app['name'])
        app_index = self._get_app_index(app['name'])

        _app['type'] = app['type']
        _app['docker'] = app['docker']
        _app['updated_at'] = int(time.time())
        _app['ui'] = app['ui']

        self.redis.lset(
            self.APP_LIST_NAME, app_index, json.dumps(_app))
        if self.auto_save:
            self.save_db()

    def delete_app(self, app_name):
        """Delete an application.

        Args:
            app_name (str): The name of the application
        """
        # app_index = self._get_app_index(app_name)
        self.redis.lrem(self.APP_LIST_NAME, 1,
                        json.dumps(self.get_app(app_name)))
        if self.auto_save:
            self.save_db()

    def set_app_state(self, app_name, state):
        """Sets the state of an application.

        Args:
            app_name (str): The name of the application.
            state (int): Number representing the state of the application
                Set to 0 for stopped and 1 for running.
        """
        ## States: 0 = NotRunning, 1 = Running
        if state not in (0, 1):  # Supported states
            raise ValueError('State does not exist')
        app = self.get_app(app_name)
        app['state'] = state
        if state == 0:
            app['docker']['container'] = {
                'name': '',
                'id': ''
            }
        app_index = self._get_app_index(app_name)
        self.redis.lset(self.APP_LIST_NAME, app_index, json.dumps(app))
        if self.auto_save:
            self.save_db()

    def set_app_property(self, app_name, prop_name, prop_value):
        app = self.get_app(app_name)
        app[prop_name] = prop_value
        app_index = self._get_app_index(app_name)
        self.redis.lset(self.APP_LIST_NAME, app_index, json.dumps(app))
        if self.auto_save:
            self.save_db()

    def app_is_running(self, app_name):
        app = self.get_app(app_name)
        if app['state'] == 1:
            return True
        return False

    def get_app_image(self, app_name):
        """Returns the docker image information of an application.

        Args:
            app_name (str): The name of the application.

        Returns:
            (dict):
        """
        _app = self.get_app(app_name)
        return _app['docker']['image']['name']

    def get_app_container(self, app_name):
        """Returns the docker container information of an application.

        Args:
            app_name (str): The name of the application.

        Returns:
            (dict):
        """
        _app = self.get_app(app_name)
        return _app['docker']['container']['id']

    def set_app_container(self, app_name, container_name, container_id):
        """Set container information of an application.

        Args:
            app_name (str): The name of the application.
            container_name (str): The name of the container.
            container_id (str): The id of the container.
        """
        _app = self.get_app(app_name)
        _app['docker']['container']['name'] = container_name
        _app['docker']['container']['id'] = container_id
        app_index = self._get_app_index(app_name)
        self.redis.lset(self.APP_LIST_NAME, app_index, json.dumps(_app))
        if self.auto_save:
            self.save_db()

    def get_running_apps(self):
        """Returns the list of currently running applications.

        Returns:
            (list):
        """
        apps = self.get_apps()
        _r_apps = []
        for app in apps:
            if app['state'] == 1:
                _r_apps.append(app)
        return _r_apps

    def _get_app_index(self, app_name):
        apps = self.get_apps()
        idx = 0
        for _app in apps:
            if _app['name'] == app_name:
                # Exists
                return idx
            idx += 1
        return -1
