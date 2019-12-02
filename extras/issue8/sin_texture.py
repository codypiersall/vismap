"""
This demonstrates the root cause of issue6, where using the MercatorTransform
does not place data where it should.  See
https://github.com/codypiersall/vismap/issues/6 for more information.
"""

import numpy as np

import vispy.gloo as gloo
from vispy.visuals.transforms.base_transform import BaseTransform
from vispy.plot import Fig

from vispy.scene.visuals import LinePlot, Markers


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
        // does asin transform using a texture
        #define M_PI 3.1415926535897932384626433832795
        vec4 good_sin_transform(vec4 pos) {
            // input is scaled from 0 to 1, we need it to be -1 to 1 (the
            // domain of asin)
            float x = (pos.x + 1.0) / 2.0;
            // lookup from center of texture coord
            x = x - 1.0 / (2 * $npoints);
            pos.y = texture1D($trans_inv, x).r;
            return pos;
        }"""

    def __init__(self, npoints):
        super().__init__()
        self.npoints = npoints
        # we're intentionally not including the endpoint
        self.x1 = x1 = np.linspace(0, 2 * np.pi, npoints, dtype='float32', endpoint=False)
        self.sin_x1 = sin_x1 = np.sin(x1)
        self._trans_tex = gloo.Texture1D(sin_x1,
                                         interpolation='linear',
                                         internalformat='r32f',
                                         )

        self.x2 = x2 = np.linspace(-1, 1, npoints, dtype='float32', endpoint=True)
        self.asin_x2 = asin_x2 = np.arcsin(x2)
        self._trans_inv = gloo.Texture1D(asin_x2,
                                         interpolation='linear',
                                         internalformat='r32f',
                                         )
        shader = self.shader_map()
        shader['trans'] = self._trans_tex
        shader['npoints'] = float(npoints)

        imap = self.shader_imap()
        imap['trans_inv'] = self._trans_inv
        imap['npoints'] = float(npoints)


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
    x0 = np.linspace(-2 * np.pi, 2 * np.pi, 100000)
    sin_cpu = np.sin(x0)

    fig = Fig()
    ax1 = fig[0, 0]
    # cpu data
    sin_line_cpu = LinePlot((x0, sin_cpu), color='k')

    # gpu lines
    gpu_sin_line = LinePlot((x0, x0), color='red')
    gpu_sin_line.transform = BuiltinSinTransform()

    coarse_sin_line = LinePlot((x0, x0), color='blue')
    coarse_sin_line.transform = TextureSinTransform(20)

    fine_sin_line = LinePlot((x0, x0), color='green')
    tr = TextureSinTransform(16384)
    fine_sin_line.transform = tr
    pos = np.array([tr.x1, tr.sin_x1]).T
    markers = Markers(pos=pos, symbol='o')


    # logic taken from PlotWidget.plot()
    ax1._configure_2d()

    # for line in sin_line_cpu, lame_sin_line, good_sin_line:
    for line in sin_line_cpu, coarse_sin_line, fine_sin_line, gpu_sin_line:
        ax1.view.add(line)
        ax1.visuals.append(line)
    ax1.view.add(markers)
    ax1.visuals.append(markers)

    ax1.title.text = 'sin(x), cpu vs gpu'
    ax1.view.camera.rect = [-1.02740, -0.85599, 0.00001, 0.00004]



    ax2 = fig[1, 0]
    ax2._configure_2d()

    x1 = np.linspace(-1, 1, 400000)
    asin_cpu = np.arcsin(x1)

    fine_asin_line = LinePlot((x1, x1), color='green')
    tr = TextureSinTransform(16384).inverse
    fine_asin_line.transform = tr

    # cpu data
    asin_line_cpu = LinePlot((x1, asin_cpu), color='k')
    ax2.view.add(asin_line_cpu)
    ax2.visuals.append(asin_line_cpu)

    ax2.view.add(fine_asin_line)
    ax2.visuals.append(fine_asin_line)

    fig.show(run=True)


if __name__ == '__main__':
    main()
