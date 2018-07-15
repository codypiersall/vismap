from vispy import app
from vispy.scene import SceneCanvas
import vismap.view


class Canvas(SceneCanvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.unfreeze()
        self.grid = self.central_widget.add_grid()
        for row in range(2):
            for col in range(2):
                view = vismap.view.MapView(vismap.tile_providers.random_provider())
                self.grid.add_widget(row=row, col=col, widget=view)
        self.freeze()


def main():
    canvas = Canvas(show=True)
    canvas.title = 'Maps'
    app.run()


if __name__ == '__main__':
    main()
