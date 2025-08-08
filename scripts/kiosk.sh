#!/bin/bash

# 단순 키오스크 모드 - 브라우저 WebUI 전체화면 실행
# 목적: 최적화된 브라우저로 F11 전체화면 WebUI 표출
# 사용법: ./simple_kiosk.sh [--browser midori|chromium] [--force-browser]

set -e

# 명령줄 인자 처리
FORCE_BROWSER=""
PREFERRED_BROWSER=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --browser)
            PREFERRED_BROWSER="$2"
            shift 2
            ;;
        --force-browser)
            FORCE_BROWSER="true"
            shift
            ;;
        -h|--help)
            echo "사용법: $0 [옵션]"
            echo "옵션:"
            echo "  --browser <midori|chromium>  사용할 브라우저 지정"
            echo "  --force-browser              Zero 2W가 아니어도 지정된 브라우저 사용"
            echo "  -h, --help                   이 도움말 표시"
            exit 0
            ;;
        *)
            echo "알 수 없는 옵션: $1"
            echo "사용법: $0 [--browser midori|chromium] [--force-browser] [-h|--help]"
            exit 1
            ;;
    esac
done

# 색상 정의
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

# 프로젝트 설정
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="$PROJECT_DIR/app.pid"
KIOSK_LOCK_FILE="$PROJECT_DIR/kiosk.lock"
LOG_DIR="$PROJECT_DIR/test/log"
LOG_FILE="$LOG_DIR/app.log"

# 로그 디렉토리 생성
mkdir -p "$LOG_DIR"

# 키오스크 중복 실행 방지
if [ -f "$KIOSK_LOCK_FILE" ]; then
    KIOSK_PID=$(cat "$KIOSK_LOCK_FILE" 2>/dev/null || echo "")
    if [ -n "$KIOSK_PID" ] && kill -0 "$KIOSK_PID" 2>/dev/null; then
        echo -e "${RED}❌ 키오스크가 이미 실행 중입니다 (PID: $KIOSK_PID)${NC}"
        echo -e "${YELLOW}💡 실행 중인 키오스크를 종료하려면: kill $KIOSK_PID${NC}"
        echo -e "${YELLOW}💡 또는 강제 정리하려면: rm $KIOSK_LOCK_FILE${NC}"
        exit 1
    else
        echo -e "${YELLOW}⚠️  이전 키오스크 락 파일을 정리합니다${NC}"
        rm -f "$KIOSK_LOCK_FILE"
    fi
fi

# 현재 키오스크 프로세스 락 파일 생성
echo $$ > "$KIOSK_LOCK_FILE"

# SSH 환경에서만 최소한의 터미널 설정
if [ -n "$SSH_CLIENT" ]; then
    echo "🔗 SSH 환경 감지됨"
fi

# 로그 파일명 생성 함수
generate_log_filename() {
    local prefix="$1"
    local timestamp=$(date +"%Y%m%d_%H%M%S")
    echo "$LOG_DIR/${prefix}_${timestamp}.log"
}

echo -e "${BLUE}🚀 스마트 스위치 디밍 - 단순 키오스크 모드${NC}"
echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}📅 시작 시간: $(date '+%Y-%m-%d %H:%M:%S')${NC}"
echo -e "${BLUE}📁 로그 디렉토리: $LOG_DIR${NC}"

# 환경 변수 설정 (SSH 환경 대응)
export FLASK_APP="$PROJECT_DIR/presentation/api/main.py"
export PYTHONPATH="$PROJECT_DIR"

# SSH 환경에서의 디스플레이 설정 (로컬 디스플레이 강제 사용)
if [ -n "$SSH_CLIENT" ]; then
    echo -e "${YELLOW}🔗 SSH 연결 감지 - 로컬 디스플레이로 강제 설정${NC}"
    export DISPLAY=:0
    echo -e "${BLUE}   SSH 클라이언트: $SSH_CLIENT${NC}"
    
    # SSH 환경에서 X11 접근 권한 설정
    echo -e "${YELLOW}🔑 SSH 환경에서 X11 접근 권한 설정 중...${NC}"
    sudo -u $(whoami) DISPLAY=:0 xhost +local: 2>/dev/null || {
        echo -e "${YELLOW}⚠️  xhost 권한 설정 시도 중...${NC}"
        DISPLAY=:0 xhost +local: 2>/dev/null || true
    }
else
    export DISPLAY=${DISPLAY:-:0}
fi
# 로케일은 브라우저별로 개별 설정

# X11 디스플레이 확인 및 설정
echo -e "${YELLOW}🖥️  디스플레이 설정 확인 중...${NC}"
if [ -z "$DISPLAY" ]; then
    echo -e "${RED}❌ DISPLAY 환경변수가 설정되지 않음${NC}"
    echo -e "${YELLOW}💡 현재 사용 가능한 디스플레이:${NC}"
    ls /tmp/.X11-unix/ 2>/dev/null || echo "   X11 소켓을 찾을 수 없음"
    
    # 디스플레이 자동 감지
    for display in :0 :1 :2; do
        if xset q -display $display >/dev/null 2>&1; then
            export DISPLAY=$display
            echo -e "${GREEN}✅ 디스플레이 감지됨: $DISPLAY${NC}"
            break
        fi
    done
    
    if [ -z "$DISPLAY" ]; then
        echo -e "${RED}❌ 사용 가능한 디스플레이를 찾을 수 없음${NC}"
        echo -e "${YELLOW}💡 해결 방법:${NC}"
        echo "   1. startx 또는 xinit 실행"
        echo "   2. VNC 서버 시작"
        echo "   3. 디스플레이 매니저 확인"
        exit 1
    fi
