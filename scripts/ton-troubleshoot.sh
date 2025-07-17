#!/bin/bash

# TON Light Client Troubleshooting Script
# Версия: 1.0
# Дата: 2025-01-18
# Описание: Автоматическая диагностика и исправление проблем TON Light Client

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

TON_USER="tonuser"
LOG_FILE="/var/log/ton-troubleshoot.log"

# Функция логирования
log() {
    echo -e "$1" | tee -a "$LOG_FILE"
}

# Функция проверки системы
check_system() {
    log "${BLUE}=== ПРОВЕРКА СИСТЕМЫ ===${NC}"
    
    local issues=0
    
    # Проверка ОС
    if [ ! -f /etc/lsb-release ]; then
        log "${RED}✗ Файл /etc/lsb-release не найден${NC}"
        ((issues++))
    else
        . /etc/lsb-release
        if [ "$DISTRIB_ID" != "Ubuntu" ] || [ "$DISTRIB_RELEASE" != "22.04" ]; then
            log "${YELLOW}⚠ Обнаружена несовместимая ОС: $DISTRIB_ID $DISTRIB_RELEASE${NC}"
            ((issues++))
        else
            log "${GREEN}✓ ОС: Ubuntu 22.04${NC}"
        fi
    fi
    
    # Проверка свободного места
    local free_space=$(df / | tail -1 | awk '{print $4}')
    if [ "$free_space" -lt 5242880 ]; then  # 5GB в KB
        log "${RED}✗ Недостаточно свободного места: $(($free_space / 1024))MB${NC}"
        ((issues++))
    else
        log "${GREEN}✓ Свободного места: $(($free_space / 1024))MB${NC}"
    fi
    
    # Проверка RAM
    local total_ram=$(free -m | awk 'NR==2{print $2}')
    if [ "$total_ram" -lt 1024 ]; then
        log "${RED}✗ Недостаточно RAM: ${total_ram}MB${NC}"
        ((issues++))
    else
        log "${GREEN}✓ RAM: ${total_ram}MB${NC}"
    fi
    
    # Проверка интернет-соединения
    if ! ping -c 1 -W 3 ton.org &> /dev/null; then
        log "${RED}✗ Нет подключения к интернету${NC}"
        ((issues++))
    else
        log "${GREEN}✓ Интернет-соединение активно${NC}"
    fi
    
    return $issues
}

# Функция проверки зависимостей
check_dependencies() {
    log "${BLUE}=== ПРОВЕРКА ЗАВИСИМОСТЕЙ ===${NC}"
    
    local issues=0
    local deps="build-essential cmake clang git ninja-build zlib1g-dev libssl-dev libsecp256k1-dev libmicrohttpd-dev libsodium-dev pkg-config gperf libreadline-dev ccache"
    
    for dep in $deps; do
        if ! dpkg -l | grep -q "^ii  $dep "; then
            log "${RED}✗ Отсутствует пакет: $dep${NC}"
            ((issues++))
        else
            log "${GREEN}✓ Установлен: $dep${NC}"
        fi
    done
    
    # Проверка компиляторов
    if ! command -v clang &> /dev/null; then
        log "${RED}✗ Компилятор clang не найден${NC}"
        ((issues++))
    else
        log "${GREEN}✓ Компилятор clang доступен${NC}"
    fi
    
    if ! command -v cmake &> /dev/null; then
        log "${RED}✗ CMake не найден${NC}"
        ((issues++))
    else
        log "${GREEN}✓ CMake доступен${NC}"
    fi
    
    return $issues
}

# Функция проверки пользователя
check_user() {
    log "${BLUE}=== ПРОВЕРКА ПОЛЬЗОВАТЕЛЯ ===${NC}"
    
    local issues=0
    
    if ! id "$TON_USER" &>/dev/null; then
        log "${RED}✗ Пользователь $TON_USER не существует${NC}"
        ((issues++))
    else
        log "${GREEN}✓ Пользователь $TON_USER существует${NC}"
        
        # Проверка домашней директории
        if [ ! -d "/home/$TON_USER" ]; then
            log "${RED}✗ Домашняя директория /home/$TON_USER не найдена${NC}"
            ((issues++))
        else
            log "${GREEN}✓ Домашняя директория существует${NC}"
        fi
        
        # Проверка прав sudo
        if ! sudo -u "$TON_USER" sudo -n true 2>/dev/null; then
            log "${YELLOW}⚠ Пользователь $TON_USER не имеет прав sudo${NC}"
        else
            log "${GREEN}✓ Права sudo настроены${NC}"
        fi
    fi
    
    return $issues
}

