import streamlit as st
import psycopg2
import pandas as pd
from datetime import datetime
import io

# --- CONFIGURACIÓN DE CONEXIÓN GLOBAL (NEON) ---
DB_URL = "postgresql://neondb_owner:npg_c7Dkwlh1jzGQ@ep-lucky-shadow-ac1thtiq-pooler.sa-east-1.aws.neon.tech/neondb?sslmode=require"

def conectar_db():
    return psycopg2.connect(DB_URL)

def inicializar_tablas():
    conn = conectar_db()
    cur = conn.cursor()
    cur.execute('CREATE TABLE IF NOT EXISTS vehiculos (id SERIAL PRIMARY KEY, placa TEXT UNIQUE NOT NULL, marca TEXT, modelo TEXT, conductor TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS gastos (id SERIAL PRIMARY KEY, vehiculo_id INTEGER REFERENCES vehiculos(id), tipo_gasto TEXT, monto NUMERIC, fecha DATE, detalle TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS ventas (id SERIAL PRIMARY KEY, vehiculo_id INTEGER REFERENCES vehiculos(id), cliente TEXT, valor_viaje NUMERIC, fecha DATE)')
    conn.commit()
    conn.close()

# Función para convertir DataFrame a Excel descargable
def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Reporte')
    return output.getvalue()

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="C&E Eficiencias", layout="wide", page_icon="🚐")

# Seguridad
st.sidebar.title("🔐 Acceso")
password = st.sidebar.text_input("Contraseña", type="password")
if password != "Jacobo2026":
    st.title("🚐 Sistema de Gestión de Transporte")
    st.warning("Por favor, ingrese la contraseña en la barra lateral.")
    st.stop()

try:
    inicializar_tablas()
except:
    pass

st.sidebar.title("Navegación")
menu = st.sidebar.radio("Ir a:", ["🏠 Inicio", "🚚 Vehículos", "💸 Gastos", "💰 Ventas"])

# --- 🏠 INICIO ---
if menu == "🏠 Inicio":
    st.title("📊 Resumen General")
    conn = conectar_db()
    v = pd.read_sql("SELECT COUNT(*) FROM vehiculos", conn).iloc[0,0]
    g = pd.read_sql("SELECT SUM(monto) FROM gastos", conn).iloc[0,0] or 0
    s = pd.read_sql("SELECT SUM(valor_viaje) FROM ventas", conn).iloc[0,0] or 0
    conn.close()
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Vehículos", v)
    col2.metric("Total Gastos", f"$ {g:,.0f}".replace(",", "."))
    col3.metric("Total Ventas", f"$ {s:,.0f}".replace(",", "."))
    
    utilidad = s - g
    if utilidad >= 0:
        st.success(f"📈 Utilidad Neta: $ {utilidad:,.0f}".replace(",", "."))
    else:
        st.error(f"📉 Déficit Actual: $ {utilidad:,.0f}".replace(",", "."))

# --- 🚚 VEHÍCULOS ---
elif menu == "🚚 Vehículos":
    st.title("🚚 Gestión de Unidades")
    with st.form("nuevo_v"):
        st.subheader("Registrar Nuevo Vehículo")
        c1, c2 = st.columns(2)
        placa = c1.text_input("Placa").upper()
        marca = c1.text_input("Marca")
        modelo = c2.text_input("Modelo")
        cond = c2.text_input("Conductor")
        if st.form_submit_button("Guardar Vehículo"):
            if placa:
                conn = conectar_db(); cur = conn.cursor()
                try:
                    cur.execute("INSERT INTO vehiculos (placa, marca, modelo, conductor) VALUES (%s,%s,%s,%s)", (placa, marca, modelo, cond))
                    conn.commit(); st.success("Vehículo guardado")
                except: st.error("Esa placa ya existe")
                finally: conn.close(); st.rerun()

    st.divider()
    conn = conectar_db()
    df_v = pd.read_sql("SELECT placa as \"Placa\", marca as \"Marca\", modelo as \"Modelo\", conductor as \"Conductor\" FROM vehiculos", conn)
    conn.close()
    st.dataframe(df_v, use_container_width=True)
    st.download_button(label="📥 Descargar Flota en Excel", data=to_excel(df_v), file_name='flota_vehiculos.xlsx')

