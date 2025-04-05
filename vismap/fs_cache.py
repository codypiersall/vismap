"""
File-system cache for requests_cache.
"""

try:
    import cPickle as pickle
except ImportError:
    import pickle
from collections import MutableMapping
import os

from requests_cache.backends.base import BaseCache


class FSDict(MutableMapping):
    """File-system based dict.  No care is taken to ensure that the key
    given to the dict can actually exist as a file on the filesystem.  For
    example, a key with a \0 in it will raise an Exception.
    """

    def __init__(self, root="cache"):
        self.root = os.path.abspath(root)
        os.makedirs(self.root, exist_ok=True)

    def _key_to_path(self, key):
        path = os.path.join(self.root, key)
        return path

    def __getitem__(self, key):
        path = self._key_to_path(key)
        if not os.path.exists(path):
            raise KeyError
        with open(path, "rb") as f:
            return f.read()

    def __delitem__(self, key):
        path = self._key_to_path(key)
        os.unlink(path)

    def __setitem__(self, key, value):
        path = self._key_to_path(key)
        if isinstance(value, str):
            value = value.encode()
        with open(path, "wb") as f:
            f.write(value)

    def __iter__(self):
        files = os.listdir(self.root)
        return (os.path.join(self.root, p) for p in files)

    def __len__(self):
        return len(os.listdir(self.root))


class FSPickleDict(FSDict):
    """Like FSDict but pickles values"""

    def __getitem__(self, key):
        sup = super(FSPickleDict, self)
        return pickle.loads(sup.__getitem__(key))

    def __setitem__(self, key, item):
        sup = super(FSPickleDict, self)
        sup.__setitem__(key, pickle.dumps(item))


class FSCache(BaseCache):
    """Filesystem cache backend."""

    def __init__(self, location="cache", **options):
        """
        :param location: root directory on filesystem cache
        """
        super(FSCache, self).__init__(**options)
        self.responses = FSPickleDict(os.path.join(location, "responses"))
        self.keys_map = FSDict(os.path.join(location, "urls"))
