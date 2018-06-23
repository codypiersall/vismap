from vispy import app
import vismap

canvas = vismap.CanvasMap(tile_provider=vismap.StamenTonerInverted(),
                           show=True)
canvas.title = 'Maaaaps'

app.run()

