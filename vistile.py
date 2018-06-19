"""
Vispy canvas that lets you do tile maps
"""


import abc
import enum
import functools
import logging
import io
import queue
import time
import threading

import mercantile
import numpy as np
import vispy
from vispy import scene
import vispy.visuals.transforms as transforms
from requests_cache import CachedSession
import PIL.Image

logger = logging.getLogger(__name__)

session = CachedSession(cache_name='tiles')


# this lock is needed any time
lock = threading.Lock()

class TileCamera(scene.PanZoomCamera):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # keep track of the time things were handled to make sure we don't
        # try to do too many events
        self.last_handled = 0.0
        self.min_interval = 0.05

    def viewbox_mouse_event(self, event):
        if event.handled:
            return
        with lock:
            super().viewbox_mouse_event(event)
        # if the tile command queue has anything in it, let's just get the
        # heck out of here; this prevents a hugely unresponsive deal.
        if not self.canvas.queue.empty():
            return
        now = time.time()
        if now > self.last_handled + self.min_interval:
            needs_update = False
            if event.type == 'mouse_wheel':
                needs_update = True
            elif event.type == 'mouse_move':
                # conditions taken from PanZoomCamera source code
                modifiers = event.mouse_event.modifiers
                if 1 in event.buttons and not modifiers:
                    # translating; need to update
                    needs_update = True
                elif 2 in event.buttons and not modifiers:
                    needs_update = True
            if needs_update:
                self.last_handled = now
                self.canvas.add_tiles_for_current_zoom()


