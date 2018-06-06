# -*- coding: utf-8 -*-
# vispy: gallery 30
# -----------------------------------------------------------------------------
# Copyright (c) Vispy Development Team. All Rights Reserved.
# Distributed under the (new) BSD License. See LICENSE.txt for more info.
# -----------------------------------------------------------------------------
"""
Simple use of SceneCanvas to display an Image.
"""
import sys

import numpy as np
from vispy import scene
from vispy import app

from vispy.ext.png import Reader

from requests_cache import CachedSession


session = CachedSession(cache_name='tiles')

canvas = scene.SceneCanvas(keys='interactive')
canvas.size = 800, 600
canvas.show()

# Set up a viewbox to display the image with interactive pan/zoom
view = canvas.central_widget.add_view()


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

image = scene.visuals.Image(png, interpolation=interpolation,
                            parent=view.scene, method='subdivide')

canvas.title = 'Spatial Filtering using %s Filter' % interpolation

# Set 2D camera (the camera will scale to the contents in the scene)
view.camera = scene.PanZoomCamera(aspect=1)
# flip y-axis to have correct aligment
view.camera.flip = (0, 1, 0)
view.camera.set_range()
view.camera.zoom(0.1, (250, 200))

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
        canvas.title = 'Spatial Filtering using %s Filter' % interpolation
        canvas.update()


if __name__ == '__main__' and sys.flags.interactive == 0:
    app.run()
