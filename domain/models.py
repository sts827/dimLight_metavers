from dataclasses import dataclass
from typing import List, Optional, Dict
from enum import Enum
from datetime import time, datetime


class ControlMode(Enum):
    AUTO = "auto"
    MANUAL = "manual"


class LightType(Enum):
    GROUP = "group"
    INDIVIDUAL = "individual"


class WeekDay(Enum):
    MONDAY = 1
    TUESDAY = 2
    WEDNESDAY = 3
    THURSDAY = 4
    FRIDAY = 5
    SATURDAY = 6
    SUNDAY = 7


@dataclass
class Light:
    """조명 개체"""
    id: str
    name: str
    brightness: int  # 0-100
    is_on: bool
    light_type: LightType
    group_id: Optional[str] = None


@dataclass
class LightGroup:
    """조명 그룹"""
    id: str
    name: str
    lights: List[Light]
    brightness: int  # 0-100
    is_on: bool


@dataclass
class Macro:
    """매크로 설정 (최대 3개, 이름 5글자 제한)"""
    id: str
    name: str  # 최대 5글자
    light_settings: Dict[str, int]  # light_id: brightness
    created_at: datetime
    updated_at: datetime

    def __post_init__(self):
        if len(self.name) > 5:
            raise ValueError("매크로 이름은 5글자 이하여야 합니다")


@dataclass
class Schedule:
    """스케줄 설정"""
    id: str
    name: str
    is_enabled: bool
    weekdays: List[WeekDay]
    on_time: time
    off_time: time
    macro_id: Optional[str] = None
    
    def __post_init__(self):
        if self.on_time == self.off_time:
            raise ValueError("켜는 시간과 끄는 시간이 같을 수 없습니다")
        if not self.weekdays:
            raise ValueError("요일을 최소 하나는 선택해야 합니다")


@dataclass
class DeviceInfo:
    """장치 정보"""
    device_name: str  # 고정값
    version: str      # 고정값
    serial_number: str  # 고정값
    manufacturer: str   # 고정값
    ip_address: str     # 변경 가능


@dataclass
class SensorData:
    """센서 데이터"""
    power_consumption: float  # 소비전력 (W)
    temperature: float        # 온도 (°C)
    humidity: float          # 습도 (%)
    timestamp: datetime


@dataclass
class SystemState:
    """시스템 상태"""
    current_mode: ControlMode
    is_screen_locked: bool = False
    last_interaction: Optional[datetime] = None
    
    def is_auto_standby_timeout(self) -> bool:
        """5분 이상 조작이 없었는지 확인"""
        if not self.last_interaction:
            return True
        return (datetime.now() - self.last_interaction).seconds > 300


@dataclass
class UIState:
    """UI 상태 관리"""
    current_screen: str
    brightness_adjustment: int = 0
    selected_light_id: Optional[str] = None
    selected_group_id: Optional[str] = None
    is_keypad_visible: bool = False
    is_time_picker_visible: bool = False
