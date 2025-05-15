import asyncio
import json
import os
import re
import sys

import aiohttp
from bs4 import BeautifulSoup
from camoufox.async_api import AsyncCamoufox
from loguru import logger

from config import COOKIES, LOGIN, PASSWORD


class YooMoneyQRClient:
    def __init__(self, login: str, password: str):
        self.login = login
        self.password = password
        self.cookies = {}
        self.secret_key = None
        self.user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0'
        self.cache_path = COOKIES
        self._load_auth_cache()
        self._otp_code = None
        self._otp_event = asyncio.Event()

    async def provide_otp(self, code: str):
        self._otp_code = code
        self._otp_event.set()

    async def process_qr(self, qr_data: str):
        redirect_info = await self._send_qr_payment(qr_data)
        if 'redirectUrl' not in redirect_info:
            raise Exception(
                f'Ошибка при получении redirectUrl: {redirect_info}'
            )
        html = await self._shop_request(redirect_info['redirectUrl'])
        return self._parse_html(html)

    def _load_auth_cache(self):
        dir_path = os.path.dirname(self.cache_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        if not os.path.exists(self.cache_path):
            logger.info('Кеш не найден. Создаём новый файл авторизации.')
            with open(self.cache_path, 'w', encoding='utf-8') as f:
                json.dump(
                    {'cookies': {}, 'secret_key': None},
                    f,
                    ensure_ascii=False,
                    indent=2,
                )

        with open(self.cache_path, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
                self.cookies = data.get('cookies', {})
                self.secret_key = data.get('secret_key')
                if self.secret_key:
                    logger.info('Загружен secret_key из кеша.')
            except json.JSONDecodeError:
                logger.warning(
                    'Ошибка при чтении кеша авторизации. Используем пустые значения.'
                )
                self.cookies = {}
                self.secret_key = None

    async def _get_cookies(self):
        logger.info('Получение cookies и secret_key через браузер...')
        async with AsyncCamoufox(headless=True) as browser:  # headless=True
            page = await browser.new_page()
            await page.goto('https://yoomoney.ru/main')
            await page.wait_for_load_state('load')

            logger.info('Ввод логина...')
            await page.wait_for_selector("input[name='login']", timeout=10000)
            await page.fill("input[name='login']", self.login)
            await page.click("button[type='submit']")
            await page.wait_for_load_state('load')

            logger.info('Ввод пароля...')
            await page.wait_for_selector(
                "input[name='password']", timeout=10000
            )
            await page.fill("input[name='password']", self.password)
            await page.click("button[type='submit']")
            await page.wait_for_load_state('load')

            logger.info('Проверка, появился ли ввод 2FA (OTP)...')
            try:
                await page.wait_for_selector(
                    "input[placeholder='Text message code']", timeout=10000
                )
                logger.info('Поле для ввода 2FA-кода найдено.')

                logger.info('Ожидание ввода кода через provide_otp...')
                await self._otp_event.wait()
                code = self._otp_code

                logger.info(f'Ввод 2FA-кода: {code}')
                await page.fill("input[placeholder='Text message code']", code)
                await asyncio.sleep(1)
                await page.keyboard.press('Enter')

                await page.wait_for_load_state('load')
                await asyncio.sleep(5)
            except Exception:
                logger.info(
                    'Поле для 2FA-кода не найдено. Продолжаем без него.'
                )

            cookies = await page.context.cookies()
            self.cookies = {
                cookie['name']: cookie['value'] for cookie in cookies
            }
            logger.success(f'Получено {len(self.cookies)} cookies.')

            html = await page.content()
            soup = BeautifulSoup(html, 'html.parser')
            script_tags = soup.find_all('script')

            for script in script_tags:
                if script.string:
                    match = re.search(r'"secretKey":"([^"]+)"', script.string)
                    if match:
                        self.secret_key = match.group(1)
                        logger.success('Извлечён secret_key из HTML.')
                        break

            with open(self.cache_path, 'w', encoding='utf-8') as f:
                json.dump(
                    {'cookies': self.cookies, 'secret_key': self.secret_key},
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
                logger.info('Авторизационные данные сохранены в кеш.')

    async def _send_qr_payment(self, qr_data: str):
        if not self.cookies or not self.secret_key:
            logger.warning('Нет cookies или ключа — выполняем авторизацию.')
            await self._get_cookies()

        headers = {
            'accept': 'application/json, text/plain, */*',
            'x-csrf-token': self.secret_key,
            'user-agent': self.user_agent,
            'content-type': 'application/json',
        }

        url = 'https://yoomoney.ru/user-entrance/api/qr-payment/parse'
        data = {'data': qr_data}

        logger.info('Отправка QR-кода на парсинг...')
        async with aiohttp.ClientSession(
            cookies=self.cookies, headers=headers
        ) as session:
            async with session.post(url, json=data) as resp:
                result = await resp.json()

        if result.get('error'):
            error = result['error']
            logger.error(f'Ошибка при парсинге QR: {error}')
            if (
                error.get('status_code') == 404
                and error.get('status') == 'Not Found'
            ):
                logger.warning('Повторная авторизация из-за 404 ошибки.')
                await self._get_cookies()
                return await self._send_qr_payment(qr_data)

        logger.success('QR успешно обработан.')
        return result

    async def _shop_request(self, url: str):
        logger.info(f'Запрос HTML страницы магазина: {url}')
        headers = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'user-agent': self.user_agent,
            'content-type': 'text/html; charset=utf-8',
        }

        async with aiohttp.ClientSession(
            cookies=self.cookies, headers=headers
        ) as session:
            async with session.get(url) as resp:
                return await resp.text()

    @staticmethod
    def _parse_html(html: str):
        logger.info('Парсинг HTML страницы оплаты...')
        soup = BeautifulSoup(html, 'html.parser')
        data = {
            'sum': soup.find('input', {'name': 'sum'}).get('value'),
            'currency': soup.find('input', {'name': 'currency'}).get('value'),
            'recipient': soup.find('input', {'name': 'brandName'}).get(
                'value'
            ),
            'legalname': soup.find('textarea', {'name': 'legalName'}).get(
                'value'
            ),
            'payment': soup.find('textarea', {'name': 'paymentPurpose'}).get(
                'value'
            ),
        }
        logger.success(f'Данные успешно извлечены: {data}')
        return data


# Пример запуска
if __name__ == '__main__':
    qr_data = 'https://qr.nspk.ru/AD20003FNSGB5S1G8IJPACMUOLTR9SOJ?type=02&bank=100000000001&sum=10700&cur=RUB&crc=B770'

    client = YooMoneyQRClient(LOGIN, PASSWORD)

    result = asyncio.run(client.process_qr(qr_data))
    print('\nРезультат:\n', result)
