from typing import List, Optional
from dataclasses import dataclass
from domain.models import Light, LightGroup, ControlMode
from app.services import LightControlService, SystemStateService
from app.gateways import LightRepository, LightGroupRepository


@dataclass
class PersonalControlViewState:
    """개별 제어 화면 상태"""
    lights: List[Light]
    groups: List[LightGroup]
    selected_light_id: Optional[str] = None
    current_brightness: int = 0
    is_auto_mode: bool = False
    error_message: Optional[str] = None
    success_message: Optional[str] = None


class PersonalViewModel:
    """개별 조명 제어 뷰모델"""
    
    def __init__(
        self,
        light_control_service: LightControlService,
        light_repo: LightRepository,
        light_group_repo: LightGroupRepository,
        system_state_service: SystemStateService
    ):
        self.light_control_service = light_control_service
        self.light_repo = light_repo
        self.light_group_repo = light_group_repo
        self.system_state_service = system_state_service
        self._state = PersonalControlViewState(lights=[], groups=[])
    
    def get_state(self) -> PersonalControlViewState:
        """현재 상태 조회"""
        try:
            # 모든 조명 조회
            lights = self.light_repo.get_all_lights()
            
            # 모든 그룹 조회 (그룹별 조명 표시를 위해)
            groups = self.light_group_repo.get_all_groups()
            
            # 시스템 모드 확인
            current_mode = self.system_state_service.get_current_mode()
            is_auto_mode = (current_mode == ControlMode.AUTO)
            
            # 선택된 조명의 현재 밝기 설정
            current_brightness = 0
            if self._state.selected_light_id:
                for light in lights:
                    if light.id == self._state.selected_light_id:
                        current_brightness = light.brightness
                        break
            
            self._state = PersonalControlViewState(
                lights=lights,
                groups=groups,
                selected_light_id=self._state.selected_light_id,
                current_brightness=current_brightness,
                is_auto_mode=is_auto_mode,
                error_message=self._state.error_message,
                success_message=self._state.success_message
            )
            
            return self._state
            
        except Exception as e:
            self._state.error_message = f"조명 정보 조회 중 오류가 발생했습니다: {str(e)}"
            return self._state
    
    def select_light(self, light_id: str) -> None:
        """조명 선택"""
        self._state.selected_light_id = light_id
        self._state.error_message = None
        self._state.success_message = None
        
        # 선택된 조명의 현재 밝기로 설정
        for light in self._state.lights:
            if light.id == light_id:
                self._state.current_brightness = light.brightness
                break
        
        # 상호작용 시간 업데이트
        self.system_state_service.update_last_interaction()
    
    def adjust_brightness(self, brightness: int) -> None:
        """밝기 조정"""
        if not self._state.selected_light_id:
            self._state.error_message = "조명을 먼저 선택해주세요"
            return
        
        if self._state.is_auto_mode:
            self._state.error_message = "자동 모드에서는 조작할 수 없습니다"
            return
        
        # 밝기 범위 확인
        brightness = max(0, min(100, brightness))
        
        try:
            # 조명 밝기 조정
            self.light_control_service.set_brightness(self._state.selected_light_id, brightness)
            
            # 상태 업데이트
            self._state.current_brightness = brightness
            
            # 조명 정보 업데이트
            for light in self._state.lights:
                if light.id == self._state.selected_light_id:
                    light.brightness = brightness
                    light.is_on = brightness > 0
                    break
            
            # 그룹 정보도 업데이트
            for group in self._state.groups:
                for light in group.lights:
                    if light.id == self._state.selected_light_id:
                        light.brightness = brightness
                        light.is_on = brightness > 0
                        
                        # 그룹의 평균 밝기 계산
                        total_brightness = sum(l.brightness for l in group.lights)
                        group.brightness = total_brightness // len(group.lights)
                        group.is_on = any(l.is_on for l in group.lights)
                        break
            
            self._state.success_message = "조명 밝기가 성공적으로 조정되었습니다"
            self._state.error_message = None
            
            # 상호작용 시간 업데이트
            self.system_state_service.update_last_interaction()
            
        except Exception as e:
            self._state.error_message = f"밝기 조정 중 오류가 발생했습니다: {str(e)}"
            self._state.success_message = None
    
    def increase_brightness(self, step: int = 10) -> None:
        """밝기 증가"""
        new_brightness = self._state.current_brightness + step
        self.adjust_brightness(new_brightness)
    
    def decrease_brightness(self, step: int = 10) -> None:
        """밝기 감소"""
        new_brightness = self._state.current_brightness - step
        self.adjust_brightness(new_brightness)
    
    def turn_on_light(self) -> None:
        """조명 켜기 (100% 밝기)"""
        self.adjust_brightness(100)
    
    def turn_off_light(self) -> None:
        """조명 끄기 (0% 밝기)"""
        self.adjust_brightness(0)
    
    def get_selected_light(self) -> Optional[Light]:
        """선택된 조명 정보 반환"""
        if not self._state.selected_light_id:
            return None
        
        for light in self._state.lights:
            if light.id == self._state.selected_light_id:
                return light
        return None
    
    def get_lights_by_group(self, group_id: str) -> List[Light]:
        """그룹별 조명 목록 반환"""
        for group in self._state.groups:
            if group.id == group_id:
                return group.lights
        return []
    
    def get_light_status_display(self, light: Light) -> str:
        """조명 상태 표시 문자열"""
        if light.is_on:
            return f"켜짐 ({light.brightness}%)"
        else:
            return "꺼짐"
    
    def is_light_selected(self, light_id: str) -> bool:
        """조명 선택 여부 확인"""
        return self._state.selected_light_id == light_id
    
    def can_control(self) -> bool:
        """조작 가능 여부 확인 (Manual 모드에서만 가능)"""
        return not self._state.is_auto_mode
    
    def get_group_name(self, light: Light) -> str:
        """조명이 속한 그룹 이름 반환"""
        if not light.group_id:
            return "미분류"
        
        for group in self._state.groups:
            if group.id == light.group_id:
                return group.name
        return "미분류"
    
    def clear_messages(self) -> None:
        """메시지 초기화"""
        self._state.error_message = None
        self._state.success_message = None
    
    def navigate_to_group_control(self) -> str:
        """그룹 제어 화면으로 이동"""
        self.system_state_service.update_last_interaction()
        return "main_group"
    
    def navigate_to_settings(self) -> str:
        """설정 화면으로 이동"""
        self.system_state_service.update_last_interaction()
        return "main_settings"
    
    def apply_preset_brightness(self, preset_brightness: int) -> None:
        """프리셋 밝기 적용"""
        self.adjust_brightness(preset_brightness)
    
    def toggle_light(self) -> None:
        """조명 켜기/끄기 토글"""
        if not self._state.selected_light_id:
            self._state.error_message = "조명을 먼저 선택해주세요"
            return
        
        selected_light = self.get_selected_light()
        if selected_light:
            if selected_light.is_on:
                self.turn_off_light()
            else:
                self.turn_on_light()
