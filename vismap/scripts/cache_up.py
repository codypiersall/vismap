"""
Populate the tile cache by making a bunch of requests to the tile servers.

The cache is populated for a specific latitude/longitude.

"""

import argparse
from math import ceil
from multiprocessing.pool import ThreadPool

import mercantile

from ..tile_providers import providers


def _get_clargs():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--lat",
        type=float,
        help="latitude at which to center the collection",
        required=True,
    )
    p.add_argument(
        "--long",
        type=float,
        help="longitude at which to center the collection",
        required=True,
    )

    p.add_argument(
        "--size",
        type=int,
        help="Number of tiles to grab for each direction at each zoom level."
        "  The total number that will be taken is SIZE**2, for each zoom "
        "level.",
        default=30,
    )

    p.add_argument(
        "--max-zoom",
        type=int,
        help="The maximum zoom at which to grab tiles",
        default=16,
    )

    p.add_argument(
        "--provider",
        choices=providers.keys(),
        help="Tile Provider (by name) to retrieve.",
        default="StamenToner",
    )

    p.add_argument(
        "--verbose",
        help="Be verbose",
        action="store_true",
        default=False,
    )
    return p.parse_args()


def _get_tile(provider, z, x, y):
    # we created this function so that we don't keep the results of retrieving
    # the tiles around.  If we just called provider.get_tile(z, x, y) in the
    # apply_async of the thread pool, the responses would not have been garbage
    # collected until the threadpool was joined.

    # Important: intentionally not returning a value.
    provider.get_tile(z, x, y)


def main():
    args = _get_clargs()
    size = ceil(args.size / 2)
    provider = providers[args.provider]()
    tp = ThreadPool(10)
    with tp:
        for zoom in range(args.max_zoom):
            tile = mercantile.tile(args.long, args.lat, zoom, truncate=True)
            x_center, y_center = tile.x, tile.y

            x_min = max(0, x_center - size)
            x_max = min(2**zoom - 1, x_center + size)

            y_min = max(0, y_center - size)
            y_max = min(2**zoom - 1, y_center + size)
            print(zoom, (x_min, x_max), (y_min, y_max))
            results = []
            for x in range(x_min, x_max + 1):
                for y in range(y_min, y_max + 1):
                    res = tp.apply_async(_get_tile, args=(provider, zoom, x, y))
                    results.append(res)

            for result in results:
                result.get()


if __name__ == "__main__":
    main()