class OnMissing(enum.Enum):
    """What action to take whenever a tile is missing"""
    # raise an exception
    RAISE = 0
    # ignore the exception and return None
    IGNORE = 1
    # return a picture of a cat.
    REPLACE_WITH_CAT = 2


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
        resp = session.get(url)
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
        self._tile_provider = tile_provider

        # cal factor done with math.  At zoom level 0, the mercator units / pixel
        # is 156543.  So our zom calibration factor needs to be based on that
        #
        # 17.256199785269995 == np.log2(self._web_mercator_bounds*2) / 256
        # (dividing by 256 because that is the number of pixels per tile)
        # Add 0.5 so that the zoom level is crisp in the middle of when it's loaded.
        self.zoom_cal = 17.256199785269995 + 0.5
        self._images = {}

        # Set 2D camera (the camera will scale to the contents in the scene)
        self.view.camera = TileCamera(aspect=1)
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
        self.view.camera.rect = rect
        self.last_event = None
        self.marker_size = 10
        self.queue = queue.Queue()
        self.worker_thread = threading.Thread(
            target=self.tile_controller,
            args=(self.queue,),
            daemon=True,
        )
        self.worker_thread.start()

        z = 1
        for x in range(2**z):
            for y in range(2**z):
                self._add_tile(z, x, y)
        self.freeze()

    def tile_controller(self, queue):
        """Background thread for doing the right thing with tiles"""
        while True:
            try:
                data = queue.get()
                if data is None:
                    break
                cmd = data['cmd']
                if cmd == 'call_method':
                    method = getattr(self, data['name'])
                    args = data.get('args', [])
                    kwargs = data.get('kwargs', {})
                    method(*args, **kwargs)
            except:
                # want to keep the loop going
                msg = 'tile_controller thread error on data {}'
                msg = msg.format(data)
                logger.exception(msg)

    @property
    def tile_provider(self):
        return self._tile_provider

    @tile_provider.setter
    def tile_provider(self, provider):
        self._tile_provider = provider
        self.add_tiles_for_current_zoom()

    def on_mouse_press(self, event):
        with lock:
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

    def _fix_y(self, y):
        if y >= self._web_mercator_bounds:
            return self._web_mercator_bounds - 1
        elif y <= -self._web_mercator_bounds:
            return -self._web_mercator_bounds + 1
        return y

    @property
    def real_rect(self):
        """Get the camera's real rectangle"""
        return self.view.camera._real_rect

    @property
    def current_bounds(self):
        """Return the tile index bounds of the current view.

        Returns a tuple of two mercantile.Tile instances
        """
        rect = self.real_rect
        z = self.best_zoom_level

        x0, y0 = rect.left, rect.top
        y0 = self._fix_y(y0)
        lng0, lat0 = mercantile.lnglat(x0, y0)
        tile0 = mercantile.tile(lng0, lat0, z)

        x1, y1 = rect.right, rect.bottom
        y1 = self._fix_y(y1)
        lng1, lat1 = mercantile.lnglat(x1, y1)
        tile1 = mercantile.tile(lng1, lat1, z)
        return tile0, tile1

    def _add_tiles_for_zoom(self, zoom_level=None, bounds=None):
        """
        """
        if zoom_level is None:
            zoom_level = self.best_zoom_level
        if bounds is None:
            bounds = self.current_bounds
        z = zoom_level
        tile0, tile1 = bounds
        # two extra tiles for smooth panning
        x0 = tile0.x - 1
        x1 = tile1.x + 1
        y0 = tile0.y - 1
        y1 = tile1.y + 1

        if y0 < 0:
            y0 = 0
        if y1 > 2**z - 1:
            y1 = 2**z - 1

        # for x in range(x0, x1 + 1):
        #     for y in range(y0, y1 + 1):
        #         self._add_tile(z, x, y)

        if (z, x0, x1, y0, y1) not in self._images:
            rgb = self._merge_tiles(z, x0, y0, x1, y1)
            image = self._add_rgb_as_image(rgb, z, x0, y1)
            self._images[z, x0, x1, y0, y1] = image

        for key in list(self._images):
            z = key[0]
            if z != zoom_level:
                self.remove_tile(key)
        assert len(self._images) == len(self.scene_images)

    def remove_tile(self, key):
        im = self._images.pop(key)
        with lock:
            im.parent = None

    def add_tiles_for_current_zoom(self):
        """
        Fill the current view with tiles
        """
        self.queue.put({
            'cmd': 'call_method',
            'name': '_add_tiles_for_zoom',
            'args': [self.best_zoom_level, self.current_bounds]
        })

    @property
    def scene_images(self):
        """Return the images that are part of the scene graph.  If the code
        is bug-free, the images here and the values of self._images should be equal.
        """
        with lock:
            c = self.view.children[0].children
            return [x for x in c if isinstance(x, scene.visuals.Image)]

    def _merge_tiles(self, z, x0, y0, x1, y1):
        """Merge range of tiles to form a single image."""
        rows = []
        start = time.time()
        for x in range(x0, x1 + 1):
            row = []
            for y in range(y1, y0 - 1, -1):
                # account for wrapping around the world...
                row.append(self.get_tile(z, x, y, missing=OnMissing.REPLACE_WITH_CAT))
            rows.append(np.concatenate(row))
        new_img = np.concatenate(rows, 1)
        return new_img

    def get_tile(self, z, x, y, missing=OnMissing.RAISE):
        """Return RGB array of tile at specified zoom, x, and y.

        If the tile for the specified zoom, x, and y cannot be found, raises a
        TileNotFoundError. Unless replace_missing_with_cat == True; then, return
        a picture of a cat.
        """
        try:
            rgb = self.tile_provider.get_tile(z, x, y)
        except TileNotFoundError:
            if missing == OnMissing.RAISE:
                raise
            elif missing == OnMissing.IGNORE:
                return
            elif missing == OnMissing.REPLACE_WITH_CAT:
                logger.warning('replacing %s with a cat.  Meow!', (z, x, y))
                rgb = self._get_cat()
            else:
                raise
        return rgb

    @functools.lru_cache(maxsize=1)
    def _get_cat(self):
        with open('cat-killer-256x256.png', 'rb') as f:
            im = PIL.Image.open(f)
            rgb = np.array(im)
        flipped = np.flip(rgb, 0)
        return flipped

    def _add_rgb_as_image(self, rgb, z, x, y):
        """Create image, and apply appropriate transform to it."""
        with lock:
            image = scene.visuals.Image(
                rgb,
                interpolation='hanning',
                parent=self.view.scene,
                method='subdivide',
            )
            transform = self.get_st_transform(z, x, y)
            image.transform = transform
        return image

    def _add_tile(self, z, x, y, missing=OnMissing.RAISE):
        if (z, x, y) in self._images:
            im = self._images[z, x, y]
            if im not in self.scene_images:
                logger.error('_images dict out of sync with scene children')
            else:
                return
        rgb = self.get_tile(z, x, y, missing)
        im = self._add_rgb_as_image(rgb, z, x, y)
        self._images[z, x, y] = im

    def add_tile(self, z, x, y, missing=OnMissing.RAISE):
        """Add tile to the canvas as an image.

        If the tile for the specified zoom, x, and y cannot be found, raises a
        TileNotFoundError.
        """
        self.queue.put({
            'cmd': 'call_method',
            'name': '_add_tile',
            'args': [z, x, y, missing],
        })