# Функция проверки сервисов
check_services() {
    log "${BLUE}=== ПРОВЕРКА СЕРВИСОВ ===${NC}"
    
    local issues=0
    
    # Проверка сервиса ton-liteclient
    if systemctl is-active --quiet ton-liteclient.service; then
        log "${GREEN}✓ Сервис ton-liteclient активен${NC}"
    else
        log "${RED}✗ Сервис ton-liteclient неактивен${NC}"
        ((issues++))
    fi
    
    # Проверка сервиса mytoncore
    if systemctl is-active --quiet mytoncore.service; then
        log "${GREEN}✓ Сервис mytoncore активен${NC}"
    else
        log "${YELLOW}⚠ Сервис mytoncore неактивен${NC}"
    fi
    
    # Проверка файлов сервисов
    if [ ! -f "/etc/systemd/system/ton-liteclient.service" ]; then
        log "${RED}✗ Файл сервиса ton-liteclient не найден${NC}"
        ((issues++))
    else
        log "${GREEN}✓ Файл сервиса ton-liteclient существует${NC}"
    fi
    
    return $issues
}

# Функция проверки файлов TON
check_ton_files() {
    log "${BLUE}=== ПРОВЕРКА ФАЙЛОВ TON ===${NC}"
    
    local issues=0
    
    # Проверка исполняемых файлов
    if [ ! -f "/usr/bin/ton/lite-client/lite-client" ]; then
        log "${RED}✗ lite-client не найден${NC}"
        ((issues++))
    else
        log "${GREEN}✓ lite-client найден${NC}"
    fi
    
    # Проверка конфигурации
    if [ ! -f "/usr/bin/ton/global.config.json" ]; then
        log "${RED}✗ global.config.json не найден${NC}"
        ((issues++))
    else
        log "${GREEN}✓ global.config.json найден${NC}"
    fi
    
    # Проверка рабочей директории
    if [ ! -d "/var/ton-work" ]; then
        log "${RED}✗ Рабочая директория /var/ton-work не найдена${NC}"
        ((issues++))
    else
        log "${GREEN}✓ Рабочая директория существует${NC}"
        
        # Проверка прав доступа
        local owner=$(stat -c %U /var/ton-work)
        if [ "$owner" != "$TON_USER" ]; then
            log "${YELLOW}⚠ Неправильный владелец /var/ton-work: $owner${NC}"
        else
            log "${GREEN}✓ Права доступа к /var/ton-work корректны${NC}"
        fi
    fi
    
    return $issues
}

# Функция проверки синхронизации
check_sync() {
    log "${BLUE}=== ПРОВЕРКА СИНХРОНИЗАЦИИ ===${NC}"
    
    local issues=0
    
    if command -v mytonctrl &> /dev/null; then
        local sync_info=$(sudo -u "$TON_USER" timeout 10 mytonctrl -c "status" 2>/dev/null | grep -i "out of sync" || echo "")
        
        if [ -n "$sync_info" ]; then
            local sync_seconds=$(echo "$sync_info" | grep -o '[0-9]\+' | tail -1)
            
            if [ -n "$sync_seconds" ]; then
                if [ "$sync_seconds" -lt 20 ]; then
                    log "${GREEN}✓ Нода синхронизирована (отставание: $sync_seconds сек)${NC}"
                elif [ "$sync_seconds" -lt 300 ]; then
                    log "${YELLOW}⚠ Нода почти синхронизирована (отставание: $sync_seconds сек)${NC}"
                else
                    log "${RED}✗ Нода не синхронизирована (отставание: $sync_seconds сек)${NC}"
                    ((issues++))
                fi
            else
                log "${RED}✗ Не удалось получить статус синхронизации${NC}"
                ((issues++))
            fi
        else
            log "${RED}✗ Нет данных о синхронизации${NC}"
            ((issues++))
        fi
    else
        log "${RED}✗ mytonctrl не найден${NC}"
        ((issues++))
    fi
    
    return $issues
}

# Функция автоматического исправления
auto_fix() {
    log "${BLUE}=== АВТОМАТИЧЕСКОЕ ИСПРАВЛЕНИЕ ===${NC}"
    
    # Исправление зависимостей
    log "${YELLOW}Обновление пакетов...${NC}"
    apt-get update -y
    apt-get --fix-broken install -y
    
    # Установка недостающих зависимостей
    log "${YELLOW}Установка зависимостей...${NC}"
    apt-get install -y build-essential cmake clang git ninja-build zlib1g-dev libssl-dev libsecp256k1-dev libmicrohttpd-dev libsodium-dev pkg-config gperf libreadline-dev ccache
    
    # Создание пользователя если отсутствует
    if ! id "$TON_USER" &>/dev/null; then
        log "${YELLOW}Создание пользователя $TON_USER...${NC}"
        adduser --disabled-password --gecos "" "$TON_USER"
        usermod -aG sudo "$TON_USER"
        echo "$TON_USER:ton123" | chpasswd
    fi
    
    # Исправление прав доступа
    if [ -d "/var/ton-work" ]; then
        log "${YELLOW}Исправление прав доступа...${NC}"
        chown -R "$TON_USER:$TON_USER" /var/ton-work
        chmod -R 755 /var/ton-work
    fi
    
    # Перезагрузка сервисов
    log "${YELLOW}Перезагрузка сервисов...${NC}"
    systemctl daemon-reload
    systemctl restart ton-liteclient.service 2>/dev/null || true
    systemctl restart mytoncore.service 2>/dev/null || true
    
    log "${GREEN}Автоматическое исправление завершено${NC}"
}

