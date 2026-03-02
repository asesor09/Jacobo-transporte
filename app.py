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
    conn.commit()
    conn.close()

# --- CONFIGURACIÓN DE LA INTERFAZ ---
st.set_page_config(page_title="Transporte Jacobo Pro", layout="wide", page_icon="🚐")

# Seguridad para acceso global
st.sidebar.title("🔐 Acceso")
password = st.sidebar.text_input("Contraseña", type="password")
if password != "Jacobo2026":
    st.title("🚐 Sistema de Gestión de Transporte")
    st.warning("Por favor, ingrese la contraseña en la barra lateral.")
    st.stop()

# Inicializar tablas al entrar
try:
    inicializar_tablas()
except:
    pass

st.title("🚐 Panel de Control - Acceso Global")
menu = st.sidebar.radio("Navegación", ["🏠 Inicio", "🚚 Gestión de Vehículos", "💸 Registro de Gastos"])

# --- 🏠 INICIO ---
if menu == "🏠 Inicio":
    conn = conectar_db()
    v = pd.read_sql("SELECT COUNT(*) FROM vehiculos", conn).iloc[0,0]
    g = pd.read_sql("SELECT SUM(monto) FROM gastos", conn).iloc[0,0] or 0
    conn.close()
    c1, c2 = st.columns(2)
    c1.metric("Vehículos en la Nube", v)
    c2.metric("Total Inversión", f"${g:,.2f}")

# --- 🚚 VEHÍCULOS ---
elif menu == "🚚 Gestión de Vehículos":
    t_reg, t_edit, t_ver = st.tabs(["➕ Registrar", "✏️ Editar", "🔍 Ver Flota"])
    
    with t_reg:
        with st.form("reg"):
            c1, c2 = st.columns(2)
            placa = c1.text_input("Placa").upper()
            marca = c1.text_input("Marca")
            modelo = c1.text_input("Modelo")
            cond = c2.text_input("Conductor")
            tipo = c2.selectbox("Tipo", ["Ambulancia", "Van", "Particular", "Microbús"])
            km = c2.number_input("KM Inicial", min_value=0)
            if st.form_submit_button("Guardar"):
                conn = conectar_db(); cur = conn.cursor()
                cur.execute("INSERT INTO vehiculos (placa, marca, modelo, tipo, conductor, km_actual) VALUES (%s,%s,%s,%s,%s,%s)", (placa, marca, modelo, tipo, cond, km))
                conn.commit(); conn.close()
                st.success("Registrado en la nube."); st.rerun()

    with t_edit:
        conn = conectar_db()
        df_v = pd.read_sql("SELECT * FROM vehiculos", conn)
        conn.close()
        if not df_v.empty:
            sel = st.selectbox("Elegir Placa", df_v['placa'])
            d = df_v[df_v['placa'] == sel].iloc[0]
            with st.form("edit"):
                n_cond = st.text_input("Conductor", value=d['conductor'])
                n_tipo = st.selectbox("Tipo", ["Ambulancia", "Van", "Particular", "Microbús"], index=["Ambulancia", "Van", "Particular", "Microbús"].index(d['tipo']))
                n_km = st.number_input("KM Actual", value=int(d['km_actual']))
                if st.form_submit_button("Actualizar"):
                    conn = conectar_db(); cur = conn.cursor()
                    cur.execute("UPDATE vehiculos SET conductor=%s, tipo=%s, km_actual=%s WHERE placa=%s", (n_cond, n_tipo, n_km, sel))
                    conn.commit(); conn.close()
                    st.success("Actualizado"); st.rerun()

    with t_ver:
        conn = conectar_db()
        st.dataframe(pd.read_sql("SELECT placa, marca, modelo, tipo, conductor, km_actual FROM vehiculos", conn), use_container_width=True)
        conn.close()

# --- 💸 GASTOS ---
elif menu == "💸 Registro de Gastos":
    conn = conectar_db()
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    if not v_data.empty:
        with st.form("gasto"):
            v_sel = st.selectbox("Vehículo", v_data['placa'])
            v_id = int(v_data[v_data['placa'] == v_sel]['id'].values[0])
            monto = st.number_input("Monto", min_value=0.0)
            inst = st.text_input("Institución")
            fecha = st.date_input("Fecha")
            if st.form_submit_button("Guardar"):
                cur = conn.cursor()
                cur.execute("INSERT INTO gastos (vehiculo_id, monto, institucion_destino, fecha) VALUES (%s,%s,%s,%s)", (v_id, monto, inst, fecha))
                conn.commit(); st.success("Gasto guardado"); st.rerun()
        
        df_g = pd.read_sql("SELECT g.*, v.placa FROM gastos g JOIN vehiculos v ON g.vehiculo_id = v.id", conn)
        conn.close()
        if not df_g.empty:
            df_g['mes'] = pd.to_datetime(df_g['fecha']).dt.strftime('%Y-%m')
            mes_sel = st.selectbox("Ver Mes", sorted(df_g['mes'].unique(), reverse=True))

            st.dataframe(df_g[df_g['mes'] == mes_sel][['fecha', 'placa', 'monto', 'institucion_destino']], use_container_width=True)
