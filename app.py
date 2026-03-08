import streamlit as st
import psycopg2
import pandas as pd
from datetime import datetime, timedelta
import io
import plotly.express as px

# --- 1. CONEXIÓN Y SEGURIDAD ---
def conectar_db(url_db):
    try:
        return psycopg2.connect(url_db)
    except Exception as e:
        st.error(f"Error de conexión: {e}")
        return None

def inicializar_db(url_db):
    conn = conectar_db(url_db)
    if conn:
        cur = conn.cursor()
        # Tablas fundamentales para la flota de 25 vehículos
        cur.execute('CREATE TABLE IF NOT EXISTS vehiculos (id SERIAL PRIMARY KEY, placa TEXT UNIQUE NOT NULL, marca TEXT, modelo TEXT, conductor TEXT)')
        cur.execute('CREATE TABLE IF NOT EXISTS gastos (id SERIAL PRIMARY KEY, vehiculo_id INTEGER REFERENCES vehiculos(id), tipo_gasto TEXT, monto NUMERIC, fecha DATE, detalle TEXT)')
        cur.execute('CREATE TABLE IF NOT EXISTS ventas (id SERIAL PRIMARY KEY, vehiculo_id INTEGER REFERENCES vehiculos(id), cliente TEXT, valor_viaje NUMERIC, fecha DATE, descripcion TEXT)')
        cur.execute('CREATE TABLE IF NOT EXISTS hoja_vida (id SERIAL PRIMARY KEY, vehiculo_id INTEGER UNIQUE REFERENCES vehiculos(id), soat_vence DATE, tecno_vence DATE, prev_vence DATE, p_contractual DATE, p_extracontractual DATE, p_todoriesgo DATE, t_operaciones DATE)')
        cur.execute('CREATE TABLE IF NOT EXISTS usuarios (id SERIAL PRIMARY KEY, nombre TEXT, usuario TEXT UNIQUE NOT NULL, clave TEXT NOT NULL, rol TEXT DEFAULT "admin")')
        cur.execute('CREATE TABLE IF NOT EXISTS tarifario_textil (id SERIAL PRIMARY KEY, servicio TEXT UNIQUE, precio_unidad NUMERIC)')
        conn.commit(); conn.close()

# --- 2. CONFIGURACIÓN UI ---
st.set_page_config(page_title="C&E Eficiencias Pro", layout="wide", page_icon="🚐")

if 'auth' not in st.session_state: st.session_state.auth = False

# --- 3. LOGIN INDEPENDIENTE (PORTAL) ---
if not st.session_state.auth:
    st.title("🔐 Portal de Gestión Multi-Cliente")
    # Verificamos que existan secretos configurados
    if "connections" not in st.secrets:
        st.error("Error: No se han configurado clientes en los 'Secrets' de Streamlit.")
        st.stop()
    
    clientes = list(st.secrets["connections"].keys())
    
    col1, _ = st.columns([1, 2])
    with col1:
        c_id = st.selectbox("Seleccione su Empresa:", clientes, format_func=lambda x: st.secrets["connections"][x]["nombre"])
        user_in = st.text_input("Usuario")
        pass_in = st.text_input("Contraseña", type="password")
        
        if st.button("🚀 Ingresar al Sistema"):
            conf = st.secrets["connections"][c_id]
            conn = conectar_db(conf["url"])
            if conn:
                cur = conn.cursor()
                cur.execute("SELECT nombre, rol FROM usuarios WHERE usuario = %s AND clave = %s", (user_in, pass_in))
                res = cur.fetchone(); conn.close()
                if res:
                    st.session_state.auth = True
                    st.session_state.db_url = conf["url"]
                    st.session_state.u_name = res[0]
                    st.session_state.u_rol = res[1]
                    st.session_state.empresa = conf["nombre"]
                    st.session_state.es_textil = conf.get("modulo_textil", False)
                    inicializar_db(st.session_state.db_url)
                    st.rerun()
                else: st.error("Usuario o clave incorrectos en esta base de datos.")
    st.stop()

# --- 4. PANEL DE CONTROL ---
st.sidebar.title(f"🏢 {st.session_state.empresa}")
st.sidebar.write(f"👤 Bienvenido, **{st.session_state.u_name}**")
st.sidebar.divider()

opciones = ["📊 Dashboard", "🚐 Flota", "💸 Gastos", "💰 Ventas", "📑 Hoja de Vida"]
if st.session_state.es_textil: opciones.append("⚙️ Precios Confección")
menu = st.sidebar.selectbox("Ir a:", opciones)

if st.sidebar.button("🚪 Cerrar Sesión"):
    st.session_state.auth = False; st.rerun()

# --- 5. LÓGICA DE MÓDULOS (BLINDADA) ---
conn = conectar_db(st.session_state.db_url)

