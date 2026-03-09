import streamlit as st
import psycopg2
import pandas as pd
from datetime import datetime, timedelta
import io
import plotly.express as px

# --- 1. CONEXIÓN CON FIX DE ESQUEMA ---
def conectar_db():
    try:
        conn = psycopg2.connect(st.session_state.db_url)
        cur = conn.cursor()
        # FIX: Esto soluciona el error InvalidSchemaName de tu imagen
        cur.execute("SET search_path TO public")
        return conn
    except Exception as e:
        st.error(f"Error de conexión: {e}")
        return None

def inicializar_db():
    conn = conectar_db()
    if conn:
        cur = conn.cursor()
        # Tablas originales para los 25 vehículos y gestión de drivers
        cur.execute('CREATE TABLE IF NOT EXISTS vehiculos (id SERIAL PRIMARY KEY, placa TEXT UNIQUE NOT NULL, marca TEXT, modelo TEXT, conductor TEXT)')
        cur.execute('CREATE TABLE IF NOT EXISTS gastos (id SERIAL PRIMARY KEY, vehiculo_id INTEGER REFERENCES vehiculos(id), tipo_gasto TEXT, monto NUMERIC, fecha DATE, detalle TEXT)')
        cur.execute('CREATE TABLE IF NOT EXISTS ventas (id SERIAL PRIMARY KEY, vehiculo_id INTEGER REFERENCES vehiculos(id), cliente TEXT, valor_viaje NUMERIC, fecha DATE, descripcion TEXT)')
        cur.execute('''CREATE TABLE IF NOT EXISTS hoja_vida (id SERIAL PRIMARY KEY, vehiculo_id INTEGER UNIQUE REFERENCES vehiculos(id), 
                        soat_vence DATE, tecno_vence DATE, prev_vence DATE, p_contractual DATE, p_extracontractual DATE, p_todoriesgo DATE, t_operaciones DATE)''')
        cur.execute('CREATE TABLE IF NOT EXISTS usuarios (id SERIAL PRIMARY KEY, nombre TEXT, usuario TEXT UNIQUE NOT NULL, clave TEXT NOT NULL, rol TEXT DEFAULT "admin")')
        cur.execute('CREATE TABLE IF NOT EXISTS tarifario_textil (id SERIAL PRIMARY KEY, servicio TEXT UNIQUE, precio_unitario NUMERIC)')
        cur.execute("INSERT INTO usuarios (nombre, usuario, clave, rol) VALUES ('Admin', 'admin', '1234', 'admin') ON CONFLICT DO NOTHING")
        conn.commit(); conn.close()

# --- 2. FUNCIÓN EXCEL ---
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

# --- 4. LOGIN ---
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

# --- 5. MENÚ ---
st.sidebar.write(f"🏢 **{st.session_state.nom_emp}**")
menu = st.sidebar.selectbox("Módulos:", ["📊 Dashboard", "🚐 Flota", "💸 Gastos", "💰 Ventas", "📑 Hoja de Vida", "⚙️ Configuración"])
if st.sidebar.button("🚪 Cerrar Sesión"): st.session_state.logged_in = False; st.rerun()

conn = conectar_db()

# --- DASHBOARD ---
if menu == "📊 Dashboard":
    st.title(f"📊 Dashboard - {st.session_state.nom_emp}")
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    if v_data.empty: st.warning("Registre vehículos primero.")
    else:
        r = st.date_input("Rango:", [datetime.now().date()-timedelta(30), datetime.now().date()])
        if len(r) == 2:
            df_g = pd.read_sql("SELECT g.fecha, v.placa, g.tipo_gasto as concepto, g.monto, g.detalle FROM gastos g JOIN vehiculos v ON g.vehiculo_id=v.id WHERE g.fecha BETWEEN %s AND %s", conn, params=[r[0], r[1]])
            df_v = pd.read_sql("SELECT s.fecha, v.placa, s.cliente, s.valor_viaje as monto, s.descripcion FROM ventas s JOIN vehiculos v ON s.vehiculo_id=v.id WHERE s.fecha BETWEEN %s AND %s", conn, params=[r[0], r[1]])
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Ingresos", f"${df_v['monto'].sum():,.0f}")
            c2.metric("Egresos", f"${df_g['monto'].sum():,.0f}")
            c3.metric("Utilidad", f"${df_v['monto'].sum()-df_g['monto'].sum():,.0f}")

            st.download_button("📥 Descargar Excel", data=to_excel(df_v, df_g, df_v), file_name="Reporte.xlsx")

