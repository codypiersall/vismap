Vismap
======

Provides a Canvas for creating maps with Vispy.  The canvas gets its tiles from
a [TileProvider](vismap/tile_providers.py).  Several tile providers are bundled
with this project; adding a tile provider simply requires knowing the URL at
which to grab a tile, and providing the attribution text for the tiles.

Run the provided [example](vismap/example.py) to check out how interacting with
the map works.  The script is installed as ``vismap-example`` if you install
vismap; so from your command line just run

    vismap-example

Use the left and right arrow keys to change the tile provider.


What's the Point?
-----------------

The idea is to be able to display real-time geographical data on top of a
map–for example, radar data.  This project provides the canvas which
automatically fills the map based on the current zoom level, and also provides
transforms, so you can actually view data on top of the map.  The transforms
are located in [vismap/transforms.py](vismap/transforms.py).

Currently, two transforms are provided:  `MercatorTransform` and
`RelativeMercatorTransform`.  Use the `MercatorTransform` when your data is
naturally represented in longitude/latitude pairs. For example, the following
will draw a line from Norman, OK to Oklahoma City, OK:

    from vismap import Canvas, MercatorTransform
    import vispy.scene.visuals as visuals
    from vispy import app
    import numpy as np

    c = Canvas()
    c.show()
    line = visuals.Line(np.array([[-97.4395, 35.2226], [-97.5164, 35.4676]]),
                        parent=c.view.scene)
    line.transform = MercatorTransform()  # the magic line!
    app.run()

The `RelativeMercatorTransform` is for plotting data that is naturally
expressed in units of length, but would be nice if it were centered somewhere
geographically.  The motivating use case is radar data: it makes sense to think
of the data in meters, relative to a specific latitude and longitude.

When you are using these transforms, make sure you **always remember to add the
visual to the correct scene**, otherwise the data will not show up and it will
probably be confusing.
