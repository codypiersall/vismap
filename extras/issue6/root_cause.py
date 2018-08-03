"""
This demonstrates the root cause of issue6, where using the MercatorTransform
does not place data where it should.  See
https://github.com/codypiersall/vismap/issues/6 for more information.
"""

import numpy as np

from vispy.visuals.transforms.base_transform import BaseTransform
from vispy.plot import Fig

from vispy.scene.visuals import LinePlot


class CosTransform(BaseTransform):
    """
    Applies the transformation (pos.y = cos(pos.x)).

    """

    Linear = False
    Orthogonal = False
    NonScaling = True
    Isometric = False

    glsl_map = """
        vec4 CosTransform_map(vec4 pos) {
            pos.y = cos(pos.x);
            return pos;
        }
    """

    glsl_imap = """
        vec4 CosTransform_imap(vec4 pos) {
             pos.y = acos(pos.x);
            return pos;
        }
    """

    def __init__(self):
        super().__init__()


def main():
    # compare CPU and GPU implementations of cos().
    x0 = np.linspace(-np.pi, np.pi, 100000)
    cos_cpu = np.cos(x0)

    fig = Fig()
    ax = fig[0, 0]
    # cpu data
    cos_line_cpu = LinePlot((x0, cos_cpu), color='k')
    # gpu data
    cos_line_gpu = LinePlot((x0, x0), color='red')
    cos_line_gpu.transform = CosTransform()

    # logic taken from PlotWidget.plot()
    ax._configure_2d()
    ax.view.add(cos_line_cpu)
    ax.visuals.append(cos_line_cpu)

    ax.view.add(cos_line_gpu)
    ax.visuals.append(cos_line_gpu)
    ax.title.text = 'Cos(x), cpu vs gpu'
    ax.view.camera.rect = [1.01162, 0.530485, 0.00001, 0.00005]
    fig.show(run=True)


if __name__ == '__main__':
    main()
