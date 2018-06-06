import abc
import logging
import os

from vispy import scene
from png import Reader
from requests_cache import CachedSession
import numpy as np
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
        resp = session.get(url)
        img_bytes = resp.content
        rgb = read_png_bytes(img_bytes)
        return rgb


class Stamen(TileProvider):
    def url(self, z, x, y):
        url = 'http://c.tile.stamen.com/{map_name}/{}/{}/{}.png'
        return url.format(z, x, y)

class StamenToner(Stamen):
    map_name = 'stamen'

class StamenLite(Stamen):
    map_name = 'stamen-lite'

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
    def __init__(self, *args, tile_provider=StamenToner(), **kwargs):
        super().__init__(*args, **kwargs)
        # Set up a viewbox to display the image with interactive pan/zoom
        self.unfreeze()
        self.view = self.central_widget.add_view()
        self.tile_provider = tile_provider

        # mapping from (z, x, y) -> visual
        self._images = {}

        self.add_tile(0, 0, 0)

        # Set 2D camera (the camera will scale to the contents in the scene)
        self.view.camera = scene.PanZoomCamera(aspect=1)
        # flip y-axis to have correct aligment
        self.view.camera.flip = (0, 1, 0)
        self.view.camera.set_range()
        self.view.camera.zoom(1, (250, 200))
        # default is 0.007, half of that feels about right
        self.view.camera.zoom_factor = 0.0035
        self.freeze()

    def add_tile(self, z, x, y):
        """Add tile to the canvas as an image"""
        # Create the image
        png = self.tile_provider.get_tile(z, x, y)
        self.image = image = scene.visuals.Image(png, interpolation='nearest',
                                                 parent=self.view.scene, method='subdivide')

# Start Program
class MainWindow(QtWidgets.QMainWindow):

    quitting = QtCore.pyqtSignal(int)
    title = 'Radar Control GUI'

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

        self.canvas = canvas = CanvasMap(tile_provider=CartodbDark(), keys='interactive')
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

    def show(self, rememberLayout=True):
        super().show()

    def closeEvent(self, event):
        """Shutdown the Application"""
        # Autosave on Exit


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
    rememberLayout = 'reset' not in sys.argv
    win.show(rememberLayout=rememberLayout)
    app.lastWindowClosed.connect(app.quit)

    try:
        sys.exit(app.exec_())
    except SystemExit:
        pass

if __name__ == '__main__':
    main()
