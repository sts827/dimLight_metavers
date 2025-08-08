from typing import Optional
from dataclasses import dataclass
from domain.models import ControlMode, DeviceInfo
from app.services import SystemStateService, DeviceInfoService
from domain.rules import DeviceRules


@dataclass
class SettingsViewState:
    """설정 화면 상태"""
    current_mode: ControlMode
    device_info: Optional[DeviceInfo] = None
    selected_menu: Optional[str] = None
    ip_address_input: str = ""
    is_keypad_visible: bool = False
    error_message: Optional[str] = None
    success_message: Optional[str] = None


class SettingsViewModel:
    """설정 화면 뷰모델"""
    
    def __init__(
        self,
        system_state_service: SystemStateService,
        device_info_service: DeviceInfoService
    ):
        self.system_state_service = system_state_service
        self.device_info_service = device_info_service
        self._state = SettingsViewState(current_mode=ControlMode.MANUAL)
    
    def get_state(self) -> SettingsViewState:
        """현재 상태 조회"""
        try:
            # 시스템 상태 조회
            current_mode = self.system_state_service.get_current_mode()
            
            # 장치 정보 조회
            device_info = self.device_info_service.get_device_info()
            
            self._state.current_mode = current_mode
            self._state.device_info = device_info
            self._state.ip_address_input = device_info.ip_address if device_info else ""
            
            return self._state
            
        except Exception as e:
            self._state.error_message = f"설정 정보 조회 중 오류가 발생했습니다: {str(e)}"
            return self._state
    
    def navigate_to_macro_settings(self) -> str:
        """매크로 설정으로 이동"""
        self._state.selected_menu = "macro"
        self.system_state_service.update_last_interaction()
        return "main_macro"
    
    def navigate_to_schedule_settings(self) -> str:
        """스케줄 설정으로 이동"""
        self._state.selected_menu = "schedule"
        self.system_state_service.update_last_interaction()
        return "main_schedule"
    
    def navigate_to_mode_settings(self) -> str:
        """모드 전환 설정으로 이동"""
        self._state.selected_menu = "mode"
        self.system_state_service.update_last_interaction()
        return "settings_mode"
    
    def navigate_to_device_info(self) -> str:
        """장치 정보 설정으로 이동"""
        self._state.selected_menu = "device"
        self.system_state_service.update_last_interaction()
        return "settings_device"
    
    def toggle_mode(self) -> None:
        """모드 전환 (Auto <-> Manual)"""
        try:
            current_mode = self._state.current_mode
            new_mode = ControlMode.MANUAL if current_mode == ControlMode.AUTO else ControlMode.AUTO
            
            self.system_state_service.set_mode(new_mode)
            self._state.current_mode = new_mode
            
            mode_name = "자동" if new_mode == ControlMode.AUTO else "수동"
            self._state.success_message = f"{mode_name} 모드로 전환되었습니다"
            self._state.error_message = None
            
            # 상호작용 시간 업데이트
            self.system_state_service.update_last_interaction()
            
        except Exception as e:
            self._state.error_message = f"모드 전환 중 오류가 발생했습니다: {str(e)}"
            self._state.success_message = None
    
    def select_auto_mode(self) -> None:
        """자동 모드 선택"""
        try:
            self.system_state_service.set_mode(ControlMode.AUTO)
            self._state.current_mode = ControlMode.AUTO
            self._state.success_message = "자동 모드로 전환되었습니다"
            self._state.error_message = None
            
            # 상호작용 시간 업데이트
            self.system_state_service.update_last_interaction()
            
        except Exception as e:
            self._state.error_message = f"자동 모드 전환 중 오류가 발생했습니다: {str(e)}"
            self._state.success_message = None
    
    def select_manual_mode(self) -> None:
        """수동 모드 선택"""
        try:
            self.system_state_service.set_mode(ControlMode.MANUAL)
            self._state.current_mode = ControlMode.MANUAL
            self._state.success_message = "수동 모드로 전환되었습니다"
            self._state.error_message = None
            
            # 상호작용 시간 업데이트
            self.system_state_service.update_last_interaction()
            
        except Exception as e:
            self._state.error_message = f"수동 모드 전환 중 오류가 발생했습니다: {str(e)}"
            self._state.success_message = None
    
    def show_ip_keypad(self) -> None:
        """IP 주소 입력 키패드 표시"""
        self._state.is_keypad_visible = True
        # 상호작용 시간 업데이트
        self.system_state_service.update_last_interaction()
    
    def hide_keypad(self) -> None:
        """키패드 숨기기"""
        self._state.is_keypad_visible = False
    
    def update_ip_address_input(self, ip_address: str) -> None:
        """IP 주소 입력 업데이트"""
        self._state.ip_address_input = ip_address
        self._state.error_message = None
        self._state.success_message = None
    
    def save_ip_address(self) -> None:
        """IP 주소 저장"""
        try:
            # IP 주소 형식 검증
            DeviceRules.validate_ip_address(self._state.ip_address_input)
            
            # IP 주소 업데이트
            self.device_info_service.update_ip_address(self._state.ip_address_input)
            
            # 장치 정보 새로고침
            self._state.device_info = self.device_info_service.get_device_info()
            
            self._state.success_message = "IP 주소가 성공적으로 저장되었습니다"
            self._state.error_message = None
            self._state.is_keypad_visible = False
            
            # 상호작용 시간 업데이트
            self.system_state_service.update_last_interaction()
            
        except Exception as e:
            self._state.error_message = str(e)
            self._state.success_message = None
    
    def is_auto_mode(self) -> bool:
        """자동 모드 여부"""
        return self._state.current_mode == ControlMode.AUTO
    
    def is_manual_mode(self) -> bool:
        """수동 모드 여부"""
        return self._state.current_mode == ControlMode.MANUAL
    
    def get_device_display_info(self) -> dict:
        """장치 정보 표시용 딕셔너리"""
        if self._state.device_info:
            return {
                "device_name": self._state.device_info.device_name,
                "version": self._state.device_info.version,
                "serial_number": self._state.device_info.serial_number,
                "manufacturer": self._state.device_info.manufacturer,
                "ip_address": self._state.device_info.ip_address
            }
        else:
            return {
                "device_name": "알 수 없음",
                "version": "알 수 없음",
                "serial_number": "알 수 없음",
                "manufacturer": "알 수 없음",
                "ip_address": "0.0.0.0"
            }
    
    def can_save_ip(self) -> bool:
        """IP 주소 저장 가능 여부"""
        try:
            DeviceRules.validate_ip_address(self._state.ip_address_input)
            return True
        except:
            return False
    
    def clear_messages(self) -> None:
        """메시지 초기화"""
        self._state.error_message = None
        self._state.success_message = None
    
    def navigate_back_to_main(self) -> str:
        """메인 화면으로 돌아가기"""
        self.system_state_service.update_last_interaction()
        
        if self._state.current_mode == ControlMode.AUTO:
            return "landing_auto"
        else:
            return "main_group"
