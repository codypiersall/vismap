"""
Classes for retrieving tiles from different providers.

"""

import abc
import io
import logging

import numpy as np
import PIL.Image
from requests_cache import CachedSession

from . import fs_cache

logger = logging.getLogger(__name__)

_session = CachedSession(backend=fs_cache.FSCache())


class TileNotFoundError(Exception):
    pass


class TileProvider(abc.ABC):
    """Class which knows how to get tiles, given a z,x,y location


    """
    @abc.abstractmethod
    def url(self, z, x, y):
        """
        For a given zoom, x, and y index, return the URL for fetching the tile.

        """

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
        # flip so that when displaying with Vispy everything shows up
        # right-side-up.
        rgba = np.flip(rgba, 0)
        return rgba

    @property
    @abc.abstractmethod
    def attribution(self):
        """"""
        pass


class Stamen(TileProvider):
    """The basic Stamen maps"""
    def url(self, z, x, y):
        url = 'http://c.tile.stamen.com/{}/{}/{}/{}.png'
        url = url.format(self.map_name, z, x, y)
        return url

    attribution = 'Map tiles by Stamen Design, under CC BY 3.0. Data '
    attribution += 'by OpenStreetMap, under ODbL'


class StamenToner(Stamen):
    map_name = 'toner'


class StamenLite(Stamen):
    map_name = 'toner-lite'


class StamenTerrain(Stamen):
    map_name = 'terrain'


class StamenWatercolor(Stamen):
    map_name = 'watercolor'
    attribution = 'Map tiles by Stamen Design, under CC BY 3.0. '
    attribution += 'Data by OpenStreetMap, under CC BY SA'


class MapStack(TileProvider):
    """Map Stack allows lots of transformations of Stamen tiles
    Subclasses must provide a "transform" attribute on the class.
    """

    def url(self, z, x, y):
        url = 'http://d.sm.mapstack.stamen.com/{}/{}/{}/{}.png'
        url = url.format(self.transform, z, x, y)
        return url

    attribution = 'Tiles by MapBox, Data © OpenStreetMap contributors\n'
    attribution += 'Tiles by Stamen Design, under CC-BY 3.0 Data © '
    attribution += 'OpenStreetMap contributors, under CC-BY-SA'


class SomeMap(MapStack):
    transform = '((watercolor,$fff[hsl-saturation@50],$ff5500[hsl-color@30]),(naip,$fff[hsl-saturation@20],mapbox-water[destination-out])[overlay])'


class CoolBlue(MapStack):
    transform = '(toner-lite,$fff[difference],$000[@40],$fff[hsl-saturation@40],$5999a6[hsl-color],buildings[destination-out])[hsl-saturation@90]'


class Wiggity(MapStack):
    transform = '(toner-background,$fff[difference],mapbox-water[destination-out])'


class BigMapOfBlue(MapStack):
    transform = '(watercolor,$fff[difference],$81e3f7[hsl-color])'


class StamenTonerInverted(MapStack):
    """Inverted colors, otherwise same as StamenToner"""
    transform = '(toner,$fff[difference])'


class CartodbBase(TileProvider):
    """Subclasses of CartodbBase must provide a `map_name` attribute on the class"""
    def url(self, z, x, y):
        base = 'http://cartodb-basemaps-1.global.ssl.fastly.net/{}/{}/{}/{}.png'
        return base.format(self.map_name, z, x, y)


class CartodbDark(CartodbBase):
    map_name = 'dark_all'


