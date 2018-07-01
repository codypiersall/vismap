"""
Transforms for moving to/from Meracator projection and latitude/longitude.
"""

import numpy as np
from vispy.visuals.transforms.base_transform import BaseTransform
from vispy.visuals.transforms._util import arg_to_vec4  # noqa

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


class MercatorTransform(BaseTransform):
    """
    Transforms longitude/latitude to Mercator coordinates.
    """

    Linear = False
    Orthogonal = True
    NonScaling = False
    Isometric = False

    glsl_map = """
        #define M_PI 3.1415926535897932384626433832795
        vec4 MercatorTransform_map(vec4 pos) {
            /* x is longitude
             * y is latitude
             * z is still z
            */
            /* Radius of Earth in meters; taken from mercantile's source code */
            const float R = 6378137;

            float lon = pos.x;
            float lat = pos.y;
            float lambda = radians(lon);
            float phi = radians(lat);

            pos.x = R * lambda;
            pos.y = R * log(tan(M_PI / 4 + phi / 2));

            /* We didn't change pos.z, which is intended */
            return pos;
        }
    """

    glsl_imap = """
        // map Mercator x,y coords to longitude/latitude.
        #define M_PI 3.1415926535897932384626433832795
        vec4 MercatorTransform_imap(vec4 pos) {
            /*
             * x -> longitude
             * y -> latitude
             * z -> z
             */

            /* Radius of Earth in meters; taken from mercantile's source code */
            const float R = 6378137.0;

            float lambda = pos.x / R;
            float lon = degrees(lambda);

            float phi = 2 * atan(exp(pos.y / R)) - M_PI / 2;
            float lat = degrees(phi);

            pos.x = lon;
            pos.y = lat;

            return pos;
        }
    """

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

