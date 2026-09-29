import streamlit as st
import pandas as pd
import re

st.set_page_config(page_title="Аналитика Ozon", layout="wide")
st.title("Управленческий учет Ozon: Деревянные изделия")

uploaded_file = st.file_uploader("Перетащите сюда Отчет по начислениям (Excel)", type=["xlsx"])

if uploaded_file is not None:
    # --- ЧТЕНИЕ И ПОДГОТОВКА ДАННЫХ ---
    df = pd.read_excel(uploaded_file, header=1)
    df_orders = df[df['ID начисления'].notna()]
    
    # Считаем ИТОГОВЫЕ деньги по заказам
    order_sums = df_orders.groupby('ID начисления')['Сумма итого, руб.'].sum().reset_index()
    order_sums.rename(columns={'Сумма итого, руб.': 'Итого на руки (руб)'}, inplace=True)
    
    # Вытягиваем товары и их количество
    sales_rows = df_orders[df_orders['Тип начисления'] == 'Выручка']
    product_info = sales_rows[['ID начисления', 'Название товара', 'Количество']].groupby(['ID начисления', 'Название товара']).sum().reset_index()
    
    # Объединяем данные
    merged = pd.merge(order_sums, product_info, on='ID начисления', how='inner')
    
    # Фильтрация по дереву
    wooden_keywords = ['щит', 'доска', 'дерево', 'сосна', 'хвоя', 'фанера', 'брус', 'ступень', 'тетива', 'подоконник', 'площадка', 'балясина', 'перила']
    merged = merged[merged['Название товара'].str.lower().apply(lambda x: any(k in x for k in wooden_keywords))]
    
    # Извлечение размеров и объема
    dim_pattern = re.compile(r'(\d+)\s*[xхХ*]\s*(\d+)\s*[xхХ*]\s*(\d+)')
    
    def extract_size(name):
        match = dim_pattern.search(name)
        return f"{match.group(1)}x{match.group(2)}x{match.group(3)}" if match else "Не указан"
        
    def calc_volume_m3(name):
        match = dim_pattern.search(name)
        if match:
            l, w, h = float(match.group(1)), float(match.group(2)), float(match.group(3))
            return (l * w * h) / 1_000_000_000
        return None

    merged['Размер'] = merged['Название товара'].apply(extract_size)
    merged['Объем 1 шт (м3)'] = merged['Название товара'].apply(calc_volume_m3)
    
    # Очистка от пустых размеров и деления на ноль
    merged = merged[merged['Объем 1 шт (м3)'].notna() & (merged['Объем 1 шт (м3)'] > 0)]
    merged = merged[merged['Количество'] > 0]
    
    # Считаем кубатуру для каждого заказа
    merged['Общий объем заказа (м3)'] = merged['Объем 1 шт (м3)'] * merged['Количество']
    
    # Оставляем только успешные продажи (где деньги > 0), чтобы возвраты не искажали статистику куба
    successful_sales = merged[merged['Итого на руки (руб)'] > 0]
    
    # --- СТРАТЕГИЧЕСКАЯ ГРУППИРОВКА ПО ТОВАРАМ ---
    # Схлопываем все заказы до уровня конкретных товаров
    product_summary = successful_sales.groupby('Название товара').agg({
        'Количество': 'sum',
        'Общий объем заказа (м3)': 'sum',
        'Итого на руки (руб)': 'sum'
    }).reset_index()
    
    # Высчитываем среднюю цену куба уже для товара целиком
    product_summary['Цена за 1 м³ (руб)'] = (product_summary['Итого на руки (руб)'] / product_summary['Общий объем заказа (м3)']).round(0)
    
    # --- ИНТЕРФЕЙС И ВЫВОД НА ЭКРАН ---
    tab1, tab2, tab3 = st.tabs(["📊 Сводка и Топ продаж", "⚠️ Ниже рентабельности", "📏 Сводка по размерам"])
    
    with tab1:
        st.subheader("Главные показатели")
        
        total_money = successful_sales['Итого на руки (руб)'].sum()
        total_volume = successful_sales['Общий объем заказа (м3)'].sum()
        avg_price = total_money / total_volume if total_volume > 0 else 0
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Средняя цена за 1 м³", f"{avg_price:,.0f} руб.")
        col2.metric("Чистая прибыль на руки", f"{total_money:,.0f} руб.")
        col3.metric("Продано кубометров", f"{total_volume:.2f} м³")
        col4.metric("Всего продано (шт)", f"{successful_sales['Количество'].sum()} шт.")
        
        st.divider()
        
        st.subheader("Топ-10 товаров по Цене за 1 м³")
        # Сортируем по цене за куб по убыванию
        top_sales = product_summary.sort_values(by='Цена за 1 м³ (руб)', ascending=False).head(10)
        
        st.dataframe(top_sales[['Название товара', 'Количество', 'Цена за 1 м³ (руб)']], use_container_width=True)
        
        # Рисуем график цен за куб
        chart_data = top_sales.set_index('Название товара')[['Цена за 1 м³ (руб)']]
        st.bar_chart(chart_data)
        
    with tab2:
        st.subheader("Контроль рентабельности по товарам")
        st.write("Товары, у которых средняя цена за кубометр оказалась ниже допустимого порога.")
        
        min_price_threshold = st.number_input("Минимально допустимая цена за 1 м³ (руб.):", value=46000, step=1000)
        
        # Ищем товары ниже порога
        bad_products = product_summary[product_summary['Цена за 1 м³ (руб)'] < min_price_threshold].sort_values(by='Цена за 1 м³ (руб)', ascending=True)
        
        st.error(f"⚠ Найдено {len(bad_products)} товаров со средней ценой куба ниже {min_price_threshold} руб.")
        st.dataframe(bad_products[['Название товара', 'Количество', 'Цена за 1 м³ (руб)', 'Итого на руки (руб)']], use_container_width=True)
        
    with tab3:
        st.subheader("Популярность размеров")
        st.write("Сводная таблица по всем габаритам.")
        
        # Группируем по размерам
        size_summary = successful_sales.groupby('Размер').agg({
            'Количество': 'sum',
            'Общий объем заказа (м3)': 'sum',
            'Итого на руки (руб)': 'sum'
        }).reset_index()
        
        size_summary['Ср. цена за куб (руб)'] = (size_summary['Итого на руки (руб)'] / size_summary['Общий объем заказа (м3)']).round(0)
        size_summary = size_summary.sort_values(by='Количество', ascending=False)
        
        st.dataframe(size_summary[['Размер', 'Количество', 'Ср. цена за куб (руб)', 'Итого на руки (руб)']], use_container_width=True)