#!/bin/bash

# 스마트 스위치 디밍 웹 애플리케이션 시작 스크립트
# 사용법: ./start.sh [옵션]
# 옵션: 
#   --dev           : 개발 모드로 실행 (디버그 활성화)
#   --prod          : 프로덕션 모드로 실행
#   --daemon        : 백그라운드 데몬으로 실행
#   --kiosk         : 서버 실행 후 키오스크(브라우저) 실행
#   --browser <b>   : 브라우저 지정 (midori|chromium)

set -e  # 에러 발생시 스크립트 중단

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 프로젝트 디렉토리 설정
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$PROJECT_DIR/venv"
PID_FILE="$PROJECT_DIR/app.pid"
LOG_FILE="$PROJECT_DIR/app.log"
# 키오스크 보조 파일
KIOSK_PID_FILE="$PROJECT_DIR/kiosk.pid"
UNCLUTTER_PID_FILE="$PROJECT_DIR/.unclutter.pid"

echo -e "${BLUE} Smart Switch Dimming 애플리케이션 시작${NC}"
echo -e "${BLUE} 프로젝트 디렉토리: $PROJECT_DIR${NC}"

# 가상환경 확인 및 생성
if [ ! -d "$VENV_DIR" ]; then
    echo -e "${YELLOW}  가상환경이 없습니다. 생성 중...${NC}"
    python3 -m venv "$VENV_DIR"
fi

# 가상환경 활성화
echo -e "${BLUE}🔧 가상환경 활성화 중...${NC}"
source "$VENV_DIR/bin/activate"

# 의존성 설치 확인
if [ ! -f "$VENV_DIR/lib/python*/site-packages/flask" ]; then
    echo -e "${YELLOW} 필수 패키지 설치 중...${NC}"
    pip install --upgrade pip
    pip install Flask Flask-SocketIO python-socketio eventlet
fi

# 기존 프로세스 확인
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if ps -p "$OLD_PID" > /dev/null 2>&1; then
        echo -e "${YELLOW}  기존 프로세스 종료 중... (PID: $OLD_PID)${NC}"
        kill "$OLD_PID"
        sleep 2
    fi
    rm -f "$PID_FILE"
fi

# 실행 모드 설정
MODE="dev"
DAEMON=false
KIOSK=false
PREFERRED_BROWSER=""

for arg in "$@"; do
    case $arg in
        --dev)
            MODE="dev"
            ;;
        --prod)
            MODE="prod"
            ;;
        --daemon)
            DAEMON=true
            ;;
        --kiosk)
            KIOSK=true
            ;;
        --browser)
            PREFERRED_BROWSER="$2"
            shift
            ;;
        --help)
            echo "사용법: $0 [옵션]"
            echo "옵션:"
            echo "  --dev             개발 모드 (기본값)"
            echo "  --prod            프로덕션 모드"
            echo "  --daemon          백그라운드 실행"
            echo "  --kiosk           서버 실행 후 키오스크(브라우저) 실행"
            echo "  --browser <b>     브라우저 지정 (midori|chromium)"
            echo "  --help    도움말 표시"
            exit 0
            ;;
    esac
done

# 환경 변수 설정
export FLASK_APP="$PROJECT_DIR/presentation/api/main.py"
export PYTHONPATH="$PROJECT_DIR"

if [ "$MODE" = "dev" ]; then
    export FLASK_ENV=development
    export FLASK_DEBUG=1
    echo -e "${GREEN} 개발 모드로 실행${NC}"
else
    export FLASK_ENV=production
    export FLASK_DEBUG=0
    echo -e "${GREEN} 프로덕션 모드로 실행${NC}"
fi

echo -e "${BLUE} 서버 시작 중... (http://localhost:5000)${NC}"

# 작업 디렉토리를 프로젝트 루트로 이동 (상대 경로 이슈 방지)
cd "$PROJECT_DIR"

# 실행 (키오스크 모드일 경우 서버는 강제 데몬 실행)
if [ "$KIOSK" = true ]; then
    DAEMON=true
fi

if [ "$DAEMON" = true ]; then
    # 백그라운드 실행
    nohup python "$PROJECT_DIR/presentation/api/main.py" > "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    echo -e "${GREEN} 서버가 백그라운드에서 시작되었습니다!${NC}"
    echo -e "${BLUE} 로그 파일: $LOG_FILE${NC}"
    echo -e "${BLUE} 상태 확인: ./status.sh${NC}"
    echo -e "${BLUE} 서버 중지: ./stop.sh${NC}"
