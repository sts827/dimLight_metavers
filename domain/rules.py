import re
from typing import List
from datetime import time
from .models import WeekDay, ControlMode
from .exceptions import (
    MacroLimitExceededException,
    MacroNameLengthException, 
    ScheduleTimeException,
    ScheduleWeekdayException,
    InvalidIPAddressException,
    AutoModeOperationException,
    BrightnessRangeException
)


class MacroRules:
    """매크로 관련 비즈니스 규칙"""
    
    MAX_MACRO_COUNT = 3
    MAX_NAME_LENGTH = 5
    
    @classmethod
    def validate_macro_count(cls, current_count: int) -> None:
        """매크로 개수 검증"""
        if current_count >= cls.MAX_MACRO_COUNT:
            raise MacroLimitExceededException()
    
    @classmethod
    def validate_macro_name(cls, name: str) -> None:
        """매크로 이름 검증"""
        if len(name) > cls.MAX_NAME_LENGTH:
            raise MacroNameLengthException()
        if not name.strip():
            raise ValueError("매크로 이름은 공백일 수 없습니다")


class ScheduleRules:
    """스케줄 관련 비즈니스 규칙"""
    
    @classmethod
    def validate_schedule_time(cls, on_time: time, off_time: time) -> None:
        """스케줄 시간 검증"""
        if on_time == off_time:
            raise ScheduleTimeException()
    
    @classmethod
    def validate_weekdays(cls, weekdays: List[WeekDay]) -> None:
        """요일 설정 검증"""
        if not weekdays:
            raise ScheduleWeekdayException()


class DeviceRules:
    """장치 관련 비즈니스 규칙"""
    
    @classmethod
    def validate_ip_address(cls, ip_address: str) -> None:
        """IP 주소 형식 검증"""
        ip_pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
        if not re.match(ip_pattern, ip_address):
            raise InvalidIPAddressException()
        
        # 각 옥텟이 0-255 범위인지 확인
        octets = ip_address.split('.')
        for octet in octets:
            if not (0 <= int(octet) <= 255):
                raise InvalidIPAddressException()


class LightControlRules:
    """조명 제어 관련 비즈니스 규칙"""
    
    MIN_BRIGHTNESS = 0
    MAX_BRIGHTNESS = 100
    
    @classmethod
    def validate_brightness(cls, brightness: int) -> None:
        """밝기 값 검증"""
        if not (cls.MIN_BRIGHTNESS <= brightness <= cls.MAX_BRIGHTNESS):
            raise BrightnessRangeException()
    
    @classmethod
    def validate_auto_mode_operation(cls, current_mode: ControlMode) -> None:
        """자동 모드에서 조작 시도 검증"""
        if current_mode == ControlMode.AUTO:
            raise AutoModeOperationException()


class UIRules:
    """UI 관련 비즈니스 규칙"""
    
    AUTO_STANDBY_TIMEOUT_MINUTES = 5
    TIME_ADJUSTMENT_MINUTES = 30  # 30분 단위 조정
    
    @classmethod
    def get_standby_timeout_seconds(cls) -> int:
        """대기 화면 전환 시간 (초)"""
        return cls.AUTO_STANDBY_TIMEOUT_MINUTES * 60
    
    @classmethod
    def validate_time_adjustment(cls, minutes: int) -> bool:
        """시간 조정 단위 검증"""
        return minutes % cls.TIME_ADJUSTMENT_MINUTES == 0
