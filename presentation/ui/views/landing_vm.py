from typing import Optional
from dataclasses import dataclass
from datetime import datetime
from domain.models import ControlMode, SensorData
from app.services import SensorDataService, SystemStateService


@dataclass
class LandingViewState:
    """대기화면 상태"""
    current_mode: ControlMode
    power_consumption: float
    temperature: float
    humidity: float
    current_time: datetime
    is_screen_locked: bool = False


class LandingViewModel:
    """대기화면 뷰모델"""
    
    def __init__(
        self,
        sensor_service: SensorDataService,
        system_state_service: SystemStateService
    ):
        self.sensor_service = sensor_service
        self.system_state_service = system_state_service
        self._state: Optional[LandingViewState] = None
    
    def get_state(self) -> LandingViewState:
        """현재 상태 조회"""
        try:
            # 센서 데이터 조회
            sensor_data = self.sensor_service.get_current_sensor_data()
            
            # 시스템 상태 조회
            current_mode = self.system_state_service.get_current_mode()
            
            self._state = LandingViewState(
                current_mode=current_mode,
                power_consumption=sensor_data.power_consumption,
                temperature=sensor_data.temperature,
                humidity=sensor_data.humidity,
                current_time=datetime.now(),
                is_screen_locked=False
            )
            
            return self._state
            
        except Exception as e:
            # 오류 발생시 기본값 반환
            return LandingViewState(
                current_mode=ControlMode.MANUAL,
                power_consumption=0.0,
                temperature=0.0,
                humidity=0.0,
                current_time=datetime.now(),
                is_screen_locked=False
            )
    
    def handle_screen_touch(self) -> str:
        """화면 터치 처리"""
        current_mode = self.system_state_service.get_current_mode()
        
        # 상호작용 시간 업데이트
        self.system_state_service.update_last_interaction()
        
        if current_mode == ControlMode.MANUAL:
            # Manual 모드: 메인 화면(그룹제어)으로 전환
            return "main_group"
        else:
            # Auto 모드: 설정 > 모드 전환 페이지로 전환
            return "settings_mode"
    
    def handle_long_touch(self) -> str:
        """긴 터치 처리 (Auto 모드에서 Manual로 전환)"""
        current_mode = self.system_state_service.get_current_mode()
        
        if current_mode == ControlMode.AUTO:
            # Auto에서 Manual로 전환
            self.system_state_service.set_mode(ControlMode.MANUAL)
            self.system_state_service.update_last_interaction()
            return "main_group"
        
        return "landing_manual"
    
    def should_show_standby(self) -> bool:
        """대기화면 표시 여부 확인"""
        return self.system_state_service.should_show_standby()
    
    def get_formatted_time(self) -> str:
        """포맷된 시간 반환"""
        if self._state:
            return self._state.current_time.strftime("%H:%M")
        return datetime.now().strftime("%H:%M")
    
    def get_formatted_date(self) -> str:
        """포맷된 날짜 반환"""
        if self._state:
            return self._state.current_time.strftime("%Y년 %m월 %d일")
        return datetime.now().strftime("%Y년 %m월 %d일")
    
    def get_power_display(self) -> str:
        """소비전력 표시 문자열"""
        if self._state:
            return f"{self._state.power_consumption:.1f}W"
        return "0.0W"
    
    def get_temperature_display(self) -> str:
        """온도 표시 문자열"""
        if self._state:
            return f"{self._state.temperature:.1f}°C"
        return "0.0°C"
    
    def get_humidity_display(self) -> str:
        """습도 표시 문자열"""
        if self._state:
            return f"{self._state.humidity:.1f}%"
        return "0.0%"
    
    def is_auto_mode(self) -> bool:
        """자동 모드 여부 확인"""
        if self._state:
            return self._state.current_mode == ControlMode.AUTO
        return False
    
    def is_manual_mode(self) -> bool:
        """수동 모드 여부 확인"""
        if self._state:
            return self._state.current_mode == ControlMode.MANUAL
        return True
