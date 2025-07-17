#!/bin/bash

# TON Light Client Auto-Installation Script
# Версия: 1.0
# Дата: 2025-01-18
# Автор: Эксперт по автоматизации Linux
# Описание: Полная установка, настройка и запуск TON Light Client на Ubuntu 22.04

set -e  # Остановка при первой ошибке

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # Без цвета

# Глобальные переменные
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
LOG_FILE="/var/log/ton-install.log"
WORKDIR="/root"
TON_USER="tonuser"
REQUIRED_DEPS="build-essential cmake clang git ninja-build zlib1g-dev libssl-dev libsecp256k1-dev libmicrohttpd-dev libsodium-dev pkg-config gperf libreadline-dev ccache wget curl"

# Функция логирования
log() {
    echo -e "$1" | tee -a "$LOG_FILE"
}

# Анимированный спиннер
spinner() {
    local pid=$1
    local message=$2
    local delay=0.1
    local spinstr='|/-\'
    
    echo -ne "${BLUE}$message${NC} "
    
    while [ "$(ps a | awk '{print $1}' | grep $pid)" ]; do
        local temp=${spinstr#?}
        printf "${YELLOW}[%c]${NC}" "$spinstr"
        local spinstr=$temp${spinstr%"$temp"}
        sleep $delay
        printf "\b\b\b"
    done
    
    wait $pid
    local exit_code=$?
    
    if [ $exit_code -eq 0 ]; then
        printf "${GREEN}[✓]${NC}\n"
    else
        printf "${RED}[✗]${NC}\n"
        log "${RED}ОШИБКА: $message завершено с кодом $exit_code${NC}"
        exit $exit_code
    fi
}

# Анимированный прогресс-бар
progress_bar() {
    local duration=$1
    local message=$2
    local width=50
    
    echo -ne "${BLUE}$message${NC} "
    
    for ((i=0; i<=duration; i++)); do
        local percent=$((i * 100 / duration))
        local filled=$((i * width / duration))
        
        printf "\r${BLUE}$message${NC} ["
        printf "%*s" $filled | tr ' ' '='
        printf "%*s" $((width - filled)) | tr ' ' '-'
        printf "] %d%%" $percent
        
        sleep 0.1
    done
    
    printf " ${GREEN}[ЗАВЕРШЕНО]${NC}\n"
}

# Функция проверки прав root
check_root() {
    if [ "$EUID" -ne 0 ]; then
        log "${RED}ОШИБКА: Скрипт должен запускаться с правами root${NC}"
        log "${YELLOW}Используйте: sudo bash $0${NC}"
        exit 1
    fi
}

# Функция создания пользователя
create_user() {
    log "${GREEN}=== СОЗДАНИЕ ПОЛЬЗОВАТЕЛЯ $TON_USER ===${NC}"
    
    if id "$TON_USER" &>/dev/null; then
        log "${YELLOW}Пользователь $TON_USER уже существует${NC}"
    else
        {
            adduser --disabled-password --gecos "" "$TON_USER"
            usermod -aG sudo "$TON_USER"
            echo "$TON_USER:ton123" | chpasswd
        } &
        spinner $! "Создание пользователя $TON_USER"
        
        log "${GREEN}Пользователь $TON_USER создан успешно${NC}"
    fi
}

# Функция очистки предыдущих установок
clean() {
    log "${GREEN}=== ОЧИСТКА ПРЕДЫДУЩИХ УСТАНОВОК ===${NC}"
    
    {
        # Остановка всех связанных процессов
        pkill -f "validator-engine" || true
        pkill -f "lite-client" || true
        pkill -f "mytonctrl" || true
        systemctl stop validator.service || true
        systemctl stop mytoncore.service || true
        systemctl disable validator.service || true
        systemctl disable mytoncore.service || true
        
        # Удаление пакетов
        apt-get remove -y --purge mytonctrl 2>/dev/null || true
        pip3 uninstall -y mytonctrl 2>/dev/null || true
        pip3 uninstall -y ton-http-api 2>/dev/null || true
        
        # Удаление файлов и директорий
        rm -rf /usr/src/ton
        rm -rf /usr/src/mytonctrl
        rm -rf /usr/bin/ton
        rm -rf /var/ton-work
        rm -rf /var/ton-dht-server
        rm -rf /etc/systemd/system/validator.service
        rm -rf /etc/systemd/system/mytoncore.service
        rm -rf /usr/local/bin/mytonctrl
        rm -rf /usr/local/bin/mytoncore
        rm -rf ~/.local/share/mytoncore
        
        # Удаление пользователей и групп
        userdel -r validator 2>/dev/null || true
        groupdel validator 2>/dev/null || true
        
        # Очистка логов
        rm -f /var/log/ton*.log
        rm -f /tmp/ton*.log
        
        # Перезагрузка systemd
        systemctl daemon-reload
        
        # Очистка кеша apt
        apt-get clean
        apt-get autoclean
        apt-get autoremove -y
    } &
    
    spinner $! "Очистка предыдущих установок"
    log "${GREEN}Очистка завершена успешно${NC}"
}

# Функция установки зависимостей
install_deps() {
    log "${GREEN}=== УСТАНОВКА ЗАВИСИМОСТЕЙ ===${NC}"
    
    {
        # Обновление репозиториев
        apt-get update -y
        apt-get upgrade -y
        
        # Установка основных зависимостей
        apt-get install -y $REQUIRED_DEPS
        
        # Установка дополнительных Python пакетов
        apt-get install -y python3 python3-pip python3-dev python3-venv
        
        # Установка LLVM 16
        if ! command -v clang-16 &> /dev/null; then
            wget -O - https://apt.llvm.org/llvm.sh | bash -s -- 16 all
        fi
        
        # Обновление альтернатив для clang
        update-alternatives --install /usr/bin/clang clang /usr/bin/clang-16 100
        update-alternatives --install /usr/bin/clang++ clang++ /usr/bin/clang++-16 100
        
    } &
    
    spinner $! "Установка зависимостей"
    log "${GREEN}Зависимости установлены успешно${NC}"
}

# Функция сборки TON
build() {
    log "${GREEN}=== СБОРКА TON LIGHT CLIENT ===${NC}"
    
    cd "$WORKDIR"
    
    # Скачивание скрипта установки mytonctrl
    {
        wget -O install.sh https://raw.githubusercontent.com/ton-blockchain/mytonctrl/master/scripts/install.sh
        chmod +x install.sh
    } &
    
    spinner $! "Скачивание скрипта установки mytonctrl"
    
    # Установка mytonctrl в режиме liteserver
    {
        # Переключение на пользователя tonuser для установки
        sudo -u "$TON_USER" bash -c "
            cd /home/$TON_USER
            wget -O install.sh https://raw.githubusercontent.com/ton-blockchain/mytonctrl/master/scripts/install.sh
            chmod +x install.sh
            bash install.sh -m liteserver -i -d
        "
    } &
    
    spinner $! "Установка mytonctrl в режиме liteserver"
    
    # Проверка установки
    if [ ! -f "/usr/bin/ton/lite-client/lite-client" ]; then
        log "${RED}ОШИБКА: lite-client не найден после установки${NC}"
        exit 1
    fi
    
    log "${GREEN}Сборка TON Light Client завершена успешно${NC}"
}

# Функция запуска Light Client
run_lightclient() {
    log "${GREEN}=== ЗАПУСК TON LIGHT CLIENT ===${NC}"
    
    # Проверка существования конфигурационного файла
    local config_file="/usr/bin/ton/global.config.json"
    if [ ! -f "$config_file" ]; then
        {
            wget -O "$config_file" https://ton-blockchain.github.io/global.config.json
        } &
        spinner $! "Скачивание конфигурации сети"
    fi
    
    # Создание systemd сервиса для Light Client
    cat > /etc/systemd/system/ton-liteclient.service << EOF
[Unit]
Description=TON Light Client
After=network.target
Wants=network.target

[Service]
Type=simple
User=$TON_USER
Group=$TON_USER
WorkingDirectory=/home/$TON_USER
ExecStart=/usr/bin/ton/lite-client/lite-client -C $config_file
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
    
    # Запуск сервиса
    {
        systemctl daemon-reload
        systemctl enable ton-liteclient.service
        systemctl start ton-liteclient.service
    } &
    
    spinner $! "Запуск TON Light Client"
    log "${GREEN}TON Light Client запущен успешно${NC}"
}

# Функция ожидания синхронизации
wait_sync() {
    log "${GREEN}=== ОЖИДАНИЕ СИНХРОНИЗАЦИИ ===${NC}"
    
    local max_attempts=180  # 30 минут (180 попыток по 10 секунд)
    local attempt=0
    local sync_status=""
    
    while [ $attempt -lt $max_attempts ]; do
        # Проверка статуса через mytonctrl
        if command -v mytonctrl &> /dev/null; then
            sync_status=$(sudo -u "$TON_USER" timeout 5 mytonctrl -c "status" 2>/dev/null | grep -i "out of sync" | awk '{print $NF}' || echo "")
            
            if [[ "$sync_status" =~ ^[0-9]+$ ]] && [ "$sync_status" -lt 20 ]; then
                log "${GREEN}Синхронизация завершена! Out of sync: $sync_status секунд${NC}"
                return 0
            fi
        fi
        
        # Анимация ожидания
        local spinner_chars="⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        local spinner_index=$((attempt % 10))
        local spinner_char=${spinner_chars:$spinner_index:1}
        
        printf "\r${BLUE}Ожидание синхронизации...${NC} ${YELLOW}$spinner_char${NC} [Попытка $((attempt+1))/$max_attempts]"
        
        sleep 10
        ((attempt++))
    done
    
    printf "\n${YELLOW}Внимание: Синхронизация может занять больше времени${NC}\n"
    log "${YELLOW}Синхронизация не завершена за отведенное время${NC}"
}

# Функция проверки системы
check_system() {
    log "${GREEN}=== ПРОВЕРКА СИСТЕМЫ ===${NC}"
    
    # Проверка версии Ubuntu
    if [ ! -f /etc/lsb-release ]; then
        log "${RED}ОШИБКА: Не найден файл /etc/lsb-release${NC}"
        exit 1
    fi
    
    . /etc/lsb-release
    
    if [ "$DISTRIB_ID" != "Ubuntu" ]; then
        log "${RED}ОШИБКА: Поддерживается только Ubuntu${NC}"
        exit 1
    fi
    
    if [ "$DISTRIB_RELEASE" != "22.04" ]; then
        log "${YELLOW}Предупреждение: Рекомендуется Ubuntu 22.04${NC}"
    fi
    
    # Проверка свободного места
    local free_space=$(df / | tail -1 | awk '{print $4}')
    if [ "$free_space" -lt 10485760 ]; then  # 10GB в KB
        log "${RED}ОШИБКА: Недостаточно свободного места (минимум 10GB)${NC}"
        exit 1
    fi
    
    # Проверка оперативной памяти
    local total_ram=$(free -m | awk 'NR==2{print $2}')
    if [ "$total_ram" -lt 2048 ]; then  # 2GB в MB
        log "${YELLOW}Предупреждение: Рекомендуется минимум 2GB ОЗУ${NC}"
    fi
    
    log "${GREEN}Проверка системы завершена${NC}"
}

# Функция отображения статуса
show_status() {
    log "${GREEN}=== СТАТУС УСТАНОВКИ ===${NC}"
    
    # Проверка статуса сервисов
    if systemctl is-active --quiet ton-liteclient.service; then
        log "${GREEN}✓ TON Light Client: Активен${NC}"
    else
        log "${RED}✗ TON Light Client: Неактивен${NC}"
    fi
    
    if systemctl is-active --quiet mytoncore.service; then
        log "${GREEN}✓ MyTonCore: Активен${NC}"
    else
        log "${YELLOW}⚠ MyTonCore: Неактивен${NC}"
    fi
    
    # Проверка портов
    local port_status=$(netstat -tuln | grep -c ":.*:.*LISTEN" || echo "0")
    log "${BLUE}Открытых портов: $port_status${NC}"
    
    # Размер рабочей директории
    if [ -d "/var/ton-work" ]; then
        local work_size=$(du -sh /var/ton-work 2>/dev/null | cut -f1 || echo "N/A")
        log "${BLUE}Размер рабочей директории: $work_size${NC}"
    fi
    
    # Информация о пользователе
    log "${BLUE}Пользователь TON: $TON_USER${NC}"
    log "${BLUE}Рабочая директория: $WORKDIR${NC}"
    
    # Команды для управления
    log "${YELLOW}=== КОМАНДЫ УПРАВЛЕНИЯ ===${NC}"
    log "${BLUE}Запуск mytonctrl: sudo -u $TON_USER mytonctrl${NC}"
    log "${BLUE}Проверка статуса: systemctl status ton-liteclient${NC}"
    log "${BLUE}Просмотр логов: journalctl -u ton-liteclient -f${NC}"
    log "${BLUE}Остановка: systemctl stop ton-liteclient${NC}"
    log "${BLUE}Запуск: systemctl start ton-liteclient${NC}"
}

# Функция обработки ошибок
error_handler() {
    local exit_code=$?
    local line_no=$1
    
    log "${RED}ОШИБКА на строке $line_no: Код выхода $exit_code${NC}"
    log "${RED}Установка прервана${NC}"
    
    # Попытка очистки при ошибке
    log "${YELLOW}Попытка очистки...${NC}"
    clean > /dev/null 2>&1 || true
    
    exit $exit_code
}

# Установка обработчика ошибок
trap 'error_handler $LINENO' ERR

# Главная функция
main() {
    clear
    
    log "${BLUE}=================================================${NC}"
    log "${BLUE}    TON Light Client Auto-Installation Script    ${NC}"
    log "${BLUE}=================================================${NC}"
    log "${GREEN}Версия: 1.0${NC}"
    log "${GREEN}Дата: $(date)${NC}"
    log "${GREEN}Система: $(uname -a)${NC}"
    log "${BLUE}=================================================${NC}"
    
    # Создание лог-файла
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
    
    log "${GREEN}=================================================${NC}"
    log "${GREEN}  УСТАНОВКА ЗАВЕРШЕНА УСПЕШНО!${NC}"
    log "${GREEN}=================================================${NC}"
    log "${YELLOW}Для использования TON Light Client:${NC}"
    log "${BLUE}1. Подключитесь как пользователь $TON_USER: su - $TON_USER${NC}"
    log "${BLUE}2. Запустите mytonctrl: mytonctrl${NC}"
    log "${BLUE}3. Проверьте статус: status${NC}"
    log "${GREEN}=================================================${NC}"
}

# Запуск скрипта
main "$@"