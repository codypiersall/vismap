"""
Vispy canvas that lets you do tile maps
"""


import abc
import logging


import mercantile
import numpy as np
import vispy
from vispy import scene
import vispy.visuals.transforms as transforms
from requests_cache import CachedSession
from png import Reader

logger = logging.getLogger(__name__)

session = CachedSession(cache_name='tiles')


# adapted from VisPy's source code
def read_png_bytes(data):
    """Read a PNG file to RGB8 or RGBA8
    Unlike imread, this requires no external dependencies.
    Parameters
    ----------
    data : bytes
        png data.
    Returns
    -------
    data : array
        Image data.
    See also
    --------
    write_png, imread, imsave
    """
    x = Reader(bytes=data)
    alpha = x.asDirect()[3]['alpha']
    if alpha:
        y = x.asRGBA8()[2]
        n = 4
    else:
        y = x.asRGB8()[2]
        n = 3
    y = np.array([yy for yy in y], np.uint8)
    y.shape = (y.shape[0], y.shape[1] // n, n)
    return y


class TileNotFoundError(Exception):
    pass


class TileProvider(abc.ABC):
    """Class which knows how to get tiles, given an x,y,z value"""
    def __init__(self):
        pass

    @abc.abstractmethod
    def url(self, z, x, y):
        pass

    def get_tile(self, z, x, y):
        """Return tile as an array of rgb values"""
        url = self.url(z, x, y)
        logger.debug('retrieving tile from %s', url)
        resp = session.get(url)
        if resp.status_code != 200:
            msg = 'Could not retrieve tile for z={}, x={}, y={}'
            msg = msg.format(z, x, y)
            raise TileNotFoundError(msg)
        img_bytes = resp.content
        import io
        import PIL.Image
        img = PIL.Image.open(io.BytesIO(img_bytes))
        return img


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


class CartodbBase(TileProvider):
    """Subclasses of CartodbBase must provide a `map_name` attribute on the class"""
    def url(self, z, x, y):
        base = 'http://cartodb-basemaps-1.global.ssl.fastly.net/{}/{}/{}/{}.png'
        return base.format(self.map_name, z, x, y)


class CartodbDark(CartodbBase):
    map_name = 'dark_all'


class CanvasMap(scene.SceneCanvas):
    """Map on top of tile data"""
    # x, y bounds for Web Mercator.
    _web_mercator_bounds = 20037508.342789244

    def __init__(self, *args, tile_provider=StamenToner(), **kwargs):
        super().__init__(*args, **kwargs)
        # Set up a viewbox to display the image with interactive pan/zoom
        self.unfreeze()
        self.view = self.central_widget.add_view()
        self.tile_provider = tile_provider

        # mapping from (z, x, y) -> visual
        self._images = {}
        # cal factor done with math.  At zoom level 0, the mercator units / pixel
        # is 156543.  So our zom calibration factor needs to be based on that
        #
        # 17.256199785269995 == np.log2(self._web_mercator_bounds*2) / 256
        # (dividing by 256 because that is the number of pixels per tile)
        # Add 0.5 so that the zoom level is crisp in the middle of when it's loaded.
        self.zoom_cal = 17.256199785269995 + 0.5

        z = 0
        self.add_tile(0, 0, 0)
        for x in range(2**z):
            for y in range(2**z):
                self.add_tile(z, x, y)

        # Set 2D camera (the camera will scale to the contents in the scene)
        self.view.camera = scene.PanZoomCamera(aspect=1)
        # flip y-axis to have correct alignment
        # self.view.camera.flip = (0, 1, 0)
        self.view.camera.set_range()
        # default is 0.007, half of that feels about right
        self.view.camera.zoom_factor = 0.0035

        # default zoom shows the whole world
        bbox = mercantile.xy_bounds(0, 0, 0)
        rect = vispy.geometry.Rect(bbox.left, bbox.bottom, bbox.right - bbox.left, bbox.top - bbox.bottom)
        self.text = vispy.scene.visuals.Text('test', parent=self.view.scene, color='red', anchor_x='left')
        self.text.font_size = 10
        self.text.order = 1
        self.text.draw()
        self.marker = vispy.scene.visuals.Markers(parent=self.view.scene)
        self.marker.set_data(np.array([[0, 0, 0]]), face_color=[(1, 1, 1)])
        self.marker.draw()
        # TODO: Remove this private variable when it's not needed anymore
        self._zoom = 0
        self.view.camera.rect = rect
        self.last_event = None
        self.marker_size = 10
        self.freeze()

    def on_mouse_press(self, event):
        self.last_event = event
        if event.button == 2:
            # right click
            self.text.text = ''
            # should be painted below anything else
            self.marker.visible = False
            return
        elif event.button == 3:
            # middle click
            canvas_x, canvas_y = event.pos
            width, height = self.size

            rect = self.view.camera._real_rect

            x_interp = canvas_x / width
            y_interp = canvas_y / height
            view_x = rect.left + x_interp * (rect.right - rect.left)
            view_y = rect.top + y_interp * (rect.bottom - rect.top)
            self.text.pos = (view_x, view_y, -1000)
            msg = '((long {:.4f} lat {:.4f}) ({:.4g}, {:.4g})'
            lng, lat = mercantile.lnglat(view_x, view_y)
            msg = msg.format(lng, lat, view_x, view_y)
            self.text.text = msg
            self.marker.set_data(np.array([[view_x, view_y, -1000]]), size=self.marker_size)
            self.marker.visible = True
            self._add_tiles_for_current_zoom()

    @property
    def mercator_scale(self):
        """Get mercator units per pixel of the canvas"""
        # figure out the right zoom level by the number of pixels per mercator units
        canvas_width, _ = self.size
        _real_rect = self.view.camera._real_rect
        # units are Mercator
        scene_width = _real_rect.width
        merc_per_pixel = scene_width / canvas_width
        return merc_per_pixel

    @property
    def best_zoom_level(self):
        merc_per_pixel = self.mercator_scale

        zoom = -np.log2(merc_per_pixel)
        # account for a good "known zoom" level
        zoom += self.zoom_cal
        zoom = int(zoom)
        if zoom < 0:
            zoom = 0
        return zoom


    def get_st_transform(self, z, x, y):
        """
        Return the STTransform for the current zoom, x, and y tile.
        """

        bbox = mercantile.xy_bounds(x, y, z)
        scale = (bbox.right - bbox.left) / 256
        scale = scale, scale, 1
        translate = bbox.left, bbox.bottom, -z
        return transforms.STTransform(scale=scale, translate=translate)

    def _add_tiles_for_current_zoom(self):
        # rect = self.view.camera._real_rect
        [[x, y, *_]] = self.text.pos
        lng, lat = mercantile.lnglat(x, y)
        tile = mercantile.tile(lng, lat, self.best_zoom_level)
        print(tile)
        self.add_tile(tile.z, tile.x, tile.y)

    def add_tile(self, z, x, y):
        """Add tile to the canvas as an image"""
        # Create the image; this should be cached if it's been used recently
        if (z, x, y) in self._images:
            # don't double add.
            return
        try:
            png = self.tile_provider.get_tile(z, x, y)
        except TileNotFoundError:
            logger.warning('tile for zoom %s not found!', (z, x, y))
            return
        png = np.flip(png, 0)
        image = scene.visuals.Image(
            png,
            interpolation='hanning',
            parent=self.view.scene,
            method='subdivide',
        )
        transform = self.get_st_transform(z, x, y)
        image.transform = transform
        self._images[(z, x, y)] = image

    def remove_tile(self, z, x, y):
        """Remove a tile from the map"""
        image = self._images[z, x, y]
        # TODO: Is this the right way to remove a node from a scene?
        image.parent = None
        del self._images[z, x, y]