else
    # 포그라운드 실행
    echo -e "${GREEN} 서버가 시작되었습니다!${NC}"
    echo -e "${BLUE} 접속 URL: http://localhost:5000${NC}"
    echo -e "${BLUE} 네트워크 접속: http://$(hostname -I | cut -d' ' -f1):5000${NC}"
    echo -e "${YELLOW}  Ctrl+C로 서버를 종료할 수 있습니다${NC}"
    echo ""
    python "$PROJECT_DIR/presentation/api/main.py"
fi 

# ------------------------------
# 키오스크 모드: 디스플레이 준비 + 브라우저 실행
# ------------------------------
if [ "$KIOSK" = true ]; then
    echo -e "${BLUE} 키오스크 모드 준비 중...${NC}"

    # 서버 준비 대기
    for i in {1..30}; do
        if curl -s --max-time 1 http://127.0.0.1:5000 >/dev/null 2>&1; then
            echo -e "${GREEN} 서버 준비 완료${NC}"
            break
        fi
        sleep 1
        [ $i -eq 30 ] && { echo -e "${RED} 서버가 준비되지 않았습니다${NC}"; exit 1; }
    done

    # DISPLAY 설정 및 X 환경 점검
    export DISPLAY=${DISPLAY:-:0}
    if ! xset q >/dev/null 2>&1; then
        echo -e "${YELLOW} X11 디스플레이가 활성화되지 않았습니다. 데스크톱/VNC 세션을 확인하세요${NC}"
    else
        # 화면 절전 방지 및 커서 숨김
        xset s off; xset -dpms; xset s noblank || true
        if command -v unclutter >/dev/null 2>&1; then
            unclutter -idle 1 -root &
            echo $! > "$UNCLUTTER_PID_FILE"
        fi
    fi

    # 라즈베리파이 모델 확인
    IS_ZERO2W=false
    if [ -f /proc/device-tree/model ]; then
        MODEL=$(tr -d '\0' </proc/device-tree/model)
        [[ "$MODEL" == *"Zero 2"* ]] && IS_ZERO2W=true
    fi

    # 브라우저 선택
    BROWSER=""
    BROWSER_TYPE=""
    if [ -n "$PREFERRED_BROWSER" ]; then
        case "$PREFERRED_BROWSER" in
            midori)
                command -v midori >/dev/null 2>&1 && { BROWSER="midori"; BROWSER_TYPE="midori"; }
                ;;
            chromium)
                if command -v chromium-browser >/dev/null 2>&1; then BROWSER="chromium-browser"; BROWSER_TYPE="chromium"; fi
                if [ -z "$BROWSER" ] && command -v chromium >/dev/null 2>&1; then BROWSER="chromium"; BROWSER_TYPE="chromium"; fi
                ;;
        esac
    fi
    if [ -z "$BROWSER" ]; then
        if [ "$IS_ZERO2W" = true ] && command -v midori >/dev/null 2>&1; then
            BROWSER="midori"; BROWSER_TYPE="midori"
        elif command -v chromium-browser >/dev/null 2>&1; then
            BROWSER="chromium-browser"; BROWSER_TYPE="chromium"
        elif command -v chromium >/dev/null 2>&1; then
            BROWSER="chromium"; BROWSER_TYPE="chromium"
        elif command -v midori >/dev/null 2>&1; then
            BROWSER="midori"; BROWSER_TYPE="midori"
        fi
    fi
    if [ -z "$BROWSER" ]; then
        echo -e "${RED} 사용 가능한 브라우저를 찾지 못했습니다 (midori/chromium)${NC}"
        exit 1
    fi

    # 브라우저 플래그
    if [ "$BROWSER_TYPE" = "chromium" ]; then
        BROWSER_FLAGS=(
            "--kiosk" "--start-fullscreen" "--no-first-run" "--disable-infobars"
            "--user-data-dir=/tmp/kiosk-$(date +%s)" "--disable-logging" "--no-default-browser-check"
        )
        [ "$IS_ZERO2W" = true ] && BROWSER_FLAGS+=("--disable-gpu" "--window-size=800,480")
        "$BROWSER" "${BROWSER_FLAGS[@]}" http://127.0.0.1:5000 &
        echo $! > "$KIOSK_PID_FILE"
        echo -e "${GREEN} Chromium 키오스크가 시작되었습니다 (PID: $(cat "$KIOSK_PID_FILE"))${NC}"
    else
        "$BROWSER" -e Fullscreen http://127.0.0.1:5000 &
        echo $! > "$KIOSK_PID_FILE"
        echo -e "${GREEN} Midori 키오스크가 시작되었습니다 (PID: $(cat "$KIOSK_PID_FILE"))${NC}"
    fi
fi