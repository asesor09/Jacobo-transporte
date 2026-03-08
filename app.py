import streamlit as st
import psycopg2
import pandas as pd
from datetime import datetime, timedelta
import io
import plotly.express as px

# --- 1. CONEXIÓN SEGURA ---
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
    st.title("🔐 Acceso Multi-Cliente C&E")
    if "connections" in st.secrets:
        emp_sel = st.selectbox("Empresa:", list(st.secrets["connections"].keys()), format_func=lambda x: st.secrets["connections"][x]["nombre"])
        u, p = st.text_input("Usuario"), st.text_input("Contraseña", type="password")
        if st.button("Ingresar"):
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
                else: st.error("Clave incorrecta")
    st.stop()

# --- 5. INTERFAZ ---
st.sidebar.write(f"🏢 **{st.session_state.nom_emp}**")
menu = st.sidebar.selectbox("Módulos:", ["📊 Dashboard", "🚐 Flota", "💸 Gastos", "💰 Ventas", "📑 Hoja de Vida", "⚙️ Usuarios"])
if st.session_state.es_textil: st.sidebar.info("🧵 Modo Textil Activo")
if st.sidebar.button("🚪 Salir"): st.session_state.logged_in = False; st.rerun()

conn = conectar_db()

# --- MÓDULO: DASHBOARD ---
if menu == "📊 Dashboard":
    st.title("📊 Análisis de Operación")
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    if v_data.empty: st.warning("No hay datos. Registre vehículos primero.")
    else:
        r = st.date_input("Rango:", [datetime.now().date()-timedelta(30), datetime.now().date()])
        if len(r)==2:
            df_g = pd.read_sql("SELECT g.fecha, v.placa, g.tipo_gasto as concepto, g.monto, g.detalle FROM gastos g JOIN vehiculos v ON g.vehiculo_id=v.id WHERE g.fecha BETWEEN %s AND %s", conn, params=[r[0], r[1]])
            df_v = pd.read_sql("SELECT s.fecha, v.placa, s.cliente, s.valor_viaje as monto, s.descripcion FROM ventas s JOIN vehiculos v ON s.vehiculo_id=v.id WHERE s.fecha BETWEEN %s AND %s", conn, params=[r[0], r[1]])
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Ingresos", f"${df_v['monto'].sum():,.0f}")
            c2.metric("Egresos", f"${df_g['monto'].sum():,.0f}")
            c3.metric("Utilidad", f"${df_v['monto'].sum()-df_g['monto'].sum():,.0f}")
            
            st.download_button("📥 Excel Completo", data=to_excel(df_v, df_g, df_v), file_name="Reporte.xlsx")
            with st.expander("🔍 Detalle por día"):
                st.write("Ventas:"); st.dataframe(df_v, use_container_width=True)
                st.write("Gastos:"); st.dataframe(df_g, use_container_width=True)

# --- MÓDULO: VENTAS (CORREGIDO) ---
elif menu == "💰 Ventas":
    st.title("💰 Control de Ventas")
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    if v_data.empty: st.warning("Registre un vehículo en 'Flota' antes de continuar.")
    else:
        with st.form("f_v"):
            v_sel = st.selectbox("Vehículo", v_data['placa'])
            v_id = v_data[v_data['placa']==v_sel]['id'].values[0]
            if st.session_state.es_textil:
                tarifas = pd.read_sql("SELECT * FROM tarifario_textil", conn)
                serv = st.selectbox("Servicio", tarifas['servicio'].tolist()) if not tarifas.empty else "Sin tarifas"
                p_u = tarifas[tarifas['servicio']==serv]['precio_unitario'].values[0] if not tarifas.empty else 0
                cant = st.number_input("Cantidad", min_value=1)
                monto, desc = cant * p_u, f"Servicio: {serv} Cant: {cant}"
            else:
                desc = st.text_input("Cliente/Detalle")
                monto = st.number_input("Valor", min_value=0)
            
            if st.form_submit_button("💾 Guardar"):
                cur=conn.cursor(); cur.execute("INSERT INTO ventas (vehiculo_id, cliente, valor_viaje, fecha, descripcion) VALUES (%s,%s,%s,%s,%s)", (int(v_id), desc, monto, datetime.now().date(), desc))
                conn.commit(); st.success("Guardado"); st.rerun()

# --- MÓDULO: HOJA DE VIDA ---
elif menu == "📑 Hoja de Vida":
    st.title("📑 Vencimientos y Documentos")
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    if not v_data.empty:
        with st.form("f_hv"):
            v_sel = st.selectbox("Vehículo", v_data['placa'])
            v_id = v_data[v_data['placa']==v_sel]['id'].values[0]
            s_v = st.date_input("Vence SOAT")
            if st.form_submit_button("🔄 Actualizar"):
                cur=conn.cursor(); cur.execute("INSERT INTO hoja_vida (vehiculo_id, soat_vence) VALUES (%s,%s) ON CONFLICT (vehiculo_id) DO UPDATE SET soat_vence=EXCLUDED.soat_vence", (int(v_id), s_v))
                conn.commit(); st.success("Actualizado"); st.rerun()
    st.dataframe(pd.read_sql("SELECT v.placa, h.soat_vence FROM vehiculos v LEFT JOIN hoja_vida h ON v.id=h.vehiculo_id", conn), use_container_width=True)

# --- MÓDULO: FLOTA ---
elif menu == "🚐 Flota":
    st.title("🚐 Flota")
    with st.form("f_f"):
        p = st.text_input("Placa").upper()
        if st.form_submit_button("➕ Añadir"):
            cur=conn.cursor(); cur.execute("INSERT INTO vehiculos (placa) VALUES (%s) ON CONFLICT DO NOTHING", (p,))
            conn.commit(); st.rerun()
    st.dataframe(pd.read_sql("SELECT * FROM vehiculos", conn), use_container_width=True)

# --- MÓDULO: USUARIOS / TARIFAS ---
elif menu == "⚙️ Usuarios":
    if st.session_state.es_textil:
        st.subheader("🧵 Tarifas de Confección")
        with st.form("f_t"):
            s = st.text_input("Servicio"); p = st.number_input("Precio/U")
            if st.form_submit_button("💾 Guardar Tarifa"):
                cur=conn.cursor(); cur.execute("INSERT INTO tarifario_textil (servicio, precio_unitario) VALUES (%s,%s) ON CONFLICT (servicio) DO UPDATE SET precio_unitario=EXCLUDED.precio_unitario", (s, p))
                conn.commit(); st.rerun()

conn.close()