# --- VENTAS (CON CAMPO TOTAL Y FECHA) ---
elif menu == "💰 Ventas":
    st.title("💰 Registro de Ventas")
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    if v_data.empty: st.warning("⚠️ Primero cree un vehículo.")
    else:
        with st.form("f_v"):
            v_sel = st.selectbox("Seleccione Vehículo", v_data['placa'])
            v_id = v_data[v_data['placa']==v_sel]['id'].values[0]
            fec = st.date_input("Fecha de Venta", datetime.now().date())
            
            if st.session_state.es_textil:
                tarifas = pd.read_sql("SELECT * FROM tarifario_textil", conn)
                if tarifas.empty: st.error("⚠️ Registre tarifas en Configuración.")
                else:
                    serv = st.selectbox("Servicio Textil", tarifas['servicio'].tolist())
                    p_u = tarifas[tarifas['servicio']==serv]['precio_unitario'].values[0]
                    cant = st.number_input(f"Cantidad (Precio/U: ${p_u:,.0f})", min_value=1)
                    # CAMPO TOTAL AUTOMÁTICO
                    total_calc = cant * p_u
                    st.markdown(f"### 💵 TOTAL A COBRAR: **${total_calc:,.0f}**")
                    det = f"{serv} - {cant} unds"
                    if st.form_submit_button("💾 Guardar Venta"):
                        cur=conn.cursor(); cur.execute("INSERT INTO ventas (vehiculo_id, cliente, valor_viaje, fecha, descripcion) VALUES (%s,%s,%s,%s,%s)", (int(v_id), serv, total_calc, fec, det))
                        conn.commit(); st.success("¡Venta guardada!"); st.rerun()
            else:
                det = st.text_input("Cliente / Concepto")
                monto = st.number_input("Valor del Viaje", min_value=0)
                if st.form_submit_button("💾 Guardar Viaje"):
                    cur=conn.cursor(); cur.execute("INSERT INTO ventas (vehiculo_id, cliente, valor_viaje, fecha, descripcion) VALUES (%s,%s,%s,%s,%s)", (int(v_id), det, monto, fec, det))
                    conn.commit(); st.success("¡Venta guardada!"); st.rerun()

# --- HOJA DE VIDA (7 DOCUMENTOS) ---
elif menu == "📑 Hoja de Vida":
    st.title("📑 Gestión Documental")
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    if not v_data.empty:
        with st.form("f_hv"):
            v_sel = st.selectbox("Vehículo", v_data['placa'])
            v_id = v_data[v_data['placa']==v_sel]['id'].values[0]
            c1, c2 = st.columns(2)
            s_v, t_v, p_v = c1.date_input("SOAT"), c1.date_input("Tecno"), c1.date_input("Preventivo")
            pc_v, pe_v, ptr_v = c2.date_input("Pol. Cont."), c2.date_input("Pol. Extra"), c2.date_input("Todo Riesgo")
            to_v = st.date_input("Tarjeta Operación")
            if st.form_submit_button("🔄 Actualizar Documentos"):
                cur=conn.cursor(); cur.execute('''INSERT INTO hoja_vida (vehiculo_id, soat_vence, tecno_vence, prev_vence, p_contractual, p_extracontractual, p_todoriesgo, t_operaciones) 
                               VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (vehiculo_id) DO UPDATE SET 
                               soat_vence=EXCLUDED.soat_vence, tecno_vence=EXCLUDED.tecno_vence, prev_vence=EXCLUDED.prev_vence,
                               p_contractual=EXCLUDED.p_contractual, p_extracontractual=EXCLUDED.p_extracontractual,
                               p_todoriesgo=EXCLUDED.p_todoriesgo, t_operaciones=EXCLUDED.t_operaciones''',
                            (int(v_id), s_v, t_v, p_v, pc_v, pe_v, ptr_v, to_v))
                conn.commit(); st.success("Actualizado"); st.rerun()
    st.dataframe(pd.read_sql("SELECT v.placa, h.* FROM vehiculos v LEFT JOIN hoja_vida h ON v.id=h.vehiculo_id", conn), use_container_width=True)

# --- FLOTA ---
elif menu == "🚐 Flota":
    st.title("🚐 Flota")
    with st.form("f_f"):
        p, m, mod, cond = st.text_input("Placa"), st.text_input("Marca"), st.text_input("Modelo"), st.text_input("Conductor")
        if st.form_submit_button("➕ Registrar"):
            cur=conn.cursor(); cur.execute("INSERT INTO vehiculos (placa, marca, modelo, conductor) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING", (p.upper(), m, mod, cond))
            conn.commit(); st.rerun()
    st.dataframe(pd.read_sql("SELECT * FROM vehiculos", conn), use_container_width=True)

# --- CONFIGURACIÓN ---
elif menu == "⚙️ Configuración":
    if st.session_state.es_textil:
        st.subheader("🧵 Tarifas Textil")
        with st.form("f_t"):
            s, p = st.text_input("Servicio"), st.number_input("Precio/U")
            if st.form_submit_button("💾 Guardar"):
                cur=conn.cursor(); cur.execute("INSERT INTO tarifario_textil (servicio, precio_unitario) VALUES (%s,%s) ON CONFLICT (servicio) DO UPDATE SET precio_unitario=EXCLUDED.precio_unitario", (s, p))
                conn.commit(); st.rerun()
        st.table(pd.read_sql("SELECT * FROM tarifario_textil", conn))

conn.close()
