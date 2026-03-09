import streamlit as st
import psycopg2
import pandas as pd
from datetime import datetime, timedelta
import io
import plotly.express as px

# --- 1. CONEXIÓN BLINDADA ---
def conectar_db():
    try:
        conn = psycopg2.connect(st.session_state.db_url)
        # Esta línea soluciona el error de InvalidSchemaName
        cur = conn.cursor()
        cur.execute("SET search_path TO public")
        return conn
    except Exception as e:
        st.error(f"❌ Error de conexión: {e}")
        return None

def inicializar_db():
    conn = conectar_db()
    if conn:
        cur = conn.cursor()
        # Restauradas TODAS tus tablas con todas sus columnas originales
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

# --- 2. EXCEL (RESTAURADO) ---
def to_excel(df_balance, df_g, df_v):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_balance.to_excel(writer, index=False, sheet_name='Balance General')
        df_g.to_excel(writer, index=False, sheet_name='Detalle Gastos')
        df_v.to_excel(writer, index=False, sheet_name='Detalle Ventas')
    return output.getvalue()

# --- 3. CONFIGURACIÓN UI ---
st.set_page_config(page_title="C&E Eficiencias", layout="wide", page_icon="🚐")

if 'logged_in' not in st.session_state: st.session_state.logged_in = False

# --- 4. LOGIN ---
if not st.session_state.logged_in:
    st.title("🔐 Acceso C&E Eficiencias")
    if "connections" in st.secrets:
        emp_sel = st.selectbox("Empresa:", list(st.secrets["connections"].keys()), format_func=lambda x: st.secrets["connections"][x]["nombre"])
        u, p = st.text_input("Usuario"), st.text_input("Contraseña", type="password")
        if st.button("🚀 Ingresar"):
            conf = st.secrets["connections"][emp_sel]
            st.session_state.db_url = conf["url"]
            st.session_state.es_textil = conf.get("modulo_textil", False)
            st.session_state.nom_emp = conf["nombre"]
            
            inicializar_db()
            conn = conectar_db()
            if conn:
                cur = conn.cursor()
                cur.execute("SELECT nombre, rol FROM usuarios WHERE usuario=%s AND clave=%s", (u, p))
                res = cur.fetchone(); conn.close()
                if res:
                    st.session_state.logged_in, st.session_state.u_name, st.session_state.u_rol = True, res[0], res[1]
                    st.rerun()
                else: st.error("❌ Credenciales incorrectas.")
    st.stop()

# --- 5. MENÚ ---
st.sidebar.write(f"🏢 **{st.session_state.nom_emp}**")
menu = st.sidebar.selectbox("Módulos:", ["📊 Dashboard", "🚐 Flota", "💸 Gastos", "💰 Ventas", "📑 Hoja de Vida", "⚙️ Configuración"])
target = st.sidebar.number_input("🎯 Meta Utilidad ($)", value=5000000)
if st.sidebar.button("🚪 Cerrar Sesión"): st.session_state.logged_in = False; st.rerun()

conn = conectar_db()

# --- MÓDULO: DASHBOARD (CON EXCEL Y DETALLES) ---
if menu == "📊 Dashboard":
    st.title(f"📊 Dashboard - {st.session_state.nom_emp}")
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    if v_data.empty: st.warning("⚠️ Sin vehículos registrados.")
    else:
        placa_f = st.selectbox("Filtrar por Vehículo:", ["TODOS"] + v_data['placa'].tolist())
        r = st.date_input("Rango de Fechas:", [datetime.now().date()-timedelta(30), datetime.now().date()])
        
        if len(r) == 2:
            q_g = "SELECT g.fecha, v.placa, g.tipo_gasto as concepto, g.monto, g.detalle FROM gastos g JOIN vehiculos v ON g.vehiculo_id=v.id WHERE g.fecha BETWEEN %s AND %s"
            q_v = "SELECT s.fecha, v.placa, s.cliente, s.valor_viaje as monto, s.descripcion FROM ventas s JOIN vehiculos v ON s.vehiculo_id=v.id WHERE s.fecha BETWEEN %s AND %s"
            params = [r[0], r[1]]
            if placa_f != "TODOS":
                q_g += " AND v.placa = %s"; q_v += " AND v.placa = %s"; params.append(placa_f)
            
            df_g = pd.read_sql(q_g, conn, params=params)
            df_v = pd.read_sql(q_v, conn, params=params)
            
            utilidad = df_v['monto'].sum() - df_g['monto'].sum()
            c1, c2, c3 = st.columns(3)
            c1.metric("Ingresos", f"${df_v['monto'].sum():,.0f}")
            c2.metric("Egresos", f"${df_g['monto'].sum():,.0f}", delta_color="inverse")
            c3.metric("Utilidad", f"${utilidad:,.0f}", delta=f"{utilidad-target:,.0f}")

            # Botón Excel (Recuperado)
            res_v = df_v.groupby('placa')['monto'].sum().reset_index().rename(columns={'monto':'Venta'})
            res_g = df_g.groupby('placa')['monto'].sum().reset_index().rename(columns={'monto':'Gasto'})
            balance_df = pd.merge(res_v, res_g, on='placa', how='outer').fillna(0)
            st.download_button("📥 Descargar Reporte Excel", data=to_excel(balance_df, df_g, df_v), file_name="Reporte_Completo.xlsx")

            with st.expander("🔍 Detalle de Movimientos por Día"):
                st.write("Ventas:"); st.dataframe(df_v, use_container_width=True, hide_index=True)
                st.write("Gastos:"); st.dataframe(df_g, use_container_width=True, hide_index=True)

