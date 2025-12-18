from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Tuple

try:
    # pydantic v2 compatibility layer
    from pydantic.v1 import BaseModel, Field, conlist, validator
except ImportError:  # pragma: no cover
    from pydantic import BaseModel, Field, conlist, validator

Vec2 = Tuple[float, float]
Vec3 = Tuple[float, float, float]
Tri = Tuple[int, int, int]


def _normalize_ring(points: List[Vec2]) -> List[Vec2]:
    if len(points) >= 2 and points[0] == points[-1]:
        points = points[:-1]
    return points


class WallSegment2D(BaseModel):
    id: Optional[str] = Field(default=None, description="Optional wall id for referencing doors/windows.")
    start: Vec2
    end: Vec2
    thickness: Optional[float] = Field(default=None, gt=0)


class Opening2D(BaseModel):
    id: str
    type: Literal["door", "window"]
    wall_id: Optional[str] = Field(
        default=None,
        description="If provided, the opening is anchored on a wall segment with this id.",
    )
    center: Optional[Vec2] = Field(
        default=None,
        description="Opening center point in plan coordinates if wall_id is not used.",
    )
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    bottom: float = Field(default=0.0, ge=0, description="Bottom offset from floor (meters).")


class Room2DInput(BaseModel):
    id: str
    name: Optional[str] = None
    level: Optional[int] = Field(default=None, description="樓層編號（1-based），用於堆疊")
    z_offset: float = Field(default=0.0, description="以公尺計的 Z 偏移，用於樓層堆疊")
    polygon: conlist(Vec2, min_items=3) = Field(
        description="Room outer boundary as a ring of [x,y] points; last point may repeat the first.",
    )
    holes: List[conlist(Vec2, min_items=3)] = Field(
        default_factory=list,
        description="Optional inner rings (holes), each as a ring of [x,y] points.",
    )
    walls: List[WallSegment2D] = Field(
        default_factory=list,
        description="Optional explicit wall segments; if omitted, walls are derived from polygon edges.",
    )
    openings: List[Opening2D] = Field(default_factory=list, description="Optional doors/windows.")
    height: Optional[float] = Field(default=None, gt=0, description="Overrides default wall_height for this room.")

    @validator("polygon", pre=True)
    def _normalize_polygon(cls, value: Any) -> Any:
        if isinstance(value, list):
            value = _normalize_ring(value)
        return value

    @validator("holes", pre=True)
    def _normalize_holes(cls, value: Any) -> Any:
        if not isinstance(value, list):
            return value
        return [_normalize_ring(ring) if isinstance(ring, list) else ring for ring in value]


class MeshPart(BaseModel):
    """單一幾何部分的頂點/面定義"""
    vertices: List[Vec3] = Field(..., description="頂點座標列表 [[x,y,z], ...]")
    faces: List[Tri] = Field(..., description="面片索引列表 [[v1,v2,v3], ...]")


class MeshGenerationParams(BaseModel):
    wall_height: float = Field(default=2.8, gt=0)
    wall_thickness: float = Field(default=0.12, gt=0)
    floor_thickness: float = Field(default=0.0, ge=0)
    use_csg: bool = Field(
        default=False,
        description="If true, try trimesh+shapely boolean operations to cut openings with wall thickness.",
    )
    up_axis: Literal["z"] = "z"
    units: Literal["m"] = "m"


class Generate3DRequest(BaseModel):
    home_id: str = Field(description="Home identifier. Used to relate the mesh to the twin configuration.")
    rooms: List[Room2DInput] = Field(default_factory=list)
    params: MeshGenerationParams = Field(default_factory=MeshGenerationParams)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MeshData(BaseModel):
    """完整的 3D 網格數據包"""
    floor: MeshPart
    walls: MeshPart
    ceiling: Optional[MeshPart] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


# 解決 ForwardRef 造成的欄位未準備好問題
MeshData.update_forward_refs()
Generate3DRequest.update_forward_refs()
