"""
Provides several tile providers.

"""

import abc
import io
import logging

import numpy as np
import PIL.Image
from requests_cache import CachedSession

logger = logging.getLogger(__name__)

# caching is good
_session = CachedSession(cache_name='tiles', fast_save=True)


class TileNotFoundError(Exception):
    pass


class TileProvider(abc.ABC):
    """Class which knows how to get tiles, given an x,y,z value"""
    @abc.abstractmethod
    def url(self, z, x, y):
        pass

    def get_tile(self, z, x, y):
        """Return tile as an array of rgb values"""
        x = x % (2 ** z)
        url = self.url(z, x, y)
        logger.debug('retrieving tile from %s', url)
        resp = _session.get(url)
        if resp.status_code != 200:
            msg = 'Could not retrieve tile for z={}, x={}, y={}'
            msg = msg.format(z, x, y)
            raise TileNotFoundError(msg)
        img_bytes = resp.content
        img = PIL.Image.open(io.BytesIO(img_bytes))
        rgba = img.convert('RGBA')
        rgba = np.flip(rgba, 0)
        return rgba


class Stamen(TileProvider):
    def url(self, z, x, y):
        url = 'http://c.tile.stamen.com/{}/{}/{}/{}.png'
        url = url.format(self.map_name, z, x, y)
        return url

class StamenToner(Stamen):
    map_name = 'toner'

class StamenLite(Stamen):
    map_name = 'toner-lite'

class StamenTerrain(Stamen):
    map_name = 'terrain'

class StamenWatercolor(Stamen):
    map_name = 'watercolor'

class StamenTonerInverted(TileProvider):
    """Inverted colors, otherwise same as StamenToner"""
    def url(self, z, x, y):
        url = ('http://d.sm.mapstack.stamen.com/'
               '(toner,$fff[difference])/{}/{}/{}.png'
               )
        url = url.format(z, x, y)
        return url


class CartodbBase(TileProvider):
    """Subclasses of CartodbBase must provide a `map_name` attribute on the class"""
    def url(self, z, x, y):
        base = 'http://cartodb-basemaps-1.global.ssl.fastly.net/{}/{}/{}/{}.png'
        return base.format(self.map_name, z, x, y)


class CartodbDark(CartodbBase):
    map_name = 'dark_all'


