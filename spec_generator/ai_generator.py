"""
Генерация описаний через AI API.

Поддерживает два режима:
1. Anthropic Claude (нативный SDK)
2. OpenAI-совместимый прокси (GPT-4o mini, GPT-4o, и т.д.)

Один запрос на всю спецификацию = минимальная стоимость.
"""

import json
from openai import OpenAI


# ─── Системный промпт ─────────────────────────────────────────────────────────
SYSTEM_PROMPT = """Ты эксперт по каталожным описаниям и ценообразованию мебели, бытовой техники и электрооборудования для российских государственных и коммерческих объектов.

Твоя задача: по названию товара сгенерировать описание И оценить рыночную цену.

ПРАВИЛА:
1. description — 1-2 предложения на русском. ТОЛЬКО технические факты, БЕЗ маркетинга («идеально», «отличный», «комфорт» и т.п.).
   Включай только то, что актуально для данного типа товара:
   - ЛДСП-мебель (шкаф, стол, кровать, гарнитур): материал + толщина (ЛДСП 16/25 мм), кромка ПВХ, фурнитура если есть, цвет «под заказ» если кастомная.
   - Мягкая мебель (диван, кресло, стул, пуфик): каркас, обивка, механизм трансформации если есть, плотность ППУ если известна.
   - Бытовая техника (холодильник, плита, стиралка): ключевые тех. параметры (объём/загрузка/конфорки), тип управления, цвет корпуса.
   - Освещение (торшер, люстра): материал, тип цоколя, мощность, высота.
   - Зеркало: толщина полотна, тип крепления, наличие рамки.
   - Матрас: конструкция слоёв, тип пружин если есть, жёсткость.
   Не перечисляй всё подряд — только значимые характеристики для данного конкретного товара.
2. dimensions — формат "ШхГхВ" или "ДхШ" в сантиметрах. Если неизвестны — реалистичные типовые для данного товара. Для кабелей, труб, расходников — пустая строка "".
3. manufacturer — "Россия" для корпусной мебели на заказ; для техники — страна бренда (IEK, EKF, DKC — Россия; ATLANT — Беларусь; Indesit, Bosch — Италия/Германия; без бренда — Китай).
4. article — если в названии есть артикул/модель (буквенно-цифровой код: R5ST0549, B3DFR57H23W, AR-M06N-3-C016) — вставь его. Во всех остальных случаях (нет модели в названии) — пиши "инд.изготовление". Никогда не оставляй пустым.
5. market_price_rub — ЦЕЛОЕ ЧИСЛО, оценка средней розничной цены в рублях на российском рынке (WB, Ozon, магазины).
   Ориентиры: стул офисный 3000-8000, кресло офисное 8000-25000, шкаф-купе 20000-60000, диван 25000-80000,
   кухонный гарнитур 40000-150000, холодильник 25000-60000, газовая плита 15000-35000,
   кабель ВВГнг 3х2.5 (руб/м) 80-130, автомат 1P 16А 300-800, шкаф электрический DKC 5000-15000,
   блок питания 30Вт 1500-3000, металлорукав (руб/м) 40-80, труба гофрированная (руб/м) 20-50.
   Если бюджетная цена указана и она разумна — используй её как ориентир.
   Для позиций с кол-вом в метрах — цена за 1 метр.

ФОРМАТ ОТВЕТА — строго JSON-массив без пояснений, markdown, комментариев:
[
  {
    "row": 1,
    "description": "...",
    "dimensions": "...",
    "manufacturer": "...",
    "article": "...",
    "market_price_rub": 15000
  }
]"""


def generate_descriptions(
    items: list,
    api_key: str,
    base_url: str = None,
    model: str = 'gpt-4o-mini',
    progress_callback=None,
) -> list:
    """
    Генерирует описания для всех позиций одним запросом.

    items: [{'row': int, 'name': str, 'qty': int, 'budget_price': float}, ...]
    api_key: ключ API
    base_url: базовый URL для прокси (None = OpenAI по умолчанию)
    model: модель (gpt-4o-mini, gpt-4o, claude-haiku и т.д. — зависит от прокси)

    Возвращает тот же список, дополненный полями:
      description, dimensions, manufacturer, article
    """
    if not items:
        return items

    # Инициализируем клиент (OpenAI SDK совместим с большинством прокси)
    client_kwargs = {'api_key': api_key}
    if base_url:
        client_kwargs['base_url'] = base_url.rstrip('/')

    client = OpenAI(**client_kwargs)

    # Формируем таблицу позиций
    lines = ['Позиции спецификации:\n']
    for item in items:
        lines.append(
            f"row={item['row']} | {item['name']} "
            f"| кол-во: {item['qty']} шт "
            f"| бюджет: {item.get('budget_price', 0):,.0f} руб."
        )
    user_message = '\n'.join(lines)

    if progress_callback:
        progress_callback(f'Отправляю запрос к {model}...')

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {'role': 'system', 'content': SYSTEM_PROMPT},
                {'role': 'user',   'content': user_message},
            ],
            max_tokens=4096,
            temperature=0.2,  # низкая температура = стабильный структурированный вывод
            response_format={'type': 'json_object'} if 'gpt' in model.lower() else None,
        )

        raw = response.choices[0].message.content.strip()

        # Чистим если модель добавила markdown
        if '```' in raw:
            parts = raw.split('```')
            for part in parts:
                part = part.strip()
                if part.startswith('json'):
                    part = part[4:].strip()
                if part.startswith('[') or part.startswith('{'):
                    raw = part
                    break

        # Если вернулся объект {"items": [...]} вместо массива
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            # Ищем массив внутри
            for v in parsed.values():
                if isinstance(v, list):
                    parsed = v
                    break

        if not isinstance(parsed, list):
            raise ValueError(f'AI вернул неожиданный формат: {type(parsed)}')

        # Индексируем по row
        ai_by_row = {d.get('row', i + 1): d for i, d in enumerate(parsed)}

        result = []
        for item in items:
            r = item.get('row', 0)
            ai = ai_by_row.get(r, {})
            ai_price = ai.get('market_price_rub', 0)
            try:
                ai_price = int(ai_price) if ai_price else 0
            except (ValueError, TypeError):
                ai_price = 0
            result.append({
                **item,
                'description':      ai.get('description', ''),
                'dimensions':       ai.get('dimensions', ''),
                'manufacturer':     ai.get('manufacturer', 'Россия'),
                'article':          ai.get('article', ''),
                'ai_market_price':  ai_price,
            })

        return result

    except json.JSONDecodeError as e:
        print(f'[AI] Ошибка парсинга JSON: {e}')
        print(f'[AI] Ответ модели: {raw[:500]}')
        # Возвращаем без описаний — лучше пустые поля, чем падение
        return [
            {**item, 'description': '', 'dimensions': '',
             'manufacturer': 'Россия', 'article': ''}
            for item in items
        ]
    except Exception as e:
        err = str(e).lower()
        if 'auth' in err or '401' in err or 'invalid' in err:
            raise ValueError(f'Неверный API ключ или нет доступа к модели «{model}».')
        if 'rate' in err or '429' in err:
            raise ValueError('Превышен лимит запросов. Подождите минуту и попробуйте снова.')
        if 'model' in err or '404' in err:
            raise ValueError(f'Модель «{model}» не найдена на этом прокси.')
        raise ValueError(f'Ошибка AI API: {e}')
