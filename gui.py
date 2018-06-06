import os
import logging
import time
import os
import sys

from vispy import scene
from vispy.ext.png import Reader
from requests_cache import CachedSession
import numpy as np
from PyQt4 import QtCore, QtGui
QtWidgets = QtGui
from PyQt4.QtCore import Qt
from qtconsole.inprocess import QtInProcessKernelManager
from qtconsole.rich_jupyter_widget import RichJupyterWidget

DEFAULT_NLOGD_ADDR = 'tcp://10.203.7.171:46000'

logger = logging.getLogger(__name__)

session = CachedSession(cache_name='tiles')


class CanvasMap(scene.SceneCanvas):
    pass


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

        self.canvas = canvas = CanvasMap(keys='interactive')
        canvas.size = 800, 600
        canvas.show()

        # Set up a viewbox to display the image with interactive pan/zoom
        self.view = canvas.central_widget.add_view()

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


        # Create the image
        resp = session.get('http://c.tile.stamen.com/toner/0/0/0.png')
        resp = session.get('http://c.tile.stamen.com/toner/1/0/0.png')
        resp = session.get('http://c.tile.stamen.com/toner/1/0/1.png')
        resp = session.get('http://c.tile.stamen.com/toner/1/1/0.png')
        resp = session.get('http://c.tile.stamen.com/toner/1/1/1.png')
        img_bytes = resp.content
        png = read_png_bytes(img_bytes)
        interpolation = 'nearest'

        self.image = image = scene.visuals.Image(png, interpolation=interpolation,
                                    parent=self.view.scene, method='subdivide')

        canvas.title = 'Spatial Filtering using %s Filter' % interpolation

        # Set 2D camera (the camera will scale to the contents in the scene)
        self.view.camera = scene.PanZoomCamera(aspect=1)
        # flip y-axis to have correct aligment
        self.view.camera.flip = (0, 1, 0)
        self.view.camera.set_range()
        self.view.camera.zoom(0.1, (250, 200))

        # get interpolation functions from Image
        names = image.interpolation_functions
        names = list(names)
        names.sort()
        act = 17


        # Implement key presses
        @canvas.events.key_press.connect
        def on_key_press(event):
            global act
            if event.key in ['Left', 'Right']:
                if event.key == 'Right':
                    step = 1
                else:
                    step = -1
                act = (act + step) % len(names)
                interpolation = names[act]
                image.interpolation = interpolation
                self.canvas.title = 'Spatial Filtering using %s Filter' % interpolation
                self.canvas.update()

        self.vislayout = QtWidgets.QBoxLayout(1)
        self.vislayout.addWidget(self.canvas.native)
        self.dockedWidget = QtWidgets.QWidget()
        statusWidget.setWidget(self.dockedWidget)
        self.dockedWidget.setLayout(self.vislayout)

        statusWidget.setWidget(self.dockedWidget)
        statusWidget.setLayout(self.vislayout)
        statusWidget.show()

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
        self.quitting.emit(1)
        time.sleep(2)
        self.statusThread.quit()
        self.logThread.quit()


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