fi

# 화면 해상도 확인 및 설정
echo -e "${YELLOW}📐 화면 해상도 확인 중...${NC}"
if ! xrandr --current >/dev/null 2>&1; then
    echo -e "${RED}❌ xrandr 명령어 실행 실패${NC}"
    echo -e "${YELLOW}💡 X11 서버가 실행 중인지 확인하세요${NC}"
    exit 1
fi

# 시스템 사양 감지
detect_system_specs() {
    # RAM 크기 확인 (MB 단위)
    TOTAL_RAM=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)
    
    # CPU 코어 수 확인
    CPU_CORES=$(nproc)
    
    # 라즈베리파이 모델 감지 (강화된 로직)
    IS_ZERO2W=false
    PI_MODEL=""
    
    # 방법 1: /proc/device-tree/model 확인
    if [ -f /proc/device-tree/model ]; then
        PI_MODEL=$(cat /proc/device-tree/model 2>/dev/null | tr -d '\0' || echo "")
    fi
    
    # 방법 2: /proc/cpuinfo 확인 (fallback)
    if [ -z "$PI_MODEL" ]; then
        PI_MODEL=$(grep "Model" /proc/cpuinfo 2>/dev/null | cut -d: -f2 | sed 's/^ *//' || echo "")
    fi
    
    # Zero 2W 감지
    if [[ "$PI_MODEL" == *"Zero 2"* ]]; then
        IS_ZERO2W=true
        echo -e "${BLUE}🔍 Raspberry Pi Zero 2W 감지됨${NC}"
    elif [[ "$PI_MODEL" == *"Pi 4"* ]] || [[ "$PI_MODEL" == *"Model B"* ]]; then
        IS_ZERO2W=false
        echo -e "${BLUE}🔍 Raspberry Pi 4B+ 감지됨${NC}"
    else
        IS_ZERO2W=false
        echo -e "${YELLOW}⚠️  라즈베리파이 모델 감지 실패 - Pi 4B+ 모드로 실행${NC}"
    fi
    
    echo -e "${BLUE}📋 감지된 모델: $PI_MODEL${NC}"
    
    echo -e "${BLUE}💻 시스템 사양: RAM ${TOTAL_RAM}MB, CPU ${CPU_CORES}코어${NC}"
}

# 시스템 사양 감지
detect_system_specs

# 기본 해상도 설정 (Zero 2W + 800x480 LCD 최적화)
RESOLUTION=$(xrandr --current 2>/dev/null | grep '*' | awk '{print $1}' | head -1 | tr -d '\0')
if [ -n "$RESOLUTION" ] && [[ "$RESOLUTION" =~ ^[0-9]+x[0-9]+$ ]]; then
    echo -e "${GREEN}✅ 현재 해상도: $RESOLUTION${NC}"
    
    # Zero 2W + 800x480 LCD 패널 최적화
    if [ "$IS_ZERO2W" = true ]; then
        # 800x480 LCD 패널에 맞게 해상도 설정
        if [ "$RESOLUTION" != "800x480" ]; then
            echo -e "${YELLOW}🔧 Zero 2W + 800x480 LCD 패널에 맞게 해상도 조정${NC}"
            # 여러 출력 방식 시도
            xrandr --output HDMI-1 --mode 800x480 2>/dev/null || \
            xrandr --output HDMI-A-1 --mode 800x480 2>/dev/null || \
            xrandr --output DSI-1 --mode 800x480 2>/dev/null || \
            xrandr --output DPI-1 --mode 800x480 2>/dev/null || \
            echo -e "${YELLOW}⚠️  800x480 해상도 설정 실패 - 현재 해상도 유지${NC}"
        else
            echo -e "${GREEN}✅ 이미 800x480 해상도로 설정됨${NC}"
        fi
    fi
else
    echo -e "${YELLOW}⚠️  해상도를 감지할 수 없음 - 기본값 사용${NC}"
    # Zero 2W는 800x480, 기타는 1080p
    if [ "$IS_ZERO2W" = true ]; then
        echo -e "${YELLOW}🔧 Zero 2W 800x480 LCD 패널 해상도 설정 시도${NC}"
        xrandr --output HDMI-1 --mode 800x480 2>/dev/null || \
        xrandr --output HDMI-A-1 --mode 800x480 2>/dev/null || \
        xrandr --output DSI-1 --mode 800x480 2>/dev/null || \
        xrandr --output DPI-1 --mode 800x480 2>/dev/null || \
        echo -e "${YELLOW}⚠️  800x480 해상도 설정 실패 - 기본값 유지${NC}"
    else
        xrandr --output HDMI-1 --mode 1920x1080 2>/dev/null || \
        xrandr --output HDMI-1 --mode 1280x720 2>/dev/null || \
        echo -e "${YELLOW}⚠️  해상도 설정 실패 - 기본값 유지${NC}"
    fi
fi

