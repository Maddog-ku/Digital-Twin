from __future__ import annotations

from typing import Optional, Dict, Any, List

import cv2
import numpy as np


def parse_single_floor_image(
    file_stream,
    level: int = 1,
    floor_height: float = 3.0,
    ratio: float = 0.01,
) -> Optional[Dict[str, Any]]:
    """分水嶺版解析：使用 distance transform 分離沾黏房間，輸出樓層與房間 polygons。"""
    file_bytes = np.frombuffer(file_stream.read(), np.uint8)
    img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
    if img is None:
        return None

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)

    kernel = np.ones((3, 3), np.uint8)
    sure_bg = cv2.dilate(binary, kernel, iterations=3)

    dist_transform = cv2.distanceTransform(binary, cv2.DIST_L2, 5)
    _, sure_fg = cv2.threshold(dist_transform, 0.5 * dist_transform.max(), 255, 0)
    sure_fg = np.uint8(sure_fg)

    unknown = cv2.subtract(sure_bg, sure_fg)

    _, markers = cv2.connectedComponents(sure_fg)
    markers = markers + 1
    markers[unknown == 255] = 0

    markers = cv2.watershed(img, markers)

    rooms_payload: List[Dict[str, Any]] = []
    for label in range(2, int(markers.max()) + 1):
        room_mask = np.zeros(gray.shape, dtype=np.uint8)
        room_mask[markers == label] = 255

        contours, _ = cv2.findContours(room_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            continue
        cnt = contours[0]
        if cv2.contourArea(cnt) < 2000:
            continue

        epsilon = 0.015 * cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, epsilon, True)

        polygon: List[List[float]] = []
        for point in approx:
            x, y = point[0]
            polygon.append([float(x) * ratio, float(y) * ratio])

        rooms_payload.append(
            {
                "id": f"room_{level}_{label}",
                "name": f"Room {label-1}",
                "level": level,
                "height": floor_height,
                "polygon": polygon,
                "openings": [],
            }
        )

    return {
        "id": f"floor_{level}",
        "level": level,
        "z_offset": (level - 1) * floor_height,
        "rooms": rooms_payload,
    }
