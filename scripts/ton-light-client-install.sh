#!/bin/bash

# Полный скрипт установки TON Light Client (liteserver) на Ubuntu 22.04
# Исправленная версия для работы с актуальным mytonctrl

set -e  # Останавливаться при первой ошибке

# Глобальные переменные
LOG_FILE="/var/log/ton-install.log"
TONUSER="tonuser"
INSTALL_DIR="/opt/ton"
MYTONCTRL_DIR="/usr/local/bin/mytonctrl"
TEMP_DIR="/tmp/ton-install"

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Функция вывода сообщений
log_message() {
    local level=$1
    local message=$2
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    
    case $level in
        "INFO")
            echo -e "${GREEN}[INFO]${NC} $message"
            echo "[$timestamp] [INFO] $message" >> "$LOG_FILE"
            ;;
        "WARN")
            echo -e "${YELLOW}[WARN]${NC} $message"
            echo "[$timestamp] [WARN] $message" >> "$LOG_FILE"
            ;;
        "ERROR")
            echo -e "${RED}[ERROR]${NC} $message"
            echo "[$timestamp] [ERROR] $message" >> "$LOG_FILE"
            ;;
        "DEBUG")
            echo -e "${BLUE}[DEBUG]${NC} $message"
            echo "[$timestamp] [DEBUG] $message" >> "$LOG_FILE"
            ;;
    esac
}

# Функция обработки ошибок
error_handler() {
    local line_number=$1
    log_message "ERROR" "Ошибка на строке $line_number. Код завершения: $?"
    log_message "ERROR" "Установка прервана из-за критической ошибки"
    cleanup
    exit 1
}

# Установка обработчика ошибок
trap 'error_handler $LINENO' ERR

