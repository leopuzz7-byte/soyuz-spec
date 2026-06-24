"""
Поиск изображений товаров через Bing (DDGS).
"""

import re
import io
import json
import time
import random
import requests
from typing import Optional
from PIL import Image

try:
    from bs4 import BeautifulSoup
    BS4_OK = True
except ImportError:
    BS4_OK = False

HEADERS_YA = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/136.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'ru-RU,ru;q=0.9',
    'Referer': 'https://yandex.ru/',
}

HEADERS_DL = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/136.0.0.0 Safari/537.36'
    ),
    'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
}


# ─── Очистка запроса ─────────────────────────────────────────────────────────

def _clean_query(name: str) -> str:
    q = name
    q = re.sub(r'\d+[xхX×]\d+([xхX×]\d+)?\s*(см|мм|м)?', '', q)
    q = re.sub(r'\d+\s*(см|мм|м|"|дюйм|литр|кг|вт|w)', '', q, flags=re.IGNORECASE)
    q = re.sub(r'\(.*?\)', '', q)
    return ' '.join(q.split()).strip() or name


# ─── Проверка качества изображения ───────────────────────────────────────────

def _is_clean_photo(img_bytes: bytes) -> bool:
    try:
        img = Image.open(io.BytesIO(img_bytes)).convert('RGB')
        w, h = img.size
        if w < 100 or h < 100:
            return False
        ratio = w / h
        if ratio > 2.8 or ratio < 0.25:
            return False
        pts = [(0,0),(w-1,0),(0,h-1),(w-1,h-1),(w//2,0),(w//2,h-1),(0,h//2),(w-1,h//2)]
        pixels = [img.getpixel(p) for p in pts]
        light = sum(1 for r,g,b in pixels if r>175 and g>175 and b>175)
        return light >= 4
    except Exception:
        return True


def _download(url: str, timeout: int = 8) -> Optional[bytes]:
    try:
        resp = requests.get(url, headers=HEADERS_DL, timeout=timeout)
        if resp.status_code == 200 and len(resp.content) > 2000:
            ct = resp.headers.get('Content-Type', '')
            if 'image' in ct or any(url.lower().endswith(e) for e in ('.jpg','.jpeg','.png','.webp')):
                return resp.content
    except Exception:
        pass
    return None


# ─── Яндекс.Картинки ─────────────────────────────────────────────────────────

def _search_yandex(query: str, max_results: int = 12) -> list:
    """
    Возвращает список URL изображений с Яндекс.Картинок.
    Метод 1: regex по raw HTML (не зависит от CSS-классов).
    Метод 2: data-bem (старая структура).
    """
    try:
        time.sleep(random.uniform(1.0, 2.0))
        resp = requests.get(
            'https://yandex.ru/images/search',
            params={'text': query, 'isize': 'large', 'nomisspell': 1},
            headers=HEADERS_YA,
            timeout=15,
        )
        if resp.status_code != 200:
            print(f'[Яндекс] HTTP {resp.status_code} для «{query[:30]}»')
            return []

        html = resp.text
        urls = []

        # Метод 1: regex — ищем "img_href":"..." прямо в HTML/JSON
        matches = re.findall(r'"img_href"\s*:\s*"((?:https?:)?//[^"]+)"', html)
        for m in matches[:max_results]:
            url = 'https:' + m if m.startswith('//') else m
            if url not in urls:
                urls.append(url)

        # Метод 2: data-bem (старая структура, если первый не сработал)
        if not urls and BS4_OK:
            soup = BeautifulSoup(html, 'html.parser')
            for item in soup.find_all('div', {'class': 'serp-item'})[:max_results]:
                try:
                    data = json.loads(item.get('data-bem', '{}'))
                    url = data.get('serp-item', {}).get('img_href', '')
                    if url:
                        urls.append('https:' + url if url.startswith('//') else url)
                except Exception:
                    continue

        print(f'[Яндекс] «{query[:35]}» → {len(urls)} результатов (HTML={len(html)} б)')
        return urls

    except Exception as e:
        print(f'[Яндекс] Ошибка: {e}')
        return []


def search_yandex_image(query: str) -> Optional[bytes]:
    """Ищет чистое фото через Яндекс.Картинки."""
    clean_q = _clean_query(query)

    for variant in [f'{clean_q} на белом фоне', clean_q]:
        urls = _search_yandex(variant)
        for url in urls:
            img = _download(url)
            if img and _is_clean_photo(img):
                print(f'[Яндекс] ✓ Найдено для «{clean_q[:30]}»')
                return img

    return None


# ─── Bing через DDGS ─────────────────────────────────────────────────────────

def _search_bing(query: str, max_results: int = 8) -> Optional[bytes]:
    try:
        from ddgs import DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            return None

    clean_q = _clean_query(query)

    # Пробуем варианты запроса без задержек
    for variant in [f'{clean_q} на белом фоне', clean_q]:
        try:
            results = DDGS().images(
                variant, region='ru-ru', safesearch='off',
                max_results=max_results, backend='bing', type_image='photo',
            )
            if not results:
                continue
            for r in results:
                img_url = r.get('image', '')
                if not img_url:
                    continue
                thumb = _download(r.get('thumbnail', ''), timeout=3)
                if thumb and not _is_clean_photo(thumb):
                    continue
                img = _download(img_url, timeout=6)
                if img and _is_clean_photo(img):
                    print(f'[Bing] ✓ «{clean_q[:30]}»')
                    return img
        except Exception as e:
            print(f'[Bing] Ошибка: {e}')
            continue

    return None


# ─── Одиночный поиск ─────────────────────────────────────────────────────────

def search_image(query: str) -> Optional[bytes]:
    """Ищет чистое предметное фото через Bing."""
    print(f'[image_search] Запрос: «{query[:40]}»')
    result = _search_bing(query)
    if not result:
        print(f'[image_search] Не найдено: «{query[:30]}»')
    return result


# ─── Параллельный пакетный поиск ─────────────────────────────────────────────

def search_images_batch(queries: list[str], max_workers: int = 6) -> dict[str, Optional[bytes]]:
    """
    Параллельный поиск для списка запросов.
    Возвращает dict {query: bytes_or_None}.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_to_q = {pool.submit(_search_bing, q): q for q in queries}
        for future in as_completed(future_to_q):
            q = future_to_q[future]
            try:
                results[q] = future.result()
            except Exception as e:
                print(f'[Bing batch] Ошибка «{q[:30]}»: {e}')
                results[q] = None
    return results
