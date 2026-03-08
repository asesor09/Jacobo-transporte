import streamlit as st
import psycopg2
import pandas as pd
from datetime import datetime, timedelta
import io
import plotly.express as px

# --- 1. CONEXIÓN ---
def conectar_db():
    try: return psycopg2.connect(st.session_state.db_url)
    except: return None

def inicializar_db():
    conn = conectar_db()
    if conn:
        cur = conn.cursor()
        cur.execute('CREATE TABLE IF NOT EXISTS vehiculos (id SERIAL PRIMARY KEY, placa TEXT UNIQUE NOT NULL, marca TEXT, modelo TEXT, conductor TEXT)')
        cur.execute('CREATE TABLE IF NOT EXISTS gastos (id SERIAL PRIMARY KEY, vehiculo_id INTEGER REFERENCES vehiculos(id), tipo_gasto TEXT, monto NUMERIC, fecha DATE, detalle TEXT)')
        cur.execute('CREATE TABLE IF NOT EXISTS ventas (id SERIAL PRIMARY KEY, vehiculo_id INTEGER REFERENCES vehiculos(id), cliente TEXT, valor_viaje NUMERIC, fecha DATE, descripcion TEXT)')
        cur.execute('CREATE TABLE IF NOT EXISTS hoja_vida (id SERIAL PRIMARY KEY, vehiculo_id INTEGER UNIQUE REFERENCES vehiculos(id), soat_vence DATE, tecno_vence DATE, prev_vence DATE, p_contractual DATE, p_extracontractual DATE, p_todoriesgo DATE, t_operaciones DATE)')
        cur.execute('CREATE TABLE IF NOT EXISTS usuarios (id SERIAL PRIMARY KEY, nombre TEXT, usuario TEXT UNIQUE NOT NULL, clave TEXT NOT NULL, rol TEXT DEFAULT "admin")')
        cur.execute('CREATE TABLE IF NOT EXISTS tarifario_textil (id SERIAL PRIMARY KEY, servicio TEXT UNIQUE, precio_unitario NUMERIC)')
        cur.execute("INSERT INTO usuarios (nombre, usuario, clave, rol) VALUES ('Admin', 'admin', '1234', 'admin') ON CONFLICT DO NOTHING")
        conn.commit(); conn.close()

# --- 2. EXCEL ---
def to_excel(df_balance, df_g, df_v):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_balance.to_excel(writer, index=False, sheet_name='Balance')
        df_g.to_excel(writer, index=False, sheet_name='Gastos')
        df_v.to_excel(writer, index=False, sheet_name='Ventas')
    return output.getvalue()

# --- 3. CONFIGURACIÓN ---
st.set_page_config(page_title="C&E Eficiencias Pro", layout="wide", page_icon="🚐")

if 'logged_in' not in st.session_state: st.session_state.logged_in = False

# --- 4. LOGIN ---
if not st.session_state.logged_in:
    st.title("🔐 Acceso C&E Eficiencias")
    if "connections" in st.secrets:
        emp_sel = st.selectbox("Seleccione Empresa:", list(st.secrets["connections"].keys()), format_func=lambda x: st.secrets["connections"][x]["nombre"])
        u, p = st.text_input("Usuario"), st.text_input("Contraseña", type="password")
        if st.button("🚀 Ingresar"):
            conf = st.secrets["connections"][emp_sel]
            st.session_state.db_url, st.session_state.es_textil, st.session_state.nom_emp = conf["url"], conf.get("modulo_textil", False), conf["nombre"]
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

