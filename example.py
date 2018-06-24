import itertools

from vispy import app
import vismap
import vismap.tile_providers as tp


class CircularSequeunce:
    def __init__(self, data):
        self.data = data

    def __getitem__(self, item):
        return self.data[item % len(self.data)]


_names = list(tp.providers)
_names = CircularSequeunce(_names)


class Canvas(vismap.CanvasMap):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.unfreeze()
        self._provider_index = 0
        self._update_provider()
        self.freeze()

    def on_key_press(self, e):
        if e.key == 'Left':
            self._provider_index -= 1
            self._update_provider()
        elif e.key == 'Right':
            self._provider_index += 1
            self._update_provider()

    def _update_provider(self):
        name = _names[self._provider_index]
        self.tile_provider = tp.providers[name]()
        self.title = name

canvas = Canvas(show=True)
canvas.title = 'Maaaaps'

app.run()

