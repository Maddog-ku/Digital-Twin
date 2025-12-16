# core/models.py

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from sqlalchemy import Column, String, Float, Boolean, ForeignKey
from sqlalchemy.orm import declarative_base, relationship

# SQLAlchemy 模型基礎
Base = declarative_base()

# --- 數據庫 ORM 模型定義 ---

class SensorModel(Base):
    """感測器配置與最新狀態 (對應 PostgreSQL 的 sensors 表)"""
    __tablename__ = 'sensors'
    
    # 配置
    id = Column(String, primary_key=True)
    type = Column(String, nullable=False) # PIR, DoorContact, Smoke
    location_x = Column(Float, default=0.0)
    location_y = Column(Float, default=0.0)
    location_z = Column(Float, default=0.0)
    
    # 關聯
    room_id = Column(String, ForeignKey('rooms.id'), nullable=False)
    
    # 狀態 (用於持久化最新狀態)
    status = Column(String, default='unknown')
    is_alert = Column(Boolean, default=False)
    
    # 啟用關聯，但這裡不需要 to_dict 方法，因為服務層會用 DataClass 轉換
    
class RoomModel(Base):
    """房間配置 (對應 PostgreSQL 的 rooms 表)"""
    __tablename__ = 'rooms'
    
    # 配置
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    owner = Column(String) # 例如: User A, Common Area
    
    # 關聯：一個房間有多個感測器
    sensors = relationship("SensorModel", backref="room", cascade="all, delete-orphan")
    
class HomeTwinModel(Base):
    """住家總體配置 (對應 PostgreSQL 的 home_twin 表)"""
    __tablename__ = 'home_twin'
    
    # 配置 (單列，PK 固定為 'main_home_config')
    home_id = Column(String, primary_key=True)
    security_status = Column(String, default='Safe')

# --- 服務層使用的 Python 數據類 (您原來的 DataClass 定義) ---
@dataclass
class Sensor:
    """單個感測器的數位孿生模型"""
    id: str
    type: str # 例如: PIR, DoorContact, Smoke
    location: Optional[List[float]] = field(default_factory=list) # 3D/2D 坐標，高擴展性
    status: Any = 'unknown' # 即時狀態值
    is_alert: bool = False  # 狀態是否為警報

    def to_dict(self):
        """將物件轉換為可供 API 返回的字典"""
        return {
            "id": self.id,
            "type": self.type,
            "status": self.status,
            "location": self.location,
            "is_alert": self.is_alert
        }

@dataclass
class Room:
    """單個房間的數位孿生模型"""
    id: str
    name: str
    sensors: Dict[str, Sensor] = field(default_factory=dict) # 使用字典存儲感測器，方便按ID查找

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "sensors": [s.to_dict() for s in self.sensors.values()]
        }

@dataclass
class HomeTwin:
    """整個住家數位孿生模型"""
    home_id: str
    rooms: Dict[str, Room] = field(default_factory=dict)
    security_status: str = "Safe"

    def to_dict(self):
        return {
            "home_id": self.home_id,
            "security_status": self.security_status,
            "rooms": [r.to_dict() for r in self.rooms.values()]
        }