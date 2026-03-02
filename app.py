import streamlit as st
import psycopg2
import pandas as pd
from datetime import datetime

# --- CONFIGURACIÓN DE CONEXIÓN GLOBAL (NEON) ---
DB_URL = "postgresql://neondb_owner:npg_c7Dkwlh1jzGQ@ep-lucky-shadow-ac1thtiq-pooler.sa-east-1.aws.neon.tech/neondb?sslmode=require"

def conectar_db():
    return psycopg2.connect(DB_URL)

def inicializar_tablas():
    conn = conectar_db()
    cur = conn.cursor()
    # Tabla de Vehículos
    cur.execute('''
        CREATE TABLE IF NOT EXISTS vehiculos (
            id SERIAL PRIMARY KEY,
            placa TEXT UNIQUE NOT NULL,
            marca TEXT,
            modelo TEXT,
            tipo TEXT,
            conductor TEXT,
            km_actual INTEGER DEFAULT 0
        )
    ''')
    # Tabla de Gastos
    cur.execute('''
        CREATE TABLE IF NOT EXISTS gastos (
            id SERIAL PRIMARY KEY,
            vehiculo_id INTEGER REFERENCES vehiculos(id),
            tipo_gasto TEXT,
            monto NUMERIC,
            institucion_destino TEXT,
            fecha DATE,
            detalle TEXT
        )
    ''')
    # Tabla de Ventas / Viajes
    cur.execute('''
        CREATE TABLE IF NOT EXISTS ventas (
            id SERIAL PRIMARY KEY,
            vehiculo_id INTEGER REFERENCES vehiculos(id),
            cliente TEXT,
            origen TEXT,
            destino TEXT,
            valor_viaje NUMERIC,
            fecha DATE
        )
    ''')
    conn.commit()
    conn.close()

# --- INTERFAZ ---
st.set_page_config(page_title="Transporte Jacobo Pro", layout="wide", page_icon="🚐")

# Seguridad
st.sidebar.title("🔐 Acceso")
password = st.sidebar.text_input("Contraseña", type="password")
if password != "Jacobo2026":
    st.title("🚐 Sistema de Gestión de Transporte")
    st.warning("Por favor, ingrese la contraseña.")
    st.stop()

try:
    inicializar_tablas()
except:
    pass

st.title("🚐 Panel de Control - Gestión Global")
menu = st.sidebar.radio("Navegación", ["🏠 Inicio", "🚚 Gestión de Vehículos", "💸 Registro de Gastos", "💰 Ventas / Viajes"])

# --- 🏠 1. SECCIÓN INICIO ---
if menu == "🏠 Inicio":
    conn = conectar_db()
    v = pd.read_sql("SELECT COUNT(*) FROM vehiculos", conn).iloc[0,0]
    g = pd.read_sql("SELECT SUM(monto) FROM gastos", conn).iloc[0,0] or 0
    s = pd.read_sql("SELECT SUM(valor_viaje) FROM ventas", conn).iloc[0,0] or 0
    conn.close()
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Unidades en Flota", v)
    c2.metric("Total Gastos", f"${g:,.2f}")
    c3.metric("Total Ventas", f"${s:,.2f}")
    st.info(f"💡 Utilidad Actual: ${s-g:,.2f}")

# --- 🚚 2. SECCIÓN VEHÍCULOS ---
elif menu == "🚚 Gestión de Vehículos":
    t_reg, t_edit, t_ver = st.tabs(["➕ Registrar", "✏️ Editar", "🔍 Ver Flota"])
    with t_reg:
        with st.form("reg_v"):
            c1, c2 = st.columns(2)
            placa = c1.text_input("Placa").upper()
            marca = c1.text_input("Marca")
            modelo = c1.text_input("Modelo")
            cond = c2.text_input("Conductor")
            tipo = c2.selectbox("Tipo", ["Ambulancia", "Van", "Particular"])
            km = c2.number_input("KM Inicial", min_value=0)
            if st.form_submit_button("Guardar Vehículo"):
                conn = conectar_db(); cur = conn.cursor()
                cur.execute("INSERT INTO vehiculos (placa, marca, modelo, tipo, conductor, km_actual) VALUES (%s,%s,%s,%s,%s,%s)", (placa, marca, modelo, tipo, cond, km))
                conn.commit(); conn.close(); st.success("Registrado"); st.rerun()
    with t_ver:
        conn = conectar_db()
        st.dataframe(pd.read_sql("SELECT * FROM vehiculos", conn), use_container_width=True)
        conn.close()

# --- 💸 3. SECCIÓN GASTOS ---
elif menu == "💸 Registro de Gastos":
    st.header("Control de Gastos")
    conn = conectar_db()
    v_list = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    if not v_list.empty:
        with st.form("reg_g"):
            v_sel = st.selectbox("Vehículo", v_list['placa'])
            v_id = int(v_list[v_list['placa'] == v_sel]['id'].values[0])
            monto = st.number_input("Monto", min_value=0.0)
            inst = st.text_input("Institución/Detalle")
            fecha = st.date_input("Fecha Gasto")
            if st.form_submit_button("Guardar Gasto"):
                cur = conn.cursor()
                cur.execute("INSERT INTO gastos (vehiculo_id, monto, institucion_destino, fecha) VALUES (%s,%s,%s,%s)", (v_id, monto, inst, fecha))
                conn.commit(); st.success("Gasto guardado"); st.rerun()
        df_g = pd.read_sql("SELECT g.*, v.placa FROM gastos g JOIN vehiculos v ON g.vehiculo_id = v.id", conn)
        st.dataframe(df_g, use_container_width=True)
    conn.close()

# --- 💰 4. SECCIÓN VENTAS ---
elif menu == "💰 Ventas / Viajes":
    st.header("Registro de Ventas")
    conn = conectar_db()
    v_list = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    if not v_list.empty:
        with st.form("reg_s"):
            v_sel = st.selectbox("Vehículo", v_list['placa'])
            v_id = int(v_list[v_list['placa'] == v_sel]['id'].values[0])
            cliente = st.text_input("Cliente")
            valor = st.number_input("Valor Viaje", min_value=0.0)
            fecha = st.date_input("Fecha Viaje")
            if st.form_submit_button("Guardar Venta"):
                cur = conn.cursor()
                cur.execute("INSERT INTO ventas (vehiculo_id, cliente, valor_viaje, fecha) VALUES (%s,%s,%s,%s)", (v_id, cliente, valor, fecha))
                conn.commit(); st.success("Venta guardada"); st.rerun()
        df_v = pd.read_sql("SELECT s.*, v.placa FROM ventas s JOIN vehiculos v ON s.vehiculo_id = v.id", conn)
        st.dataframe(df_v, use_container_width=True)
    conn.close()
