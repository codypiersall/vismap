import mercantile
import numpy as np
from vismap import Canvas, MercatorTransform
from vispy import app
from vispy.scene.visuals import Text, Markers

c = Canvas(show=True)
c.title = "Issue 5"
c.view.camera.rect = (-1.08475e07, 4.18788e06), (2886.92, 2886.92)
c.view.add_tiles_for_current_zoom()

# add reference marker, using calculated x, y
long, lat = -97.441296, 35.18048
x, y = mercantile.xy(long, lat)

m_expected = Markers(parent=c.view.scene)
m_expected.set_data(np.array([(x, y, 0)]), face_color=(0, 1, 1))

t_ok = Text(
    "Expected position",
    pos=(x + 100, y),
    anchor_x="left",
    parent=c.view.scene,
    color=(0, 1, 1),
)
t_ok.order = 10

m_bad = c.view.marker_at((long - 0.0005, lat), face_color=(1, 0, 0))
t_bad = Text(
    "Actual position",
    pos=(long, lat),
    anchor_x="left",
    parent=c.view.scene,
    color=(1, 0, 0),
)
t_bad.order = 10
t_bad.transform = MercatorTransform()

app.run()
