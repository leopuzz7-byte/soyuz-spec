"""
Переименовывает диваны 6-10 в категорию "диван угловой".
Запуск: python fix_sofas.py
"""
from pathlib import Path

STYLES_DIR = Path(__file__).parent / 'spec_generator' / 'styles' / 'Современный'

print('Переименовываю угловые диваны...')
for i, n in enumerate(range(6, 11), start=1):
    src = STYLES_DIR / f'диван {n}.jpg'
    dst = STYLES_DIR / f'диван угловой {i}.jpg'
    if dst.exists():
        print(f'  — {dst.name} уже есть, пропускаю')
    elif src.exists():
        src.rename(dst)
        print(f'  ✓ диван {n}.jpg → диван угловой {i}.jpg')
    else:
        print(f'  ⚠️  {src.name} не найден')

print('Готово!')
