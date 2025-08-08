from typing import List, Dict, Optional
from datetime import datetime
from domain.models import (
    Light, LightGroup, Macro, Schedule, DeviceInfo, 
    SensorData, SystemState, ControlMode
)


class LightControlService:
    """조명 제어 서비스"""
    
    def __init__(self, light_controller):
        self.light_controller = light_controller
    
    def set_brightness(self, light_id: str, brightness: int) -> None:
        """조명 밝기 설정"""
        self.light_controller.set_brightness(light_id, brightness)
    
    def turn_on(self, light_id: str) -> None:
        """조명 켜기"""
        self.light_controller.turn_on(light_id)
    
    def turn_off(self, light_id: str) -> None:
        """조명 끄기"""
        self.light_controller.turn_off(light_id)
    
    def apply_macro(self, macro: Macro) -> None:
        """매크로 적용"""
        for light_id, brightness in macro.light_settings.items():
            self.set_brightness(light_id, brightness)


class ScheduleService:
    """스케줄 서비스"""
    
    def __init__(self, schedule_repo, macro_repo, light_control_service):
        self.schedule_repo = schedule_repo
        self.macro_repo = macro_repo
        self.light_control_service = light_control_service
    
    def execute_scheduled_tasks(self) -> None:
        """스케줄된 작업 실행"""
        now = datetime.now()
        current_weekday = now.weekday() + 1  # 월요일이 1
        current_time = now.time()
        
        schedules = self.schedule_repo.get_all_schedules()
        
        for schedule in schedules:
            if not schedule.is_enabled:
                continue
                
            # 현재 요일이 스케줄에 포함되는지 확인
            if current_weekday not in [wd.value for wd in schedule.weekdays]:
                continue
            
            # 켜는 시간 확인 (1분 오차 허용)
            if self._is_time_match(current_time, schedule.on_time):
                if schedule.macro_id:
                    macro = self.macro_repo.get_macro(schedule.macro_id)
                    self.light_control_service.apply_macro(macro)
            
            # 끄는 시간 확인 (1분 오차 허용)
            elif self._is_time_match(current_time, schedule.off_time):
                # 모든 조명 끄기
                # TODO: 여기서는 임시로 0으로 설정, 실제로는 모든 조명 목록을 가져와야 함
                pass
    
    def _is_time_match(self, current_time, target_time) -> bool:
        """시간 매칭 확인 (1분 오차 허용)"""
        current_minutes = current_time.hour * 60 + current_time.minute
        target_minutes = target_time.hour * 60 + target_time.minute
        return abs(current_minutes - target_minutes) <= 1


class SystemStateService:
    """시스템 상태 서비스"""
    
    def __init__(self, system_state_repo):
        self.system_state_repo = system_state_repo
    
    def get_current_mode(self) -> ControlMode:
        """현재 모드 가져오기"""
        return self.system_state_repo.get_current_mode()
    
    def set_mode(self, mode: ControlMode) -> None:
        """모드 설정"""
        self.system_state_repo.set_mode(mode)
    
    def update_last_interaction(self) -> None:
        """마지막 상호작용 시간 업데이트"""
        self.system_state_repo.update_last_interaction(datetime.now())
    
    def should_show_standby(self) -> bool:
        """대기화면 표시 여부 확인"""
        state = self.system_state_repo.get_system_state()
        return state.is_auto_standby_timeout()


class SensorDataService:
    """센서 데이터 서비스"""
    
    def __init__(self, sensor_gateway):
        self.sensor_gateway = sensor_gateway
    
    def get_current_sensor_data(self) -> SensorData:
        """현재 센서 데이터 가져오기"""
        return self.sensor_gateway.read_sensor_data()
    
    def get_power_consumption(self) -> float:
        """소비전력 가져오기"""
        sensor_data = self.get_current_sensor_data()
        return sensor_data.power_consumption
    
    def get_temperature(self) -> float:
        """온도 가져오기"""
        sensor_data = self.get_current_sensor_data()
        return sensor_data.temperature
    
    def get_humidity(self) -> float:
        """습도 가져오기"""
        sensor_data = self.get_current_sensor_data()
        return sensor_data.humidity


class DeviceInfoService:
    """장치 정보 서비스"""
    
    def __init__(self, device_info_repo):
        self.device_info_repo = device_info_repo
    
    def get_device_info(self) -> DeviceInfo:
        """장치 정보 가져오기"""
        return self.device_info_repo.get_device_info()
    
    def update_ip_address(self, ip_address: str) -> None:
        """IP 주소 업데이트"""
        from domain.rules import DeviceRules
        DeviceRules.validate_ip_address(ip_address)
        self.device_info_repo.update_ip_address(ip_address)
