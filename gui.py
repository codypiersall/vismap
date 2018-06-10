import abc
import logging
import os

import mercantile
import numpy as np
import vispy
from vispy import scene
import vispy.visuals.transforms as transforms
from requests_cache import CachedSession
from png import Reader
from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt
from qtconsole.inprocess import QtInProcessKernelManager
from qtconsole.rich_jupyter_widget import RichJupyterWidget

QtWidgets = QtGui
DEFAULT_NLOGD_ADDR = 'tcp://10.203.7.171:46000'

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
            raise ValueError(msg)
        img_bytes = resp.content
        rgb = read_png_bytes(img_bytes)
        return rgb


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

        z = 0
        self.add_tile(0, 0, 0)
        for x in range(z*2):
            for y in range(z*2):
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
        self.text.draw()
        self.marker = vispy.scene.visuals.Markers(parent=self.view.scene)
        self.marker.set_data(np.array([[0, 0, 0]]), face_color=[(1, 1, 1)])
        self.marker.draw()
        self.view.camera.rect = rect
        self.last_event = None
        self.size = self.size
        self.freeze()

    def on_mouse_press(self, event):
        self.last_event = event
        canvas_x, canvas_y = event.pos
        width, height = self.size

        rect = self.view.camera.rect
        x_interp = canvas_x / width
        y_interp = canvas_y / height
        view_x = rect.left + x_interp * (rect.right - rect.left)
        view_y = rect.top + y_interp * (rect.bottom - rect.top)
        self.text.pos = (view_x, view_y)
        msg = '({:d}, {:d}), ({:.3g}, {:.3g})'
        msg = msg.format(canvas_x, canvas_y, view_x, view_y)
        self.text.text = msg

    def get_st_transform(self, z, x, y):
        """
        Return the STTransform for the current zoom, x, and y tile.
        """

        bbox = mercantile.xy_bounds(x, y, z)
        scale = (bbox.right - bbox.left) / 256
        scale = scale, scale, 1
        translate = bbox.left, bbox.bottom, -z
        logger.info('top %s', bbox.top)
        return transforms.STTransform(scale=scale, translate=translate)

    def add_tile(self, z, x, y):
        """Add tile to the canvas as an image"""
        # Create the image; this should be cached if it's been used recently
        if (z, x, y) in self._images:
            # don't double add.
            # TODO: decide how to tell if the map provider changed.
            pass
        png = self.tile_provider.get_tile(z, x, y)
        png = np.flip(png, 0)
        image = scene.visuals.Image(
            png, interpolation='hanning', parent=self.view.scene, method='subdivide'
        )
        transform = self.get_st_transform(z, x, y)
        image.transform = transform
        self._images[(z, x, y)] = image

    def remove_tile(self, z, x, y):
        """Remove a tile from the map"""
        image = self.images[z, x, y]
        self.scene.remove_subvisual(image)


# Start Program
class MainWindow(QtWidgets.QMainWindow):

    quitting = QtCore.pyqtSignal(int)
    title = 'Vispy Tilemaps'

    def __init__(self, parent=None):

        QtWidgets.QMainWindow.__init__(self, parent)
        self.setWindowTitle(self.title)
        self.resize(1200, 900)
        self.setDockOptions(self.AnimatedDocks | self.AllowNestedDocks | self.AllowTabbedDocks)

        # Create GUI Elements
        ## Setup MenuBar


        ## Setup Bottom Dock
        self.__createBottomDockWidgets()
        # Set Default Positions
        self.statusBar().showMessage('Ready')

    def pushNewIPython(self, scan):
        try:
            self.IPythonConsole.push({'scan': scan})
        except IndexError:
            pass

    def __createBottomDockWidgets(self):
        """Setup the bottom dock widgets"""
        ## Configure Status Widget
        self.statusWidget = statusWidget = QtWidgets.QDockWidget('Status')
        statusWidget.setObjectName('Status')

        self.canvas = canvas = CanvasMap(tile_provider=StamenToner(), keys='interactive')
        # self.canvas = canvas = CanvasMap(keys='interactive')

        self.vislayout = QtWidgets.QBoxLayout(1)
        self.vislayout.addWidget(self.canvas.native)
        self.dockedWidget = QtWidgets.QWidget()
        statusWidget.setWidget(self.dockedWidget)
        self.dockedWidget.setLayout(self.vislayout)

        ## Configure Console/Log Area
        consoleDock = QtWidgets.QDockWidget('Console')
        consoleDock.setObjectName('Console')
        consoleDock.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Ignored)

        self.IPythonConsole = SizedRichJupyterWidget()
        self.IPythonConsole.push({'self': self, 'np': np})
        self.IPythonConsole.push(globals())
        self.IPythonConsole.push(locals())

        consoleDock.setWidget(self.IPythonConsole)

        # self.hw_config = HardwareManager()

        #use dummy controller by default
        self.radar_controller_name = os.environ.get('RADAR_DEV_PLATFORM', 'CPPAR')

        logDock = QtWidgets.QDockWidget('Log')
        logDock.setObjectName('Log')

        self.addDockWidget(Qt.RightDockWidgetArea,   consoleDock,  Qt.Vertical)
        self.addDockWidget(Qt.BottomDockWidgetArea,  logDock,      Qt.Horizontal)
        self.addDockWidget(Qt.RightDockWidgetArea,   statusWidget, Qt.Horizontal)
        # self.addDockWidget(Qt.BottomDockWidgetArea,  statusWidget, Qt.Horizontal)

        # self.tabifyDockWidget(consoleDock, logDock)

    def show(self):
        super().show()


class MinimalJupyterWidget(RichJupyterWidget):
    """A Jupyter widget that can be placed into a GUI as a widget.

    This widget creates a kernel and a client as the docs recommend.
    """
    def __init__(self, *args, profile='radar', **kwargs):
        super().__init__(*args, **kwargs)
        self.manager = manager = QtInProcessKernelManager()
        manager.start_kernel()
        manager.kernel.log.level = 60  # Disable IPython Logging

        client = manager.client(profile=profile)
        client.start_channels()
        client.log.level = 60
        self.kernel_manager = manager
        self.kernel_client = client

    def push(self, d):
        """Push dict into IPython namespace"""
        self.manager.kernel.shell.push(d)


class SizedRichJupyterWidget(MinimalJupyterWidget):
    def sizeHint(self):
        s = QtCore.QSize()
        s.setWidth(super(SizedRichJupyterWidget, self).sizeHint().width())
        s.setHeight(100)
        return s

def main():
    import sys
    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow()
    win.show()
    app.lastWindowClosed.connect(app.quit)

    try:
        sys.exit(app.exec_())
    except SystemExit:
        pass

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    main()