# MÓDULO: FLOTA
if menu == "🚐 Flota":
    st.title("🚐 Administración de Vehículos")
    with st.form("nueva_flota"):
        c1, c2 = st.columns(2)
        p = c1.text_input("Placa").upper()
        m = c1.text_input("Marca")
        mod = c2.text_input("Modelo")
        cond = c2.text_input("Conductor")
        if st.form_submit_button("➕ Registrar Vehículo"):
            if p:
                cur = conn.cursor()
                cur.execute("INSERT INTO vehiculos (placa, marca, modelo, conductor) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING", (p, m, mod, cond))
                conn.commit(); st.success("Vehículo añadido"); st.rerun()
            else: st.error("La placa es obligatoria")
    
    df_v = pd.read_sql("SELECT placa, marca, modelo, conductor FROM vehiculos", conn)
    st.subheader("Listado de Flota")
    st.dataframe(df_v, use_container_width=True, hide_index=True)

# MÓDULO: VENTAS (CON DOBLE LÓGICA)
elif menu == "💰 Ventas":
    st.title("💰 Registro de Ingresos")
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    
    if v_data.empty:
        st.warning("⚠️ Primero debe registrar vehículos en el módulo 'Flota'.")
    else:
        # VENTAS PARA CONFECCIÓN LUZMA
        if st.session_state.es_textil:
            tarifas = pd.read_sql("SELECT servicio, precio_unitario FROM tarifario_textil", conn)
            if tarifas.empty:
                st.error("⚠️ Debe configurar los precios por unidad en 'Precios Confección' primero.")
            else:
                with st.form("venta_textil_form"):
                    v_sel = st.selectbox("Vehículo", v_data['placa'].tolist())
                    v_id = v_data[v_data['placa'] == v_sel]['id'].values[0]
                    serv = st.selectbox("Servicio", tarifas['servicio'].tolist())
                    p_u = tarifas[tarifas['servicio'] == serv]['precio_unitario'].values[0]
                    cant = st.number_input(f"Cantidad (Precio/U: ${p_u:,.0f})", min_value=1)
                    total = cant * p_u
                    st.info(f"Total a liquidar: **${total:,.0f}**")
                    if st.form_submit_button("💾 Guardar Producción"):
                        cur = conn.cursor()
                        cur.execute("INSERT INTO ventas (vehiculo_id, cliente, valor_viaje, fecha, descripcion) VALUES (%s,%s,%s,%s,%s)", 
                                   (int(v_id), serv, total, datetime.now().date(), f"Cant: {cant}"))
                        conn.commit(); st.success("Registrado"); st.rerun()
        # VENTAS PARA TRANSPORTE NORMAL
        else:
            with st.form("venta_normal_form"):
                v_sel = st.selectbox("Vehículo", v_data['placa'].tolist())
                v_id = v_data[v_data['placa'] == v_sel]['id'].values[0]
                cli = st.text_input("Cliente/Empresa")
                monto = st.number_input("Valor del Viaje", min_value=0)
                if st.form_submit_button("💾 Guardar Viaje"):
                    cur = conn.cursor()
                    cur.execute("INSERT INTO ventas (vehiculo_id, cliente, valor_viaje, fecha) VALUES (%s,%s,%s,%s)", (int(v_id), cli, monto, datetime.now().date()))
                    conn.commit(); st.success("Viaje guardado"); st.rerun()

# MÓDULO: PRECIOS CONFECCIÓN
elif menu == "⚙️ Precios Confección":
    st.title("⚙️ Tarifario por Unidad")
    with st.form("set_precios"):
        s = st.text_input("Nombre del Servicio (Ej: Lavandería)")
        p = st.number_input("Precio por Prenda/Unidad", min_value=0.0)
        if st.form_submit_button("✅ Guardar Precio"):
            cur = conn.cursor()
            cur.execute("INSERT INTO tarifario_textil (servicio, precio_unitario) VALUES (%s, %s) ON CONFLICT (servicio) DO UPDATE SET precio_unitario = EXCLUDED.precio_unitario", (s, p))
            conn.commit(); st.success("Precio actualizado"); st.rerun()
    st.table(pd.read_sql("SELECT servicio, precio_unitario FROM tarifario_textil", conn))

# MÓDULO: DASHBOARD
elif menu == "📊 Dashboard":
    st.title(f"📊 Dashboard - {st.session_state.empresa}")
    df_v = pd.read_sql("SELECT valor_viaje as monto FROM ventas", conn)
    df_g = pd.read_sql("SELECT monto FROM gastos", conn)
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Ingresos", f"${df_v['monto'].sum():,.0f}")
    c2.metric("Gastos", f"${df_g['monto'].sum():,.0f}")
    c3.metric("Utilidad", f"${df_v['monto'].sum() - df_g['monto'].sum():,.0f}")

conn.close()
