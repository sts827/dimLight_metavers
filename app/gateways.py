from typing import Protocol, List, Dict, Optional
from domain.models import (
    Light, LightGroup, Macro, Schedule, DeviceInfo, 
    SensorData, SystemState, ControlMode
)


class SensorGateway(Protocol):
    """센서 게이트웨이 인터페이스"""
    
    def read_sensor_data(self) -> SensorData:
        """센서 데이터 읽기"""
        ...
    
    def read_temperature(self) -> float:
        """온도 읽기"""
        ...
    
    def read_humidity(self) -> float:
        """습도 읽기"""
        ...
    
    def read_power_consumption(self) -> float:
        """소비전력 읽기"""
        ...


class LightControllerGateway(Protocol):
    """조명 제어 게이트웨이 인터페이스"""
    
    def set_brightness(self, light_id: str, brightness: int) -> None:
        """조명 밝기 설정"""
        ...
    
    def turn_on(self, light_id: str) -> None:
        """조명 켜기"""
        ...
    
    def turn_off(self, light_id: str) -> None:
        """조명 끄기"""
        ...
    
    def get_light_status(self, light_id: str) -> Dict:
        """조명 상태 조회"""
        ...


class LightRepository(Protocol):
    """조명 저장소 인터페이스"""
    
    def save_light(self, light: Light) -> None:
        ...
    
    def get_light(self, light_id: str) -> Light:
        ...
    
    def get_all_lights(self) -> List[Light]:
        ...
    
    def delete_light(self, light_id: str) -> None:
        ...


class LightGroupRepository(Protocol):
    """조명 그룹 저장소 인터페이스"""
    
    def save_group(self, group: LightGroup) -> None:
        ...
    
    def get_group(self, group_id: str) -> LightGroup:
        ...
    
    def get_all_groups(self) -> List[LightGroup]:
        ...
    
    def delete_group(self, group_id: str) -> None:
        ...


class MacroRepository(Protocol):
    """매크로 저장소 인터페이스"""
    
    def save_macro(self, macro: Macro) -> None:
        ...
    
    def get_macro(self, macro_id: str) -> Macro:
        ...
    
    def get_all_macros(self) -> List[Macro]:
        ...
    
    def delete_macro(self, macro_id: str) -> None:
        ...


class ScheduleRepository(Protocol):
    """스케줄 저장소 인터페이스"""
    
    def save_schedule(self, schedule: Schedule) -> None:
        ...
    
    def get_schedule(self, schedule_id: str) -> Schedule:
        ...
    
    def get_all_schedules(self) -> List[Schedule]:
        ...
    
    def delete_schedule(self, schedule_id: str) -> None:
        ...


class DeviceInfoRepository(Protocol):
    """장치 정보 저장소 인터페이스"""
    
    def get_device_info(self) -> DeviceInfo:
        ...
    
    def update_ip_address(self, ip_address: str) -> None:
        ...


class SystemStateRepository(Protocol):
    """시스템 상태 저장소 인터페이스"""
    
    def get_system_state(self) -> SystemState:
        ...
    
    def get_current_mode(self) -> ControlMode:
        ...
    
    def set_mode(self, mode: ControlMode) -> None:
        ...
    
    def update_last_interaction(self, timestamp) -> None:
        ...
    
    def set_screen_lock(self, is_locked: bool) -> None:
        ...


class MQTTGateway(Protocol):
    """MQTT 게이트웨이 인터페이스"""
    
    def publish(self, topic: str, message: str) -> None:
        """메시지 발행"""
        ...
    
    def subscribe(self, topic: str, callback) -> None:
        """토픽 구독"""
        ...
    
    def connect(self) -> None:
        """MQTT 브로커 연결"""
        ...
    
    def disconnect(self) -> None:
        """MQTT 브로커 연결 해제"""
        ...


class BLEDALIGateway(Protocol):
    """BLE-DALI 게이트웨이 인터페이스"""
    
    def send_dali_command(self, device_address: str, command: str) -> None:
        """DALI 명령 전송"""
        ...
    
    def scan_devices(self) -> List[str]:
        """BLE 장치 스캔"""
        ...
    
    def connect_device(self, device_address: str) -> None:
        """BLE 장치 연결"""
        ...
    
    def disconnect_device(self, device_address: str) -> None:
        """BLE 장치 연결 해제"""
        ...


class GPIOGateway(Protocol):
    """GPIO 게이트웨이 인터페이스"""
    
    def set_pin_output(self, pin: int, value: bool) -> None:
        """GPIO 핀 출력 설정"""
        ...
    
    def read_pin_input(self, pin: int) -> bool:
        """GPIO 핀 입력 읽기"""
        ...
    
    def setup_pin(self, pin: int, mode: str) -> None:
        """GPIO 핀 모드 설정"""
        ...
    
    def cleanup(self) -> None:
        """GPIO 정리"""
        ...
