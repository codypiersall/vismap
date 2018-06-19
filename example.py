from vispy import app
import vistile

canvas = vistile.CanvasMap(tile_provider=vistile.StamenToner(), show=True)

app.run()

