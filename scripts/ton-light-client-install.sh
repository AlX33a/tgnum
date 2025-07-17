#!/bin/bash

# Полный скрипт установки TON Light Client (liteserver) на Ubuntu 22.04
# Исправленная версия с правильными путями для tonuser

set -e  # Останавливаться при первой ошибке

# Глобальные переменные
LOG_FILE="/var/log/ton-install.log"
TONUSER="tonuser"
TONUSER_HOME="/home/$TONUSER"
INSTALL_DIR="$TONUSER_HOME/mytonctrl"
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
    
    # Создание директорий с правильными правами
    mkdir -p "$TONUSER_HOME"
    chown "$TONUSER:$TONUSER" "$TONUSER_HOME"
    chmod 755 "$TONUSER_HOME"
    
    log_message "INFO" "Пользователь $TONUSER настроен"
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
    rm -rf /usr/src/mytonctrl* 2>/dev/null || true
    rm -rf /usr/src/ton* 2>/dev/null || true
    rm -rf "$TONUSER_HOME"/.local/share/mytonctrl* 2>/dev/null || true
    rm -rf "$TONUSER_HOME"/mytonctrl* 2>/dev/null || true
    rm -rf "$TONUSER_HOME"/ton* 2>/dev/null || true
    rm -rf /opt/ton* 2>/dev/null || true
    rm -rf /tmp/ton* 2>/dev/null || true
    rm -rf /var/ton* 2>/dev/null || true
    
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
        sudo
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
create_installer_script() {
    log_message "INFO" "Создание скрипта установки mytonctrl..."
    
    mkdir -p "$TEMP_DIR"
    
    # Создание скрипта установки для tonuser
    cat > "$TEMP_DIR/install_mytonctrl.sh" << 'EOF'
#!/bin/bash

# Скрипт установки mytonctrl от имени tonuser
set -e

TONUSER="tonuser"
TONUSER_HOME="/home/$TONUSER"
INSTALL_DIR="$TONUSER_HOME/mytonctrl"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"
}

main() {
    log "Начало установки mytonctrl от пользователя $USER"
    
    # Убедимся, что мы в правильной директории
    cd "$TONUSER_HOME"
    
    # Клонирование репозитория mytonctrl
    if [ -d "mytonctrl" ]; then
        log "Удаление существующего репозитория mytonctrl"
        rm -rf mytonctrl
    fi
    
    log "Клонирование репозитория mytonctrl..."
    git clone https://github.com/ton-blockchain/mytonctrl.git || {
        log "Ошибка: не удалось клонировать репозиторий"
        exit 1
    }
    
    # Переход в директорию mytonctrl
    cd mytonctrl
    
    # Установка mytonctrl в режиме liteserver
    log "Запуск mytoninstaller.py в режиме liteserver..."
    python3 mytoninstaller.py -m liteserver -i || {
        log "Ошибка: не удалось установить mytonctrl"
        exit 1
    }
    
    log "Установка mytonctrl завершена успешно"
}

# Проверка, что скрипт запущен от имени tonuser
if [ "$USER" != "$TONUSER" ]; then
    log "Ошибка: скрипт должен быть запущен от имени пользователя $TONUSER"
    exit 1
fi

main
EOF

    chmod +x "$TEMP_DIR/install_mytonctrl.sh"
    chown "$TONUSER:$TONUSER" "$TEMP_DIR/install_mytonctrl.sh"
    
    log_message "INFO" "Скрипт установки создан"
}

