# -*- coding: utf-8 -*-
"""Remove a near-white background connected to image edges and write RGBA PNG.

This deliberately does not remove enclosed white regions, so white faces, eyes,
clothes and logo counters remain opaque.
"""
from __future__ import annotations

import argparse
from collections import deque
from pathlib import Path

from PIL import Image


def remove_edge_background(source: Path, target: Path, threshold: int = 242) -> None:
    """只移除与图片边缘连通的近白背景，保留角色内部白色区域。"""
    image = Image.open(source).convert("RGBA")
    pixels = image.load()
    width, height = image.size
    seen = bytearray(width * height)
    queue: deque[tuple[int, int]] = deque()

    def is_background(x: int, y: int) -> bool:
        r, g, b, _ = pixels[x, y]
        return min(r, g, b) >= threshold and max(r, g, b) - min(r, g, b) <= 18

    def add(x: int, y: int) -> None:
        idx = y * width + x
        if seen[idx] or not is_background(x, y):
            return
        seen[idx] = 1
        queue.append((x, y))

    for x in range(width):
        add(x, 0)
        add(x, height - 1)
    for y in range(height):
        add(0, y)
        add(width - 1, y)

    while queue:
        x, y = queue.popleft()
        r, g, b, _ = pixels[x, y]
        whiteness = min(r, g, b)
        alpha = max(0, min(255, (threshold - whiteness) * 18))
        pixels[x, y] = (r, g, b, alpha)
        if x:
            add(x - 1, y)
        if x + 1 < width:
            add(x + 1, y)
        if y:
            add(x, y - 1)
        if y + 1 < height:
            add(x, y + 1)

    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target, "PNG", optimize=True)


def main() -> None:
    """批量处理指定图片并输出透明 PNG。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument("--threshold", type=int, default=242)
    args = parser.parse_args()
    remove_edge_background(args.source, args.target, args.threshold)


if __name__ == "__main__":
    main()