# 마우스 커서 숨기기 함수
hide_cursor() {
    echo -e "${YELLOW}🖱️  마우스 커서 숨기는 중...${NC}"
    
    # unclutter 설치 확인
    if command -v unclutter >/dev/null 2>&1; then
        # unclutter로 마우스 커서 자동 숨김 (1초 후)
        unclutter -idle 1 -root &
        UNCLUTTER_PID=$!
        echo "unclutter PID: $UNCLUTTER_PID" > /tmp/unclutter.pid
        echo -e "${GREEN}✅ unclutter로 마우스 커서 숨김 활성화${NC}"
    else
        # unclutter가 없으면 xsetroot로 빈 커서 설정
        if command -v xsetroot >/dev/null 2>&1; then
            # 빈 커서 비트맵 생성
            echo -e "${YELLOW}📦 unclutter 설치 중...${NC}"
            sudo apt update >/dev/null 2>&1 && sudo apt install -y unclutter >/dev/null 2>&1
            
            if command -v unclutter >/dev/null 2>&1; then
                unclutter -idle 1 -root &
                UNCLUTTER_PID=$!
                echo "unclutter PID: $UNCLUTTER_PID" > /tmp/unclutter.pid
                echo -e "${GREEN}✅ unclutter 설치 및 마우스 커서 숨김 완료${NC}"
            else
                echo -e "${YELLOW}⚠️  unclutter 설치 실패 - 기본 방법 사용${NC}"
                xsetroot -cursor_name none 2>/dev/null || true
            fi
        fi
    fi
}

# 마우스 커서 복원 함수
show_cursor() {
    echo -e "${YELLOW}🖱️  마우스 커서 복원 중...${NC}"
    
    # unclutter 프로세스 종료
    if [ -f /tmp/unclutter.pid ]; then
        UNCLUTTER_PID=$(cat /tmp/unclutter.pid 2>/dev/null)
        if [ -n "$UNCLUTTER_PID" ] && kill -0 "$UNCLUTTER_PID" 2>/dev/null; then
            kill "$UNCLUTTER_PID" 2>/dev/null || true
        fi
        rm -f /tmp/unclutter.pid
    fi
    
    # 모든 unclutter 프로세스 종료
    pkill -f unclutter 2>/dev/null || true
    
    # 기본 커서로 복원
    xsetroot -cursor_name left_ptr 2>/dev/null || true
    
    echo -e "${GREEN}✅ 마우스 커서 복원 완료${NC}"
}

# 기존 프로세스 정리
echo -e "${YELLOW}🧹 기존 프로세스 정리 중...${NC}"
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE" 2>/dev/null || echo "")
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        echo "   기존 서버 종료 (PID: $OLD_PID)"
        kill "$OLD_PID" 2>/dev/null || true
        sleep 2
    fi
    rm -f "$PID_FILE"
fi

# 기존 브라우저 완전 정리 (강화된 로직)
echo -e "${YELLOW}🧹 모든 브라우저 프로세스 강제 정리 중...${NC}"

# 1단계: 모든 midori 프로세스 강제 종료
sudo pkill -9 midori 2>/dev/null || true
sudo pkill -9 -f "WebKitNetworkProcess" 2>/dev/null || true
sudo pkill -9 -f "WebKitWebProcess" 2>/dev/null || true

# 2단계: chromium 프로세스 정리
sudo pkill -f "chromium.*localhost:5000" 2>/dev/null || true
sudo pkill -f "chromium.*127.0.0.1:5000" 2>/dev/null || true

# 3단계: 완전 정리 대기
sleep 3

# 4단계: 남은 프로세스 확인 및 추가 정리
REMAINING=$(ps aux | grep -E "(midori|WebKit)" | grep -v grep | wc -l)
if [ "$REMAINING" -gt 0 ]; then
    echo -e "${RED}⚠️  $REMAINING 개의 브라우저 프로세스가 남아있음 - 추가 정리${NC}"
    sudo killall -9 midori 2>/dev/null || true
    sudo killall -9 WebKitNetworkProcess 2>/dev/null || true
    sleep 2
fi

echo -e "${GREEN}✅ 브라우저 프로세스 정리 완료${NC}"

