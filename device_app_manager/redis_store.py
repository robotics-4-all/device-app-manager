from redis import Redis
from collections import MutableMapping
from pickle import loads, dumps


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
