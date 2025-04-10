"""
Vispy canvas that lets you do tile maps
"""

from vispy import scene

from . import MapView
from .tile_providers import StamenToner, TileProvider


class Canvas(scene.SceneCanvas):
    """Map on top of tile data"""

    def __init__(self, *args, tile_provider: TileProvider = StamenToner(), **kwargs):
        super().__init__(*args, **kwargs)
        # Set up a viewbox to display the image with interactive pan/zoom
        self.unfreeze()
        self.view = self.central_widget.add_widget(MapView(tile_provider))
        self.freeze()
