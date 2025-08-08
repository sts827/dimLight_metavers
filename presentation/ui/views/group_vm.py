from typing import List, Optional, Dict
from dataclasses import dataclass
from domain.models import LightGroup, Light, ControlMode
from app.usecases.dim_group import DimGroupUseCase, DimGroupRequest
from app.services import SystemStateService
from app.gateways import LightGroupRepository


@dataclass
class GroupControlViewState:
    """그룹 제어 화면 상태"""
    groups: List[LightGroup]
    selected_group_id: Optional[str] = None
    current_brightness: int = 0
    is_auto_mode: bool = False
    error_message: Optional[str] = None
    success_message: Optional[str] = None


class GroupViewModel:
    """그룹 제어 뷰모델"""
    
    def __init__(
        self,
        dim_group_usecase: DimGroupUseCase,
        light_group_repo: LightGroupRepository,
        system_state_service: SystemStateService
    ):
        self.dim_group_usecase = dim_group_usecase
        self.light_group_repo = light_group_repo
        self.system_state_service = system_state_service
        self._state = GroupControlViewState(groups=[])
    
    def get_state(self) -> GroupControlViewState:
        """현재 상태 조회"""
        try:
            # 모든 그룹 조회
            groups = self.light_group_repo.get_all_groups()
            
            # 시스템 모드 확인
            current_mode = self.system_state_service.get_current_mode()
            is_auto_mode = (current_mode == ControlMode.AUTO)
            
            # 선택된 그룹의 현재 밝기 설정
            current_brightness = 0
            if self._state.selected_group_id:
                for group in groups:
                    if group.id == self._state.selected_group_id:
                        current_brightness = group.brightness
                        break
            
            self._state = GroupControlViewState(
                groups=groups,
                selected_group_id=self._state.selected_group_id,
                current_brightness=current_brightness,
                is_auto_mode=is_auto_mode,
                error_message=self._state.error_message,
                success_message=self._state.success_message
            )
            
            return self._state
            
        except Exception as e:
            self._state.error_message = f"그룹 정보 조회 중 오류가 발생했습니다: {str(e)}"
            return self._state
    
    def select_group(self, group_id: str) -> None:
        """그룹 선택"""
        self._state.selected_group_id = group_id
        self._state.error_message = None
        self._state.success_message = None
        
        # 선택된 그룹의 현재 밝기로 설정
        for group in self._state.groups:
            if group.id == group_id:
                self._state.current_brightness = group.brightness
                break
        
        # 상호작용 시간 업데이트
        self.system_state_service.update_last_interaction()
    
    def adjust_brightness(self, brightness: int) -> None:
        """밝기 조정"""
        if not self._state.selected_group_id:
            self._state.error_message = "그룹을 먼저 선택해주세요"
            return
        
        # 밝기 범위 확인
        brightness = max(0, min(100, brightness))
        
        try:
            # 그룹 디밍 실행
            request = DimGroupRequest(
                group_id=self._state.selected_group_id,
                brightness=brightness
            )
            
            response = self.dim_group_usecase.execute(request)
            
            if response.success:
                self._state.current_brightness = brightness
                self._state.success_message = response.message
                self._state.error_message = None
                
                # 그룹 정보 업데이트
                for i, group in enumerate(self._state.groups):
                    if group.id == self._state.selected_group_id:
                        self._state.groups[i] = response.group
                        break
            else:
                self._state.error_message = response.message
                self._state.success_message = None
            
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
    
    def turn_on_group(self) -> None:
        """그룹 켜기 (100% 밝기)"""
        self.adjust_brightness(100)
    
    def turn_off_group(self) -> None:
        """그룹 끄기 (0% 밝기)"""
        self.adjust_brightness(0)
    
    def get_selected_group(self) -> Optional[LightGroup]:
        """선택된 그룹 정보 반환"""
        if not self._state.selected_group_id:
            return None
        
        for group in self._state.groups:
            if group.id == self._state.selected_group_id:
                return group
        return None
    
    def get_group_status_display(self, group: LightGroup) -> str:
        """그룹 상태 표시 문자열"""
        if group.is_on:
            return f"켜짐 ({group.brightness}%)"
        else:
            return "꺼짐"
    
    def is_group_selected(self, group_id: str) -> bool:
        """그룹 선택 여부 확인"""
        return self._state.selected_group_id == group_id
    
    def can_control(self) -> bool:
        """조작 가능 여부 확인 (Manual 모드에서만 가능)"""
        return not self._state.is_auto_mode
    
    def clear_messages(self) -> None:
        """메시지 초기화"""
        self._state.error_message = None
        self._state.success_message = None
    
    def navigate_to_personal_control(self) -> str:
        """개별 제어 화면으로 이동"""
        self.system_state_service.update_last_interaction()
        return "main_personal"
    
    def navigate_to_settings(self) -> str:
        """설정 화면으로 이동"""
        self.system_state_service.update_last_interaction()
        return "main_settings"