# Анимированный спиннер
spinner() {
    local pid=$1
    local delay=0.1
    local spinstr='|/-\'
    local temp
    
    while ps -p $pid > /dev/null 2>&1; do
        temp=${spinstr#?}
        printf "\r[%c] Выполняется..." "$spinstr"
        spinstr=$temp${spinstr%"$temp"}
        sleep $delay
    done
    printf "\r"
}

# Прогресс-бар
progress_bar() {
    local duration=$1
    local step=$((duration / 50))
    local progress=0
    
    for i in $(seq 1 50); do
        printf "\r["
        for j in $(seq 1 $i); do
            printf "="
        done
        for j in $(seq $((i + 1)) 50); do
            printf " "
        done
        printf "] %d%%" $((i * 2))
        sleep $step
    done
    printf "\n"
}

# Проверка прав root
check_root() {
    log_message "INFO" "Проверка прав суперпользователя..."
    
    if [[ $EUID -ne 0 ]]; then
        log_message "ERROR" "Скрипт должен быть запущен от имени root"
        log_message "ERROR" "Используйте: sudo bash $0"
        exit 1
    fi
    
    log_message "INFO" "Права root подтверждены"
}

# Проверка системы
check_system() {
    log_message "INFO" "Проверка системы..."
    
    # Проверка версии Ubuntu
    if ! grep -q "Ubuntu 22.04" /etc/os-release; then
        log_message "WARN" "Обнаружена не Ubuntu 22.04. Продолжение на свой страх и риск"
    fi
    
    # Проверка доступности интернета
    if ! ping -c 1 google.com &> /dev/null; then
        log_message "ERROR" "Нет доступа к интернету"
        exit 1
    fi
    
    # Проверка свободного места (минимум 20GB)
    local free_space=$(df / | tail -1 | awk '{print $4}')
    if [[ $free_space -lt 20971520 ]]; then
        log_message "ERROR" "Недостаточно свободного места на диске (требуется минимум 20GB)"
        exit 1
    fi
    
    log_message "INFO" "Система проверена успешно"
}

# Создание пользователя tonuser
create_user() {
    log_message "INFO" "Создание пользователя $TONUSER..."
    
    if ! id "$TONUSER" &>/dev/null; then
        useradd -m -s /bin/bash "$TONUSER" || {
            log_message "ERROR" "Не удалось создать пользователя $TONUSER"
            exit 1
        }
        log_message "INFO" "Пользователь $TONUSER создан"
    else
        log_message "INFO" "Пользователь $TONUSER уже существует"
    fi
    
    # Добавление пользователя в группу sudo
    usermod -aG sudo "$TONUSER" || {
        log_message "ERROR" "Не удалось добавить пользователя в группу sudo"
        exit 1
    }
}

# Очистка предыдущих установок
clean() {
    log_message "INFO" "Очистка предыдущих установок TON..."
    
    # Остановка сервисов
    systemctl stop ton-liteclient 2>/dev/null || true
    systemctl stop mytoncore 2>/dev/null || true
    systemctl stop validator 2>/dev/null || true
    
    # Удаление процессов
    pkill -f "ton-lite-client" 2>/dev/null || true
    pkill -f "mytoncore" 2>/dev/null || true
    pkill -f "validator" 2>/dev/null || true
    
    # Удаление файлов и директорий
    rm -rf /usr/local/bin/mytonctrl* 2>/dev/null || true
    rm -rf /usr/local/bin/ton* 2>/dev/null || true
    rm -rf /home/$TONUSER/.local/share/mytonctrl* 2>/dev/null || true
    rm -rf /home/$TONUSER/ton* 2>/dev/null || true
    rm -rf /opt/ton* 2>/dev/null || true
    rm -rf /tmp/ton* 2>/dev/null || true
    
    # Удаление systemd сервисов
    rm -f /etc/systemd/system/ton-*.service 2>/dev/null || true
    rm -f /etc/systemd/system/mytoncore.service 2>/dev/null || true
    
    systemctl daemon-reload
    
    log_message "INFO" "Очистка завершена"
}

# Установка зависимостей
install_deps() {
    log_message "INFO" "Установка зависимостей..."
    
    # Обновление репозиториев
    apt-get update -y || {
        log_message "ERROR" "Не удалось обновить репозитории"
        exit 1
    }
    
    # Установка базовых пакетов
    local packages=(
        build-essential
        cmake
        clang
        openssl
        libssl-dev
        zlib1g-dev
        gperf
        libreadline-dev
        ccache
        libmicrohttpd-dev
        pkg-config
        libsodium-dev
        libsecp256k1-dev
        git
        wget
        curl
        python3
        python3-pip
        screen
        htop
        nano
        jq
        unzip
    )
    
    for package in "${packages[@]}"; do
        log_message "INFO" "Установка $package..."
        apt-get install -y "$package" || {
            log_message "ERROR" "Не удалось установить $package"
            exit 1
        }
    done
    
    log_message "INFO" "Зависимости установлены"
}

# Создание исправленного скрипта установки mytonctrl
create_fixed_installer() {
    log_message "INFO" "Создание исправленного скрипта установки..."
    
    mkdir -p "$TEMP_DIR"
    
    # Скачивание оригинального скрипта
    wget -O "$TEMP_DIR/install.sh" "https://raw.githubusercontent.com/ton-blockchain/mytonctrl/master/scripts/install.sh" || {
        log_message "ERROR" "Не удалось скачать скрипт установки"
        exit 1
    }
    
    # Создание исправленной версии
    cat > "$TEMP_DIR/install_fixed.sh" << 'EOF'
#!/bin/bash

# Исправленный скрипт установки mytonctrl для liteserver режима
# Убираем проверку root и добавляем флаг для liteserver

set -e

# Переменные
TONUSER="tonuser"
INSTALL_DIR="/home/$TONUSER"

# Функции из оригинального скрипта (без проверки root)
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"
}

# Основная логика установки
main() {
    log "Начало установки mytonctrl в режиме liteserver"
    
    # Переход в домашнюю директорию пользователя
    cd "$INSTALL_DIR"
    
    # Клонирование репозитория
    if [ -d "mytonctrl" ]; then
        rm -rf mytonctrl
    fi
    
    git clone https://github.com/ton-blockchain/mytonctrl.git
    cd mytonctrl
    
    # Установка с игнорированием системных требований в режиме liteserver
    python3 install.py -i -t liteserver
    
    log "Установка mytonctrl завершена"
}

# Запуск от имени tonuser
if [ "$USER" != "$TONUSER" ]; then
    log "Переключение на пользователя $TONUSER"
    sudo -u "$TONUSER" bash "$0"
    exit $?
fi

main
EOF

    chmod +x "$TEMP_DIR/install_fixed.sh"
    log_message "INFO" "Исправленный скрипт создан"
}

