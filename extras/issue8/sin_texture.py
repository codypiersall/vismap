"""
This demonstrates the root cause of issue6, where using the MercatorTransform
does not place data where it should.  See
https://github.com/codypiersall/vismap/issues/6 for more information.
"""

import numpy as np

import vispy.gloo as gloo
from vispy.visuals.transforms.base_transform import BaseTransform
from vispy.plot import Fig

from vispy.scene.visuals import LinePlot


def to_rgb(x):
    p1 = np.floor(x * 256)
    x //= 256
    p2 = np.floor(x * 256)
    x //= 256
    p3 = np.round(x * 256)
    return p1, p2, p3


class TextureSinTransform(BaseTransform):
    """
    Applies the transformation (pos.y = sin(pos.x)) using a texture

    """

    glsl_map = """
        #define M_PI 3.1415926535897932384626433832795
        vec4 good_sin_transform(vec4 pos) {
            // need to scale pos to be between [0, 1]
            float x;
            x = pos.x / (2 * M_PI);
            // center the x coordinate now
            x = x + 1.0 / (2 * $npoints);
            pos.y = texture1D($trans, x).r;
            return pos;
        }"""

    glsl_imap = """
        #define M_PI 3.1415926535897932384626433832795
        vec4 good_sin_transform(vec4 pos) {
            pos.y = texture1D($trans_inv, pos.x).r;
            return pos;
        }"""

    def __init__(self, npoints):
        super().__init__()
        self.npoints = npoints
        # we're intentionally not including the endpoint
        x = np.linspace(0, 2 * np.pi, npoints, dtype='float32', endpoint=False)
        sin_x = np.sin(x)
        data = np.array([x, sin_x])
        self._trans_tex = gloo.Texture1D(sin_x,
                                         interpolation='linear',
                                         internalformat='r32f',
                                         )
        self._trans_inv = gloo.Texture1D(x,
                                         interpolation='linear',
                                         internalformat='r32f',
                                         )
        shader = self.shader_map()
        shader['trans'] = self._trans_tex
        shader['npoints'] = float(npoints)
        self.shader_imap()['trans_inv'] = self._trans_inv


class BuiltinSinTransform(BaseTransform):
    """
    Applies the transformation (pos.y = sin(pos.x)).

    """

    Linear = False
    Orthogonal = False
    NonScaling = True
    Isometric = False

    glsl_map = """
        vec4 BuiltinSinTransform_map(vec4 pos) {
            pos.y = sin(pos.x);
            return pos;
        }
    """

    glsl_imap = """
        vec4 BuiltinSinTransform_imap(vec4 pos) {
             pos.y = asin(pos.x);
            return pos;
        }
    """

    def __init__(self):
        super().__init__()


def main():
    # compare CPU and GPU implementations of sin().
    x0 = np.linspace(-2 * np.pi, 2 * np.pi, 400000)
    sin_cpu = np.sin(x0)

    fig = Fig()
    ax = fig[0, 0]
    # cpu data
    sin_line_cpu = LinePlot((x0, sin_cpu), color='k')

    # gpu lines
    gpu_sin_line = LinePlot((x0, x0), color='red')
    gpu_sin_line.transform = BuiltinSinTransform()

    coarse_sin_line = LinePlot((x0, x0), color='blue')
    coarse_sin_line.transform = TextureSinTransform(20)

    fine_sin_line = LinePlot((x0, x0), color='green', symbol='o')
    fine_sin_line.transform = TextureSinTransform(8192 * 2)


    # logic taken from PlotWidget.plot()
    ax._configure_2d()

    # for line in sin_line_cpu, lame_sin_line, good_sin_line:
    for line in sin_line_cpu, coarse_sin_line, fine_sin_line, gpu_sin_line:
        ax.view.add(line)
        ax.visuals.append(line)

    ax.title.text = 'sin(x), cpu vs gpu'
    ax.view.camera.rect = [-1.02740, -0.85599, 0.00001, 0.00004]
    fig.show(run=True)


if __name__ == '__main__':
    main()
