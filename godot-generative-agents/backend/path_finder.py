"""Grid path-finding, vendored from the Generative Agents project.

Source: ``reverie/backend_server/path_finder.py`` in
https://github.com/joonspk-research/generative_agents (Apache-2.0;
Author: Joon Sung Park, joonspk@stanford.edu).

We keep only the breadth-first ``path_finder`` (and its helper
``path_finder_v2``) because that is all this port needs: given a
collision grid and two tiles, return the tile-by-tile path between them so the
frontend can animate a believable walk instead of a straight line through walls.

Only change from upstream: the BFS wave cap (``except_handle``) is raised from
150 to a value that comfortably covers a cross-map walk on ``the_ville`` (a
140x100 grid). Upstream paths were short, intra-sector hops; ours span the whole
town, and a too-small cap would silently truncate a long path.

The collision grid passed in here is normalized to ints (1 = blocked, 0 = open)
by ``world_map.WorldMap``, so ``collision_block_char`` is ``1`` -- robust no
matter which tile id the Tiled export used for walls.

(Upstream imported numpy for a single distance calc in ``closest_coordinate``;
we use ``math.hypot`` instead so the backend has no third-party dependency.)
"""

import math

# Upper bound on BFS expansion waves. The wave count equals the path length, so
# this must exceed the longest believable walk on the map. 140 + 100 (map
# diagonal) plus slack for detours around buildings; 4000 is generous and cheap.
_MAX_WAVES = 4000


def path_finder_v2(a, start, end, collision_block_char, verbose=False):
    def make_step(m, k):
        for i in range(len(m)):
            for j in range(len(m[i])):
                if m[i][j] == k:
                    if i > 0 and m[i - 1][j] == 0 and a[i - 1][j] == 0:
                        m[i - 1][j] = k + 1
                    if j > 0 and m[i][j - 1] == 0 and a[i][j - 1] == 0:
                        m[i][j - 1] = k + 1
                    if i < len(m) - 1 and m[i + 1][j] == 0 and a[i + 1][j] == 0:
                        m[i + 1][j] = k + 1
                    if j < len(m[i]) - 1 and m[i][j + 1] == 0 and a[i][j + 1] == 0:
                        m[i][j + 1] = k + 1

    new_maze = []
    for row in a:
        new_row = []
        for j in row:
            if j == collision_block_char:
                new_row += [1]
            else:
                new_row += [0]
        new_maze += [new_row]
    a = new_maze

    m = []
    for i in range(len(a)):
        m.append([])
        for j in range(len(a[i])):
            m[-1].append(0)
    i, j = start
    m[i][j] = 1

    k = 0
    except_handle = _MAX_WAVES
    while m[end[0]][end[1]] == 0:
        k += 1
        make_step(m, k)

        if except_handle == 0:
            break
        except_handle -= 1

    i, j = end
    k = m[i][j]
    the_path = [(i, j)]
    while k > 1:
        if i > 0 and m[i - 1][j] == k - 1:
            i, j = i - 1, j
            the_path.append((i, j))
            k -= 1
        elif j > 0 and m[i][j - 1] == k - 1:
            i, j = i, j - 1
            the_path.append((i, j))
            k -= 1
        elif i < len(m) - 1 and m[i + 1][j] == k - 1:
            i, j = i + 1, j
            the_path.append((i, j))
            k -= 1
        elif j < len(m[i]) - 1 and m[i][j + 1] == k - 1:
            i, j = i, j + 1
            the_path.append((i, j))
            k -= 1

    the_path.reverse()
    return the_path


def path_finder(maze, start, end, collision_block_char, verbose=False):
    # EMERGENCY PATCH (from upstream): the BFS indexes the grid as [row][col] =
    # [y][x], but callers pass tiles as (x, y). Swap on the way in and back out.
    start = (start[1], start[0])
    end = (end[1], end[0])

    path = path_finder_v2(maze, start, end, collision_block_char, verbose)

    new_path = []
    for i in path:
        new_path += [(i[1], i[0])]
    return new_path


def closest_coordinate(curr_coordinate, target_coordinates):
    """Return the target tile nearest (Euclidean) to ``curr_coordinate``."""
    cx, cy = curr_coordinate
    min_dist = None
    closest = None
    for coordinate in target_coordinates:
        dist = math.hypot(coordinate[0] - cx, coordinate[1] - cy)
        if closest is None or min_dist > dist:
            min_dist = dist
            closest = coordinate
    return closest
