import logging
from typing import Dict, Optional

import aiohttp

from settings import CRYPTOBOT_TOKEN

logger = logging.getLogger(__name__)


class CryptoBot:
    """Класс для работы с CryptoBot API"""
    
    def __init__(self, token: str):
        self.token = token
        self.base_url = "https://testnet-pay.crypt.bot/api"
        self.headers = {
            "Crypto-Pay-API-Token": token
        }
    
    async def create_invoice(self, amount: float, currency: str, 
                           description: str, payload: str) -> Optional[Dict]:
        """Создать инвойс для оплаты"""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/createInvoice"
                data = {
                    "amount": str(amount),
                    "currency_type": "crypto",
                    "asset": currency,
                    "description": description,
                    "payload": payload,
                    "paid_btn_name": "callback",
                    "paid_btn_url": "https://t.me/your_bot"
                }
                
                async with session.post(url, headers=self.headers, json=data) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        if result.get('ok'):
                            return result.get('result')
                    logger.error(f"CryptoBot API error: {await resp.text()}")
                    return None
        except Exception as e:
            logger.error(f"CryptoBot create_invoice error: {e}")
            return None
    
    async def get_invoice(self, invoice_id: int) -> Optional[Dict]:
        """Получить информацию об инвойсе"""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/getInvoices"
                params = {"invoice_ids": str(invoice_id)}
                
                async with session.get(url, headers=self.headers, params=params) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        if result.get('ok') and result.get('result', {}).get('items'):
                            return result['result']['items'][0]
                    return None
        except Exception as e:
            logger.error(f"CryptoBot get_invoice error: {e}")
            return None

    async def transfer(self, user_id: int, amount: float,
                       currency: str, spend_id: str) -> Optional[Dict]:
        """Перевести средства пользователю"""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/transfer"
                data = {
                    "user_id": user_id,
                    "amount": str(amount),
                    "asset": currency,
                    "spend_id": spend_id
                }

                async with session.post(url, headers=self.headers, json=data) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        if result.get('ok'):
                            return result.get('result')
                    logger.error(f"CryptoBot transfer error: {await resp.text()}")
                    return None
        except Exception as e:
            logger.error(f"CryptoBot transfer error: {e}")
            return None
    
    async def get_balance(self) -> Optional[Dict]:
        """Получить баланс бота"""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/getBalance"
                
                async with session.get(url, headers=self.headers) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        if result.get('ok'):
                            return result.get('result')
                    return None
        except Exception as e:
            logger.error(f"CryptoBot get_balance error: {e}")
            return None

crypto_bot = CryptoBot(CRYPTOBOT_TOKEN)

