from __future__ import annotations

from typing import Iterable, List
from io import BytesIO

import ezdxf
from shapely.geometry import LineString
from shapely.ops import polygonize


class DxfToMeshParser:
    """將 CAD DXF 中指定圖層的線條轉為房間 polygons。"""

    def __init__(self, target_layer_names: Iterable[str] | None = None):
        names = target_layer_names or ["WALL", "WALLS", "STRUCTURE"]
        self.target_layers = [name.upper() for name in names]

    def parse(self, file_stream, level: int = 1, height: float = 3.0):
        """讀取 DXF 並輸出樓層/房間資料。"""
        # 接受 bytes、str 或類 file 物件
        if hasattr(file_stream, "read"):
            data = file_stream.read()
        else:
            data = file_stream
        if isinstance(data, str):
            data = data.encode("utf-8", errors="ignore")

        try:
            doc = ezdxf.read(BytesIO(data))
        except Exception as e:
            raise ValueError(f"Invalid DXF file: {e}")

        msp = doc.modelspace()
        lines: List[LineString] = []

        for entity in msp:
            layer_name = (entity.dxf.layer or "").upper()
            if layer_name not in self.target_layers:
                continue

            etype = entity.dxftype()
            if etype == "LINE":
                start = entity.dxf.start
                end = entity.dxf.end
                lines.append(LineString([(start.x, start.y), (end.x, end.y)]))
            elif etype == "LWPOLYLINE":
                pts = entity.get_points("xy")
                for i in range(len(pts) - 1):
                    lines.append(LineString([pts[i], pts[i + 1]]))
                if entity.closed and len(pts) >= 2:
                    lines.append(LineString([pts[-1], pts[0]]))

        if not lines:
            raise ValueError(
                f"No lines found in layers: {self.target_layers}. Please check layer names in CAD."
            )

        polygons = list(polygonize(lines))
        rooms_payload = []
        for i, poly in enumerate(polygons):
            coords = list(poly.exterior.coords)
            formatted_coords = [[float(p[0]), float(p[1])] for p in coords]
            rooms_payload.append(
                {
                    "id": f"room_dxf_{level}_{i}",
                    "name": f"Space {i+1}",
                    "level": level,
                    "height": height,
                    "polygon": formatted_coords,
                    "openings": [],
                }
            )

        return {
            "id": f"floor_dxf_{level}",
            "level": level,
            "z_offset": (level - 1) * height,
            "rooms": rooms_payload,
        }
