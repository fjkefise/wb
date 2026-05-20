from src.wb_price_monitor.matcher import is_accessory_name, match_product_to_model

def test_light_vs_light2():
    assert match_product_to_model('Яндекс Станция Лайт', 'station_light')
    assert not match_product_to_model('Яндекс Станция Лайт 2', 'station_light')
    assert match_product_to_model('Яндекс Станция Лайт 2', 'station_light_2')
    assert match_product_to_model('Яндекс Станция Лайт 2 с часами', 'station_light_2_clock')

def test_mini_clock():
    assert match_product_to_model('Яндекс Станция Мини', 'station_mini')
    assert match_product_to_model('Яндекс Станция Мини с часами', 'station_mini_clock')

def test_new_station_variants():
    assert match_product_to_model('Яндекс Станция 3', 'station_3')
    assert not match_product_to_model('Яндекс Станция Мини 3', 'station_3')
    assert match_product_to_model('Яндекс Станция Мини 3', 'station_mini_3')
    assert not match_product_to_model('Яндекс Станция Мини 3 Про', 'station_mini_3')
    assert match_product_to_model('Яндекс Станция Мини 3 Про', 'station_mini_3_pro')

def test_max_variants():
    assert match_product_to_model('Яндекс Станция Макс', 'station_max')
    assert match_product_to_model('Яндекс Станция Макс с Zigbee', 'station_max_zigbee')
    assert match_product_to_model('Яндекс Станция Дуо Макс', 'station_duo_max')

def test_accessories_do_not_match_stations():
    assert is_accessory_name('Полка для умной колонки "Яндекс Станции Миди"')
    assert not match_product_to_model('Полка для умной колонки "Яндекс Станции Миди"', 'station_midi')
    assert not match_product_to_model('Кронштейн настенный для Яндекс Станция Макс', 'station_max')
    assert not match_product_to_model('Чехол для Яндекс Станция Лайт 2', 'station_light_2')
    assert not match_product_to_model('Декор для Яндекс Станции Миди', 'station_midi')
    assert not match_product_to_model('Держатель под Яндекс Станцию Лайт', 'station_light')

def test_model_words_without_station_context_do_not_match():
    assert not match_product_to_model('MIDI кабель для акустики', 'station_midi')
    assert not match_product_to_model('MAX держатель для колонки', 'station_max')

def test_iphone_17_variants():
    assert match_product_to_model('Смартфон Apple iPhone 17e 256 ГБ', 'iphone_17e')
    assert match_product_to_model('Apple iPhone 17 256GB', 'iphone_17')
    assert match_product_to_model('Смартфон Apple iPhone Air 256 ГБ', 'iphone_air')
    assert match_product_to_model('Apple iPhone 17 Pro 256GB', 'iphone_17_pro')
    assert match_product_to_model('Apple iPhone 17 Pro Max 256GB', 'iphone_17_pro_max')

def test_iphone_17_variants_do_not_cross_match():
    assert not match_product_to_model('Apple iPhone 17 Pro 256GB', 'iphone_17')
    assert not match_product_to_model('Apple iPhone 17 Pro Max 256GB', 'iphone_17_pro')
    assert not match_product_to_model('Apple iPhone 17e 256GB', 'iphone_17')

def test_iphone_accessories_do_not_match():
    assert not match_product_to_model('Чехол для iPhone 17 Pro Max', 'iphone_17_pro_max')
    assert not match_product_to_model('Защитное стекло на iPhone 17', 'iphone_17')
    assert not match_product_to_model('Муляж Apple iPhone 17 Pro Max', 'iphone_17_pro_max')
    assert not match_product_to_model('Восстановленный iPhone 17 Pro', 'iphone_17_pro')
