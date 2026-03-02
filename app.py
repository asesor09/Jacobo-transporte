import streamlit as st
import psycopg2
import pandas as pd
import plotly.express as px
from datetime import datetime
import io

# --- 1. CONFIGURACIÓN DE CONEXIÓN ---
DB_URL = "postgresql://neondb_owner:npg_c7Dkwlh1jzGQ@ep-lucky-shadow-ac1thtiq-pooler.sa-east-1.aws.neon.tech/neondb?sslmode=require"

def conectar_db():
    return psycopg2.connect(DB_URL)

def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Reporte')
    return output.getvalue()

# --- 2. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="C&E Eficiencias", layout="wide", page_icon="📊")

# Seguridad
st.sidebar.title("🔐 Acceso")
password = st.sidebar.text_input("Contraseña", type="password")
if password != "Jacobo2026":
    st.title("🚐 Sistema C&E Eficiencias")
    st.info("Ingrese la contraseña para continuar.")
    st.stop()

# --- 3. MENÚ PRINCIPAL ---
st.sidebar.divider()
menu = st.sidebar.radio("Navegación", ["📊 Dashboard Visual", "🚚 Flota de Vehículos", "💸 Gestión de Gastos", "💰 Control de Ventas"])

# --- 📊 MÓDULO 1: DASHBOARD VISUAL Y MENSUAL ---
if menu == "📊 Dashboard Visual":
    st.title("📈 Análisis de Rendimiento Mensual")
    conn = conectar_db()
    df_g = pd.read_sql("SELECT monto, fecha, tipo_gasto FROM gastos", conn)
    df_v = pd.read_sql("SELECT valor_viaje, fecha FROM ventas", conn)
    conn.close()

    if not df_g.empty or not df_v.empty:
        # Procesamiento de Fechas
        df_g['mes'] = pd.to_datetime(df_g['fecha']).dt.strftime('%Y-%m')
        df_v['mes'] = pd.to_datetime(df_v['fecha']).dt.strftime('%Y-%m')

        # Totales para métricas
        total_g = df_g['monto'].sum()
        total_v = df_v['valor_viaje'].sum()

        c1, c2, c3 = st.columns(3)
        c1.metric("Ingresos Totales", f"$ {total_v:,.0f}".replace(",", "."))
        c2.metric("Gastos Totales", f"$ {total_g:,.0f}".replace(",", "."))
        c3.metric("Utilidad Actual", f"$ {total_v - total_g:,.0f}".replace(",", "."), delta=f"{total_v - total_g:,.0f}")

        st.divider()

        # Gráfica Mensual (Barras)
        st.subheader("🗓️ Comparativo Mensual: Ventas vs Gastos")
        ventas_mes = df_v.groupby('mes')['valor_viaje'].sum().reset_index()
        gastos_mes = df_g.groupby('mes')['monto'].sum().reset_index()
        df_merge = pd.merge(ventas_mes, gastos_mes, on='mes', how='outer').fillna(0)
        df_merge.columns = ['Mes', 'Ingresos', 'Gastos']
        
        fig_bar = px.bar(df_merge, x='Mes', y=['Ingresos', 'Gastos'], barmode='group',
                         color_discrete_map={'Ingresos': '#28a745', 'Gastos': '#dc3545'})
        st.plotly_chart(fig_bar, use_container_width=True)

        # Gráfica de Pastel (Distribución)
        st.subheader("🍕 Distribución de Gastos por Tipo")
        fig_pie = px.pie(df_g, values='monto', names='tipo_gasto', hole=0.4)
        st.plotly_chart(fig_pie, use_container_width=True)
    else:
        st.warning("No hay datos suficientes para generar gráficas aún.")

# --- 🚚 MÓDULO 2: VEHÍCULOS ---
elif menu == "🚚 Flota de Vehículos":
    st.title("🚚 Registro de Flota")
    with st.expander("Registrar Nuevo Vehículo"):
        with st.form("v_form"):
            placa = st.text_input("Placa").upper()
            cond = st.text_input("Conductor")
            if st.form_submit_button("Guardar"):
                conn = conectar_db(); cur = conn.cursor()
                cur.execute("INSERT INTO vehiculos (placa, conductor) VALUES (%s,%s)", (placa, cond))
                conn.commit(); conn.close(); st.success("Guardado"); st.rerun()
    
    conn = conectar_db()
    df_v = pd.read_sql("SELECT * FROM vehiculos", conn)
    conn.close()
    st.dataframe(df_v, use_container_width=True)

# --- 💸 MÓDULO 3: GASTOS (VENTANA COMPLETA) ---
elif menu == "💸 Gestión de Gastos":
    st.title("💸 Registro de Gastos")
    conn = conectar_db()
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    
    with st.form("g_form"):
        v_sel = st.selectbox("Vehículo", v_data['placa'])
        v_id = int(v_data[v_data['placa'] == v_sel]['id'].values[0])
        tipo = st.selectbox("Tipo de Gasto", ["Combustible", "Peaje", "Mantenimiento", "Lavada", "Otros"])
        monto = st.number_input("Monto ($)", min_value=0)
        fecha = st.date_input("Fecha")
        if st.form_submit_button("Registrar Gasto"):
            cur = conn.cursor()
            cur.execute("INSERT INTO gastos (vehiculo_id, tipo_gasto, monto, fecha) VALUES (%s,%s,%s,%s)", (v_id, tipo, monto, fecha))
            conn.commit(); st.success("Gasto Registrado"); st.rerun()
    
    st.divider()
    df_g = pd.read_sql("SELECT g.fecha, v.placa, g.tipo_gasto, g.monto FROM gastos g JOIN vehiculos v ON g.vehiculo_id = v.id ORDER BY g.fecha DESC", conn)
    conn.close()
    
    if not df_g.empty:
        df_visto = df_g.copy()
        df_visto['monto'] = df_visto['monto'].apply(lambda x: f"$ {x:,.0f}".replace(",", "."))
        st.dataframe(df_visto, use_container_width=True)
        st.download_button("Descargar Gastos en Excel", data=to_excel(df_g), file_name="gastos.xlsx")

# --- 💰 MÓDULO 4: VENTAS ---
elif menu == "💰 Control de Ventas":
    st.title("💰 Registro de Ventas")
    conn = conectar_db()
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    
    with st.form("s_form"):
        v_sel = st.selectbox("Vehículo", v_data['placa'])
        v_id = int(v_data[v_data['placa'] == v_sel]['id'].values[0])
        cliente = st.text_input("Cliente")
        valor = st.number_input("Valor Viaje ($)", min_value=0)
        fecha = st.date_input("Fecha")
        if st.form_submit_button("Registrar Venta"):
            cur = conn.cursor()
            cur.execute("INSERT INTO ventas (vehiculo_id, cliente, valor_viaje, fecha) VALUES (%s,%s,%s,%s)", (v_id, cliente, valor, fecha))
            conn.commit(); st.success("Venta Registrada"); st.rerun()
    
    st.divider()
    df_s = pd.read_sql("SELECT s.fecha, v.placa, s.cliente, s.valor_viaje FROM ventas s JOIN vehiculos v ON s.vehiculo_id = v.id ORDER BY s.fecha DESC", conn)
    conn.close()
    
    if not df_s.empty:
        df_visto_s = df_s.copy()
        df_visto_s['valor_viaje'] = df_visto_s['valor_viaje'].apply(lambda x: f"$ {x:,.0f}".replace(",", "."))
        st.dataframe(df_visto_s, use_container_width=True)
        st.download_button("Descargar Ventas en Excel", data=to_excel(df_s), file_name="ventas.xlsx")
