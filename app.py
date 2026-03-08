import streamlit as st
import psycopg2
import pandas as pd
from datetime import datetime, timedelta
import io
import plotly.express as px

# --- 1. CONEXIÓN DINÁMICA (Caja Fuerte) ---
def conectar_db(url_db):
    return psycopg2.connect(url_db)

def inicializar_db(url_db):
    conn = conectar_db(url_db); cur = conn.cursor()
    # Tablas Base
    cur.execute('CREATE TABLE IF NOT EXISTS vehiculos (id SERIAL PRIMARY KEY, placa TEXT UNIQUE NOT NULL, marca TEXT, modelo TEXT, conductor TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS gastos (id SERIAL PRIMARY KEY, vehiculo_id INTEGER REFERENCES vehiculos(id), tipo_gasto TEXT, monto NUMERIC, fecha DATE, detalle TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS ventas (id SERIAL PRIMARY KEY, vehiculo_id INTEGER REFERENCES vehiculos(id), cliente TEXT, valor_viaje NUMERIC, fecha DATE, descripcion TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS hoja_vida (id SERIAL PRIMARY KEY, vehiculo_id INTEGER UNIQUE REFERENCES vehiculos(id), soat_vence DATE, tecno_vence DATE, prev_vence DATE, p_contractual DATE, p_extracontractual DATE, p_todoriesgo DATE, t_operaciones DATE)')
    cur.execute('CREATE TABLE IF NOT EXISTS usuarios (id SERIAL PRIMARY KEY, nombre TEXT, usuario TEXT UNIQUE NOT NULL, clave TEXT NOT NULL, rol TEXT DEFAULT "vendedor")')
    # Tabla especial para clientes de Confección/Textil
    cur.execute('CREATE TABLE IF NOT EXISTS tarifario_textil (id SERIAL PRIMARY KEY, servicio TEXT UNIQUE, precio_unidad NUMERIC)')
    conn.commit(); conn.close()

# --- 2. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Gestor Operativo C&E", layout="wide", page_icon="🚐")

# --- 3. LOGIN MULTI-CLIENTE ---
if 'auth' not in st.session_state: st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 Portal de Gestión C&E")
    # Leer clientes configurados en los Secrets
    clientes = list(st.secrets["connections"].keys())
    
    col_log, _ = st.columns([1, 2])
    with col_log:
        c_sel = st.selectbox("Seleccione su Empresa:", clientes, format_func=lambda x: st.secrets["connections"][x]["nombre"])
        u_input = st.text_input("Usuario")
        p_input = st.text_input("Contraseña", type="password")
        
        if st.button("Ingresar"):
            conf = st.secrets["connections"][c_sel]
            # Conectar a la DB de ese cliente específico para validar usuario
            try:
                conn = conectar_db(conf["url"])
                cur = conn.cursor()
                cur.execute("SELECT nombre, rol FROM usuarios WHERE usuario = %s AND clave = %s", (u_input, p_input))
                res = cur.fetchone(); conn.close()
                
                if res:
                    st.session_state.auth = True
                    st.session_state.db_url = conf["url"]
                    st.session_state.u_name, st.session_state.u_rol = res[0], res[1]
                    st.session_state.es_textil = conf.get("modulo_textil", False)
                    st.session_state.empresa_nom = conf["nombre"]
                    inicializar_db(st.session_state.db_url)
                    st.rerun()
                else: st.error("Usuario o clave incorrectos en esta base de datos.")
            except: st.error("Error al conectar con la base de datos de este cliente.")
    st.stop()

# --- 4. MENÚ LATERAL ---
st.sidebar.write(f"🏢 **{st.session_state.empresa_nom}**")
st.sidebar.write(f"👤 {st.session_state.u_name}")
st.sidebar.divider()

opciones = ["📊 Dashboard", "🚐 Flota", "💸 Gastos", "💰 Ventas", "📑 Hoja de Vida"]
if st.session_state.es_textil: opciones.append("⚙️ Config. Precios")
if st.session_state.u_rol == "admin": opciones.append("⚙️ Usuarios")

menu = st.sidebar.selectbox("📂 MÓDULOS", opciones)
if st.sidebar.button("🚪 CERRAR SESIÓN"): st.session_state.auth = False; st.rerun()

# --- 5. LÓGICA DE MÓDULOS (VERSION ACTUALIZADA) ---

conn = conectar_db(st.session_state.db_url)

if menu == "📊 Dashboard":
    st.title(f"📊 Análisis - {st.session_state.empresa_nom}")
    # (Aquí va la lógica de gráficos y balance que ya tenías, pero usando 'conn')
    st.info("Visualización de utilidades y metas operativas.")

elif menu == "⚙️ Config. Precios":
    st.title("⚙️ Tarifario de Confección")
    with st.form("f_precios"):
        serv = st.text_input("Nombre del Servicio (Ej: Maquila Jeans)")
        prec = st.number_input("Precio por Unidad", min_value=0.0)
        if st.form_submit_button("Guardar Precio"):
            cur = conn.cursor()
            cur.execute("INSERT INTO tarifario_textil (servicio, precio_unidad) VALUES (%s, %s) ON CONFLICT (servicio) DO UPDATE SET precio_unidad = EXCLUDED.precio_unidad", (serv, prec))
            conn.commit(); st.success("Precio actualizado")
    
    df_p = pd.read_sql("SELECT servicio, precio_unidad FROM tarifario_textil", conn)
    st.table(df_p)

elif menu == "💰 Ventas":
    st.title("💰 Registro de Ventas")
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    
    if st.session_state.es_textil:
        tarifas = pd.read_sql("SELECT * FROM tarifario_textil", conn)
        with st.form("v_textil"):
            v_sel = st.selectbox("Vehículo", v_data['placa'])
            v_id = v_data[v_data['placa'] == v_sel]['id'].values[0]
            s_sel = st.selectbox("Servicio", tarifas['servicio'].tolist())
            p_unit = tarifas[tarifas['servicio'] == s_sel]['precio_unitario'].values[0]
            cant = st.number_input(f"Cantidad (Precio unitario: ${p_unit:,.0f})", min_value=1)
            total = cant * p_unit
            st.write(f"### Total: ${total:,.0f}")
            if st.form_submit_button("💰 Registrar Producción"):
                cur = conn.cursor()
                cur.execute("INSERT INTO ventas (vehiculo_id, cliente, valor_viaje, fecha, descripcion) VALUES (%s,%s,%s,%s,%s)", (int(v_id), s_sel, total, datetime.now().date(), f"Cant: {cant}"))
                conn.commit(); st.success("Registrado")
    else:
        # Registro normal de transporte que ya tenías
        with st.form("v_normal"):
            # ... (tu código de ventas anterior)
            st.write("Registro de viaje estándar.")
            st.form_submit_button("Guardar")

# (Se repiten los demás módulos: Flota, Gastos, Hoja de Vida usando la conexión 'conn')
conn.close()
