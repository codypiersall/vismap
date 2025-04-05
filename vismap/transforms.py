"""
Transforms for moving to/from Meracator projection and latitude/longitude.
"""

import mercantile
import numpy as np
from vispy.visuals.transforms.base_transform import BaseTransform
from vispy.visuals.transforms._util import arg_to_vec4  # noqa
from vispy.visuals.shaders import Function

# radius of Earth, in meters.  Value taken from mercantile source code.
R = 6378137

# equations from Wikipedia:
# https://en.wikipedia.org/wiki/Mercator_projection#Derivation_of_the_Mercator_projection
# forward transforms:
#   x = R(λ - λ₀), where:
#       R is the radius of the Earth in meters
#       λ is longitude in radians
#       λ₀ is reference longitude (0, for our purposes)
#
#   y = R * ln(tan(π / 4 + φ / 2)), where:
#       R is the radius of the Earth in meters
#       φ is the latitude in radians
#
# inverse transforms
#   λ = λ₀ + x / R
#   φ = 2 tan⁻¹(exp(y/r)) - π / 2

# used in a couple translate functions
long_to_x = Function("""
    float long_to_x(float lon) {
        const float R = 6378137;
        float lambda = radians(lon);
        float x =  R * lambda;
        return x;
    }
""")

lat_to_y = Function("""
    #define M_PI 3.1415926535897932384626433832795
    float lat_to_y(float lat) {
        const float R = 6378137;
        float phi = radians(lat);
        float y = R * log(tan(M_PI / 4 + phi / 2));
        return y;
    }
""")

x_to_long = Function("""
    float x_to_long(float x) {
    /* Radius of Earth in meters; taken from mercantile's source code */
    const float R = 6378137.0;
    float lambda = x / R;
    float lon = degrees(lambda);
    return lon;

    }
""")

y_to_lat = Function("""
    #define M_PI 3.1415926535897932384626433832795
    float y_to_lat(float y) {
    /* Radius of Earth in meters; taken from mercantile's source code */
    const float R = 6378137.0;
    float phi = 2 * atan(exp(y / R)) - M_PI / 2;
    float lat = degrees(phi);
    return lat;
    }
""")


def offset_coord(long, lat, x, y):
    """Offset x, y (given in meters) from specified long, lat.

    Returns new long, lat tuple
    """
    d_lat = y / R
    d_long = x / (R * np.cos(np.pi * lat / 180))
    lat_other = lat + d_lat * 180 / np.pi
    long_other = long + d_long * 180 / np.pi
    return long_other, lat_other


class MercatorTransform(BaseTransform):
    """
    Transforms longitude/latitude to Mercator coordinates.
    """

    Linear = False
    Orthogonal = True
    NonScaling = True
    Isometric = False

    glsl_map = """
        /* Transform latitude/longitude to Mercator coordinates*/
        vec4 MercatorTransform_map(vec4 pos) {
            /* pos.x is longitude (initially)
             * pos.y is latitude (initially)
             * z we don't change */
            pos.x = $long_to_x(pos.x);
            pos.y = $lat_to_y(pos.y);

            /* We didn't change pos.z, which is intended */
            return pos;
        }
    """

    glsl_imap = """
        // Transform Mercator x,y coords to longitude/latitude.
        #define M_PI 3.1415926535897932384626433832795
        vec4 MercatorTransform_imap(vec4 pos) {
            /* pos.x is Mercator x, transforming to long
             * pos.y is Mercator y, transforming to lat
             * pos.z we don't mess with */
             pos.x = $x_to_long(pos.x);
             pos.y = $y_to_lat(pos.y);
            return pos;
        }
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._shader_map["long_to_x"] = long_to_x
        self._shader_map["lat_to_y"] = lat_to_y

        self._shader_imap["x_to_long"] = x_to_long
        self._shader_imap["y_to_lat"] = y_to_lat

    @arg_to_vec4
    def map(self, coords):
        # https://en.wikipedia.org/wiki/Mercator_projection#Derivation_of_the_Mercator_projection
        m = np.empty(coords.shape)
        lambda_ = np.radians(coords[:, 0])
        phi = np.radians(coords[:, 1])
        m[:, 0] = R * np.radians(lambda_)
        m[:, 1] = R * np.log(np.tan(np.pi / 4 * phi / 2))
        m[:, 2:] = coords[:, 2:]
        return m

    @arg_to_vec4
    def imap(self, coords):
        # https://en.wikipedia.org/wiki/Mercator_projection#Derivation_of_the_Mercator_projection
        m = np.empty(coords.shape)
        x = coords[:, 0]
        y = coords[:, 1]
        lambda_ = x / R
        phi = 2 * np.atan(np.exp(y / R) - np.pi / 2)
        m[:, 0] = np.degrees(lambda_)
        m[:, 1] = np.degrees(phi)
        m[:, 2:] = coords[:, 2:]
        return m


class RelativeMercatorTransform(BaseTransform):
    """
    For this transform, the actual data to plot is in meters, but it is
    translated to the specified longitude/latitude.  An example use case is
    to plot a 10 km circle centered at a specific longitude/latitude.

    Parameters
    ----------
    longitude : Longitude at which to center the +latitude : Latitude at
    which to center the data

    """

    glsl_map = """
        #define M_PI 3.1415926535897932384626433832795
        vec4 RelativeMercatorTransform_map(vec4 pos) {
            const float R = 6378137.0;
            float long_center = $lon;
            float lat_center = $lat;

            float lat_to_add = $y_to_lat(pos.y);
            float lat_fin = lat_center + lat_to_add;
            pos.y = $lat_to_y(lat_fin);

            /* https://gis.stackexchange.com/a/2980
             * account for how many meters/degree longitude changing based on
             * how far from the equator you are */
            float long_offs = degrees(pos.x / (R * cos(radians(lat_center))));
            pos.x = $long_to_x(long_center + long_offs);

            return pos;
        }
    """

    Linear = False
    Orthogonal = True
    NonScaling = True
    Isometric = False

    glsl_imap = """
    vec4 RelativeMercatorTransform_imap(vec4 pos) {
        // TODO: this
        // my brain can't understand what the inverse mapping of this even means
        return pos;
    }
    """

    def __init__(self, longitude, latitude, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._longitude = longitude
        self._latitude = latitude
        s = self._shader_map
        s["lon"] = longitude
        s["lat"] = latitude
        s["long_to_x"] = long_to_x
        s["lat_to_y"] = lat_to_y
        s["y_to_lat"] = y_to_lat

    @property
    def longitude(self):
        return self._longitude

    @longitude.setter
    def longitude(self, long):
        self._shader_map["lon"] = long
        self._longitude = long

    @property
    def latitude(self):
        return self._latitude

    @latitude.setter
    def latitude(self, lat):
        self._latitude = lat
        self._shader_map["lat"] = lat

    @arg_to_vec4
    def map(self, coords):
        # TODO: test this
        m = np.empty(coords.shape)
        x, y = coords[:, 0], coords[:, 1]
        long, lat = offset_coord(self.longitude, self.latitude, x, y)
        x, y = mercantile.xy(long, lat)
        m[:, 0] = x
        m[:, 1] = y
        m[:, 2:] = coords[:, 2:]
        return m
