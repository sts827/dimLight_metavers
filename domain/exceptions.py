class DomainException(Exception):
    """도메인 예외 기본 클래스"""
    pass


class LightControlException(DomainException):
    """조명 제어 관련 예외"""
    pass


class MacroException(DomainException):
    """매크로 관련 예외"""
    pass


class MacroLimitExceededException(MacroException):
    """매크로 개수 제한 초과 예외"""
    def __init__(self):
        super().__init__("매크로는 최대 3개까지만 생성할 수 있습니다")


class MacroNameLengthException(MacroException):
    """매크로 이름 길이 초과 예외"""
    def __init__(self):
        super().__init__("매크로 이름은 5글자 이하여야 합니다")


class ScheduleException(DomainException):
    """스케줄 관련 예외"""
    pass


class ScheduleTimeException(ScheduleException):
    """스케줄 시간 설정 예외"""
    def __init__(self):
        super().__init__("켜는 시간과 끄는 시간이 같을 수 없습니다")


class ScheduleWeekdayException(ScheduleException):
    """스케줄 요일 설정 예외"""
    def __init__(self):
        super().__init__("요일을 최소 하나는 선택해야 합니다")


class DeviceException(DomainException):
    """장치 관련 예외"""
    pass


class InvalidIPAddressException(DeviceException):
    """잘못된 IP 주소 예외"""
    def __init__(self):
        super().__init__("IP 주소를 다시 확인해주세요")


class AutoModeOperationException(DomainException):
    """자동 모드에서 조작 시도 예외"""
    def __init__(self):
        super().__init__("자동 모드에서는 조작할 수 없습니다")


class BrightnessRangeException(LightControlException):
    """밝기 범위 초과 예외"""
    def __init__(self):
        super().__init__("밝기는 0-100 사이의 값이어야 합니다")
