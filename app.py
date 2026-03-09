import streamlit as st
import psycopg2
import pandas as pd
from datetime import datetime, timedelta
import io
import plotly.express as px

# --- 1. CONEXIÓN BLINDADA (SOLUCIÓN AL ERROR DE ESQUEMA) ---
def conectar_db():
    try:
        conn = psycopg2.connect(st.session_state.db_url)
        cur = conn.cursor()
        # Esta línea obliga a la base de datos a encontrar tus tablas siempre
        cur.execute("SET search_path TO public")
        return conn
    except Exception as e:
        st.error(f"Error de conexión: {e}")
        return None

def inicializar_db():
    conn = conectar_db()
    if conn:
        cur = conn.cursor()
        # Tablas para la gestión de la flota de 25 vehículos y conductores
        cur.execute('CREATE TABLE IF NOT EXISTS vehiculos (id SERIAL PRIMARY KEY, placa TEXT UNIQUE NOT NULL, marca TEXT, modelo TEXT, conductor TEXT)')
        cur.execute('CREATE TABLE IF NOT EXISTS gastos (id SERIAL PRIMARY KEY, vehiculo_id INTEGER REFERENCES vehiculos(id), tipo_gasto TEXT, monto NUMERIC, fecha DATE, detalle TEXT)')
        cur.execute('CREATE TABLE IF NOT EXISTS ventas (id SERIAL PRIMARY KEY, vehiculo_id INTEGER REFERENCES vehiculos(id), cliente TEXT, valor_viaje NUMERIC, fecha DATE, descripcion TEXT)')
        cur.execute('''CREATE TABLE IF NOT EXISTS hoja_vida (
                        id SERIAL PRIMARY KEY, vehiculo_id INTEGER UNIQUE REFERENCES vehiculos(id), 
                        soat_vence DATE, tecno_vence DATE, prev_vence DATE,
                        p_contractual DATE, p_extracontractual DATE, p_todoriesgo DATE, t_operaciones DATE)''')
        cur.execute('CREATE TABLE IF NOT EXISTS usuarios (id SERIAL PRIMARY KEY, nombre TEXT, usuario TEXT UNIQUE NOT NULL, clave TEXT NOT NULL, rol TEXT DEFAULT "admin")')
        cur.execute('CREATE TABLE IF NOT EXISTS tarifario_textil (id SERIAL PRIMARY KEY, servicio TEXT UNIQUE, precio_unitario NUMERIC)')
        cur.execute("INSERT INTO usuarios (nombre, usuario, clave, rol) VALUES ('Admin', 'admin', '1234', 'admin') ON CONFLICT DO NOTHING")
        conn.commit(); conn.close()

# --- 2. EXCEL Y REPORTES ---
def to_excel(df_balance, df_g, df_v):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_balance.to_excel(writer, index=False, sheet_name='Balance General')
        df_g.to_excel(writer, index=False, sheet_name='Detalle Gastos')
        df_v.to_excel(writer, index=False, sheet_name='Detalle Ventas')
    return output.getvalue()

# --- 3. CONFIGURACIÓN ---
st.set_page_config(page_title="C&E Eficiencias", layout="wide", page_icon="🚐")
if 'logged_in' not in st.session_state: st.session_state.logged_in = False

# --- 4. LOGIN MULTI-CLIENTE ---
if not st.session_state.logged_in:
    st.title("🔐 Acceso al Sistema")
    if "connections" in st.secrets:
        emp_sel = st.selectbox("Empresa:", list(st.secrets["connections"].keys()), format_func=lambda x: st.secrets["connections"][x]["nombre"])
        u, p = st.text_input("Usuario"), st.text_input("Contraseña", type="password")
        if st.button("Ingresar"):
            conf = st.secrets["connections"][emp_sel]
            st.session_state.db_url = conf["url"]
            st.session_state.es_textil = conf.get("modulo_textil", False)
            st.session_state.nom_emp = conf["nombre"]
            inicializar_db()
            conn = conectar_db()
            if conn:
                cur = conn.cursor(); cur.execute("SELECT nombre, rol FROM usuarios WHERE usuario=%s AND clave=%s", (u, p))
                res = cur.fetchone(); conn.close()
                if res:
                    st.session_state.logged_in, st.session_state.u_name, st.session_state.u_rol = True, res[0], res[1]
                    st.rerun()
                else: st.error("❌ Credenciales incorrectas.")
    st.stop()