# Функция генерации отчета
generate_report() {
    log "${BLUE}=== ГЕНЕРАЦИЯ ОТЧЕТА ===${NC}"
    
    local report_file="/tmp/ton-diagnostic-report-$(date +%Y%m%d_%H%M%S).txt"
    
    cat > "$report_file" << EOF
TON Light Client Diagnostic Report
Generated: $(date)
System: $(uname -a)

=== SYSTEM INFO ===
OS: $(lsb_release -d | cut -f2)
Kernel: $(uname -r)
Uptime: $(uptime)
Free Space: $(df -h / | tail -1 | awk '{print $4}')
RAM: $(free -h | awk 'NR==2{print $2}')

=== SERVICES STATUS ===
ton-liteclient: $(systemctl is-active ton-liteclient.service 2>/dev/null || echo "inactive")
mytoncore: $(systemctl is-active mytoncore.service 2>/dev/null || echo "inactive")

=== FILES STATUS ===
lite-client: $([ -f "/usr/bin/ton/lite-client/lite-client" ] && echo "exists" || echo "missing")
config: $([ -f "/usr/bin/ton/global.config.json" ] && echo "exists" || echo "missing")
work dir: $([ -d "/var/ton-work" ] && echo "exists" || echo "missing")

=== PROCESSES ===
$(ps aux | grep -E "(lite-client|validator|mytonctrl)" | grep -v grep || echo "No TON processes found")

=== NETWORK ===
$(netstat -tuln | grep LISTEN | head -5)

=== RECENT LOGS ===
$(journalctl -u ton-liteclient.service --no-pager -n 10 2>/dev/null || echo "No logs available")

=== DISK USAGE ===
$(df -h)

=== MEMORY USAGE ===
$(free -h)

EOF
    
    log "${GREEN}Отчет сохранен: $report_file${NC}"
    echo "$report_file"
}

# Функция полной диагностики
full_diagnostic() {
    log "${BLUE}=== ПОЛНАЯ ДИАГНОСТИКА ===${NC}"
    
    local total_issues=0
    
    check_system
    total_issues=$((total_issues + $?))
    
    check_dependencies
    total_issues=$((total_issues + $?))
    
    check_user
    total_issues=$((total_issues + $?))
    
    check_services
    total_issues=$((total_issues + $?))
    
    check_ton_files
    total_issues=$((total_issues + $?))
    
    check_sync
    total_issues=$((total_issues + $?))
    
    log "${BLUE}=== РЕЗУЛЬТАТЫ ДИАГНОСТИКИ ===${NC}"
    
    if [ $total_issues -eq 0 ]; then
        log "${GREEN}✓ Проблем не обнаружено${NC}"
    else
        log "${RED}✗ Обнаружено проблем: $total_issues${NC}"
        
        echo -e "${YELLOW}Хотите запустить автоматическое исправление? (y/n)${NC}"
        read -r answer
        
        if [ "$answer" = "y" ] || [ "$answer" = "Y" ]; then
            auto_fix
        fi
    fi
    
    return $total_issues
}

# Функция отображения справки
show_help() {
    echo -e "${BLUE}=== СПРАВКА ===${NC}"
    echo "Использование: $0 [команда]"
    echo
    echo "Команды:"
    echo "  full        - Полная диагностика"
    echo "  system      - Проверка системы"
    echo "  deps        - Проверка зависимостей"
    echo "  user        - Проверка пользователя"
    echo "  services    - Проверка сервисов"
    echo "  files       - Проверка файлов TON"
    echo "  sync        - Проверка синхронизации"
    echo "  fix         - Автоматическое исправление"
    echo "  report      - Генерация отчета"
    echo "  help        - Показать справку"
    echo
    echo "Примеры:"
    echo "  $0 full"
    echo "  $0 fix"
    echo "  $0 report"
}

# Основная функция
main() {
    if [ "$EUID" -ne 0 ]; then
        echo -e "${RED}ОШИБКА: Скрипт должен запускаться с правами root${NC}"
        exit 1
    fi
    
    # Создание лог-файла
    touch "$LOG_FILE"
    chmod 644 "$LOG_FILE"
    
    case "${1:-full}" in
        "full")
            full_diagnostic
            ;;
        "system")
            check_system
            ;;
        "deps")
            check_dependencies
            ;;
        "user")
            check_user
            ;;
        "services")
            check_services
            ;;
        "files")
            check_ton_files
            ;;
        "sync")
            check_sync
            ;;
        "fix")
            auto_fix
            ;;
        "report")
            generate_report
            ;;
        "help"|"-h"|"--help")
            show_help
            ;;
        *)
            echo -e "${RED}Неизвестная команда: $1${NC}"
            show_help
            exit 1
            ;;
    esac
}

# Запуск скрипта
main "$@"