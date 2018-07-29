"""
Contains the MapView, which automatically grabs the correct tiles based on
the current zoom level.
"""

import enum
import functools
import logging
import os
import multiprocessing.pool
import queue
import threading

import PIL.Image
import mercantile
import numpy as np
import vispy
from vispy import scene
from vispy.visuals import transforms as transforms

from .tile_providers import StamenTonerInverted, TileNotFoundError
from .transforms import RelativeMercatorTransform, MercatorTransform

_CAT_FILE = os.path.join(os.path.dirname(__file__),
                         'cat-killer-256x256.png')


class OnMissing(enum.Enum):
    """What action to take whenever a tile is missing"""
    # raise an exception
    RAISE = 0
    # ignore the exception and return None
    IGNORE = 1
    # return a picture of a cat.
    REPLACE_WITH_CAT = 2


logger = logging.getLogger(__name__)


class MapView(scene.ViewBox):
    # x, y bounds for Web Mercator.
    _web_mercator_bounds = 20037508.342789244

    def __init__(self, tile_provider=StamenTonerInverted(), *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.unfreeze()
        # this lock is needed any time the scene graph is touched, or nodes of the
        # scene graph are transformed.
        self.scene_lock = threading.Lock()
        self._enabled = True

        self._images = {}
        # mapping of {(lnglat, radius): vispy.scene.visuals.Ellipse}
        # circles drawn around specific points
        self._circles = {}
        self._tile_provider = tile_provider
        # TODO: how big to make thread pool?
        self.request_pool = multiprocessing.pool.ThreadPool(10)

        # cal factor done with math.  At zoom level 0, the mercator units / pixel
        # is 156543.  So our zom calibration factor needs to be based on that
        #
        # 17.256199785269995 == np.log2(self._web_mercator_bounds*2) / 256
        # (dividing by 256 because that is the number of pixels per tile)
        # Add 0.5 so that the zoom level is crisp in the middle of when it's loaded.
        self.zoom_cal = 17.256199785269995 + 0.5

        # Set 2D camera (the camera will scale to the contents in the scene)
        self.camera = TileCamera(aspect=1)
        # flip y-axis to have correct alignment
        # self.camera.flip = (0, 1, 0)
        self.camera.set_range()
        # default is 0.007, half of that feels about right
        self.camera.zoom_factor = 0.0035

        # default zoom shows the whole world
        bbox = mercantile.xy_bounds(0, 0, 0)
        rect = vispy.geometry.Rect(bbox.left, bbox.bottom, bbox.right - bbox.left, bbox.top - bbox.bottom)
        self.longlat_text = vispy.scene.visuals.Text(
            '',
            parent=self.scene,
            color='red',
            anchor_x='left',
            font_size=10,
        )
        self.longlat_text.order = 1

        self._attribution = vispy.scene.visuals.Text(
            tile_provider.attribution,
            parent=self,
            # a few pixels from the top left
            pos=(4, 4),
            color='white',
            anchor_x='left',
            anchor_y='bottom',
            font_size=9,
        )
        self._attribution.order = 1

        self.marker = vispy.scene.visuals.Markers(parent=self.scene)
        self.marker.set_data(np.array([[0, 0]]), face_color=[(1, 1, 1)])
        self.marker.order = 1
        self.marker.draw()
        self.camera.rect = rect
        self.last_event = None
        self.marker_size = 10
        self.queue = queue.Queue()
        self.worker_thread = threading.Thread(
            target=self.tile_controller,
            args=(self.queue,),
            daemon=True,
        )
        self.worker_thread.start()

        self.tile_provider = tile_provider
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
        for im in list(self._images):
            self.remove_tile(im)
        self.add_tiles_for_current_zoom()
        self._attribution.text = provider.attribution

    def on_mouse_press(self, event):
        # lock needed here? we're messing with the marker and some text.
        with self.scene_lock:
            self.last_event = event
            if event.button == 2:
                # right click
                self.longlat_text.text = ''
                # should be painted below anything else
                self.marker.visible = False
                return
            elif event.button == 3:
                # middle click
                canvas_x, canvas_y, *_ = event.pos
                width, height = self.size

                rect = self.camera._real_rect

                x_interp = canvas_x / width
                y_interp = canvas_y / height
                view_x = rect.left + x_interp * (rect.right - rect.left)
                view_y = rect.top + y_interp * (rect.bottom - rect.top)
                self.longlat_text.pos = (view_x, view_y)
                msg = '((long {:f} lat {:f}) ({:f}, {:f})'
                lng, lat = mercantile.lnglat(view_x, view_y)
                msg = msg.format(lng, lat, view_x, view_y)
                self.longlat_text.text = msg
                self.marker.set_data(np.array([[view_x, view_y]]),
                                     size=self.marker_size)
                self.marker.visible = True

    @property
    def mercator_scale(self):
        """Get mercator units per pixel of the canvas"""
        # figure out the right zoom level by the number of pixels per mercator units
        canvas_width, _ = self.size
        _real_rect = self.camera._real_rect
        # units are Mercator
        scene_width = _real_rect.width
        merc_per_pixel = scene_width / canvas_width
        return merc_per_pixel

    @property
    def tile_zoom_level(self):
        merc_per_pixel = self.mercator_scale

        zoom = -np.log2(merc_per_pixel)
        # account for a good "known zoom" level
        zoom += self.zoom_cal
        zoom = int(zoom)
        if zoom < 0:
            zoom = 0
        return zoom

    def _update_transforms(self):
        """
        Holds the scene_lock while updating transforms.  It was seen through
        tracebacks that this method seemed to be the best place to put a lock.

        """
        with self.scene_lock:
            super()._update_transforms()

    def get_st_transform(self, z, x, y):
        """
        Return the STTransform for the current zoom, x, and y tile.
        """

        bbox = mercantile.xy_bounds(x, y, z)
        scale = (bbox.right - bbox.left) / 256
        scale = scale, scale, 1

        # place the tiles up high, so that everything will show up correctly
        # TODO: figure out why setting z super high works!  Not sure if it's
        # expected behavior or just a detail of the current Vispy
        # implementation.  Seems like setting order would be a better way,
        # but it doesn't work.
        # If we ever switch to a different type of camera probably nothing
        # will work.
        translate = bbox.left, bbox.bottom, 9e5 - z
        return transforms.STTransform(scale=scale, translate=translate)

    def _fix_y(self, y):
        """Make sure ``y`` fits in the Web Mercator bounds."""
        if y >= self._web_mercator_bounds:
            return self._web_mercator_bounds - 1
        elif y <= -self._web_mercator_bounds:
            return -self._web_mercator_bounds + 1
        return y

    @property
    def current_bounds(self):
        """Return the tile index bounds of the current view.

        Returns a tuple of two mercantile.Tile instances: the northwest and
        southeast corners.
        """
        rect = self.camera._real_rect
        z = self.tile_zoom_level

        x0, y0 = rect.left, rect.top
        y0 = self._fix_y(y0)
        lng0, lat0 = mercantile.lnglat(x0, y0)
        northwest = mercantile.tile(lng0, lat0, z)

        x1, y1 = rect.right, rect.bottom
        y1 = self._fix_y(y1)
        lng1, lat1 = mercantile.lnglat(x1, y1)
        southeast = mercantile.tile(lng1, lat1, z)
        return northwest, southeast

    def _add_tiles_for_zoom(self, zoom_level=None, bounds=None, extra=1):
        """
        (Synchronously) add tiles to the canvas specified zoom. and bounds.

        if zoom_level is None, use ``self.current_zoom``

        """
        if zoom_level is None:
            zoom_level = self.tile_zoom_level
        if bounds is None:
            bounds = self.current_bounds
        z = zoom_level
        northwest, southeast = bounds
        # extra tiles for smooth panning
        x0 = northwest.x - extra
        x1 = southeast.x + extra
        y0 = northwest.y - extra
        y1 = southeast.y + extra

        if y0 < 0:
            y0 = 0
        if y1 > 2**z - 1:
            y1 = 2**z - 1

        if (z, x0, x1, y0, y1) not in self._images:
            rgb = self._merge_tiles(z, x0, y0, x1, y1)
            image = self._add_rgb_as_image(rgb, z, x0, y1)
            self._images[z, x0, x1, y0, y1] = image

        for key in list(self._images):
            z = key[0]
            if z != zoom_level:
                self.remove_tile(key)

    def remove_tile(self, key):
        """Remove the tile from the scene.

        ``key`` must be a key in self._images
        """
        im = self._images.pop(key)
        with self.scene_lock:
            im.parent = None

    def add_tiles_for_current_zoom(self):
        """
        Fill the current view with tiles.  Does the actual operation in the
        background.
        """
        self.queue.put({
            'cmd': 'call_method',
            'name': '_add_tiles_for_zoom',
            'args': [self.tile_zoom_level, self.current_bounds]
        })

    @property
    def scene_images(self):
        """Return the images that are part of the scene graph.  If the code
        is bug-free, the images here and the values of self._images should be
        equal.
        """
        with self.scene_lock:
            c = self.children[0].children
            return [x for x in c if isinstance(x, scene.visuals.Image)]

    def _merge_tiles(self, z, x0, y0, x1, y1):
        """Merge range of tiles to form a single image."""
        requests = []
        x_range = range(x0, x1 + 1)
        y_range = range(y1, y0 - 1, -1)
        for x in x_range:
            for y in y_range:
                requests.append((z, x, y, OnMissing.REPLACE_WITH_CAT))
        results = self.request_pool.starmap(self.get_tile, requests)

        # iterate over results, which will be exactly the same size as the
        # number of requests made
        it = iter(results)
        rows = []
        for x in range(x0, x1 + 1):
            row = []
            for y in range(y1, y0 - 1, -1):
                row.append(next(it))
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
        with open(_CAT_FILE, 'rb') as f:
            im = PIL.Image.open(f)
            rgb = np.array(im)
        flipped = np.flip(rgb, 0)
        return flipped

    def _add_rgb_as_image(self, rgb, z, x, y):
        """Create image, and apply appropriate transform to it."""
        with self.scene_lock:
            image = scene.visuals.Image(
                rgb,
                interpolation='hanning',
                parent=self.scene,
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

    @property
    def map_enabled(self):
        """
        Enable or disable the mapping capabilities of this view.

        """
        return self._enabled

    @map_enabled.setter
    def map_enabled(self, enabled):
        self._enabled = enabled

        self._attribution.visible = enabled
        if enabled:
            self.add_tiles_for_current_zoom()
        else:
            images = list(self._images.keys())
            for im in images:
                self.remove_tile(im)

    def circle(self, longlat, radius, border_color=(1, 1, 1), color=(1, 1, 1 , 0)):
        """Add a circle centere at ``center`` of radius ``radius``

        Args:
          longlat: center of the circle, given as a (longitude, latitude) tuple
          radius: radius of the circle, specified in meters
          border_color: color of the circle's border
          color: fill color of the circle (usually transparent)

        """
        key = longlat, radius
        if key in self._circles:
            self.remove_circle(*key)
        c = scene.visuals.Ellipse(
            center=longlat,
            radius=(radius, radius),
            border_color=border_color,
            color=color,
            parent=self.scene,
        )
        c.transform = RelativeMercatorTransform(*longlat)
        self._circles[key] = c

    def circle_at_marker(self, radius, border_color=(1, 1, 1), color=(1, 1, 1, 0)):
        longlat = self.marker_pos
        self.circle(longlat, radius, border_color, color)

    def remove_circle(self, longlat, radius):
        """Remove the circle at ``longlat`` with radius ``radius`` from the
        scene.
        """
        c = self._circles.pop((longlat, radius))
        c.parent = None

    @property
    def marker_pos(self):
        """Return Marker's position as a (longitude, latitude) tuple"""
        return mercantile.lnglat(*self.marker._data[0][0][0:2])

    def marker_at(self, longlat, face_color=(0, 1, 1), size=10):
        marker = scene.visuals.Markers(parent=self.scene)
        data = np.array([longlat])
        marker.set_data(data, face_color=[face_color], size=size)
        marker.transform = MercatorTransform()

class TileCamera(scene.PanZoomCamera):
    def viewbox_mouse_event(self, event):
        view = self.parent.parent
        with view.scene_lock:
            super().viewbox_mouse_event(event)
            if not view.map_enabled:
                return
            # if the tile command queue has anything in it, let's just get the
            # heck out of here; this prevents a hugely unresponsive deal.
            if not view.queue.empty():
                return
            # figure out if we need an update; if the mouse is moving, but no key
            # is held down, we don't need to update.
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
                view.add_tiles_for_current_zoom()
