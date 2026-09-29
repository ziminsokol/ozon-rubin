import streamlit as st
import pandas as pd
import re
import io

# Настройки страницы
st.set_page_config(page_title="Расчет цены за куб", page_icon="🧊", layout="wide")

# Заголовок
st.markdown("<h1 style='text-align: center;'>🧊 Расчет цены за кубометр Ozon</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: gray;'>Аналитика рентабельности и контроль стоимости деревянных изделий</p>", unsafe_allow_html=True)
st.write("")

# Блок загрузки файла
with st.container():
    uploaded_file = st.file_uploader("📂 Загрузите 'Отчет по начислениям' (формат .xlsx)", type=["xlsx"])

if uploaded_file is not None:
    with st.spinner('Анализируем данные...'):
        # --- ЧТЕНИЕ И ПОДГОТОВКА ДАННЫХ ---
        df = pd.read_excel(uploaded_file, header=1)
        df_orders = df[df['ID начисления'].notna()]
        
        order_sums = df_orders.groupby('ID начисления')['Сумма итого, руб.'].sum().reset_index()
        order_sums.rename(columns={'Сумма итого, руб.': 'Итого на руки (руб)'}, inplace=True)
        
        sales_rows = df_orders[df_orders['Тип начисления'] == 'Выручка']
        product_info = sales_rows[['ID начисления', 'Название товара', 'Количество']].groupby(['ID начисления', 'Название товара']).sum().reset_index()
        
        merged = pd.merge(order_sums, product_info, on='ID начисления', how='inner')
        
        wooden_keywords = ['щит', 'доска', 'дерево', 'сосна', 'хвоя', 'фанера', 'брус', 'ступень', 'тетива', 'подоконник', 'площадка', 'балясина', 'перила']
        merged = merged[merged['Название товара'].str.lower().apply(lambda x: any(k in x for k in wooden_keywords))]
        
        dim_pattern = re.compile(r'(\d+)\s*[xхХ*]\s*(\d+)\s*[xхХ*]\s*(\d+)')
        
        def extract_size(name):
            match = dim_pattern.search(name)
            return f"{match.group(1)}x{match.group(2)}x{match.group(3)}" if match else "Не указан"
            
        def calc_volume_m3(name):
            match = dim_pattern.search(name)
            if match:
                return (float(match.group(1)) * float(match.group(2)) * float(match.group(3))) / 1_000_000_000
            return None

        merged['Размер'] = merged['Название товара'].apply(extract_size)
        merged['Объем 1 шт (м3)'] = merged['Название товара'].apply(calc_volume_m3)
        
        merged = merged[merged['Объем 1 шт (м3)'].notna() & (merged['Объем 1 шт (м3)'] > 0)]
        merged = merged[merged['Количество'] > 0]
        
        merged['Общий объем заказа (м3)'] = merged['Объем 1 шт (м3)'] * merged['Количество']
        successful_sales = merged[merged['Итого на руки (руб)'] > 0]
        
        product_summary = successful_sales.groupby('Название товара').agg({
            'Количество': 'sum',
            'Общий объем заказа (м3)': 'sum',
            'Итого на руки (руб)': 'sum'
        }).reset_index()
        
        product_summary['Цена за 1 м³ (руб)'] = (product_summary['Итого на руки (руб)'] / product_summary['Общий объем заказа (м3)']).round(0)
        
        # --- БОКОВАЯ ПАНЕЛЬ (SIDEBAR) ---
        st.sidebar.header("⚙️ Настройки отчета")
        min_price_threshold = st.sidebar.number_input("Мин. планка 1 м³ (руб.):", value=46000, step=1000)
        
        # Подготовка данных для таблиц и Excel
        bad_products = product_summary[product_summary['Цена за 1 м³ (руб)'] < min_price_threshold].sort_values(by='Цена за 1 м³ (руб)', ascending=True)
        
        size_summary = successful_sales.groupby('Размер').agg({
            'Количество': 'sum',
            'Общий объем заказа (м3)': 'sum',
            'Итого на руки (руб)': 'sum'
        }).reset_index()
        size_summary['Ср. цена за куб (руб)'] = (size_summary['Итого на руки (руб)'] / size_summary['Общий объем заказа (м3)']).round(0)
        size_summary = size_summary.sort_values(by='Количество', ascending=False)

        # Функция создания Excel файла в памяти
        def to_excel(df_prod, df_bad, df_size):
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_prod.to_excel(writer, index=False, sheet_name='Все товары')
                if not df_bad.empty:
                    df_bad.to_excel(writer, index=False, sheet_name='Ниже маржи')
                df_size.to_excel(writer, index=False, sheet_name='Сводка по размерам')
            return output.getvalue()

        excel_data = to_excel(product_summary, bad_products, size_summary)
        
        st.sidebar.divider()
        st.sidebar.download_button(
            label="📥 Выгрузить в Excel",
            data=excel_data,
            file_name="ozon_analytics.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        # --- ИНТЕРФЕЙС И ВЫВОД НА ЭКРАН ---
        tab1, tab2, tab3 = st.tabs(["📊 Главная сводка", "📉 Контроль рентабельности", "📐 Анализ размеров"])
        
        with tab1:
            st.markdown("### 🎯 Ключевые показатели")
            
            total_money = successful_sales['Итого на руки (руб)'].sum()
            total_volume = successful_sales['Общий объем заказа (м3)'].sum()
            avg_price = total_money / total_volume if total_volume > 0 else 0
            
            with st.container(border=True):
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Ср. цена за 1 м³", f"{avg_price:,.0f} ₽")
                col2.metric("Чистая прибыль", f"{total_money:,.0f} ₽")
                col3.metric("Продано кубометров", f"{total_volume:.2f} м³")
                col4.metric("Количество", f"{successful_sales['Количество'].sum()} шт.")
            
            st.info("💡 Полную детализацию по всем проданным товарам можно скачать кнопкой «Выгрузить в Excel» в левом боковом меню.")
            
        with tab2:
            st.markdown("### ⚠️ Товары с низкой маржинальностью")
            st.info("Позиции ниже заданной планки. Настроить порог можно в левом боковом меню.")
            
            if not bad_products.empty:
                st.warning(f"Найдено товаров, не дотягивающих до нормы: {len(bad_products)}")
                st.dataframe(
                    bad_products,
                    column_config={
                        "Название товара": "Наименование товара",
                        "Количество": st.column_config.NumberColumn("Продано шт", format="%d"),
                        "Общий объем заказа (м3)": None,
                        "Итого на руки (руб)": st.column_config.NumberColumn("Сумма на руки", format="%d ₽"),
                        "Цена за 1 м³ (руб)": st.column_config.NumberColumn("Фактическая цена м³", format="%d ₽")
                    },
                    hide_index=True,
                    use_container_width=True
                )
            else:
                st.success("Отличный результат! Все товары продаются выше установленного порога.")
            
        with tab3:
            st.markdown("### 📐 Статистика по габаритам")
            st.dataframe(
                size_summary,
                column_config={
                    "Размер": "Габариты (ДхШхВ)",
                    "Количество": st.column_config.NumberColumn("Продано", format="%d шт"),
                    "Общий объем заказа (м3)": st.column_config.NumberColumn("Общий объем", format="%.3f м³"),
                    "Итого на руки (руб)": st.column_config.NumberColumn("Чистая выручка", format="%d ₽"),
                    "Ср. цена за куб (руб)": st.column_config.NumberColumn("Ср. цена м³", format="%d ₽")
                },
                hide_index=True,
                use_container_width=True
            )
