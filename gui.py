import logging
import os


import numpy as np
from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt
from qtconsole.inprocess import QtInProcessKernelManager
from qtconsole.rich_jupyter_widget import RichJupyterWidget

from vistile import CanvasMap, StamenToner, CartodbDark, StamenWatercolor, \
    StamenTonerInverted, StamenTerrain

QtWidgets = QtGui


# Start Program
class MainWindow(QtWidgets.QMainWindow):

    quitting = QtCore.pyqtSignal(int)
    title = 'Vispy Tilemaps'

    def __init__(self, parent=None):

        QtWidgets.QMainWindow.__init__(self, parent)
        self.setWindowTitle(self.title)
        self.resize(1200, 900)
        self.setDockOptions(self.AnimatedDocks | self.AllowNestedDocks | self.AllowTabbedDocks)

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

        self.canvas = canvas = CanvasMap(tile_provider=StamenTonerInverted(),
                                         keys='interactive')

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

        self.addDockWidget(Qt.RightDockWidgetArea,   consoleDock,  Qt.Vertical)
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
    logging.basicConfig(level=logging.INFO)
    l = logging.getLogger('PIL.PngImagePlugin')
    l.setLevel(logging.WARNING)
    main()