# --- 💸 GASTOS ---
elif menu == "💸 Gastos":
    st.title("💸 Registro de Gastos")
    conn = conectar_db()
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    
    if not v_data.empty:
        with st.form("form_gastos", clear_on_submit=True):
            col1, col2 = st.columns(2)
            veh_sel = col1.selectbox("Vehículo", v_data['placa'])
            v_id = int(v_data[v_data['placa'] == veh_sel]['id'].values[0])
            tipo = col1.selectbox("Tipo de Gasto", ["Combustible", "Peaje", "Mantenimiento", "Lavada", "Otros"])
            monto = col2.number_input("Monto ($)", min_value=0)
            fecha = col2.date_input("Fecha", value=datetime.now())
            detalle = st.text_input("Detalle")
            if st.form_submit_button("Registrar Gasto"):
                cur = conn.cursor()
                cur.execute("INSERT INTO gastos (vehiculo_id, tipo_gasto, monto, fecha, detalle) VALUES (%s,%s,%s,%s,%s)", (v_id, tipo, monto, fecha, detalle))
                conn.commit(); st.success("Gasto registrado"); st.rerun()

        st.divider()
        df_g = pd.read_sql('''
            SELECT g.fecha as "Fecha", v.placa as "Placa", g.tipo_gasto as "Tipo", g.monto as "Monto_Num", g.detalle as "Detalle" 
            FROM gastos g JOIN vehiculos v ON g.vehiculo_id = v.id ORDER BY g.fecha DESC
        ''', conn)
        
        if not df_g.empty:
            # Formatear para visualización con puntos de miles
            df_mostrar = df_g.copy()
            df_mostrar["Monto"] = df_mostrar["Monto_Num"].apply(lambda x: f"$ {x:,.0f}".replace(",", "."))
            st.dataframe(df_mostrar[["Fecha", "Placa", "Tipo", "Monto", "Detalle"]], use_container_width=True)
            st.download_button(label="📥 Descargar Gastos en Excel", data=to_excel(df_g), file_name='reporte_gastos.xlsx')
    conn.close()

# --- 💰 VENTAS ---
elif menu == "💰 Ventas":
    st.title("💰 Registro de Ventas")
    conn = conectar_db()
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    
    if not v_data.empty:
        with st.form("form_ventas"):
            c1, c2 = st.columns(2)
            veh_sel = c1.selectbox("Vehículo", v_data['placa'])
            v_id = int(v_data[v_data['placa'] == veh_sel]['id'].values[0])
            cliente = c1.text_input("Cliente")
            valor = c2.number_input("Valor Viaje ($)", min_value=0)
            fecha = c2.date_input("Fecha")
            if st.form_submit_button("Guardar Venta"):
                cur = conn.cursor()
                cur.execute("INSERT INTO ventas (vehiculo_id, cliente, valor_viaje, fecha) VALUES (%s,%s,%s,%s)", (v_id, cliente, valor, fecha))
                conn.commit(); st.success("Venta guardada"); st.rerun()
        
        st.divider()
        df_v = pd.read_sql('''
            SELECT s.fecha as "Fecha", v.placa as "Placa", s.cliente as "Cliente", s.valor_viaje as "Valor_Num" 
            FROM ventas s JOIN vehiculos v ON s.vehiculo_id = v.id ORDER BY s.fecha DESC
        ''', conn)
        
        if not df_v.empty:
            df_mostrar_v = df_v.copy()
            df_mostrar_v["Ingreso"] = df_mostrar_v["Valor_Num"].apply(lambda x: f"$ {x:,.0f}".replace(",", "."))
            st.dataframe(df_mostrar_v[["Fecha", "Placa", "Cliente", "Ingreso"]], use_container_width=True)
            st.download_button(label="📥 Descargar Ventas en Excel", data=to_excel(df_v), file_name='reporte_ventas.xlsx')
    conn.close()