# --- MÓDULO: VENTAS (CON CAJA DE FECHA Y CALCULADORA TEXTIL) ---
elif menu == "💰 Ventas":
    st.title("💰 Registro de Ventas")
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    if v_data.empty: st.warning("⚠️ Primero crea un vehículo.")
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
                    monto, det = cant * p_u, f"{serv} - {cant} unds"
            else:
                det = st.text_input("Cliente / Concepto")
                monto = st.number_input("Valor del Viaje", min_value=0)

            if st.form_submit_button("💾 Guardar Venta"):
                cur=conn.cursor(); cur.execute("INSERT INTO ventas (vehiculo_id, cliente, valor_viaje, fecha, descripcion) VALUES (%s,%s,%s,%s,%s)", (int(v_id), det, monto, fec, det))
                conn.commit(); st.success("¡Venta guardada!"); st.rerun()

# --- MÓDULO: HOJA DE VIDA (RESTAURADA CON LOS 7 VENCIMIENTOS) ---
elif menu == "📑 Hoja de Vida":
    st.title("📑 Gestión Documental")
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    if not v_data.empty:
        with st.form("f_hv"):
            v_sel = st.selectbox("Vehículo", v_data['placa'])
            v_id = v_data[v_data['placa']==v_sel]['id'].values[0]
            c1, c2 = st.columns(2)
            s_v, t_v, p_v = c1.date_input("SOAT"), c1.date_input("Tecno"), c1.date_input("Preventivo")
            pc_v, pe_v, ptr_v = c2.date_input("Póliza Cont."), c2.date_input("Póliza Extra"), c2.date_input("Todo Riesgo")
            to_v = st.date_input("Tarjeta Operación")
            
            if st.form_submit_button("🔄 Actualizar"):
                cur=conn.cursor()
                cur.execute('''INSERT INTO hoja_vida (vehiculo_id, soat_vence, tecno_vence, prev_vence, p_contractual, p_extracontractual, p_todoriesgo, t_operaciones) 
                               VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (vehiculo_id) DO UPDATE SET 
                               soat_vence=EXCLUDED.soat_vence, tecno_vence=EXCLUDED.tecno_vence, prev_vence=EXCLUDED.prev_vence,
                               p_contractual=EXCLUDED.p_contractual, p_extracontractual=EXCLUDED.p_extracontractual,
                               p_todoriesgo=EXCLUDED.p_todoriesgo, t_operaciones=EXCLUDED.t_operaciones''',
                            (int(v_id), s_v, t_v, p_v, pc_v, pe_v, ptr_v, to_v))
                conn.commit(); st.success("Documentos actualizados."); st.rerun()
    st.dataframe(pd.read_sql("SELECT v.placa, h.* FROM vehiculos v LEFT JOIN hoja_vida h ON v.id=h.vehiculo_id", conn), use_container_width=True)

# --- MÓDULO: GASTOS (CON CAJA DE FECHA) ---
elif menu == "💸 Gastos":
    st.title("💸 Registro de Gastos")
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    if not v_data.empty:
        with st.form("f_g"):
            v_sel = st.selectbox("Vehículo", v_data['placa'])
            v_id = v_data[v_data['placa']==v_sel]['id'].values[0]
            fec = st.date_input("Fecha Gasto", datetime.now().date())
            tipo = st.selectbox("Concepto", ["Combustible", "Peaje", "Mantenimiento", "Otros"])
            val = st.number_input("Monto", min_value=0)
            if st.form_submit_button("💾 Guardar"):
                cur=conn.cursor(); cur.execute("INSERT INTO gastos (vehiculo_id, tipo_gasto, monto, fecha) VALUES (%s,%s,%s,%s)", (int(v_id), tipo, val, fec))
                conn.commit(); st.success("Gasto guardado"); st.rerun()

# --- MÓDULO: FLOTA (COMPLETO) ---
elif menu == "🚐 Flota":
    st.title("🚐 Administración de Flota")
    with st.form("f_f"):
        p, m, mod, cond = st.text_input("Placa"), st.text_input("Marca"), st.text_input("Modelo"), st.text_input("Conductor")
        if st.form_submit_button("➕ Registrar"):
            cur=conn.cursor(); cur.execute("INSERT INTO vehiculos (placa, marca, modelo, conductor) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING", (p.upper(), m, mod, cond))
            conn.commit(); st.rerun()
    st.dataframe(pd.read_sql("SELECT * FROM vehiculos", conn), use_container_width=True)

# --- CONFIGURACIÓN ---
elif menu == "⚙️ Configuración":
    if st.session_state.es_textil:
        st.subheader("🧵 Precios de Confección")
        with st.form("f_t"):
            s, p = st.text_input("Servicio"), st.number_input("Precio/U")
            if st.form_submit_button("💾 Guardar"):
                cur=conn.cursor(); cur.execute("INSERT INTO tarifario_textil (servicio, precio_unitario) VALUES (%s,%s) ON CONFLICT (servicio) DO UPDATE SET precio_unitario=EXCLUDED.precio_unitario", (s, p))
                conn.commit(); st.rerun()
        st.table(pd.read_sql("SELECT * FROM tarifario_textil", conn))

conn.close()
