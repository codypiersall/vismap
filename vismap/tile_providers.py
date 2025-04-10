"""
Classes for retrieving tiles from different providers.

"""

import abc
import io
import logging
import os
import random

import numpy as np
import PIL.Image
from requests_cache import CachedSession, FileCache

CACHE_DIR = os.path.expanduser("~/.vismap-tiles")

logger = logging.getLogger(__name__)

_session = CachedSession(backend=FileCache(CACHE_DIR, decode_content=False))

headers = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "http://127.0.0.1/",
}

# mapping of class name: TileProvider.  Built up with register() decorator.
providers = {}


def register(cls):
    """Register a class as a tile provider."""
    providers[cls.__name__] = cls
    return cls


class TileNotFoundError(Exception):
    pass


class TileProvider(abc.ABC):
    """Class which knows how to get tiles, given a z,x,y location"""

    @abc.abstractmethod
    def url(self, z, x, y) -> str:
        """
        For a given zoom, x, and y index, return the URL for fetching the tile.

        """

    def get_tile(self, z, x, y):
        """Return tile as an array of rgb values"""
        x = x % (2**z)
        url = self.url(z, x, y)
        logger.debug("retrieving tile from %s", url)
        resp = _session.get(url, headers=headers)
        if resp.status_code != 200:
            msg = "Could not retrieve tile for z={}, x={}, y={}"
            msg = msg.format(z, x, y)
            raise TileNotFoundError(msg)
        img_bytes = resp.content
        img = PIL.Image.open(io.BytesIO(img_bytes))
        rgba: np.ndarray = img.convert("RGBA")  # type: ignore
        # flip so that when displaying with Vispy everything shows up
        # right-side-up.
        rgba = np.flip(rgba, 0)
        return rgba

    @property
    @abc.abstractmethod
    def attribution(self):
        """"""
        pass


class StamenBase(TileProvider):
    """The basic Stamen maps"""

    # subclasses must override
    map_name = None

    def url(self, z, x, y):
        url = f"https://tiles.stadiamaps.com/tiles/{self.map_name}/{z}/{x}/{y}.png"
        return url

    @property
    def attribution(self):
        return (
            "Map tiles by Stamen Design, under CC BY 3.0. Data "
            "by OpenStreetMap, under ODbL"
        )


@register
class StamenToner(StamenBase):
    map_name = "stamen_toner"


@register
class StamenLite(StamenBase):
    map_name = "stamen_toner_lite"


@register
class StamenTerrain(StamenBase):
    map_name = "stamen_terrain"


@register
class StamenWatercolor(StamenBase):
    map_name = "stamen_watercolor"

    @property
    def attribution(self):
        return (
            "Map tiles by Stamen Design, under CC BY 3.0. "
            "Data by OpenStreetMap, under CC BY SA"
        )


class CartodbBase(TileProvider):
    """Subclasses of CartodbBase must provide a `map_name` attribute
    on the class"""

    @property
    @abc.abstractmethod
    def map_name(self) -> str:
        """map name to fill in for the URL"""

    def url(self, z, x, y):
        base = "http://cartodb-basemaps-1.global.ssl.fastly.net/{}/{}/{}/{}.png"
        return base.format(self.map_name, z, x, y)

    @property
    def attribution(self):
        return "Copyright OpenStreetMap; Copyright CartoDB"


@register
class CartodbDark(CartodbBase):
    @property
    def map_name(self):
        return "dark_all"


@register
class Mapnik(TileProvider):
    def url(self, z, x, y):
        url = "http://a.tile.openstreetmap.org/{}/{}/{}.png"
        return url.format(z, x, y)

    @property
    def attribution(self):
        return "Copyright OpenStreetMap"


@register
class OpenTopMap(TileProvider):
    def url(self, z, x, y):
        url = "http://a.tile.opentopomap.org/{}/{}/{}.png"
        return url.format(z, x, y)

    @property
    def attribution(self):
        return (
            "Map data: Copyright OpenStreetMap, SRTM \n "
            "Map style: Copyright OpenTopoMap CC-BY-SA"
        )


@register
class EsriWorldImagery(TileProvider):
    def url(self, z, x, y):
        url = (
            "http://server.arcgisonline.com/ArcGIS/rest/services"
            "/World_Imagery/MapServer/tile/{}/{}/{}"
        )
        return url.format(z, y, x)

    @property
    def attribution(self):
        return (
            "Tiles copyright Esri -- Source: Esri, i-cubed, USDA, USGS, AEX, "
            "GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User "
            "Community"
        )


def random_provider():
    """Return a random tile provider class"""
    return random.choice(list(providers.values()))()
