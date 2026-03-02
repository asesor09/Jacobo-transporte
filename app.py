import streamlit as st
import psycopg2
import pandas as pd
import plotly.express as px
from datetime import datetime
import io

# --- 1. CONEXIÓN A NEON ---
DB_URL = "postgresql://neondb_owner:npg_c7Dkwlh1jzGQ@ep-lucky-shadow-ac1thtiq-pooler.sa-east-1.aws.neon.tech/neondb?sslmode=require"

def conectar_db():
    return psycopg2.connect(DB_URL)

def inicializar_tablas():
    conn = conectar_db()
    cur = conn.cursor()
    cur.execute('CREATE TABLE IF NOT EXISTS vehiculos (id SERIAL PRIMARY KEY, placa TEXT UNIQUE NOT NULL, conductor TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS gastos (id SERIAL PRIMARY KEY, vehiculo_id INTEGER REFERENCES vehiculos(id), tipo_gasto TEXT, monto NUMERIC, fecha DATE, detalle TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS ventas (id SERIAL PRIMARY KEY, vehiculo_id INTEGER REFERENCES vehiculos(id), cliente TEXT, valor_viaje NUMERIC, fecha DATE)')
    conn.commit()
    conn.close()

# Función para generar el archivo Excel
def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Reporte_Jacobo')
    return output.getvalue()

# --- 2. CONFIGURACIÓN VISUAL ---
st.set_page_config(page_title="C&E Eficiencias", layout="wide", page_icon="📈")

# Seguridad
st.sidebar.title("🔐 Acceso")
password = st.sidebar.text_input("Contraseña", type="password")
if password != "Jacobo2026":
    st.title("🚐 Sistema de Gestión Jacobo")
    st.warning("Ingrese la contraseña para ver los reportes mensuales.")
    st.stop()

try:
    inicializar_tablas()
except:
    pass

# --- 3. MENÚ DE NAVEGACIÓN ---
menu = st.sidebar.radio("MENÚ PRINCIPAL", ["📊 Dashboard Mensual", "🚚 Flota", "💸 Gastos", "💰 Ventas"])

# --- 📊 MÓDULO 1: DASHBOARD VISUAL Y MENSUAL ---
if menu == "📊 Dashboard Mensual":
    st.title("📊 Análisis de Eficiencia Mensual")
    conn = conectar_db()
    df_g = pd.read_sql("SELECT monto, fecha, tipo_gasto FROM gastos", conn)
    df_v = pd.read_sql("SELECT valor_viaje, fecha FROM ventas", conn)
    conn.close()

    if not df_g.empty or not df_v.empty:
        # Agrupación Mensual
        df_g['mes'] = pd.to_datetime(df_g['fecha']).dt.strftime('%Y-%m')
        df_v['mes'] = pd.to_datetime(df_v['fecha']).dt.strftime('%Y-%m')
        
        gastos_mes = df_g.groupby('mes')['monto'].sum().reset_index()
        ventas_mes = df_v.groupby('mes')['valor_viaje'].sum().reset_index()
        df_total = pd.merge(ventas_mes, gastos_mes, on='mes', how='outer').fillna(0)
        df_total.columns = ['Mes', 'Ingresos', 'Egresos']

        # Métricas principales con separador de miles
        c1, c2, c3 = st.columns(3)
        ing_t = df_total['Ingresos'].sum()
        egr_t = df_total['Egresos'].sum()
        c1.metric("Ingresos Totales", f"$ {ing_t:,.0f}".replace(",", "."))
        c2.metric("Egresos Totales", f"$ {egr_t:,.0f}".replace(",", "."))
        c3.metric("Utilidad Neta", f"$ {ing_t - egr_t:,.0f}".replace(",", "."), delta=f"$ {ing_t - egr_t:,.0f}")

        st.divider()
        
        # GRÁFICA DE BARRAS MENSUAL
        st.subheader("📈 Comparativo Mensual (Ingresos vs Egresos)")
        fig = px.bar(df_total, x='Mes', y=['Ingresos', 'Egresos'], barmode='group',
                     color_discrete_map={'Ingresos': '#28a745', 'Egresos': '#dc3545'})
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No hay datos registrados para mostrar gráficas.")

