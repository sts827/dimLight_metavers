from typing import Protocol, List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime
from domain.models import Macro, LightGroup, Light
from domain.rules import MacroRules
from domain.exceptions import MacroLimitExceededException, MacroNameLengthException


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


class LightGroupRepository(Protocol):
    """조명 그룹 저장소 인터페이스"""
    def get_all_groups(self) -> List[LightGroup]:
        ...


@dataclass
class SaveMacroRequest:
    """매크로 저장 요청"""
    macro_id: Optional[str]  # None이면 새로 생성, 있으면 업데이트
    name: str
    current_light_settings: Dict[str, int]  # light_id: brightness


@dataclass
class SaveMacroResponse:
    """매크로 저장 응답"""
    success: bool
    message: str
    macro: Optional[Macro] = None
    confirmation_required: bool = False  # 기존 매크로 변경시 확인 필요


class SaveMacroUseCase:
    """매크로 저장 유스케이스"""
    
    def __init__(
        self,
        macro_repo: MacroRepository,
        light_group_repo: LightGroupRepository
    ):
        self.macro_repo = macro_repo
        self.light_group_repo = light_group_repo
    
    def execute(self, request: SaveMacroRequest) -> SaveMacroResponse:
        """매크로 저장 실행"""
        try:
            # 매크로 이름 검증
            MacroRules.validate_macro_name(request.name)
            
            if request.macro_id is None:
                # 새 매크로 생성
                return self._create_new_macro(request)
            else:
                # 기존 매크로 업데이트
                return self._update_existing_macro(request)
                
        except (MacroLimitExceededException, MacroNameLengthException) as e:
            return SaveMacroResponse(
                success=False,
                message=str(e)
            )
        except Exception as e:
            return SaveMacroResponse(
                success=False,
                message=f"매크로 저장 중 오류가 발생했습니다: {str(e)}"
            )
    
    def _create_new_macro(self, request: SaveMacroRequest) -> SaveMacroResponse:
        """새 매크로 생성"""
        # 매크로 개수 제한 확인
        existing_macros = self.macro_repo.get_all_macros()
        MacroRules.validate_macro_count(len(existing_macros))
        
        # 새 매크로 ID 생성
        macro_id = f"macro_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # 매크로 생성
        macro = Macro(
            id=macro_id,
            name=request.name,
            light_settings=request.current_light_settings.copy(),
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        # 저장
        self.macro_repo.save_macro(macro)
        
        return SaveMacroResponse(
            success=True,
            message="매크로가 성공적으로 저장되었습니다",
            macro=macro
        )
    
    def _update_existing_macro(self, request: SaveMacroRequest) -> SaveMacroResponse:
        """기존 매크로 업데이트"""
        # 기존 매크로 조회
        existing_macro = self.macro_repo.get_macro(request.macro_id)
        
        # 매크로 업데이트
        updated_macro = Macro(
            id=existing_macro.id,
            name=request.name,
            light_settings=request.current_light_settings.copy(),
            created_at=existing_macro.created_at,
            updated_at=datetime.now()
        )
        
        # 저장
        self.macro_repo.save_macro(updated_macro)
        
        return SaveMacroResponse(
            success=True,
            message="매크로가 성공적으로 변경되었습니다",
            macro=updated_macro,
            confirmation_required=True
        )
    
    def confirm_macro_update(self, macro_id: str) -> SaveMacroResponse:
        """매크로 업데이트 확인"""
        try:
            macro = self.macro_repo.get_macro(macro_id)
            return SaveMacroResponse(
                success=True,
                message="변경되었습니다",
                macro=macro
            )
        except Exception as e:
            return SaveMacroResponse(
                success=False,
                message=f"매크로 확인 중 오류가 발생했습니다: {str(e)}"
            )
