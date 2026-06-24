"""
Работа с фотографиями:
- Удаление фона (rembg, опционально)
- Ресайз для вставки в Excel
- Конвертация в PNG с белым фоном
"""

import io
from PIL import Image


def remove_background(img_bytes: bytes) -> bytes:
    """
    Удаляет фон через rembg (если установлен).
    Возвращает PNG с прозрачным фоном.
    При ошибке возвращает исходное изображение.
    """
    try:
        from rembg import remove
        result = remove(img_bytes)
        return result
    except ImportError:
        print('[photo_utils] rembg не установлен, фон не удаляется')
        return img_bytes
    except Exception as e:
        print(f'[photo_utils] Ошибка удаления фона: {e}')
        return img_bytes


def prepare_for_excel(
    img_bytes: bytes,
    max_size: int = 140,
    remove_bg: bool = True,
    white_bg: bool = True,
) -> bytes:
    """
    Подготавливает фото для вставки в Excel:
    1. Удаляет фон (опционально)
    2. Добавляет белый фон вместо прозрачного
    3. Ресайзит с сохранением пропорций
    Возвращает PNG-bytes.
    """
    try:
        # 1. Удаляем фон
        if remove_bg:
            img_bytes = remove_background(img_bytes)

        # 2. Открываем и конвертируем
        img = Image.open(io.BytesIO(img_bytes))

        if white_bg:
            # Накладываем на белый фон (убирает прозрачность)
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                img = img.convert('RGBA')
                background.paste(img, mask=img.split()[3])
            else:
                background.paste(img.convert('RGB'))
            img = background
        else:
            img = img.convert('RGB')

        # 3. Ресайз с сохранением пропорций
        w, h = img.size
        ratio = min(max_size / w, max_size / h)
        new_w = int(w * ratio)
        new_h = int(h * ratio)
        img = img.resize((new_w, new_h), Image.LANCZOS)

        # 4. Возвращаем как PNG
        buf = io.BytesIO()
        img.save(buf, format='PNG', optimize=True)
        return buf.getvalue()

    except Exception as e:
        print(f'[photo_utils] Ошибка подготовки фото: {e}')
        return img_bytes


def get_image_dimensions(img_bytes: bytes) -> tuple[int, int]:
    """Возвращает (width, height) изображения."""
    try:
        img = Image.open(io.BytesIO(img_bytes))
        return img.size
    except Exception:
        return (100, 100)