# --- 💸 MÓDULO 2: GASTOS (CON EXCEL) ---
elif menu == "💸 Gastos":
    st.title("💸 Registro de Gastos")
    conn = conectar_db()
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    
    with st.form("f_gastos", clear_on_submit=True):
        col1, col2 = st.columns(2)
        v_sel = col1.selectbox("Vehículo", v_data['placa'])
        v_id = int(v_data[v_data['placa'] == v_sel]['id'].values[0])
        tipo = col1.selectbox("Tipo", ["Combustible", "Peaje", "Mantenimiento", "Otros"])
        monto = col2.number_input("Monto ($)", min_value=0)
        fecha = col2.date_input("Fecha")
        if st.form_submit_button("Registrar Gasto"):
            cur = conn.cursor()
            cur.execute("INSERT INTO gastos (vehiculo_id, tipo_gasto, monto, fecha) VALUES (%s,%s,%s,%s)", (v_id, tipo, monto, fecha))
            conn.commit(); st.success("Gasto guardado."); st.rerun()

    st.divider()
    df_g_list = pd.read_sql("SELECT g.fecha, v.placa, g.tipo_gasto, g.monto FROM gastos g JOIN vehiculos v ON g.vehiculo_id = v.id ORDER BY g.fecha DESC", conn)
    if not df_g_list.empty:
        df_ver = df_g_list.copy()
        df_ver['monto'] = df_ver['monto'].apply(lambda x: f"$ {x:,.0f}".replace(",", "."))
        st.dataframe(df_ver, use_container_width=True)
        # BOTÓN DE EXCEL
        st.download_button("📥 Descargar Reporte de Gastos (Excel)", data=to_excel(df_g_list), file_name="gastos_jacobo.xlsx")
    conn.close()

# --- 💰 MÓDULO 3: VENTAS (CON EXCEL) ---
elif menu == "💰 Ventas":
    st.title("💰 Registro de Ventas")
    conn = conectar_db()
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    with st.form("f_ventas"):
        c1, c2 = st.columns(2)
        v_sel = c1.selectbox("Vehículo", v_data['placa'])
        v_id = int(v_data[v_data['placa'] == v_sel]['id'].values[0])
        cliente = c1.text_input("Cliente")
        valor = c2.number_input("Valor ($)", min_value=0)
        fecha = c2.date_input("Fecha")
        if st.form_submit_button("Guardar Venta"):
            cur = conn.cursor()
            cur.execute("INSERT INTO ventas (vehiculo_id, cliente, valor_viaje, fecha) VALUES (%s,%s,%s,%s)", (v_id, cliente, valor, fecha))
            conn.commit(); st.success("Venta guardada."); st.rerun()

    st.divider()
    df_s_list = pd.read_sql("SELECT s.fecha, v.placa, s.cliente, s.valor_viaje FROM ventas s JOIN vehiculos v ON s.vehiculo_id = v.id ORDER BY s.fecha DESC", conn)
    if not df_s_list.empty:
        df_ver_s = df_s_list.copy()
        df_ver_s['valor_viaje'] = df_ver_s['valor_viaje'].apply(lambda x: f"$ {x:,.0f}".replace(",", "."))
        st.dataframe(df_ver_s, use_container_width=True)
        # BOTÓN DE EXCEL
        st.download_button("📥 Descargar Reporte de Ventas (Excel)", data=to_excel(df_s_list), file_name="ventas_jacobo.xlsx")
    conn.close()

# --- 🚚 MÓDULO 4: FLOTA ---
elif menu == "🚚 Flota":
    st.title("🚚 Gestión de Flota")
    with st.form("f_v"):
        placa = st.text_input("Placa").upper()
        cond = st.text_input("Conductor")
        if st.form_submit_button("Guardar Vehículo"):
            conn = conectar_db(); cur = conn.cursor()
            cur.execute("INSERT INTO vehiculos (placa, conductor) VALUES (%s,%s)", (placa, cond))
            conn.commit(); conn.close(); st.success("Vehículo registrado."); st.rerun()
