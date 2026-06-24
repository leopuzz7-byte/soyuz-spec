"""
Подбор фото из локальной библиотеки стилей.

Структура папок:
    styles/
        Современный/   ← имя = название стиля в приложении
            шкаф.jpg
            диван.jpg
            кухонный гарнитур.jpg
            ...
        Скандинавский/
            ...
        Классический/
            ...

Принцип подбора: берём слова из названия товара,
ищем файл с наибольшим совпадением слов.
"""

import os
import re
from pathlib import Path
from typing import Optional

STYLES_DIR = Path(__file__).parent / 'styles'

# ─── База брендов техники ─────────────────────────────────────────────────────
_TECH_BRANDS = frozenset({
    # Холодильники, стиральные, посудомойки, плиты
    'samsung', 'lg', 'bosch', 'siemens', 'beko', 'indesit', 'hotpoint',
    'whirlpool', 'electrolux', 'aeg', 'miele', 'smeg', 'zanussi',
    'liebherr', 'neff', 'candy', 'haier', 'hisense', 'gorenje',
    'atlant', 'атлант', 'vestel', 'ariston', 'bauknecht', 'kaiser',
    'kuppersberg', 'graude', 'hyundai', 'lex', 'midea', 'daewoo',
    'sharp', 'hitachi', 'toshiba', 'panasonic', 'gefest', 'гефест',
    'hansa', 'dex', 'scarlett', 'redmond', 'polaris', 'vitek',
    'philips', 'tefal', 'braun', 'sony', 'xiaomi', 'tcl', 'leran',
    # Котлы, водонагреватели
    'baxi', 'vaillant', 'viessmann', 'buderus', 'navien', 'protherm',
    'ferroli', 'beretta', 'rinnai', 'immergas', 'arderia',
    'thermex', 'термекс', 'timberk', 'garanterm',
    # Кондиционеры
    'daikin', 'fujitsu', 'gree', 'aux', 'ballu', 'mitsubishi', 'electra',
    # Вытяжки, встраиваемая техника
    'maunfeld', 'elica', 'faber', 'krona', 'kronasteel', 'ciarko',
    # Электрооборудование
    'dkc', 'дкс', 'iek', 'иэк', 'ekf', 'schneider', 'legrand', 'abb',
    'rccb', 'hager', 'gewiss', 'chint', 'keaz', 'кэаз',
})

# Паттерн для артикулов: слово из 5+ символов, начинается с буквы, содержит цифры
# Примеры: B3DFR57H23W, R5ST0549, WB35RT47RSA
_MODEL_RE = re.compile(r'\b[A-Za-z][A-Za-z0-9]{4,}\b')

# Паттерны для каждого бренда (с границами слова, без учёта регистра)
_BRAND_PATTERNS = [
    re.compile(r'\b' + re.escape(b) + r'\b')
    for b in _TECH_BRANDS
]


def is_branded_tech(name: str) -> bool:
    """
    True если товар — конкретная модель техники или электрооборудования
    (обнаружен бренд или артикул модели).

    Такие товары лучше искать онлайн (Bing находит точное фото),
    а не в локальной библиотеке с обобщёнными изображениями.

    Примеры True:  «Стиральная машина Beko B3DFR57H23W»
                   «Холодильник Samsung RB38T7762B1»
                   «Шкаф ST DKC R5ST0549»
    Примеры False: «Холодильник двухкамерный», «Диван угловой», «Стол офисный»
    """
    lower = name.lower()

    # Проверка по базе брендов
    for pat in _BRAND_PATTERNS:
        if pat.search(lower):
            return True

    # Проверка на артикул модели (буквенно-цифровой код)
    for m in _MODEL_RE.finditer(name):
        token = m.group()
        if re.search(r'\d', token):   # есть цифры → это артикул, не просто слово
            return True

    return False


def list_styles() -> list:
    """Возвращает только стили у которых есть хотя бы одно фото."""
    if not STYLES_DIR.exists():
        return []
    img_ext = {'.jpg', '.jpeg', '.png', '.webp'}
    styles = []
    for d in sorted(STYLES_DIR.iterdir()):
        if not d.is_dir() or d.name.startswith('.'):
            continue
        if any(f.suffix.lower() in img_ext for f in d.iterdir()):
            styles.append(d.name)
    return styles


def _normalize(text: str) -> list:
    """Разбивает текст на слова, убирает лишнее."""
    text = text.lower()
    text = re.sub(r'\d+[xхX×]\d+([xхX×]\d+)?\s*(см|мм|м)?', '', text)
    text = re.sub(r'\d+', '', text)
    text = re.sub(r'[^\w\s]', ' ', text)
    return [w for w in text.split() if len(w) >= 2]


def find_photo(product_name: str, style: str) -> Optional[bytes]:
    """
    Ищет подходящее фото в папке styles/{style}/.
    Возвращает bytes или None.
    """
    style_dir = STYLES_DIR / style
    if not style_dir.exists():
        return None

    # Список файлов изображений
    img_extensions = {'.jpg', '.jpeg', '.png', '.webp'}
    files = [
        f for f in style_dir.iterdir()
        if f.suffix.lower() in img_extensions
    ]
    if not files:
        return None

    query_words = set(_normalize(product_name))
    if not query_words:
        return None

    # Считаем совпадение для каждого файла
    best_file = None
    best_score = 0
    best_ratio = 0.0
    best_exact = 0
    best_fwc   = 0  # кол-во слов в лучшем файле

    for f in files:
        file_words = set(_normalize(f.stem))
        exact = len(query_words & file_words)
        if exact == 0:
            continue
        # Доля совпавших слов относительно большего набора
        ratio = exact / max(len(query_words), len(file_words))
        # Бонус за частичное совпадение
        partial = sum(
            1 for qw in query_words
            for fw in file_words
            if fw in qw or qw in fw
        )
        total = exact * 2 + partial

        if total > best_score or (total == best_score and ratio > best_ratio):
            best_score = total
            best_ratio = ratio
            best_exact = exact
            best_fwc   = len(file_words)
            best_file  = f

    # Минимальное число точных совпадений:
    # если оба (запрос И файл) многословные — нужно 2+ совпадений
    # иначе достаточно 1 («Торшер» → «торшер 1.jpg», «Матрас ортоп.» → «матрас 1.jpg»)
    min_exact = 2 if (len(query_words) >= 2 and best_fwc >= 2) else 1

    if best_file and best_ratio >= 0.4 and best_exact >= min_exact:
        try:
            data = best_file.read_bytes()
            print(f'[local] ✓ «{product_name[:30]}» → {best_file.name} (score={best_score})')
            return data
        except Exception as e:
            print(f'[local] Ошибка чтения {best_file}: {e}')

    print(f'[local] Не найдено для «{product_name[:30]}» в стиле «{style}»')
    return None