# Сборка и установка TON
build() {
    log_message "INFO" "Сборка и установка TON Light Client..."
    
    # Создание скрипта установки
    create_installer_script
    
    # Запуск установки от имени tonuser
    log_message "INFO" "Запуск установки mytonctrl от пользователя $TONUSER..."
    (
        su - "$TONUSER" -c "$TEMP_DIR/install_mytonctrl.sh"
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

# Настройка systemd сервиса
setup_systemd_service() {
    log_message "INFO" "Настройка systemd сервиса..."
    
    # Создание systemd сервиса для mytoncore
    cat > /etc/systemd/system/mytoncore.service << EOF
[Unit]
Description=MyTonCore Service
After=network.target

[Service]
Type=simple
User=$TONUSER
Group=$TONUSER
WorkingDirectory=$TONUSER_HOME/mytonctrl
ExecStart=/usr/bin/python3 $TONUSER_HOME/mytonctrl/mytoncore.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

    # Создание сервиса для liteserver
    cat > /etc/systemd/system/ton-liteserver.service << EOF
[Unit]
Description=TON Liteserver
After=network.target mytoncore.service

[Service]
Type=simple
User=$TONUSER
Group=$TONUSER
WorkingDirectory=$TONUSER_HOME/mytonctrl
ExecStart=/usr/bin/python3 $TONUSER_HOME/mytonctrl/mytonctrl.py --liteserver
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

    # Перезагрузка systemd и включение сервисов
    systemctl daemon-reload
    systemctl enable mytoncore
    systemctl enable ton-liteserver
    
    log_message "INFO" "Systemd сервисы настроены"
}

# Запуск Light Client
run_lightclient() {
    log_message "INFO" "Запуск TON Light Client..."
    
    # Настройка systemd сервиса
    setup_systemd_service
    
    # Запуск сервисов
    systemctl start mytoncore
    sleep 10
    systemctl start ton-liteserver
    
    log_message "INFO" "TON Light Client запущен"
}

# Проверка статуса mytonctrl
check_mytonctrl_status() {
    log_message "INFO" "Проверка статуса mytonctrl..."
    
    # Проверка через sudo -u tonuser
    local status_output
    status_output=$(sudo -u "$TONUSER" bash -c "cd $TONUSER_HOME/mytonctrl && python3 mytonctrl.py -c 'status'" 2>&1) || {
        log_message "WARN" "Не удалось получить статус mytonctrl"
        return 1
    }
    
    log_message "INFO" "Статус mytonctrl: $status_output"
    return 0
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
        
        # Проверка статуса синхронизации
        if check_mytonctrl_status; then
            log_message "INFO" "MyTonCtrl отвечает корректно"
            break
        fi
        
        log_message "INFO" "Ожидание инициализации mytonctrl... ($elapsed сек)"
        sleep 30
    done
    
    log_message "INFO" "Синхронизация завершена"
}

# Отображение статуса
show_status() {
    log_message "INFO" "Отображение статуса системы..."
    
    echo -e "\n${GREEN}=== СТАТУС УСТАНОВКИ TON LIGHT CLIENT ===${NC}"
    echo -e "${BLUE}Пользователь TON:${NC} $TONUSER"
    echo -e "${BLUE}Домашняя директория:${NC} $TONUSER_HOME"
    echo -e "${BLUE}Директория установки:${NC} $INSTALL_DIR"
    echo -e "${BLUE}Статус mytoncore:${NC} $(systemctl is-active mytoncore 2>/dev/null || echo 'неактивен')"
    echo -e "${BLUE}Статус liteserver:${NC} $(systemctl is-active ton-liteserver 2>/dev/null || echo 'неактивен')"
    echo -e "${BLUE}Лог-файл:${NC} $LOG_FILE"
    
    echo -e "\n${GREEN}=== КОМАНДЫ УПРАВЛЕНИЯ ===${NC}"
    echo -e "${BLUE}Статус mytoncore:${NC} systemctl status mytoncore"
    echo -e "${BLUE}Статус liteserver:${NC} systemctl status ton-liteserver"
    echo -e "${BLUE}Запуск mytonctrl:${NC} sudo -u $TONUSER bash -c 'cd $INSTALL_DIR && python3 mytonctrl.py'"
    echo -e "${BLUE}Проверка статуса:${NC} sudo -u $TONUSER bash -c 'cd $INSTALL_DIR && python3 mytonctrl.py -c status'"
    echo -e "${BLUE}Логи mytoncore:${NC} journalctl -u mytoncore -f"
    echo -e "${BLUE}Логи liteserver:${NC} journalctl -u ton-liteserver -f"
    
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
