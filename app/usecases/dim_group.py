from typing import Protocol, List
from dataclasses import dataclass
from domain.models import LightGroup, Light, ControlMode
from domain.rules import LightControlRules
from domain.exceptions import AutoModeOperationException


class LightGroupRepository(Protocol):
    """조명 그룹 저장소 인터페이스"""
    def get_group(self, group_id: str) -> LightGroup:
        ...
    
    def save_group(self, group: LightGroup) -> None:
        ...
    
    def get_all_groups(self) -> List[LightGroup]:
        ...


class LightController(Protocol):
    """조명 제어 인터페이스"""
    def set_brightness(self, light_id: str, brightness: int) -> None:
        ...
    
    def turn_on(self, light_id: str) -> None:
        ...
    
    def turn_off(self, light_id: str) -> None:
        ...


class SystemStateRepository(Protocol):
    """시스템 상태 저장소 인터페이스"""
    def get_current_mode(self) -> ControlMode:
        ...


@dataclass
class DimGroupRequest:
    """그룹 디밍 요청"""
    group_id: str
    brightness: int


@dataclass
class DimGroupResponse:
    """그룹 디밍 응답"""
    success: bool
    message: str
    group: LightGroup


class DimGroupUseCase:
    """그룹 조명 디밍 유스케이스"""
    
    def __init__(
        self,
        light_group_repo: LightGroupRepository,
        light_controller: LightController,
        system_state_repo: SystemStateRepository
    ):
        self.light_group_repo = light_group_repo
        self.light_controller = light_controller
        self.system_state_repo = system_state_repo
    
    def execute(self, request: DimGroupRequest) -> DimGroupResponse:
        """그룹 디밍 실행"""
        try:
            # 자동 모드에서 조작 시도 검증
            current_mode = self.system_state_repo.get_current_mode()
            LightControlRules.validate_auto_mode_operation(current_mode)
            
            # 밝기 값 검증
            LightControlRules.validate_brightness(request.brightness)
            
            # 그룹 정보 조회
            group = self.light_group_repo.get_group(request.group_id)
            
            # 그룹 내 모든 조명의 밝기 조정
            for light in group.lights:
                self.light_controller.set_brightness(light.id, request.brightness)
                light.brightness = request.brightness
                light.is_on = request.brightness > 0
            
            # 그룹 밝기 업데이트
            group.brightness = request.brightness
            group.is_on = request.brightness > 0
            
            # 저장
            self.light_group_repo.save_group(group)
            
            return DimGroupResponse(
                success=True,
                message="그룹 밝기가 성공적으로 조정되었습니다",
                group=group
            )
            
        except AutoModeOperationException as e:
            return DimGroupResponse(
                success=False,
                message=str(e),
                group=group
            )
        except Exception as e:
            return DimGroupResponse(
                success=False,
                message=f"그룹 밝기 조정 중 오류가 발생했습니다: {str(e)}",
                group=None
            )
