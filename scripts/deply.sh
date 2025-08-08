#!/bin/bash
# 스마트 스위치 디밍 애플리케이션 배포 스크립트

set -e

echo "=== Smart Switch Dimming 애플리케이션 배포 시작 ==="

# 기본 설정
APP_NAME="SM_allione"
APP_DIR="/home/allione/Desktop/$APP_NAME"
SERVICE_NAME="SM_allione.service"
PYTHON_VERSION="3.9"

# 시스템 업데이트
echo "1. 시스템 업데이트..."
sudo apt update && sudo apt upgrade -y

# 필요한 시스템 패키지 설치
echo "2. 시스템 패키지 설치..."
sudo apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    build-essential \
    git \
    nginx \
    supervisor \
    bluetooth \
    libbluetooth-dev \
    pkg-config \
    libssl-dev \
    libffi-dev

# 애플리케이션 디렉토리 생성
echo "3. 애플리케이션 디렉토리 설정..."
if [ ! -d "$APP_DIR" ]; then
    mkdir -p "$APP_DIR"
fi

# 현재 디렉토리의 모든 파일을 애플리케이션 디렉토리로 복사
echo "4. 애플리케이션 파일 복사..."
cp -r ./* "$APP_DIR/"
sudo chown -R allione:allione "$APP_DIR"

# Python 가상환경 생성
echo "5. Python 가상환경 생성..."
cd "$APP_DIR"
python3 -m venv venv
source venv/bin/activate

# Python 의존성 설치
echo "6. Python 의존성 설치..."
pip install --upgrade pip
pip install -r requirements.txt

# systemd 서비스 설정
echo "7. systemd 서비스 설정..."
sudo cp "scripts/$SERVICE_NAME" "/etc/systemd/system/"
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"

# 방화벽 설정 (포트 5000 열기)
echo "8. 방화벽 설정..."
sudo ufw allow 5000/tcp

# GPIO 권한 설정
echo "9. GPIO 권한 설정..."
sudo usermod -a -G gpio allione

# 블루투스 권한 설정
echo "10. 블루투스 권한 설정..."
sudo usermod -a -G bluetooth allione

# 로그 디렉토리 생성
echo "11. 로그 디렉토리 생성..."
sudo mkdir -p /var/log/$APP_NAME
sudo chown allione:allione /var/log/$APP_NAME

# 키오스크 모드 설정 (선택사항)
echo "12. 키오스크 모드 설정..."
if [ "$1" = "--kiosk" ]; then
    echo "키오스크 모드 설정을 적용합니다..."
    
    # Chromium 자동 시작 설정
    mkdir -p /home/allione/.config/autostart
    cat > /home/allione/.config/autostart/kiosk.desktop << EOF
[Desktop Entry]
Type=Application
Name=Kiosk
Exec=/usr/bin/chromium-browser --noerrdialogs --disable-infobars --kiosk http://localhost:5000
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
EOF
    
    # 화면 보호기 비활성화
    cat >> /home/allione/.bashrc << EOF

# 화면 보호기 비활성화
export DISPLAY=:0
xset s off
xset s noblank
xset -dpms
EOF
fi

# 서비스 시작
echo "13. 서비스 시작..."
sudo systemctl start "$SERVICE_NAME"

# 서비스 상태 확인
echo "14. 배포 완료 - 서비스 상태 확인..."
sudo systemctl status "$SERVICE_NAME" --no-pager

echo ""
echo "=== 배포 완료 ==="
echo "애플리케이션 주소: http://localhost:5000"
echo "서비스 로그 확인: sudo journalctl -u $SERVICE_NAME -f"
echo "서비스 재시작: sudo systemctl restart $SERVICE_NAME"
echo "서비스 중지: sudo systemctl stop $SERVICE_NAME"
echo ""

# IP 주소 표시
echo "현재 시스템 IP 주소:"
hostname -I

echo ""
echo "배포가 성공적으로 완료되었습니다!" 