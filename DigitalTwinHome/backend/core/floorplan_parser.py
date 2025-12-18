from __future__ import annotations

import cv2
import numpy as np


class FloorplanToMeshParser:
    """
    移植自 FloorplanToBlender3d 的核心邏輯，
    將 2D 圖片轉為前端可用的房間 polygon JSON。
    """

    def __init__(self, pixel_to_meter_ratio: float = 0.01):
        self.ratio = pixel_to_meter_ratio

    def parse(self, file_stream, level: int = 1, height: float = 3.0):
        """讀取影像並輸出房間/樓層結構。"""
        file_bytes = np.frombuffer(file_stream.read(), np.uint8)
        img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Failed to decode image")

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        _, binary = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        clean_walls = self._clean_walls(binary)
        rooms_polygons = self._detect_rooms(clean_walls)

        return self._build_payload(rooms_polygons, level, height)

    def _clean_walls(self, binary_img):
        """清除小型雜訊並閉合牆線。"""
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary_img, connectivity=8)
        cleaned = binary_img.copy()
        for i in range(1, num_labels):
            area = stats[i, cv2.CC_STAT_AREA]
            if area < 500:
                cleaned[labels == i] = 0

        kernel_size = 15
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
        closed_walls = cv2.morphologyEx(cleaned, cv2.MORPH_CLOSE, kernel)
        return closed_walls

    def _detect_rooms(self, wall_mask):
        """找出封閉房間輪廓並簡化。"""
        rooms_map = cv2.bitwise_not(wall_mask)
        contours, _ = cv2.findContours(rooms_map, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        valid_polygons = []
        for cnt in contours:
            if cv2.contourArea(cnt) < 2000:
                continue
            epsilon = 0.015 * cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, epsilon, True)
            points = []
            for p in approx:
                points.append([float(p[0][0]), float(p[0][1])])
            valid_polygons.append(points)

        valid_polygons.sort(key=lambda p: p[0][0])
        return valid_polygons

    def _build_payload(self, polygons, level, height):
        rooms_data = []
        for i, poly in enumerate(polygons):
            scaled_poly = [[p[0] * self.ratio, p[1] * self.ratio] for p in poly]
            rooms_data.append(
                {
                    "id": f"room_{level}_{i}",
                    "name": f"Space {i+1}",
                    "level": level,
                    "height": height,
                    "polygon": scaled_poly,
                    "openings": [],
                }
            )

        return {
            "id": f"floor_{level}",
            "level": level,
            "z_offset": (level - 1) * height,
            "rooms": rooms_data,
        }
