# TON Light Client - Инструкция по использованию

## Описание

Данный комплект скриптов предназначен для автоматической установки, настройки и управления TON Light Client на Ubuntu 22.04. Скрипты обеспечивают:

- Полную очистку предыдущих установок
- Автоматическую установку всех необходимых зависимостей
- Сборку и настройку TON Light Client через mytonctrl
- Мониторинг процесса синхронизации
- Управление сервисами
- Анимированные индикаторы прогресса

## Состав

1. **ton-light-client-install.sh** - Основной скрипт установки
2. **ton-manage.sh** - Скрипт управления и мониторинга
3. **README.md** - Данная инструкция

## Системные требования

### Минимальные требования:
- Ubuntu 22.04 LTS
- 2GB RAM
- 20GB свободного места на диске
- Подключение к интернету

### Рекомендуемые требования:
- Ubuntu 22.04 LTS
- 4GB RAM
- 50GB свободного места на диске
- Стабильное подключение к интернету (100+ Mbps)

## Установка

### 1. Скачайте скрипты

```bash
# Скачивание основного скрипта
wget -O ton-light-client-install.sh [URL_TO_SCRIPT]

# Скачивание скрипта управления
wget -O ton-manage.sh [URL_TO_SCRIPT]

# Установка прав на выполнение
chmod +x ton-light-client-install.sh
chmod +x ton-manage.sh
```

### 2. Запуск установки

```bash
# ВАЖНО: Запускайте от пользователя root
sudo bash ton-light-client-install.sh
```

### 3. Процесс установки

Скрипт автоматически выполнит следующие этапы:

1. **Проверка системы** - Проверка совместимости и требований
2. **Создание пользователя** - Создание специального пользователя `tonuser`
3. **Очистка** - Удаление предыдущих установок TON
4. **Установка зависимостей** - Установка build-essential, cmake, библиотек
5. **Сборка TON** - Компиляция и установка TON Light Client
6. **Запуск сервисов** - Настройка и запуск systemd сервисов
7. **Ожидание синхронизации** - Мониторинг процесса синхронизации

## Использование

### Основные команды

```bash
# Проверка статуса
sudo ./ton-manage.sh status

# Проверка синхронизации
sudo ./ton-manage.sh sync

# Запуск сервисов
sudo ./ton-manage.sh start

# Остановка сервисов
sudo ./ton-manage.sh stop

# Перезапуск сервисов
sudo ./ton-manage.sh restart

# Просмотр логов
sudo ./ton-manage.sh logs

# Мониторинг в реальном времени
sudo ./ton-manage.sh monitor

# Создание резервной копии
sudo ./ton-manage.sh backup

# Обновление TON
sudo ./ton-manage.sh update
```

### Работа с MyTonCtrl

```bash
# Подключение как пользователь tonuser
sudo su - tonuser

# Запуск MyTonCtrl
mytonctrl

# Основные команды в MyTonCtrl
status          # Показать статус ноды
status fast     # Быстрая проверка статуса (для testnet)
help            # Показать справку
quit            # Выйти из MyTonCtrl
```

## Мониторинг и диагностика

### Проверка сервисов

```bash
# Статус сервисов
systemctl status ton-liteclient
systemctl status mytoncore

# Просмотр логов
journalctl -u ton-liteclient -f
journalctl -u mytoncore -f
```

### Индикаторы синхронизации

- **Local validator out of sync < 20 секунд** - Полная синхронизация
- **Local validator out of sync < 300 секунд** - Почти синхронизировано
- **Local validator out of sync > 300 секунд** - Требуется ожидание

### Файловая структура

```
/var/ton-work/          # Рабочая директория TON
├── db/                 # База данных
├── keys/               # Ключи
└── log.thread*         # Логи

/home/tonuser/          # Домашняя директория пользователя
└── .local/share/mytoncore/  # Конфигурация MyTonCtrl

/etc/systemd/system/
├── ton-liteclient.service   # Сервис Light Client
└── mytoncore.service       # Сервис MyTonCore
```

