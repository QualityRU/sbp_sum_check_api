# FastAPI YooMoney QR Payment Integration

Проект для интеграции с YooMoney.ru через QR-коды и одноразовые пароли (OTP). Реализован с использованием:

- FastAPI
- Camoufox
- BeautifulSoup
- Loguru

## Установка
1. Клонируйте репозиторий:
```
git clone https://github.com/QualityRU/sbp_sum_check_api
.git
cd sbp_sum_check_api
```
2. Установите зависимости:
```
pip install -r requirements.txt
```
3. Переименовать .env.example в .env и заполнить его

## Запуск
```
python3 main.py
```
или
```
uvicorn app.main:app --reload
```