# 시스템 요구사항 체크 및 최적화
check_system_requirements() {
    echo -e "${YELLOW}🔍 시스템 요구사항 체크 중...${NC}"
    
    # swap 설정 체크 및 자동 설정
    SWAP_SIZE=$(awk '/SwapTotal/ {print int($2/1024)}' /proc/meminfo)
    if [ "$TOTAL_RAM" -le 512 ] && [ "$SWAP_SIZE" -lt 100 ]; then
        echo -e "${YELLOW}⚠️  RAM ${TOTAL_RAM}MB 시스템에서 swap이 부족합니다 (현재: ${SWAP_SIZE}MB)${NC}"
        
        # swap 파일 생성 시도
        if [ ! -f /swapfile ] && [ -w /etc ]; then
            echo -e "${YELLOW}📝 100MB swap 파일 생성 시도 중...${NC}"
            if sudo fallocate -l 100M /swapfile 2>/dev/null && \
               sudo chmod 600 /swapfile && \
               sudo mkswap /swapfile >/dev/null 2>&1 && \
               sudo swapon /swapfile >/dev/null 2>&1; then
                echo -e "${GREEN}✅ 임시 swap 100MB 활성화 완료${NC}"
                # 재부팅 시에도 유지되도록 /etc/fstab에 추가 (선택사항)
                if ! grep -q "/swapfile" /etc/fstab 2>/dev/null; then
                    echo "/swapfile none swap sw 0 0" | sudo tee -a /etc/fstab >/dev/null
                fi
            else
                echo -e "${YELLOW}⚠️  swap 생성 실패 - 수동으로 설정하세요${NC}"
            fi
        fi
    else
        echo -e "${GREEN}✅ 메모리 설정 적절함 (RAM: ${TOTAL_RAM}MB, Swap: ${SWAP_SIZE}MB)${NC}"
    fi
    
    # GPU 메모리 체크 (Zero 2W 전용)
    if [ "$IS_ZERO2W" = true ]; then
        GPU_MEM=$(vcgencmd get_mem gpu 2>/dev/null | cut -d= -f2 | cut -dM -f1 || echo "64")
        if [ "$GPU_MEM" -lt 64 ]; then
            echo -e "${YELLOW}⚠️  GPU 메모리가 부족합니다 (${GPU_MEM}MB). 64MB 권장${NC}"
            echo -e "${BLUE}💡 /boot/config.txt에서 gpu_mem=64 설정하세요${NC}"
        else
            echo -e "${GREEN}✅ GPU 메모리 설정 적절함 (${GPU_MEM}MB)${NC}"
        fi
        
        # Zero 2W 전용 메모리 최적화
        echo -e "${YELLOW}🔧 Zero 2W 메모리 최적화 실행 중...${NC}"
        
        # 시스템 캐시 정리 (안전한 방법)
        sync
        echo 1 | sudo tee /proc/sys/vm/drop_caches >/dev/null 2>&1 || true
        
        # 사용되지 않는 프로세스 정리
        sudo systemctl stop cups 2>/dev/null || true
        sudo systemctl stop avahi-daemon 2>/dev/null || true
        sudo systemctl stop ModemManager 2>/dev/null || true
        
        # 메모리 상태 재확인
        CURRENT_FREE=$(awk '/MemAvailable/ {print int($2/1024)}' /proc/meminfo 2>/dev/null || echo "0")
        if [ "$CURRENT_FREE" -gt 0 ]; then
            echo -e "${GREEN}✅ 메모리 정리 완료 - 사용 가능: ${CURRENT_FREE}MB${NC}"
        fi
    fi
    
    # 필수 패키지 체크
    local missing_packages=()
    local recommended_packages=()
    
    if ! command -v python3 >/dev/null 2>&1; then
        missing_packages+=("python3")
    fi
    
    if ! command -v curl >/dev/null 2>&1; then
        missing_packages+=("curl")
    fi
    
    # X11 관련 패키지 체크
    if ! command -v xset >/dev/null 2>&1; then
        missing_packages+=("x11-xserver-utils")
    fi
    
    # Zero 2W에서 Midori 우선 권장 (경량 브라우저)
    if [ "$IS_ZERO2W" = true ]; then
        if ! command -v midori >/dev/null 2>&1; then
            recommended_packages+=("midori")
            echo -e "${YELLOW}💡 Zero 2W 저성능 환경을 위해 경량 Midori 브라우저 설치를 권장합니다${NC}"
        fi
        if ! command -v chromium-browser >/dev/null 2>&1 && ! command -v chromium >/dev/null 2>&1; then
            recommended_packages+=("chromium-browser")
            echo -e "${YELLOW}💡 대안으로 Chromium 브라우저도 설치 가능합니다 (더 무거움)${NC}"
        fi
    fi
    
    # 브라우저 체크 (하나라도 있으면 OK)
    if ! command -v chromium-browser >/dev/null 2>&1 && ! command -v chromium >/dev/null 2>&1 && ! command -v midori >/dev/null 2>&1; then
        if [ "$IS_ZERO2W" = true ]; then
            missing_packages+=("midori")
        else
            missing_packages+=("chromium-browser")
        fi
    fi
    
    if [ ${#missing_packages[@]} -gt 0 ]; then
        echo -e "${RED}❌ 필수 패키지가 누락되었습니다: ${missing_packages[*]}${NC}"
        echo -e "${YELLOW}💡 설치 명령: sudo apt update && sudo apt install ${missing_packages[*]}${NC}"
        exit 1
    fi
    
    if [ ${#recommended_packages[@]} -gt 0 ]; then
        echo -e "${YELLOW}💡 권장 패키지: ${recommended_packages[*]}${NC}"
        echo -e "${BLUE}   설치 명령: sudo apt update && sudo apt install ${recommended_packages[*]}${NC}"
    fi
}

# 시스템 요구사항 체크
check_system_requirements

# 가상환경 활성화
if [ -d "$PROJECT_DIR/venv" ]; then
    source "$PROJECT_DIR/venv/bin/activate"
    echo -e "${GREEN}✅ 가상환경 활성화${NC}"
fi

# 웹서버 시작
echo -e "${YELLOW}🌐 웹서버 시작 중...${NC}"
cd "$PROJECT_DIR"

# 기존 서버가 실행 중인지 확인 (중복 방지 강화)
EXISTING_SERVERS=$(pgrep -f "presentation/api/main.py" | wc -l)
if [ "$EXISTING_SERVERS" -gt 0 ]; then
    echo -e "${GREEN}✅ 웹서버가 이미 실행 중입니다 (${EXISTING_SERVERS}개 프로세스)${NC}"
    if [ "$EXISTING_SERVERS" -gt 1 ]; then
        echo -e "${YELLOW}⚠️  중복 프로세스 감지 - 기존 서버들을 정리합니다${NC}"
        pkill -f "presentation/api/main.py" 2>/dev/null || true
        sleep 2
        echo -e "${YELLOW}🔄 새로운 서버를 시작합니다${NC}"
    else
        SERVER_PID=$(pgrep -f "presentation/api/main.py" | head -1)
        if [ -n "$SERVER_PID" ] && curl -s http://127.0.0.1:5000 >/dev/null 2>&1; then
            echo $SERVER_PID > "$PID_FILE"
            echo -e "${GREEN}✅ 기존 서버 사용 (PID: $SERVER_PID)${NC}"
        else
            echo -e "${YELLOW}⚠️  프로세스는 있지만 응답하지 않음 - 재시작합니다${NC}"
            pkill -f "presentation/api/main.py" 2>/dev/null || true
            sleep 2
        fi
    fi
fi

# 서버가 정말 실행 중인지 최종 확인
if ! curl -s http://127.0.0.1:5000 >/dev/null 2>&1; then
    # 새 서버 시작 (가상환경 경로 명시)
    echo -e "${YELLOW}🚀 새로운 웹서버를 시작합니다${NC}"
    if [ -d "$PROJECT_DIR/venv" ]; then
        "$PROJECT_DIR/venv/bin/python" presentation/api/main.py > "$LOG_FILE" 2>&1 &
    else
        python3 presentation/api/main.py > "$LOG_FILE" 2>&1 &
    fi
    SERVER_PID=$!
    echo $SERVER_PID > "$PID_FILE"
    
    # 서버 시작 대기
    echo -e "${YELLOW}⏳ 서버 대기 중...${NC}"
    for i in {1..20}; do
        if curl -s http://127.0.0.1:5000 >/dev/null 2>&1; then
            echo -e "${GREEN}✅ 서버 준비 완료 (http://127.0.0.1:5000)${NC}"
            break
        fi
        echo -n "."
        sleep 1
        if [ $i -eq 20 ]; then
            echo -e "\n${RED}❌ 서버 시작 실패${NC}"
            echo -e "${YELLOW}📋 로그 확인:${NC}"
            tail -10 "$LOG_FILE" 2>/dev/null || echo "로그 파일을 찾을 수 없음"
            echo -e "${YELLOW}💡 수동으로 서버를 시작해보세요:${NC}"
            echo "   python3 presentation/api/main.py"
            exit 1
        fi
    done
fi

# 브라우저 감지 및 선택
detect_and_select_browser() {
    echo -e "${YELLOW}🔍 브라우저 감지 중...${NC}"
    
    # 명령줄에서 브라우저가 지정된 경우
    if [ -n "$PREFERRED_BROWSER" ]; then
        case "$PREFERRED_BROWSER" in
            midori)
                if command -v midori >/dev/null 2>&1; then
                    BROWSER="midori"
                    BROWSER_TYPE="midori"
                    echo -e "${GREEN}✅ 지정된 브라우저: Midori${NC}"
                    return 0
                else
                    echo -e "${RED}❌ 지정된 Midori 브라우저를 찾을 수 없습니다${NC}"
                    echo -e "${BLUE}   sudo apt update && sudo apt install midori${NC}"
                    exit 1
                fi
                ;;
            chromium)
                # Zero 2W에서 Chromium 강제 지정 시 경고
                if [ "$IS_ZERO2W" = true ]; then
                    echo -e "${RED}⚠️  Zero 2W 환경에서 Chromium은 성능 이슈가 있을 수 있습니다${NC}"
                    echo -e "${YELLOW}💡 권장: ./scripts/simple_kiosk.sh --browser midori${NC}"
                    echo -e "${BLUE}🔄 10초 후 계속 진행... (Ctrl+C로 중단)${NC}"
                    sleep 10
                fi
                
                if command -v chromium-browser >/dev/null 2>&1; then
                    BROWSER="chromium-browser"
                    BROWSER_TYPE="chromium"
                    echo -e "${GREEN}✅ 지정된 브라우저: Chromium${NC}"
                    return 0
                elif command -v chromium >/dev/null 2>&1; then
                    BROWSER="chromium"
                    BROWSER_TYPE="chromium"
                    echo -e "${GREEN}✅ 지정된 브라우저: Chromium${NC}"
                    return 0
                else
                    echo -e "${RED}❌ 지정된 Chromium 브라우저를 찾을 수 없습니다${NC}"
                    echo -e "${BLUE}   sudo apt update && sudo apt install chromium-browser${NC}"
                    exit 1
                fi
                ;;
            *)
                echo -e "${RED}❌ 지원되지 않는 브라우저: $PREFERRED_BROWSER${NC}"
                echo -e "${YELLOW}💡 지원되는 브라우저: midori, chromium${NC}"
                exit 1
                ;;
        esac
    fi
    
    # 자동 감지 모드 - 라즈베리파이 모델별 최적 브라우저 선택
    if [ "$IS_ZERO2W" = true ]; then
        # Zero 2W: 저성능을 위해 경량 Midori 우선 선택
        echo -e "${BLUE}🔍 Zero 2W 감지: 경량 브라우저 우선 선택${NC}"
        if command -v midori >/dev/null 2>&1; then
            BROWSER="midori"
            BROWSER_TYPE="midori"
            echo -e "${GREEN}✅ Zero 2W 최적화: Midori 브라우저 자동 선택${NC}"
            return 0
        elif command -v chromium-browser >/dev/null 2>&1; then
            BROWSER="chromium-browser"
            BROWSER_TYPE="chromium"
            echo -e "${YELLOW}⚠️  Midori 없음 - Chromium 사용 (성능 저하 가능)${NC}"
            return 0
        elif command -v chromium >/dev/null 2>&1; then
            BROWSER="chromium"
            BROWSER_TYPE="chromium"
            echo -e "${YELLOW}⚠️  Midori 없음 - Chromium 사용 (성능 저하 가능)${NC}"
            return 0
        fi
    else
        # Pi 4B/4B+: 고성능을 위해 Chromium 우선 선택
        echo -e "${BLUE}🔍 Pi 4B+ 감지: 고성능 브라우저 우선 선택${NC}"
        if command -v chromium-browser >/dev/null 2>&1; then
            BROWSER="chromium-browser"
            BROWSER_TYPE="chromium"
            echo -e "${GREEN}✅ Pi 4B+ 최적화: Chromium 브라우저 자동 선택${NC}"
            return 0
        elif command -v chromium >/dev/null 2>&1; then
            BROWSER="chromium"
            BROWSER_TYPE="chromium"
            echo -e "${GREEN}✅ Pi 4B+ 최적화: Chromium 브라우저 자동 선택${NC}"
            return 0
        elif command -v midori >/dev/null 2>&1; then
            BROWSER="midori"
            BROWSER_TYPE="midori"
            echo -e "${YELLOW}⚠️  Chromium 없음 - Midori 사용 (기능 제한 가능)${NC}"
            return 0
        fi
    fi
    
    # 여기까지 도달한 경우는 브라우저를 찾지 못한 상황
    
    # 브라우저가 없는 경우
    echo -e "${RED}❌ 지원되는 브라우저를 찾을 수 없습니다${NC}"
    if [ "$IS_ZERO2W" = true ]; then
        echo -e "${YELLOW}💡 Zero 2W용 권장 설치 (경량 브라우저):${NC}"
        echo -e "${BLUE}   sudo apt update && sudo apt install midori${NC}"
        echo -e "${YELLOW}💡 대안 설치 (더 무거움):${NC}"
        echo -e "${BLUE}   sudo apt update && sudo apt install chromium-browser${NC}"
    else
        echo -e "${YELLOW}💡 설치 명령:${NC}"
        echo -e "${BLUE}   sudo apt update && sudo apt install chromium-browser${NC}"
    fi
    exit 1
}

# 브라우저 감지 및 선택
detect_and_select_browser

# 마우스 커서 숨기기
hide_cursor

# 화면 절전 방지 설정
echo -e "${YELLOW}🔋 화면 절전 방지 설정 중...${NC}"
xset s off      # 스크린세이버 비활성화
xset -dpms      # DPMS(전력 관리) 비활성화  
xset s noblank  # 화면 블랭킹 비활성화
echo -e "${GREEN}✅ 화면이 자동으로 꺼지지 않도록 설정 완료${NC}"

# 브라우저별 플래그 생성
generate_browser_flags() {
    if [ "$BROWSER_TYPE" = "midori" ]; then
        generate_midori_flags
    else
        generate_chromium_flags
    fi
}

# Midori 플래그 최적화 (공식 키오스크 모드)
generate_midori_flags() {
    local flags=(
        "-e" "Fullscreen"
        "-e" "Navigationbar" 
        "-e" "Statusbar"
    )
    
    # Zero 2W + 800x480 LCD 전용 추가 최적화
    if [ "$IS_ZERO2W" = true ]; then
        echo -e "${YELLOW}🔧 Midori Zero 2W + 800x480 LCD 키오스크 모드 플래그 적용${NC}" >&2
        # Zero 2W용 추가 메모리 최적화 플래그
        flags+=("-i" "300")  # 5분 유휴시간 후 정리
    else
        echo -e "${YELLOW}🔧 Midori 키오스크 모드 플래그 적용${NC}" >&2
    fi
    
    printf '%s\n' "${flags[@]}"
}

# Chromium 플래그 최적화 (Zero 2W 호환성)
generate_chromium_flags() {
    local flags=(
        "--kiosk"
        "--start-fullscreen"
        "--no-first-run"
        "--no-default-browser-check"
        "--disable-infobars"
        "--disable-translate"
        "--user-data-dir=/tmp/simple-kiosk-$(date +%s)"
    )

    # 세션 타입에 맞춘 Ozone/GL 설정 (Wayland/X11 자동 감지)
    if [ "${XDG_SESSION_TYPE:-x11}" = "wayland" ] || [ -n "$WAYLAND_DISPLAY" ]; then
        flags+=("--ozone-platform=wayland" "--enable-features=UseOzonePlatform" "--use-gl=egl")
    else
        flags+=("--ozone-platform=x11" "--use-gl=egl")
    fi
    
    # Zero 2W 전용 최적화
    if [ "$IS_ZERO2W" = true ]; then
        flags+=("--window-size=800,480")
        echo -e "${YELLOW}🔧 Zero 2W + 800x480 LCD 최소 플래그 적용${NC}" >&2
    else
        # Pi 4B: 최소 플래그만 사용 (문제 시에만 GPU 관련 플래그 수동 추가 권장)
        echo -e "${YELLOW}🔧 Pi 4B 최소 Chromium 플래그 적용${NC}" >&2
    fi
    
    echo "${flags[@]}"
}

# 키오스크 모드 실행
echo -e "${GREEN}🖥️  키오스크 브라우저 시작 중...${NC}"
echo -e "${BLUE}📱 전체화면 터치 인터페이스가 시작됩니다${NC}"

# 브라우저별 실행 처리
launch_browser() {
    local BROWSER_FLAGS=$(generate_browser_flags)
    
    if [ "$BROWSER_TYPE" = "midori" ]; then
        echo -e "${BLUE}🔧 Midori 브라우저 실행${NC}"
        echo -e "${BLUE}🔧 적용된 플래그: -e Fullscreen (안정성 우선)${NC}"
        
        # WebKit 기본 최적화 설정
        export WEBKIT_DISABLE_COMPOSITING_MODE=1
        export JavaScriptCoreUseJIT=0
        export GST_DEBUG=0
        export GST_DEBUG_NO_COLOR=1
        export LANG=C.UTF-8
        export LC_CTYPE=C.UTF-8
        export LC_MESSAGES=C
        export LC_NUMERIC=C
        export DISPLAY=:0.0
        unset COLUMNS LINES
        
        # Zero 2W + 800x480 LCD 전용 추가 최적화
        if [ "$IS_ZERO2W" = true ]; then
            echo -e "${YELLOW}🔧 Zero 2W + 800x480 LCD 전용 Midori + WebKit 최적화 설정${NC}"
            
            # WebKit 메모리 최적화 (Zero 2W 전용 - 더 강력한 설정)
            export WEBKIT_DISABLE_ACCELERATED_COMPOSITING=1
            export WEBKIT_DISABLE_WEBGL=1
            export WEBKIT_DISABLE_ACCELERATED_2D_CANVAS=1
            export WEBKIT_DISABLE_MEDIA_STREAM=1
            export WEBKIT_DISABLE_WEB_AUDIO=1
            export WEBKIT_DISABLE_VIDEO=1
            export WEBKIT_DISABLE_PLUGINS=1
            
            # JavaScript 엔진 최적화 (더 보수적)
            export JSC_useJIT=false
            export JSC_useLLInt=true
            export JSC_useConcurrentJIT=false
            export JSC_useRegExpJIT=false
            export JSC_useDFGJIT=false
            export JSC_useFTLJIT=false
            
            # 메모리 압박 모드 (더 엄격하게)
            export WEBKIT_MEMORY_PRESSURE_HANDLER_ENABLED=1
            export WEBKIT_MEMORY_PRESSURE_KILL_PROCESS=1
            export WEBKIT_MAX_MEMORY_USAGE=100  # 100MB 제한
            export WEBKIT_CACHE_SIZE_LIMIT=10   # 10MB 캐시 제한
            
            # 렌더링 최적화 (CPU만 사용, GPU 완전 비활성화)
            export WEBKIT_FORCE_COMPOSITING_MODE=0
            export WEBKIT_ACCELERATED_COMPOSITING=0
            export WEBKIT_DISABLE_GPU_PROCESS=1
            
            # 800x480 LCD 디스플레이 최적화
            export WEBKIT_VIEWPORT_WIDTH=800
            export WEBKIT_VIEWPORT_HEIGHT=480
            export WEBKIT_DEVICE_PIXEL_RATIO=1.0
            export WEBKIT_DISABLE_SMOOTH_SCROLLING=1
            export WEBKIT_DISABLE_ANIMATIONS=1
            
        else
            echo -e "${YELLOW}🔧 Midori WebKit 기본 최적화 환경 변수 설정${NC}"
        fi
        
        # Midori 실행 (안정적인 방식)
        echo -e "${BLUE}🌐 URL: http://127.0.0.1:5000 (DNS 우회)${NC}"
        
        # 서버 완전 준비 확인
        echo -e "${YELLOW}⏳ 서버 연결 확인 중...${NC}"
        for i in {1..10}; do
            if curl -s --max-time 2 http://127.0.0.1:5000 >/dev/null 2>&1; then
                echo -e "${GREEN}✅ 서버 연결 확인 완료${NC}"
                break
            fi
            sleep 1
            if [ $i -eq 10 ]; then
                echo -e "${RED}❌ 서버 연결 실패${NC}"
                exit 1
            fi
        done
        
        # Zero 2W에서 Midori 실행 전 최종 메모리 정리
        if [ "$IS_ZERO2W" = true ]; then
            echo -e "${YELLOW}🧹 Midori 실행 전 최종 메모리 정리...${NC}"
            # 가비지 컬렉션 강제 실행
            sync
            echo 1 | sudo tee /proc/sys/vm/drop_caches >/dev/null 2>&1 || true
            sleep 1
        fi
        
        # Midori 실행 (공식 키오스크 모드)
        echo -e "${YELLOW}🔧 Midori 키오스크 모드 시작...${NC}"
        
        # Midori 실행 (Zero 2W에서도 일반 실행)
        echo -e "${YELLOW}⏳ Midori 브라우저 시작 중...${NC}"
        
        # 메모리 사용량 사전 체크
        AVAILABLE_MEM=$(awk '/MemAvailable/ {print int($2/1024)}' /proc/meminfo)
        if [ "$AVAILABLE_MEM" -lt 50 ]; then
            echo -e "${RED}❌ 사용 가능 메모리 부족 (${AVAILABLE_MEM}MB) - 브라우저 실행 중단${NC}"
            echo -e "${YELLOW}💡 시스템 재부팅 후 재시도하세요${NC}"
            exit 1
        fi
        
        echo -e "${GREEN}✅ 메모리 상태 양호 (${AVAILABLE_MEM}MB 사용 가능)${NC}"
        
        # Midori 단일 인스턴스로 제한된 실행
        # 프로세스 모니터링과 함께 안전하게 시작
        echo -e "${YELLOW}🔒 단일 인스턴스 Midori 실행 중...${NC}"
        $BROWSER -e Fullscreen http://127.0.0.1:5000 &
        BROWSER_PID=$!
        
        # 프로세스 시작 확인
        sleep 2
        if ! kill -0 $BROWSER_PID 2>/dev/null; then
            echo -e "${RED}❌ Midori 프로세스 시작 실패${NC}"
            exit 1
        fi
        
        echo -e "${GREEN}✅ Midori 정상 시작 (PID: $BROWSER_PID)${NC}"
        
        # Zero 2W에서는 시작 확인을 더 오래 대기
        if [ "$IS_ZERO2W" = true ]; then
            echo -e "${YELLOW}⏳ Zero 2W 환경 - 브라우저 로딩 대기 중...${NC}"
            sleep 3
        fi
    else
        # Chromium 직접 실행 (시스템 래퍼 우회)
        local CHROMIUM_BINARY
        if [ -f "/usr/lib/chromium/chromium" ]; then
            CHROMIUM_BINARY="/usr/lib/chromium/chromium"
        elif [ -f "/usr/bin/chromium" ]; then
            CHROMIUM_BINARY="/usr/bin/chromium"
        else
            CHROMIUM_BINARY="$BROWSER"
        fi
        
        echo -e "${BLUE}🔧 Chromium 바이너리: $CHROMIUM_BINARY${NC}"
        echo -e "${BLUE}🔧 최적화 플래그 적용 (${#BROWSER_FLAGS} 문자)${NC}"
        
        # 명령어 실행 (긴 플래그는 출력하지 않음)
        $CHROMIUM_BINARY $BROWSER_FLAGS http://127.0.0.1:5000 &
        BROWSER_PID=$!
    fi
}

# 브라우저 실행
launch_browser

# BROWSER_PID는 launch_browser 함수 내에서 설정됨
echo -e "${GREEN}✅ 키오스크 모드 시작 완료!${NC}"
echo -e "${BLUE}🔍 웹서버 PID: $SERVER_PID${NC}"
echo -e "${BLUE}🌐 브라우저 PID: $BROWSER_PID${NC}"
echo -e "${BLUE}📋 로그 파일: $LOG_FILE${NC}"
echo -e "${BLUE}📁 로그 디렉토리: $LOG_DIR${NC}"
echo -e "${YELLOW}🛑 종료하려면 Ctrl+C를 누르세요${NC}"

# 강화된 종료 처리 함수
cleanup() {
    echo -e "\n${YELLOW}🛑 키오스크 모드 안전 종료 중...${NC}"
    
    # 마우스 커서 복원
    show_cursor
    
    # 1단계: 지정된 브라우저 프로세스 정리
    if [ -n "$BROWSER_PID" ] && kill -0 $BROWSER_PID 2>/dev/null; then
        echo "   지정된 브라우저 종료 (PID: $BROWSER_PID)"
        kill -TERM $BROWSER_PID 2>/dev/null || true
        sleep 2
        kill -9 $BROWSER_PID 2>/dev/null || true
    fi
    
    # 2단계: 모든 관련 프로세스 강제 정리
    echo "   모든 브라우저 관련 프로세스 정리 중..."
    sudo pkill -9 midori 2>/dev/null || true
    sudo pkill -9 -f "WebKitNetworkProcess" 2>/dev/null || true
    sudo pkill -9 -f "WebKitWebProcess" 2>/dev/null || true
    
    # 3단계: 서버 안전 종료
    if [ -n "$SERVER_PID" ] && kill -0 $SERVER_PID 2>/dev/null; then
        echo "   웹서버 안전 종료 (PID: $SERVER_PID)"
        kill -TERM $SERVER_PID 2>/dev/null || true
        sleep 2
        if kill -0 $SERVER_PID 2>/dev/null; then
            echo "   웹서버 강제 종료"
            kill -9 $SERVER_PID 2>/dev/null || true
        fi
    fi
    
    # Python 웹서버 프로세스 정리
    echo "   남은 웹서버 프로세스 정리 중..."
    pkill -f "presentation/api/main.py" 2>/dev/null || true
    
    # 4단계: 임시 파일 정리
    rm -f "$PID_FILE"
    rm -f "$KIOSK_LOCK_FILE"
    rm -rf /tmp/simple-kiosk* 2>/dev/null || true
    rm -f /tmp/unclutter.pid 2>/dev/null || true
    
    # 5단계: 메모리 정리
    sudo sync && sudo sysctl vm.drop_caches=1 2>/dev/null || true
    
    echo -e "${BLUE}📁 로그 파일들이 저장된 위치: $LOG_DIR${NC}"
    echo -e "${GREEN}✅ 안전 종료 완료${NC}"
    exit 0
}

# 종료 신호 처리
trap cleanup SIGINT SIGTERM

# 브라우저 프로세스 대기
echo -e "${BLUE}🔄 키오스크 모드 실행 중... (Ctrl+C로 종료)${NC}"
wait $BROWSER_PID 2>/dev/null || true

# 브라우저가 종료되면 정리
cleanup 