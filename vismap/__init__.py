# Note: from .view import MapView needs to be before anything else to prevent
# import breakage
from ._version import __version__
from .view import MapView
from .canvas import Canvas
from .transforms import MercatorTransform, RelativeMercatorTransform
from . import tile_providers
