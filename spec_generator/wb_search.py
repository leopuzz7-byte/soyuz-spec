"""
Поиск товаров на Wildberries + получение фотографий.

Ключевое: используем persistent Session с cookies — как настоящий браузер.
Это решает проблему 429 (rate limit).
"""

import requests
import io
import time
import random
from typing import Optional
from PIL import Image


# ─── Глобальная сессия (инициализируется один раз) ────────────────────────────
_session: Optional[requests.Session] = None
_wb_blocked: bool = False  # если IP заблокирован — не тратим время на WB


def _get_session() -> requests.Session:
    """
    Возвращает сессию с cookies WB.
    При первом вызове заходит на главную WB чтобы получить cookies.
    """
    global _session
    if _session is not None:
        return _session

    _session = requests.Session()
    _session.headers.update({
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/136.0.0.0 Safari/537.36'
        ),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.9',
    })

    # Получаем cookies — имитируем первый заход на сайт
    try:
        print('[WB] Инициализирую сессию (получаю cookies)...')
        _session.get('https://www.wildberries.ru/', timeout=15)
        time.sleep(2)
        print('[WB] Сессия готова')
    except Exception as e:
        print(f'[WB] Ошибка инициализации сессии: {e}')

    # После инициализации — заголовки для API-запросов
    _session.headers.update({
        'Accept': 'application/json, text/plain, */*',
        'Referer': 'https://www.wildberries.ru/',
        'Origin': 'https://www.wildberries.ru',
    })

    return _session


def get_basket_num(vol: int) -> int:
    """Определяет номер сервера (basket) по vol-части nmId."""
    ranges = [
        (0,    143,  1),  (144,  287,  2),  (288,  431,  3),
        (432,  719,  4),  (720,  1007, 5),  (1008, 1061, 6),
        (1062, 1115, 7),  (1116, 1169, 8),  (1170, 1313, 9),
        (1314, 1601, 10), (1602, 1655, 11), (1656, 1919, 12),
        (1920, 2045, 13), (2046, 2189, 14), (2190, 2405, 15),
        (2406, 2621, 16), (2622, 2837, 17), (2838, 3053, 18),
        (3054, 3269, 19), (3270, 3485, 20), (3486, 3701, 21),
        (3702, 3917, 22), (3918, 4133, 23), (4134, 4349, 24),
        (4350, 4565, 25), (4566, 4781, 26), (4782, 4997, 27),
        (4998, 5213, 28), (5214, 5429, 29), (5430, 5645, 30),
        (5646, 5861, 31), (5862, 6077, 32), (6078, 6293, 33),
        (6294, 6509, 34), (6510, 6725, 35), (6726, 6941, 36),
        (6942, 7157, 37), (7158, 7373, 38), (7374, 7589, 39),
        (7590, 7805, 40), (7806, 8021, 41), (8022, 8237, 42),
        (8238, 8453, 43),
    ]
    for start, end, num in ranges:
        if start <= vol <= end:
            return num
    return 43 + (vol - 8453) // 216 + 1


def get_photo_url(nm_id: int, photo_num: int = 1, size: str = 'c516x688') -> str:
    vol = nm_id // 100000
    part = nm_id // 1000
    basket = get_basket_num(vol)
    return (
        f'https://basket-{basket:02d}.wbbasket.ru'
        f'/vol{vol}/part{part}/{nm_id}/images/{size}/{photo_num}.jpg'
    )


