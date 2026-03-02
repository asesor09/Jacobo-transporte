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
    # NUEVA: Tabla de Ventas / Viajes
    cur.execute('''
        CREATE TABLE IF NOT EXISTS ventas (
            id SERIAL PRIMARY KEY,
            vehiculo_id INTEGER REFERENCES vehiculos(id),
            cliente TEXT,
            origen TEXT,
            destino TEXT,
            valor_viaje NUMERIC,
            fecha DATE,
            descripcion TEXT
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

st.title("🚐 Panel de Control - Gestión de Eficiencia")
menu = st.sidebar.radio("Navegación", ["🏠 Inicio", "🚚 Vehículos", "💸 Gastos", "💰 Ventas / Viajes"])

# --- 🏠 INICIO (Actualizado con Ventas) ---
if menu == "🏠 Inicio":
    conn = conectar_db()
    v = pd.read_sql("SELECT COUNT(*) FROM vehiculos", conn).iloc[0,0]
    g = pd.read_sql("SELECT SUM(monto) FROM gastos", conn).iloc[0,0] or 0
    s = pd.read_sql("SELECT SUM(valor_viaje) FROM ventas", conn).iloc[0,0] or 0
    conn.close()
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Unidades", v)
    c2.metric("Total Gastos", f"${g:,.2f}")
    c3.metric("Total Ventas", f"${s:,.2f}", delta=f"${s-g:,.2f} (Utilidad)")

# --- 💰 NUEVA SECCIÓN: VENTAS / VIAJES ---
elif menu == "💰 Ventas / Viajes":
    st.header("Registro de Ventas y Viajes")
    conn = conectar_db()
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    
    if not v_data.empty:
        t_reg, t_ver = st.tabs(["➕ Registrar Viaje", "🔍 Historial de Ventas"])
        
        with t_reg:
            with st.form("reg_venta"):
                col1, col2 = st.columns(2)
                v_sel = col1.selectbox("Vehículo que hizo el viaje", v_data['placa'])
                v_id = int(v_data[v_data['placa'] == v_sel]['id'].values[0])
                cliente = col1.text_input("Cliente / Empresa")
                valor = col1.number_input("Valor del Viaje ($)", min_value=0.0)
                
                origen = col2.text_input("Origen")
                destino = col2.text_input("Destino")
                fecha = col2.date_input("Fecha del Viaje")
                
                if st.form_submit_button("Guardar Venta"):
                    cur = conn.cursor()
                    cur.execute('''INSERT INTO ventas (vehiculo_id, cliente, origen, destino, valor_viaje, fecha) 
                                   VALUES (%s,%s,%s,%s,%s,%s)''', (v_id, cliente, origen, destino, valor, fecha))
                    conn.commit(); st.success("Venta registrada correctamente"); st.rerun()
        
        with t_ver:
            df_s = pd.read_sql('''SELECT v.fecha, veh.placa, v.cliente, v.origen, v.destino, v.valor_viaje 
                                  FROM ventas v JOIN vehiculos veh ON v.vehiculo_id = veh.id''', conn)
            if not df_s.empty:
                st.dataframe(df_s, use_container_width=True)
            else:
                st.info("No hay viajes registrados aún.")
    else:
        st.warning("Debe registrar un vehículo primero.")
    conn.close()

# ... (El resto del código de Vehículos y Gastos se mantiene igual)
