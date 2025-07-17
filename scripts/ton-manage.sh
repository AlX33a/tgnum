#!/bin/bash

# TON Light Client Management Script
# Версия: 1.0
# Дата: 2025-01-18
# Описание: Скрипт для управления и мониторинга TON Light Client

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

TON_USER="tonuser"

# Функция отображения статуса
show_status() {
    echo -e "${BLUE}=== СТАТУС TON LIGHT CLIENT ===${NC}"
    
    # Статус сервисов
    if systemctl is-active --quiet ton-liteclient.service; then
        echo -e "${GREEN}✓ TON Light Client Service: АКТИВЕН${NC}"
    else
        echo -e "${RED}✗ TON Light Client Service: НЕАКТИВЕН${NC}"
    fi
    
    if systemctl is-active --quiet mytoncore.service; then
        echo -e "${GREEN}✓ MyTonCore Service: АКТИВЕН${NC}"
    else
        echo -e "${YELLOW}⚠ MyTonCore Service: НЕАКТИВЕН${NC}"
    fi
    
    # Проверка синхронизации
    if command -v mytonctrl &> /dev/null; then
        echo -e "${BLUE}Проверка синхронизации...${NC}"
        sudo -u "$TON_USER" timeout 10 mytonctrl -c "status" 2>/dev/null || echo -e "${YELLOW}Не удалось получить статус${NC}"
    fi
    
    # Использование ресурсов
    local cpu_usage=$(ps -eo pid,ppid,cmd,%mem,%cpu --sort=-%cpu | head -10 | grep -E "(lite-client|validator|mytonctrl)" || echo "Нет активных процессов")
    echo -e "${BLUE}Использование ресурсов:${NC}"
    echo "$cpu_usage"
    
    # Сетевая активность
    local network_connections=$(netstat -tuln | grep -c LISTEN || echo "0")
    echo -e "${BLUE}Активных соединений: $network_connections${NC}"
    
    # Размер данных
    if [ -d "/var/ton-work" ]; then
        local data_size=$(du -sh /var/ton-work 2>/dev/null | cut -f1 || echo "N/A")
        echo -e "${BLUE}Размер данных: $data_size${NC}"
    fi
}

# Функция проверки синхронизации
check_sync() {
    echo -e "${BLUE}=== ПРОВЕРКА СИНХРОНИЗАЦИИ ===${NC}"
    
    if ! command -v mytonctrl &> /dev/null; then
        echo -e "${RED}MyTonCtrl не найден${NC}"
        return 1
    fi
    
    local sync_info=$(sudo -u "$TON_USER" timeout 15 mytonctrl -c "status" 2>/dev/null | grep -i "out of sync")
    
    if [ -n "$sync_info" ]; then
        echo -e "${GREEN}$sync_info${NC}"
        
        local sync_seconds=$(echo "$sync_info" | grep -o '[0-9]\+' | tail -1)
        
        if [ -n "$sync_seconds" ] && [ "$sync_seconds" -lt 20 ]; then
            echo -e "${GREEN}✓ Нода синхронизирована (отставание: $sync_seconds сек)${NC}"
        elif [ -n "$sync_seconds" ] && [ "$sync_seconds" -lt 300 ]; then
            echo -e "${YELLOW}⚠ Нода почти синхронизирована (отставание: $sync_seconds сек)${NC}"
        else
            echo -e "${RED}✗ Нода не синхронизирована (отставание: $sync_seconds сек)${NC}"
        fi
    else
        echo -e "${YELLOW}Не удалось получить информацию о синхронизации${NC}"
    fi
}

# Функция запуска сервисов
start_services() {
    echo -e "${BLUE}=== ЗАПУСК СЕРВИСОВ ===${NC}"
    
    systemctl start ton-liteclient.service
    systemctl start mytoncore.service 2>/dev/null || echo -e "${YELLOW}MyTonCore не установлен${NC}"
    
    echo -e "${GREEN}Сервисы запущены${NC}"
}

# Функция остановки сервисов
stop_services() {
    echo -e "${BLUE}=== ОСТАНОВКА СЕРВИСОВ ===${NC}"
    
    systemctl stop ton-liteclient.service
    systemctl stop mytoncore.service 2>/dev/null || true
    
    echo -e "${GREEN}Сервисы остановлены${NC}"
}

