from vispy import app
import vistile

canvas = vistile.CanvasMap(tile_provider=vistile.StamenTonerInverted(),
                           show=True)
canvas.title = 'Tiles!'

app.run()

