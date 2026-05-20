import re

ACCESSORY_WORDS = [
    'чехол',
    'подставк',
    'держат',
    'держател',
    'кронштейн',
    'креплен',
    'крепеж',
    'кабель',
    'провод',
    'адаптер',
    'блок питания',
    'зарядк',
    'пульт',
    'накле',
    'пленк',
    'плёнк',
    'стекл',
    'запчаст',
    'ремонт',
    'аксессуар',
    'сумк',
    'силикон',
    'полк',
    'полоч',
    'настенн',
    'подвес',
    'органайзер',
    'shelf',
    'stand',
    'mount',
    'holder',
    'case',
    'cover',
    'защитн',
    'magsafe',
    'магнитн',
    'линз',
    'ремеш',
    'муляж',
    'макет',
    'копия',
    'реплика',
    'корпус',
    'дисплей',
    'экран',
    'аккумулятор',
    'шлейф',
    'refurb',
    'восстановлен',
    'витрин',
    'уцен',
    'б у',
    'бу ',
]

ACCESSORY_PATTERNS = [
    r'\bдля\s+(?:умной\s+)?колонк',
    r'\bдля\s+(?:яндекс\s+)?станци',
    r'\bпод\s+(?:яндекс\s+)?станци',
    r'\bна\s+(?:яндекс\s+)?станци',
    r'\bдля\s+(?:apple\s+)?iphone',
    r'\bдля\s+айфон',
    r'\bна\s+(?:apple\s+)?iphone',
    r'\bбез\s+face\s+id',
]

def _normalize(s: str) -> str:
    if s is None:
        return ''
    s = s.lower()
    s = s.replace('ё', 'е')
    s = re.sub(r'[^a-zа-я0-9\s%\-]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def contains_any(s, words):
    for w in words:
        if w in s:
            return True
    return False

def is_accessory_name(product_name: str) -> bool:
    name = _normalize(product_name)
    if not name:
        return False
    return contains_any(name, ACCESSORY_WORDS) or any(re.search(pattern, name) for pattern in ACCESSORY_PATTERNS)

def has_station_context(name: str) -> bool:
    return contains_any(name, [
        'яндекс станция',
        'yandex station',
        'станция яндекс',
        'умная колонка',
        'смарт колонка',
    ])

def has_iphone_context(name: str) -> bool:
    return contains_any(name, [
        'iphone',
        'айфон',
        'смартфон apple',
        'смартфон эппл',
    ])

def has_any_model_token(name: str, tokens) -> bool:
    return contains_any(name, tokens)

def match_product_to_model(product_name: str, model_key: str) -> bool:
    name = _normalize(product_name)
    if is_accessory_name(name):
        return False

    k = model_key

    if k.startswith('iphone_'):
        if not has_iphone_context(name):
            return False

        if k == 'iphone_17e':
            return has_any_model_token(name, ['iphone 17e', 'айфон 17e']) and not contains_any(name, ['pro', 'про', 'max', 'air'])

        if k == 'iphone_17':
            return has_any_model_token(name, ['iphone 17', 'айфон 17']) and not contains_any(name, ['17e', 'pro', 'про', 'max', 'air'])

        if k == 'iphone_air':
            return has_any_model_token(name, ['iphone air', 'айфон air', 'айфон эйр']) and not contains_any(name, ['pro', 'про', 'max'])

        if k == 'iphone_17_pro':
            return has_any_model_token(name, ['iphone 17 pro', 'айфон 17 pro', 'айфон 17 про']) and not contains_any(name, ['max', 'макс'])

        if k == 'iphone_17_pro_max':
            return has_any_model_token(name, ['iphone 17 pro max', 'айфон 17 pro max', 'айфон 17 про max', 'айфон 17 про макс'])

        return False

    if not has_station_context(name):
        return False

    if k == 'station_light':
        return contains_any(name, ['станция лайт', 'station light']) and not contains_any(name, ['лайт 2', 'light 2', 'с часами', 'часы', 'clock'])

    if k == 'station_light_2':
        return contains_any(name, ['лайт 2', 'light 2']) and not contains_any(name, ['с часами', 'часы', 'clock'])

    if k == 'station_light_2_clock':
        return contains_any(name, ['лайт 2', 'light 2']) and contains_any(name, ['с часами', 'часы', 'clock'])

    if k == 'station_3':
        return contains_any(name, ['станция 3', 'station 3']) and not contains_any(name, ['мини 3', 'mini 3'])

    if k == 'station_mini':
        return contains_any(name, ['станция мини', 'station mini']) and not contains_any(name, ['с часами', 'часы', 'clock'])

    if k == 'station_mini_clock':
        return contains_any(name, ['станция мини', 'station mini']) and contains_any(name, ['с часами', 'часы', 'clock'])

    if k == 'station_mini_3':
        return contains_any(name, ['мини 3', 'mini 3']) and not contains_any(name, ['про', 'pro'])

    if k == 'station_mini_3_pro':
        return contains_any(name, ['мини 3', 'mini 3']) and contains_any(name, ['про', 'pro'])

    if k == 'station_midi':
        return contains_any(name, ['станция миди', 'station midi'])

    if k == 'station_2':
        return contains_any(name, ['станция 2', 'station 2']) and not contains_any(name, ['лайт 2', 'light 2'])

    if k == 'station_max':
        return contains_any(name, ['станция макс', 'station max']) and not contains_any(name, ['дуо', 'zigbee', 'зигби', 'duo'])

    if k == 'station_max_zigbee':
        return contains_any(name, ['станция макс', 'station max']) and contains_any(name, ['zigbee', 'зигби'])

    if k == 'station_duo_max':
        return contains_any(name, ['станция дуо макс', 'station duo max', 'дуо макс', 'duo max'])

    return False