# --- MÓDULO: VENTAS (CON CAJA DE FECHA DEVUELTA) ---
if menu == "💰 Ventas":
    st.title("💰 Registro de Ingresos (Ventas)")
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    if v_data.empty: st.warning("⚠️ No hay vehículos. Registre uno en 'Flota'.")
    else:
        with st.form("form_ventas_completo"):
            v_sel = st.selectbox("Seleccione Vehículo", v_data['placa'].tolist())
            v_id = v_data[v_data['placa'] == v_sel]['id'].values[0]
            
            fec_v = st.date_input("Fecha del servicio/viaje", datetime.now().date()) # <--- AQUÍ VOLVIÓ LA FECHA
            
            if st.session_state.es_textil:
                tarifas = pd.read_sql("SELECT * FROM tarifario_textil", conn)
                if tarifas.empty: st.error("⚠️ No hay precios configurados.")
                else:
                    serv = st.selectbox("Tipo de Confección", tarifas['servicio'].tolist())
                    p_u = tarifas[tarifas['servicio'] == serv]['precio_unitario'].values[0]
                    cant = st.number_input(f"Cantidad (Precio/U: ${p_u:,.0f})", min_value=1)
                    monto = cant * p_u
                    det = f"{serv} - {cant} unidades"
            else:
                det = st.text_input("Cliente / Empresa / Detalle")
                monto = st.number_input("Valor del Viaje", min_value=0)
            
            if st.form_submit_button("✅ Guardar Venta"):
                cur = conn.cursor()
                cur.execute("INSERT INTO ventas (vehiculo_id, cliente, valor_viaje, fecha, descripcion) VALUES (%s,%s,%s,%s,%s)", 
                           (int(v_id), det, monto, fec_v, det))
                conn.commit(); st.success("¡Venta guardada!"); st.rerun()

# --- MÓDULO: GASTOS (CON CAJA DE FECHA) ---
elif menu == "💸 Gastos":
    st.title("💸 Registro de Gastos")
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    if v_data.empty: st.warning("Registre vehículos primero.")
    else:
        with st.form("form_gastos"):
            v_sel = st.selectbox("Vehículo", v_data['placa'].tolist())
            v_id = v_data[v_data['placa'] == v_sel]['id'].values[0]
            fec_g = st.date_input("Fecha del Gasto", datetime.now().date()) # <--- AQUÍ VOLVIÓ LA FECHA
            tipo = st.selectbox("Concepto", ["Combustible", "Peaje", "Mantenimiento", "Lavada", "Otros"])
            val = st.number_input("Monto ($)", min_value=0)
            det = st.text_input("Detalle adicional")
            if st.form_submit_button("💾 Guardar Gasto"):
                cur = conn.cursor()
                cur.execute("INSERT INTO gastos (vehiculo_id, tipo_gasto, monto, fecha, detalle) VALUES (%s,%s,%s,%s,%s)", (int(v_id), tipo, val, fec_g, det))
                conn.commit(); st.success("Gasto registrado"); st.rerun()

# --- MÓDULO: DASHBOARD (CON EXCEL Y DETALLE POR DÍA) ---
elif menu == "📊 Dashboard":
    st.title("📊 Análisis Operativo")
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    if v_data.empty: st.warning("Sin datos.")
    else:
        r = st.date_input("Rango:", [datetime.now().date()-timedelta(30), datetime.now().date()])
        if len(r)==2:
            df_g = pd.read_sql("SELECT g.fecha, v.placa, g.tipo_gasto as concepto, g.monto, g.detalle FROM gastos g JOIN vehiculos v ON g.vehiculo_id=v.id WHERE g.fecha BETWEEN %s AND %s", conn, params=[r[0], r[1]])
            df_v = pd.read_sql("SELECT s.fecha, v.placa, s.cliente, s.valor_viaje as monto, s.descripcion FROM ventas s JOIN vehiculos v ON s.vehiculo_id=v.id WHERE s.fecha BETWEEN %s AND %s", conn, params=[r[0], r[1]])
            
            st.metric("Utilidad", f"${df_v['monto'].sum() - df_g['monto'].sum():,.0f}")
            st.download_button("📥 Descargar Excel", data=to_excel(df_v, df_g, df_v), file_name="Reporte_Final.xlsx")
            
            with st.expander("🔍 Detalle día por día"):
                st.write("Ventas:"); st.dataframe(df_v, use_container_width=True)
                st.write("Gastos:"); st.dataframe(df_g, use_container_width=True)

# --- MÓDULO: FLOTA (PLACA, MARCA, MODELO, CONDUCTOR) ---
elif menu == "🚐 Flota":
    st.title("🚐 Gestión de Flota")
    with st.form("form_flota"):
        p = st.text_input("Placa (XYZ123)").upper()
        m = st.text_input("Marca")
        mod = st.text_input("Modelo")
        cond = st.text_input("Conductor")
        if st.form_submit_button("➕ Registrar Carro"):
            cur=conn.cursor(); cur.execute("INSERT INTO vehiculos (placa, marca, modelo, conductor) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING", (p,m,mod,cond))
            conn.commit(); st.success("Registrado"); st.rerun()
    st.dataframe(pd.read_sql("SELECT * FROM vehiculos", conn), use_container_width=True)

conn.close()
