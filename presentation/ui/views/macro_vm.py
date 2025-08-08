from typing import List, Optional, Dict
from dataclasses import dataclass
from domain.models import Macro, LightGroup
from app.usecases.macro_save import SaveMacroUseCase, SaveMacroRequest
from app.services import SystemStateService
from app.gateways import MacroRepository, LightGroupRepository


@dataclass
class MacroViewState:
    """매크로 설정 화면 상태"""
    macros: List[Macro]
    selected_macro_id: Optional[str] = None
    macro_name: str = ""
    is_editing: bool = False
    show_confirmation: bool = False
    confirmation_message: str = ""
    error_message: Optional[str] = None
    success_message: Optional[str] = None
    is_keypad_visible: bool = False
    current_light_settings: Dict[str, int] = None
    
    def __post_init__(self):
        if self.current_light_settings is None:
            self.current_light_settings = {}


class MacroViewModel:
    """매크로 설정 뷰모델"""
    
    def __init__(
        self,
        save_macro_usecase: SaveMacroUseCase,
        macro_repo: MacroRepository,
        light_group_repo: LightGroupRepository,
        system_state_service: SystemStateService
    ):
        self.save_macro_usecase = save_macro_usecase
        self.macro_repo = macro_repo
        self.light_group_repo = light_group_repo
        self.system_state_service = system_state_service
        self._state = MacroViewState(macros=[])
    
    def get_state(self) -> MacroViewState:
        """현재 상태 조회"""
        try:
            # 모든 매크로 조회
            macros = self.macro_repo.get_all_macros()
            
            self._state.macros = macros
            
            return self._state
            
        except Exception as e:
            self._state.error_message = f"매크로 정보 조회 중 오류가 발생했습니다: {str(e)}"
            return self._state
    
    def load_current_light_settings(self) -> None:
        """현재 조명 설정값 로드"""
        try:
            # 모든 그룹의 현재 설정값을 가져와서 개별 조명별로 저장
            groups = self.light_group_repo.get_all_groups()
            current_settings = {}
            
            for group in groups:
                for light in group.lights:
                    current_settings[light.id] = light.brightness
            
            self._state.current_light_settings = current_settings
            
        except Exception as e:
            self._state.error_message = f"현재 조명 설정 로드 중 오류가 발생했습니다: {str(e)}"
    
    def select_macro(self, macro_id: str) -> None:
        """매크로 선택"""
        self._state.selected_macro_id = macro_id
        self._state.is_editing = True
        self._state.error_message = None
        self._state.success_message = None
        
        # 선택된 매크로 정보 로드
        for macro in self._state.macros:
            if macro.id == macro_id:
                self._state.macro_name = macro.name
                break
        
        # 상호작용 시간 업데이트
        self.system_state_service.update_last_interaction()
    
    def start_new_macro(self) -> None:
        """새 매크로 생성 시작"""
        if len(self._state.macros) >= 3:
            self._state.error_message = "매크로는 최대 3개까지만 생성할 수 있습니다"
            return
        
        self._state.selected_macro_id = None
        self._state.macro_name = ""
        self._state.is_editing = True
        self._state.error_message = None
        self._state.success_message = None
        self._state.show_confirmation = False
        
        # 현재 조명 설정값 로드
        self.load_current_light_settings()
        
        # 상호작용 시간 업데이트
        self.system_state_service.update_last_interaction()
    
    def save_macro(self) -> None:
        """매크로 저장"""
        if not self._state.macro_name.strip():
            self._state.error_message = "매크로 이름을 입력해주세요"
            return
        
        if not self._state.current_light_settings:
            self.load_current_light_settings()
        
        try:
            request = SaveMacroRequest(
                macro_id=self._state.selected_macro_id,
                name=self._state.macro_name,
                current_light_settings=self._state.current_light_settings
            )
            
            response = self.save_macro_usecase.execute(request)
            
            if response.success:
                if response.confirmation_required:
                    # 기존 매크로 변경시 확인창 표시
                    self._state.show_confirmation = True
                    self._state.confirmation_message = f"매크로이름({self._state.macro_name})설정을 변경하시겠습니까?"
                else:
                    # 새 매크로 생성
                    self._state.success_message = response.message
                    self._state.is_editing = False
                    self._state.macro_name = ""
                    self._state.selected_macro_id = None
                    # 매크로 목록 새로고침
                    self._state.macros = self.macro_repo.get_all_macros()
                
                self._state.error_message = None
            else:
                self._state.error_message = response.message
                self._state.success_message = None
            
            # 상호작용 시간 업데이트
            self.system_state_service.update_last_interaction()
            
        except Exception as e:
            self._state.error_message = f"매크로 저장 중 오류가 발생했습니다: {str(e)}"
            self._state.success_message = None
    
    def confirm_macro_change(self) -> None:
        """매크로 변경 확인"""
        try:
            if self._state.selected_macro_id:
                response = self.save_macro_usecase.confirm_macro_update(self._state.selected_macro_id)
                
                if response.success:
                    self._state.success_message = response.message
                    self._state.is_editing = False
                    self._state.show_confirmation = False
                    self._state.macro_name = ""
                    self._state.selected_macro_id = None
                    # 매크로 목록 새로고침
                    self._state.macros = self.macro_repo.get_all_macros()
                else:
                    self._state.error_message = response.message
                
                self._state.confirmation_message = ""
            
        except Exception as e:
            self._state.error_message = f"매크로 확인 중 오류가 발생했습니다: {str(e)}"
            self._state.show_confirmation = False
    
    def cancel_macro_change(self) -> None:
        """매크로 변경 취소"""
        self._state.show_confirmation = False
        self._state.confirmation_message = ""
        self._state.is_editing = False
        self._state.macro_name = ""
        self._state.selected_macro_id = None
    
    def show_name_keypad(self) -> None:
        """이름 변경 키패드 표시"""
        self._state.is_keypad_visible = True
        self.system_state_service.update_last_interaction()
    
    def hide_keypad(self) -> None:
        """키패드 숨기기"""
        self._state.is_keypad_visible = False
    
    def update_macro_name(self, name: str) -> None:
        """매크로 이름 업데이트 (5글자 제한)"""
        if len(name) <= 5:
            self._state.macro_name = name
        else:
            self._state.error_message = "매크로 이름은 5글자 이하여야 합니다"
    
    def can_save_macro(self) -> bool:
        """매크로 저장 가능 여부"""
        return (
            bool(self._state.macro_name.strip()) and
            bool(self._state.current_light_settings) and
            not self._state.show_confirmation
        )
    
    def get_macro_count(self) -> int:
        """현재 매크로 개수"""
        return len(self._state.macros)
    
    def can_create_new_macro(self) -> bool:
        """새 매크로 생성 가능 여부"""
        return self.get_macro_count() < 3
    
    def clear_messages(self) -> None:
        """메시지 초기화"""
        self._state.error_message = None
        self._state.success_message = None
    
    def cancel_editing(self) -> None:
        """편집 취소"""
        self._state.is_editing = False
        self._state.macro_name = ""
        self._state.selected_macro_id = None
        self._state.show_confirmation = False
        self._state.is_keypad_visible = False
        self.clear_messages()
