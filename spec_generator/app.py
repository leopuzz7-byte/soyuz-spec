"""
Генератор коммерческих спецификаций по мебели — ООО «СОЮЗ-М»

Запуск:
    streamlit run app.py
"""

import io
import json
import time
import datetime
import streamlit as st

from input_parser  import parse_input_excel
from wb_search     import search_and_get_photo
from image_search  import search_image, search_images_batch
from local_photos  import find_photo, list_styles, is_branded_tech
from photo_utils   import prepare_for_excel
from ai_generator  import generate_descriptions
from excel_output  import build_excel

# ─── Настройка страницы ───────────────────────────────────────────────────────
st.set_page_config(
    page_title='Генератор спецификаций | СОЮЗ-М',
    page_icon='📋',
    layout='wide',
)

# ─── Стили ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.stApp { max-width: 1200px; margin: 0 auto; }
div[data-testid="stSidebar"] { background: #f0f4fa; }
h1 { color: #1F5C99; }
.status-box { background: #e8f0f8; border-radius: 8px; padding: 12px 16px;
              border-left: 4px solid #1F5C99; margin: 8px 0; }
.success-box { background: #e8f5e9; border-radius: 8px; padding: 12px 16px;
               border-left: 4px solid #2e7d32; margin: 8px 0; }
.warn-box { background: #fff9c4; border-radius: 8px; padding: 12px 16px;
            border-left: 4px solid #f9a825; margin: 8px 0; }
</style>
""", unsafe_allow_html=True)


# ─── Сайдбар: настройки ───────────────────────────────────────────────────────
with st.sidebar:
    st.title('Настройки')

    st.subheader('💰 Ценообразование')
    markup_pct = st.slider(
        'Наценка к рыночной цене WB (%)',
        min_value=0, max_value=100, value=10, step=5,
        help='Розничная цена = медиана WB × (1 + наценка / 100)',
    )
    use_budget_if_no_wb = st.checkbox(
        'Использовать бюджетную цену если WB не нашёл',
        value=True,
    )

    st.divider()
    st.subheader('🖼 Фотографии')

    available_styles = list_styles()
    if available_styles:
        photo_source = st.radio(
            'Источник фотографий',
            options=['Библиотека стилей', 'Библиотека + Bing', 'Только Bing'],
            index=0,
        )
        selected_style = st.selectbox(
            'Стиль интерьера',
            options=available_styles,
            disabled=(photo_source == 'Только Bing'),
        )
    else:
        photo_source = 'Только Bing'
        selected_style = None
        st.info('📁 Папка styles/ пуста. Добавь фото чтобы выбрать стиль.')

    skip_photo_on_error = st.checkbox('Пропускать фото при ошибке', value=True)

    st.divider()
    st.subheader('🔑 AI настройки')
    _default_key = st.secrets.get('PROXYAPI_KEY', '') if hasattr(st, 'secrets') else ''
    api_key = st.text_input(
        'API ключ',
        value=_default_key,
        type='password',
        placeholder='sk-...',
        help='Ключ от прокси (или Anthropic/OpenAI)',
    )
    proxy_base_url = st.text_input(
        'Base URL прокси',
        value='https://api.proxyapi.ru/openai/v1',
        help='URL прокси-сервера. ProxyAPI.ru уже вписан по умолчанию.',
    )
    ai_model = st.selectbox(
        'Модель',
        options=['gpt-4o-mini', 'gpt-4o', 'gpt-4.1-mini', 'o4-mini'],
        index=0,
        help='gpt-4o-mini — оптимальный баланс цена/качество',
    )

    st.divider()
    st.subheader('ℹ️ О приложении')
    st.caption('v1.0 · СОЮЗ-М · 2026')
    st.caption('Автоматизация генерации спецификаций')


# ─── Основной контент ────────────────────────────────────────────────────────
st.title('📋 Генератор спецификаций по мебели')
st.markdown('Загрузите входной файл → система найдёт товары на WB, сгенерирует описания и соберёт спецификацию.')

tab_main, tab_preview, tab_help = st.tabs(['📁 Генерация', '👁 Предпросмотр', '❓ Помощь'])

# ─── ТАБЛИЦА ПРЕДПРОСМОТРА (session state) ────────────────────────────────────
if 'result_items'   not in st.session_state: st.session_state.result_items   = []
if 'result_bytes'   not in st.session_state: st.session_state.result_bytes   = None
if 'result_filename'not in st.session_state: st.session_state.result_filename= ''


# ═══════════════════════════════════════════════════════════════════════════════
# ТАБ 1: ГЕНЕРАЦИЯ
# ═══════════════════════════════════════════════════════════════════════════════
with tab_main:

    col_left, col_right = st.columns([2, 1])

    with col_left:
        st.subheader('1. Загрузите входной файл')
        uploaded = st.file_uploader(
            'Excel с перечнем мебели (.xlsx, .xls)',
            type=['xlsx', 'xls'],
            help='Файл должен содержать колонки: Наименование, Количество, Цена (Цена — опционально)',
        )

    with col_right:
        st.subheader('2. Параметры документа')
        object_name = st.text_input(
            'Адрес / название объекта',
            placeholder='с.Старая Икшурма, ул.Кирова, 29б',
        )
        spec_title = st.text_input(
            'Заголовок спецификации',
            value='СПЕЦИФИКАЦИЯ по мебели',
        )

    st.divider()

    # Предпросмотр входного файла
    if uploaded:
        try:
            file_bytes = uploaded.read()
            doc_title, items_raw = parse_input_excel(file_bytes)

            st.markdown(f'<div class="status-box">📄 <b>Файл загружен:</b> {uploaded.name} | '
                        f'<b>Позиций:</b> {len(items_raw)} | <b>Заголовок:</b> {doc_title or "—"}</div>',
                        unsafe_allow_html=True)

            # Таблица входных данных
            with st.expander('Список позиций из файла', expanded=True):
                cols = st.columns([1, 6, 2, 3])
                cols[0].markdown('**№**')
                cols[1].markdown('**Наименование**')
                cols[2].markdown('**Кол-во**')
                cols[3].markdown('**Бюджет, руб.**')
                for it in items_raw:
                    cols2 = st.columns([1, 6, 2, 3])
                    cols2[0].write(it['row'])
                    cols2[1].write(it['name'])
                    cols2[2].write(it['qty'])
                    cols2[3].write(f"{it['budget_price']:,.0f}" if it['budget_price'] else '—')

            st.divider()

            # Кнопка запуска
            if not api_key:
                st.warning('⚠️ Введите API ключ в боковой панели слева.')

            can_run = bool(api_key) and len(items_raw) > 0

            if st.button('🚀 Сгенерировать спецификацию', type='primary', disabled=not can_run):

                progress_bar = st.progress(0)
                status_placeholder = st.empty()
                log_lines = []

                def log(msg: str):
                    log_lines.append(f'• {msg}')
                    status_placeholder.markdown('\n'.join(log_lines[-6:]))

                try:
                    total_steps = len(items_raw) + 2

                    # ── Шаг 1а: Библиотека — мгновенно для всех ──────────────
                    use_library  = photo_source in ('Библиотека стилей', 'Библиотека + Bing') and selected_style
                    use_bing     = photo_source in ('Библиотека + Bing', 'Только Bing')
                    library_photos = {}
                    need_online    = []

                    if use_library:
                        log('📚 Проверяю библиотеку...')
                        for item in items_raw:
                            name = item['name']
                            if is_branded_tech(name) and use_bing:
                                library_photos[name] = None
                                need_online.append(name)
                            else:
                                ph = find_photo(name, selected_style)
                                library_photos[name] = ph
                                if ph is None and use_bing:
                                    need_online.append(name)
                        found_lib = sum(1 for v in library_photos.values() if v)
                        log(f'  📚 Библиотека: {found_lib}/{len(items_raw)}' +
                            (f' | Bing: {len(need_online)}' if use_bing else ''))
                    else:
                        need_online = [item['name'] for item in items_raw]

                    # ── Шаг 1б: Bing — параллельно для недостающих ────────────
                    online_photos = {}
                    if use_bing and need_online:
                        log(f'🔍 Bing: {len(need_online)} запросов параллельно...')
                        progress_bar.progress(0.3)
                        online_photos = search_images_batch(need_online, max_workers=6)
                        found_online = sum(1 for v in online_photos.values() if v)
                        log(f'  🌐 Bing: {found_online}/{len(need_online)}')

                    progress_bar.progress(0.6)

                    # ── Шаг 1в: Собираем результаты ───────────────────────────
                    items_with_wb = []
                    for idx, item in enumerate(items_raw):
                        name   = item['name']
                        budget = item.get('budget_price') or 0
                        retail_price = round(budget * (1 + markup_pct / 100)) if budget > 0 else 0

                        raw_photo = library_photos.get(name) or online_photos.get(name)

                        photo_bytes = None
                        if raw_photo:
                            try:
                                photo_bytes = prepare_for_excel(
                                    raw_photo, max_size=130, remove_bg=False,
                                )
                            except Exception as e:
                                if not skip_photo_on_error:
                                    raise
                                log(f'  ⚠️ Ошибка фото [{idx+1}]: {e}')

                        items_with_wb.append({
                            **item,
                            'market_price':  budget,
                            'retail_price':  retail_price,
                            'photo_bytes':   photo_bytes,
                            'wb_candidates': [],
                        })

                    # ── Шаг 2: AI-описания ────────────────────────────────────
                    log(f'🤖 Генерирую описания ({ai_model})...')
                    progress_bar.progress(0.8)

                    items_for_ai = [
                        {'row': it['row'], 'name': it['name'],
                         'qty': it['qty'], 'budget_price': it['budget_price']}
                        for it in items_with_wb
                    ]
                    items_ai = generate_descriptions(
                        items_for_ai,
                        api_key=api_key,
                        base_url=proxy_base_url or None,
                        model=ai_model,
                        progress_callback=log,
                    )

                    # Объединяем
                    ai_by_row = {it['row']: it for it in items_ai}
                    final_items = []
                    for it in items_with_wb:
                        ai = ai_by_row.get(it['row'], {})

                        # Цена: бюджет из файла → AI оценка → 0
                        budget       = it.get('budget_price') or 0
                        ai_price     = ai.get('ai_market_price') or 0
                        market_price = budget if budget > 0 else ai_price
                        retail_price = round(market_price * (1 + markup_pct / 100)) if market_price > 0 else 0

                        # Обновляем цену в итоговом элементе
                        source = 'файл' if budget > 0 else ('AI' if ai_price > 0 else '—')
                        if ai_price and not budget:
                            log(f'  💡 AI оценил цену: ~{ai_price:,} руб.')

                        final_items.append({
                            **it,
                            'market_price':  market_price,
                            'retail_price':  retail_price,
                            'description':   ai.get('description', ''),
                            'dimensions':    ai.get('dimensions', ''),
                            'manufacturer':  ai.get('manufacturer', 'Россия'),
                            'article':       ai.get('article', ''),
                        })

                    log(f'✓ AI сгенерировал описания для {len(final_items)} позиций')

                    # ── Шаг 3: Сборка Excel ───────────────────────────────────
                    log('📊 Собираю Excel-файл...')
                    progress_bar.progress(0.95)

                    excel_bytes = build_excel(
                        items=final_items,
                        object_name=object_name,
                        spec_title=spec_title,
                    )

                    date_str = datetime.date.today().strftime('%d.%m.%Y')
                    filename = f'Спецификация по мебели от {date_str}.xlsx'

                    # Сохраняем в session_state
                    st.session_state.result_items    = final_items
                    st.session_state.result_bytes    = excel_bytes
                    st.session_state.result_filename = filename

                    progress_bar.progress(1.0)
                    log(f'✅ Готово! Файл: {filename}')

                    st.success(f'✅ Спецификация готова! {len(final_items)} позиций.')

                except ValueError as e:
                    st.error(f'❌ Ошибка: {e}')
                except Exception as e:
                    st.error(f'❌ Неожиданная ошибка: {e}')
                    raise

            # ── Кнопка скачивания (если есть результат) ──────────────────────
            if st.session_state.result_bytes:
                st.divider()
                st.download_button(
                    label=f'⬇️ Скачать {st.session_state.result_filename}',
                    data=st.session_state.result_bytes,
                    file_name=st.session_state.result_filename,
                    mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    type='primary',
                    key='download_tab1',
                )

        except ValueError as e:
            st.error(f'❌ Ошибка чтения файла: {e}')
        except Exception as e:
            st.error(f'❌ Неожиданная ошибка при чтении файла: {e}')


# ═══════════════════════════════════════════════════════════════════════════════
# ТАБ 2: ПРЕДПРОСМОТР
# ═══════════════════════════════════════════════════════════════════════════════
with tab_preview:
    if not st.session_state.result_items:
        st.info('Сначала сгенерируйте спецификацию на вкладке «Генерация».')
    else:
        items = st.session_state.result_items
        st.subheader(f'Результат: {len(items)} позиций')

        total = sum(it.get('retail_price', 0) * it.get('qty', 1) for it in items)
        st.metric('Общая стоимость', f'{total:,.0f} руб.')

        for it in items:
            with st.expander(f"**{it['row']}. {it['name']}**  —  {it.get('retail_price', 0):,} руб.", expanded=False):
                c1, c2 = st.columns([1, 3])

                with c1:
                    if it.get('photo_bytes'):
                        st.image(it['photo_bytes'], width=160)
                    else:
                        st.markdown('*Фото не найдено*')

                with c2:
                    st.markdown(f"**Описание:** {it.get('description', '—')}")
                    st.markdown(f"**Размеры:** {it.get('dimensions', '—')}")
                    st.markdown(f"**Производитель:** {it.get('manufacturer', '—')}")
                    st.markdown(f"**Артикул:** {it.get('article', '—')}")
                    cols = st.columns(3)
                    cols[0].metric('Цена WB (медиана)', f"{it.get('market_price', 0):,} руб.")
                    cols[1].metric('Розничная цена', f"{it.get('retail_price', 0):,} руб.")
                    cols[2].metric('Итого', f"{it.get('retail_price', 0) * it.get('qty', 1):,} руб.")

                    # WB кандидаты
                    candidates = it.get('wb_candidates', [])
                    if candidates:
                        st.markdown('**Найдено на WB:**')
                        for c in candidates[:3]:
                            st.markdown(f"  • [{c['name'][:50]}]({c.get('photo_url', '#')}) — {c['price']:,} руб.")

        st.divider()
        if st.session_state.result_bytes:
            st.download_button(
                label=f'⬇️ Скачать {st.session_state.result_filename}',
                data=st.session_state.result_bytes,
                file_name=st.session_state.result_filename,
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                type='primary',
                key='download_tab2',
            )


# ═══════════════════════════════════════════════════════════════════════════════
# ТАБ 3: ПОМОЩЬ
# ═══════════════════════════════════════════════════════════════════════════════
with tab_help:
    st.subheader('Как пользоваться')
    st.markdown("""
**1. Получите API ключ Claude:**
- Зайдите на [console.anthropic.com](https://console.anthropic.com)
- Создайте ключ (Settings → API Keys)
- Вставьте в поле «API ключ» в левой панели
- Стоимость: ~1 рубль за спецификацию из 17 позиций

**2. Подготовьте входной файл:**
- Excel (.xlsx или .xls)
- Обязательная колонка: **Наименование**
- Желательно: **Количество**, **Цена** (бюджетная)
- Пример — файл «Мебель для ИВА.xlsx»

**3. Настройте наценку:**
- Система находит медианную цену на WB
- Применяет заданный % наценки
- Если товар не найден на WB — использует бюджетную цену из входного файла

**4. Нажмите «Сгенерировать»:**
- Система ищет каждую позицию на WB (~0.5 сек/позиция)
- Скачивает чистые фотографии
- Удаляет фон (опционально, требует rembg)
- Генерирует описания через Claude Haiku
- Собирает Excel со всеми данными

**5. Проверьте и скачайте:**
- Вкладка «Предпросмотр» показывает все позиции с фото
- Скачайте готовый .xlsx файл

---
**Требования к системе:**
```
pip install streamlit openpyxl requests anthropic Pillow
pip install rembg  # опционально, для удаления фона
```

**Возможные проблемы:**
- *WB не нашёл товар* — используется бюджетная цена из файла, описание генерирует AI
- *Фото не скачалось* — в спецификацию вставляется пустая ячейка
- *Ошибка API ключа* — проверьте ключ на console.anthropic.com
    """)