# Функция перезапуска сервисов
restart_services() {
    echo -e "${BLUE}=== ПЕРЕЗАПУСК СЕРВИСОВ ===${NC}"
    
    systemctl restart ton-liteclient.service
    systemctl restart mytoncore.service 2>/dev/null || echo -e "${YELLOW}MyTonCore не установлен${NC}"
    
    echo -e "${GREEN}Сервисы перезапущены${NC}"
}

# Функция просмотра логов
view_logs() {
    echo -e "${BLUE}=== ПРОСМОТР ЛОГОВ ===${NC}"
    echo -e "${YELLOW}Нажмите Ctrl+C для выхода${NC}"
    
    journalctl -u ton-liteclient.service -f --no-pager
}

# Функция обновления
update_ton() {
    echo -e "${BLUE}=== ОБНОВЛЕНИЕ TON ===${NC}"
    
    if command -v mytonctrl &> /dev/null; then
        echo -e "${BLUE}Обновление через mytonctrl...${NC}"
        sudo -u "$TON_USER" mytonctrl -c "update"
    else
        echo -e "${YELLOW}MyTonCtrl не найден, пропуск обновления${NC}"
    fi
}

# Функция резервного копирования
backup_config() {
    echo -e "${BLUE}=== РЕЗЕРВНОЕ КОПИРОВАНИЕ ===${NC}"
    
    local backup_dir="/root/ton-backup-$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$backup_dir"
    
    # Копирование конфигурации
    if [ -d "/var/ton-work" ]; then
        cp -r /var/ton-work/keys "$backup_dir/" 2>/dev/null || true
        cp -r /var/ton-work/db/config.json "$backup_dir/" 2>/dev/null || true
    fi
    
    # Копирование настроек пользователя
    if [ -d "/home/$TON_USER/.local/share/mytoncore" ]; then
        cp -r "/home/$TON_USER/.local/share/mytoncore" "$backup_dir/" 2>/dev/null || true
    fi
    
    echo -e "${GREEN}Резервная копия создана: $backup_dir${NC}"
}

# Функция мониторинга в реальном времени
monitor() {
    echo -e "${BLUE}=== МОНИТОРИНГ В РЕАЛЬНОМ ВРЕМЕНИ ===${NC}"
    echo -e "${YELLOW}Нажмите Ctrl+C для выхода${NC}"
    
    while true; do
        clear
        echo -e "${BLUE}TON Light Client Monitor - $(date)${NC}"
        echo "=================================================="
        
        show_status
        check_sync
        
        echo "=================================================="
        echo -e "${YELLOW}Обновление через 30 секунд...${NC}"
        
        sleep 30
    done
}

# Функция отображения помощи
show_help() {
    echo -e "${BLUE}=== ПОМОЩЬ ===${NC}"
    echo "Использование: $0 [команда]"
    echo
    echo "Команды:"
    echo "  status      - Показать статус сервисов"
    echo "  sync        - Проверить синхронизацию"
    echo "  start       - Запустить сервисы"
    echo "  stop        - Остановить сервисы"
    echo "  restart     - Перезапустить сервисы"
    echo "  logs        - Просмотр логов"
    echo "  update      - Обновить TON"
    echo "  backup      - Создать резервную копию"
    echo "  monitor     - Мониторинг в реальном времени"
    echo "  help        - Показать эту справку"
    echo
    echo "Примеры:"
    echo "  $0 status"
    echo "  $0 monitor"
    echo "  $0 logs"
}

# Основная функция
main() {
    if [ "$EUID" -ne 0 ]; then
        echo -e "${RED}ОШИБКА: Скрипт должен запускаться с правами root${NC}"
        exit 1
    fi
    
    case "${1:-status}" in
        "status")
            show_status
            ;;
        "sync")
            check_sync
            ;;
        "start")
            start_services
            ;;
        "stop")
            stop_services
            ;;
        "restart")
            restart_services
            ;;
        "logs")
            view_logs
            ;;
        "update")
            update_ton
            ;;
        "backup")
            backup_config
            ;;
        "monitor")
            monitor
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