## Устранение проблем

### Частые проблемы

1. **Нода не синхронизируется**
   ```bash
   # Проверьте подключение к интернету
   ping ton.org
   
   # Перезапустите сервисы
   sudo ./ton-manage.sh restart
   
   # Проверьте логи
   sudo ./ton-manage.sh logs
   ```

2. **Ошибки при установке зависимостей**
   ```bash
   # Обновите репозитории
   sudo apt update
   
   # Исправьте поврежденные пакеты
   sudo apt --fix-broken install
   
   # Переустановите зависимости
   sudo apt install --reinstall build-essential cmake
   ```

3. **Недостаточно места на диске**
   ```bash
   # Проверьте использование диска
   df -h
   
   # Очистите системные логи
   sudo journalctl --vacuum-time=7d
   
   # Удалите ненужные пакеты
   sudo apt autoremove
   ```

4. **Проблемы с правами доступа**
   ```bash
   # Проверьте владельца файлов
   ls -la /var/ton-work/
   
   # Исправьте права
   sudo chown -R tonuser:tonuser /var/ton-work/
   ```

### Логи для диагностики

```bash
# Основные логи
tail -f /var/log/ton-install.log          # Лог установки
tail -f /var/ton-work/log.thread*          # Логи TON ноды
tail -f ~/.local/share/mytoncore/mytoncore.log  # Логи MyTonCore

# Системные логи
journalctl -u ton-liteclient -f --no-pager
journalctl -u mytoncore -f --no-pager
```

## Обновление

```bash
# Обновление через MyTonCtrl
sudo su - tonuser
mytonctrl
update

# Или через скрипт управления
sudo ./ton-manage.sh update
```

## Удаление

```bash
# Остановка сервисов
sudo ./ton-manage.sh stop

# Удаление сервисов
sudo systemctl disable ton-liteclient
sudo systemctl disable mytoncore

# Удаление файлов
sudo rm -rf /var/ton-work/
sudo rm -rf /usr/src/ton
sudo rm -rf /usr/src/mytonctrl
sudo userdel -r tonuser
```

## Полезные команды

### Проверка производительности

```bash
# Использование CPU и памяти
htop

# Сетевая активность
iftop

# Использование диска
iotop

# Статистика TON
sudo -u tonuser mytonctrl -c "status"
```

### Резервное копирование

```bash
# Создание резервной копии
sudo ./ton-manage.sh backup

# Восстановление из резервной копии
sudo cp -r /root/ton-backup-*/keys /var/ton-work/
sudo cp -r /root/ton-backup-*/mytoncore /home/tonuser/.local/share/
sudo chown -R tonuser:tonuser /home/tonuser/.local/share/mytoncore
```

## Безопасность

### Рекомендации

1. **Используйте фаервол**
   ```bash
   sudo ufw enable
   sudo ufw allow ssh
   sudo ufw allow from any to any port 3278 proto udp  # TON DHT
   ```

2. **Регулярно обновляйте систему**
   ```bash
   sudo apt update && sudo apt upgrade
   ```

3. **Мониторьте логи**
   ```bash
   sudo ./ton-manage.sh monitor
   ```

4. **Создавайте резервные копии**
   ```bash
   sudo ./ton-manage.sh backup
   ```

## Поддержка

При возникновении проблем:

1. Проверьте логи установки: `/var/log/ton-install.log`
2. Запустите диагностику: `sudo ./ton-manage.sh status`
3. Посетите официальную документацию: https://docs.ton.org/
4. Обратитесь в сообщество TON

## Лицензия

Скрипты распространяются под лицензией MIT. TON Blockchain - проект с открытым исходным кодом.

## Версия

- **Версия скрипта**: 1.0
- **Дата**: 2025-01-18
- **Поддерживаемые системы**: Ubuntu 22.04 LTS
- **Совместимость**: TON Blockchain latest version