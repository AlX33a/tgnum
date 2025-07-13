# GetGems Parser

Проект парсера офферов с уведомлением о значимом падении floor-price.

## Установка

pip install -r requirements.txt

text

## Конфигурация

Отредактируйте `config.yaml` в корне проекта.

## Запуск

Разовый запуск
python -m cli.main --profile prod --mode single

Непрерывная работа с уведомлениями
python -m cli.main --profile prod --mode continuous