# Сборка и установка TON
build() {
    log_message "INFO" "Сборка и установка TON Light Client..."
    
    # Создание исправленного скрипта
    create_fixed_installer
    
    # Установка как root, но с переключением на tonuser
    log_message "INFO" "Запуск установки mytonctrl..."
    (
        cd "$TEMP_DIR"
        bash install_fixed.sh
    ) &
    
    local install_pid=$!
    
    # Показываем спиннер во время установки
    spinner $install_pid
    
    # Ждем завершения установки
    wait $install_pid || {
        log_message "ERROR" "Установка mytonctrl завершилась с ошибкой"
        exit 1
    }
    
    log_message "INFO" "Установка mytonctrl завершена успешно"
}

# Запуск Light Client
run_lightclient() {
    log_message "INFO" "Запуск TON Light Client..."
    
    # Создание systemd сервиса для liteserver
    cat > /etc/systemd/system/ton-liteserver.service << EOF
[Unit]
Description=TON Liteserver
After=network.target

[Service]
Type=simple
User=$TONUSER
WorkingDirectory=/home/$TONUSER
ExecStart=/usr/local/bin/mytonctrl liteserver
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable ton-liteserver
    systemctl start ton-liteserver
    
    log_message "INFO" "TON Light Client запущен"
}

# Ожидание синхронизации
wait_sync() {
    log_message "INFO" "Ожидание синхронизации с сетью TON..."
    
    local sync_timeout=3600  # 1 час
    local start_time=$(date +%s)
    
    while true; do
        local current_time=$(date +%s)
        local elapsed=$((current_time - start_time))
        
        if [ $elapsed -gt $sync_timeout ]; then
            log_message "ERROR" "Превышено время ожидания синхронизации"
            exit 1
        fi
        
        # Проверка статуса синхронизации через mytonctrl
        local sync_status=$(sudo -u "$TONUSER" mytonctrl -c "status" 2>/dev/null | grep -i "out of sync" || echo "synced")
        
        if [[ "$sync_status" == *"synced"* ]] || [[ "$sync_status" == *"< 20"* ]]; then
            log_message "INFO" "Синхронизация завершена успешно"
            break
        fi
        
        log_message "INFO" "Синхронизация в процессе... ($elapsed сек)"
        sleep 30
    done
}

# Отображение статуса
show_status() {
    log_message "INFO" "Отображение статуса системы..."
    
    echo -e "\n${GREEN}=== СТАТУС УСТАНОВКИ TON LIGHT CLIENT ===${NC}"
    echo -e "${BLUE}Пользователь TON:${NC} $TONUSER"
    echo -e "${BLUE}Директория установки:${NC} /home/$TONUSER"
    echo -e "${BLUE}Статус сервиса:${NC} $(systemctl is-active ton-liteserver)"
    echo -e "${BLUE}Лог-файл:${NC} $LOG_FILE"
    
    echo -e "\n${GREEN}=== КОМАНДЫ УПРАВЛЕНИЯ ===${NC}"
    echo -e "${BLUE}Статус:${NC} systemctl status ton-liteserver"
    echo -e "${BLUE}Запуск:${NC} systemctl start ton-liteserver"
    echo -e "${BLUE}Остановка:${NC} systemctl stop ton-liteserver"
    echo -e "${BLUE}MyTonCtrl:${NC} sudo -u $TONUSER mytonctrl"
    
    echo -e "\n${GREEN}=== УСТАНОВКА ЗАВЕРШЕНА ===${NC}"
}

# Функция очистки при ошибке
cleanup() {
    log_message "INFO" "Очистка временных файлов..."
    rm -rf "$TEMP_DIR" 2>/dev/null || true
}

# Основная функция
main() {
    log_message "INFO" "Запуск установки TON Light Client на $(date)"
    
    # Создание лог-файла
    mkdir -p "$(dirname "$LOG_FILE")"
    touch "$LOG_FILE"
    chmod 644 "$LOG_FILE"
    
    # Выполнение этапов установки
    check_root
    check_system
    create_user
    clean
    install_deps
    build
    run_lightclient
    wait_sync
    show_status
    
    log_message "INFO" "Установка TON Light Client завершена успешно!"
    cleanup
}

# Запуск основной функции
main "$@"