def search_wb(query: str, limit: int = 5) -> list:
    """
    Поиск товаров на WB (v18 API) с сессионными cookies.
    Если IP заблокирован (2× 429) — устанавливаем флаг и больше не пытаемся.
    """
    global _wb_blocked

    if _wb_blocked:
        return []

    url = 'https://search.wb.ru/exactmatch/ru/common/v18/search'
    params = {
        'appType': '1',
        'curr': 'rub',
        'dest': '-1257786',
        'lang': 'ru',
        'page': '1',
        'query': query,
        'resultset': 'catalog',
        'sort': 'popular',
        'spp': '30',
    }

    session = _get_session()
    consecutive_429 = 0

    for attempt in range(2):
        try:
            resp = session.get(url, params=params, timeout=12)

            if resp.status_code == 429:
                consecutive_429 += 1
                wait = 20 if attempt == 0 else 0
                print(f'[WB] 429 rate limit, жду {wait}с...')
                if wait:
                    time.sleep(wait)
                if consecutive_429 >= 2:
                    print('[WB] IP заблокирован WB. Отключаю поиск WB для этой сессии.')
                    _wb_blocked = True
                continue

            resp.raise_for_status()
            data = resp.json()

            products_raw = data.get('products', [])
            if not products_raw:
                products_raw = data.get('data', {}).get('products', [])

            results = []
            for p in products_raw[:limit]:
                sizes = p.get('sizes', [])
                price_raw = 0
                if sizes:
                    price_raw = sizes[0].get('price', {}).get('product', 0)
                if not price_raw:
                    price_raw = p.get('salePriceU') or p.get('priceU') or 0
                price_rub = round(price_raw / 100) if price_raw else 0
                results.append({
                    'id':        p.get('id', 0),
                    'name':      p.get('name', ''),
                    'brand':     p.get('brand', ''),
                    'price_rub': price_rub,
                    'supplier':  p.get('supplier', ''),
                })
            return results

        except Exception as e:
            print(f'[WB search] Ошибка попытка {attempt+1}: {e}')
            if attempt == 0:
                time.sleep(3)

    return []


def get_median_price(results: list[dict]) -> int:
    prices = [r['price_rub'] for r in results if r['price_rub'] > 0]
    if not prices:
        return 0
    prices.sort()
    mid = len(prices) // 2
    return (prices[mid - 1] + prices[mid]) // 2 if len(prices) % 2 == 0 else prices[mid]


def download_photo(nm_id: int, timeout: int = 10) -> Optional[bytes]:
    """
    Скачивает фото с WB CDN.
    CDN не rate-limit'ится, пробуем расчётный basket ± соседей.
    """
    vol = nm_id // 100000
    part = nm_id // 1000
    basket = get_basket_num(vol)

    # CDN-запросы нужны с правильным Accept: image/*, иначе сервер может отклонить
    img_headers = {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/136.0.0.0 Safari/537.36'
        ),
        'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.9',
        'Referer': 'https://www.wildberries.ru/',
    }

    baskets_to_try = list(range(max(1, basket - 2), basket + 4))

    for b in baskets_to_try:
        for size in ['c516x688', 'c246x328', 'big']:
            url = (
                f'https://basket-{b:02d}.wbbasket.ru'
                f'/vol{vol}/part{part}/{nm_id}/images/{size}/1.jpg'
            )
            try:
                resp = requests.get(url, headers=img_headers, timeout=timeout)
                print(f'[WB photo] nmId={nm_id} basket={b} size={size} → {resp.status_code} ({len(resp.content)} б)')
                if resp.status_code == 200 and len(resp.content) > 3000:
                    return resp.content
            except Exception as e:
                print(f'[WB photo] Ошибка {url}: {e}')
                continue

    print(f'[WB photo] Не удалось скачать для nmId={nm_id}')
    return None


def is_clean_photo(img_bytes: bytes) -> bool:
    try:
        img = Image.open(io.BytesIO(img_bytes)).convert('RGB')
        w, h = img.size
        top = img.crop((0, 0, w, h // 3))
        pixels = list(top.getdata())
        light = sum(1 for r, g, b in pixels if r > 200 and g > 200 and b > 200)
        return light / len(pixels) > 0.35
    except Exception:
        return True


def search_and_get_photo(name: str, extra_query: str = '', max_candidates: int = 5) -> dict:
    """
    Полный цикл: поиск WB → медианная цена → скачивание чистого фото.
    """
    global _wb_blocked

    if _wb_blocked:
        return {'price_rub': 0, 'photo_bytes': None, 'photo_candidates': [], 'wb_results': []}

    query = name + (' ' + extra_query if extra_query else '')

    # Задержка между запросами
    time.sleep(random.uniform(3.0, 5.0))

    results = search_wb(query, limit=max_candidates)
    median_price = get_median_price(results)

    photo_bytes = None
    candidates = []

    for r in results[:3]:
        nm_id = r['id']
        candidates.append({
            'nm_id': nm_id,
            'name': r['name'],
            'price': r['price_rub'],
            'photo_url': get_photo_url(nm_id),
        })
        if photo_bytes is None:
            raw = download_photo(nm_id)
            if raw and is_clean_photo(raw):
                photo_bytes = raw

    if photo_bytes is None and results:
        photo_bytes = download_photo(results[0]['id'])

    return {
        'price_rub':        median_price,
        'photo_bytes':      photo_bytes,
        'photo_candidates': candidates,
        'wb_results':       results,
    }