# --- 5. INTERFAZ ---
st.sidebar.write(f"🏢 **{st.session_state.nom_emp}**")
menu = st.sidebar.selectbox("Módulos:", ["📊 Dashboard", "🚐 Flota", "💸 Gastos", "💰 Ventas", "📑 Hoja de Vida", "⚙️ Configuración"])
if st.sidebar.button("🚪 Cerrar Sesión"): st.session_state.logged_in = False; st.rerun()

conn = conectar_db()

# --- MÓDULO: GASTOS (RECUPERADO) ---
if menu == "💸 Gastos":
    st.title("💸 Registro de Gastos Operativos")
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    if v_data.empty: st.warning("⚠️ Primero cree un vehículo en el módulo 'Flota'.")
    else:
        with st.form("form_gastos"):
            v_sel = st.selectbox("Vehículo", v_data['placa'])
            v_id = v_data[v_data['placa']==v_sel]['id'].values[0]
            fec = st.date_input("Fecha del Gasto", datetime.now().date())
            tipo = st.selectbox("Concepto", ["Combustible", "Peaje", "Mantenimiento", "Lavada", "Viáticos", "Otros"])
            val = st.number_input("Monto ($)", min_value=0)
            det = st.text_input("Nota/Detalle")
            if st.form_submit_button("💾 Guardar Gasto"):
                cur = conn.cursor()
                cur.execute("INSERT INTO gastos (vehiculo_id, tipo_gasto, monto, fecha, detalle) VALUES (%s,%s,%s,%s,%s)", (int(v_id), tipo, val, fec, det))
                conn.commit(); st.success("Gasto registrado"); st.rerun()
        st.dataframe(pd.read_sql("SELECT * FROM gastos ORDER BY fecha DESC", conn), use_container_width=True)

# --- MÓDULO: VENTAS (CON TOTAL CALCULADO) ---
elif menu == "💰 Ventas":
    st.title("💰 Registro de Ventas")
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    if v_data.empty: st.warning("⚠️ Cree un vehículo primero.")
    else:
        with st.form("f_v"):
            v_sel = st.selectbox("Vehículo", v_data['placa'])
            v_id = v_data[v_data['placa']==v_sel]['id'].values[0]
            fec = st.date_input("Fecha", datetime.now().date())
            if st.session_state.es_textil:
                tarifas = pd.read_sql("SELECT * FROM tarifario_textil", conn)
                if tarifas.empty: st.error("⚠️ Configure tarifas en 'Configuración'.")
                else:
                    serv = st.selectbox("Servicio", tarifas['servicio'].tolist())
                    p_u = tarifas[tarifas['servicio']==serv]['precio_unitario'].values[0]
                    cant = st.number_input(f"Cantidad (Precio/U: ${p_u:,.0f})", min_value=1)
                    # MOSTRAR EL TOTAL
                    total_v = cant * p_u
                    st.info(f"💰 **TOTAL A REGISTRAR: ${total_v:,.0f}**")
                    if st.form_submit_button("💾 Guardar Producción"):
                        cur=conn.cursor(); cur.execute("INSERT INTO ventas (vehiculo_id, cliente, valor_viaje, fecha, descripcion) VALUES (%s,%s,%s,%s,%s)", (int(v_id), serv, total_v, fec, f"Cant: {cant}"))
                        conn.commit(); st.success("Venta guardada"); st.rerun()
            else:
                cli = st.text_input("Cliente/Empresa")
                val = st.number_input("Valor", min_value=0)
                if st.form_submit_button("💾 Guardar Viaje"):
                    cur=conn.cursor(); cur.execute("INSERT INTO ventas (vehiculo_id, cliente, valor_viaje, fecha) VALUES (%s,%s,%s,%s)", (int(v_id), cli, val, fec))
                    conn.commit(); st.success("Viaje guardado"); st.rerun()

# --- MÓDULO: DASHBOARD ---
elif menu == "📊 Dashboard":
    st.title("📊 Dashboard Operativo")
    # ... (Lógica de métricas y Excel que ya conoces, usando 'conn')
    st.write("Análisis de ingresos y egresos por vehículo.")

# --- OTROS MÓDULOS (FLOTA, HOJA VIDA, CONFIG) ---
# ... (Se mantienen igual que en las versiones previas respetando tu estructura)

conn.close()
