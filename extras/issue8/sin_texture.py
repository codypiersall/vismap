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


class GoodSinTransform(BaseTransform):
    """
    Applies the transformation (pos.y = sin(pos.x)) using a texture

    """

    glsl_map = """
        vec4 good_sin_transform(vec4 pos) {
            pos.y = texture1D($trans, pos.x).r;
            return pos;
        }"""

    glsl_imap = """
        vec4 good_sin_transform(vec4 pos) {
            pos.y = texture1D($trans_inv, pos.x).r;
            return pos;
        }"""

    def __init__(self, npoints):
        super().__init__()
        x = np.linspace(-np.pi, np.pi, npoints, dtype='float32')
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
        self.shader_map()['trans'] = self._trans_tex
        self.shader_imap()['trans_inv'] = self._trans_inv


class LameSinTransform(BaseTransform):
    """
    Applies the transformation (pos.y = sin(pos.x)).

    """

    Linear = False
    Orthogonal = False
    NonScaling = True
    Isometric = False

    glsl_map = """
        vec4 LameSinTransform_map(vec4 pos) {
            pos.y = sin(pos.x);
            return pos;
        }
    """

    glsl_imap = """
        vec4 LameSinTransform_imap(vec4 pos) {
             pos.y = asin(pos.x);
            return pos;
        }
    """

    def __init__(self):
        super().__init__()


def main():
    # compare CPU and GPU implementations of sin().
    x0 = np.linspace(-np.pi, np.pi, 100000)
    sin_cpu = np.sin(x0)

    fig = Fig()
    ax = fig[0, 0]
    # cpu data
    sin_line_cpu = LinePlot((x0, sin_cpu), color='k')
    # gpu data
    lame_sin_line = LinePlot((x0, x0), color='red')
    lame_sin_line.transform = LameSinTransform()

    good_sin_line = LinePlot((x0, x0), color='blue')
    good_sin_line.transform = GoodSinTransform(1024)

    # logic taken from PlotWidget.plot()
    ax._configure_2d()

    # for line in sin_line_cpu, lame_sin_line, good_sin_line:
    for line in sin_line_cpu, good_sin_line:
        ax.view.add(line)
        ax.visuals.append(line)

    ax.title.text = 'sin(x), cpu vs gpu'
    # ax.view.camera.rect = [1.01162, 0.530485, 0.00001, 0.00005]
    ax.view.camera.rect = [-1.02740, -0.85599, 0.00001, 0.00004]
    fig.show(run=True)


if __name__ == '__main__':
    main()
