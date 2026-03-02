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
    cur.execute('''
        CREATE TABLE IF NOT EXISTS ventas (
            id SERIAL PRIMARY KEY,
            vehiculo_id INTEGER REFERENCES vehiculos(id),
            cliente TEXT,
            valor_viaje NUMERIC,
            fecha DATE
        )
    ''')
    conn.commit()
    conn.close()

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
    # Agregamos el signo $ aquí
    col2.metric("Total Gastos", f"$ {g:,.0f}")
    col3.metric("Total Ventas", f"$ {s:,.0f}")
    
    utilidad = s - g
    if utilidad >= 0:
        st.success(f"📈 Utilidad Neta: $ {utilidad:,.0f}")
    else:
        st.error(f"📉 Déficit Actual: $ {utilidad:,.0f}")

# --- 🚚 VEHÍCULOS ---
elif menu == "🚚 Vehículos":
    st.title("🚚 Gestión de Unidades")
    with st.form("nuevo_v"):
        st.subheader("Registrar Nuevo Vehículo")
        c1, c2 = st.columns(2)
        placa = c1.text_input("Placa (Ej: XYZ123)").upper()
        marca = c1.text_input("Marca")
        modelo = c2.text_input("Modelo (Año)")
        cond = c2.text_input("Conductor Asignado")
        if st.form_submit_button("Guardar Vehículo"):
            if placa:
                conn = conectar_db(); cur = conn.cursor()
                try:
                    cur.execute("INSERT INTO vehiculos (placa, marca, modelo, conductor) VALUES (%s,%s,%s,%s)", (placa, marca, modelo, cond))
                    conn.commit(); st.success("Vehículo guardado en la nube")
                except: st.error("Esa placa ya existe")
                finally: conn.close(); st.rerun()

# --- 💸 GASTOS ---
elif menu == "💸 Gastos":
    st.title("💸 Registro de Gastos")
    conn = conectar_db()
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    
    if v_data.empty:
        st.warning("⚠️ Primero debe registrar un vehículo.")
    else:
        with st.form("form_gastos", clear_on_submit=True):
            col1, col2 = st.columns(2)
            veh_sel = col1.selectbox("Vehículo", v_data['placa'])
            v_id = int(v_data[v_data['placa'] == veh_sel]['id'].values[0])
            tipo = col1.selectbox("Tipo de Gasto", ["Combustible", "Peaje", "Mantenimiento", "Lavada", "Parqueadero", "Otros"])
            monto = col2.number_input("Monto ($)", min_value=0)
            fecha = col2.date_input("Fecha", value=datetime.now())
            detalle = st.text_input("Detalle / Observación")
            
            if st.form_submit_button("Registrar Gasto"):
                cur = conn.cursor()
                cur.execute("INSERT INTO gastos (vehiculo_id, tipo_gasto, monto, fecha, detalle) VALUES (%s,%s,%s,%s,%s)", (v_id, tipo, monto, fecha, detalle))
                conn.commit(); st.success(f"Gasto de $ {monto:,.0f} registrado."); st.rerun()

        st.divider()
        df_gastos = pd.read_sql('''
            SELECT g.fecha as "Fecha", v.placa as "Placa", g.tipo_gasto as "Tipo", 
            concat('$ ', format('%s', g.monto)) as "Valor", g.detalle as "Detalle" 
            FROM gastos g JOIN vehiculos v ON g.vehiculo_id = v.id ORDER BY g.fecha DESC
        ''', conn)
        st.dataframe(df_gastos, use_container_width=True)
    conn.close()

# --- 💰 VENTAS ---
elif menu == "💰 Ventas":
    st.title("💰 Registro de Ventas")
    conn = conectar_db()
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    
    if v_data.empty:
        st.warning("⚠️ Registre un vehículo primero.")
    else:
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
                conn.commit(); st.success(f"Venta de $ {valor:,.0f} guardada."); st.rerun()
        
        df_v = pd.read_sql('''
            SELECT s.fecha as "Fecha", v.placa as "Placa", s.cliente as "Cliente", 
            concat('$ ', format('%s', s.valor_viaje)) as "Ingreso" 
            FROM ventas s JOIN vehiculos v ON s.vehiculo_id = v.id ORDER BY s.fecha DESC
        ''', conn)
        st.dataframe(df_v, use_container_width=True)
    conn.close()
