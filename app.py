import streamlit as st
import psycopg2
import pandas as pd
from datetime import datetime, timedelta
import io
import plotly.express as px

# --- 1. CONEXIÓN Y BASE DE DATOS ---
def conectar_db():
    try: return psycopg2.connect(st.session_state.db_url)
    except: return None

def inicializar_db():
    conn = conectar_db()
    if conn:
        cur = conn.cursor()
        # Restauradas todas las tablas con tus columnas originales
        cur.execute('CREATE TABLE IF NOT EXISTS vehiculos (id SERIAL PRIMARY KEY, placa TEXT UNIQUE NOT NULL, marca TEXT, modelo TEXT, conductor TEXT)')
        cur.execute('CREATE TABLE IF NOT EXISTS gastos (id SERIAL PRIMARY KEY, vehiculo_id INTEGER REFERENCES vehiculos(id), tipo_gasto TEXT, monto NUMERIC, fecha DATE, detalle TEXT)')
        cur.execute('CREATE TABLE IF NOT EXISTS ventas (id SERIAL PRIMARY KEY, vehiculo_id INTEGER REFERENCES vehiculos(id), cliente TEXT, valor_viaje NUMERIC, fecha DATE, descripcion TEXT)')
        # Hoja de Vida con los 7 documentos completos
        cur.execute('''CREATE TABLE IF NOT EXISTS hoja_vida (
                        id SERIAL PRIMARY KEY, vehiculo_id INTEGER UNIQUE REFERENCES vehiculos(id), 
                        soat_vence DATE, tecno_vence DATE, prev_vence DATE,
                        p_contractual DATE, p_extracontractual DATE, p_todoriesgo DATE, t_operaciones DATE)''')
        cur.execute('CREATE TABLE IF NOT EXISTS usuarios (id SERIAL PRIMARY KEY, nombre TEXT, usuario TEXT UNIQUE NOT NULL, clave TEXT NOT NULL, rol TEXT DEFAULT "admin")')
        cur.execute('CREATE TABLE IF NOT EXISTS tarifario_textil (id SERIAL PRIMARY KEY, servicio TEXT UNIQUE, precio_unitario NUMERIC)')
        cur.execute("INSERT INTO usuarios (nombre, usuario, clave, rol) VALUES ('Admin', 'admin', '1234', 'admin') ON CONFLICT DO NOTHING")
        conn.commit(); conn.close()

# --- 2. FUNCIÓN DE EXCEL (RESTAURADA) ---
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

# --- 5. MENÚ ---
st.sidebar.write(f"🏢 **{st.session_state.nom_emp}**")
menu = st.sidebar.selectbox("Módulos:", ["📊 Dashboard", "🚐 Flota", "💸 Gastos", "💰 Ventas", "📑 Hoja de Vida", "⚙️ Configuración"])
target = st.sidebar.number_input("🎯 Meta Utilidad", value=5000000)
if st.sidebar.button("🚪 Cerrar Sesión"): st.session_state.logged_in = False; st.rerun()

conn = conectar_db()

# --- DASHBOARD COMPLETO ---
if menu == "📊 Dashboard":
    st.title(f"📊 Análisis de {st.session_state.nom_emp}")
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    if v_data.empty: st.warning("Registre vehículos primero.")
    else:
        placa_f = st.selectbox("Vehículo:", ["TODOS"] + v_data['placa'].tolist())
        r = st.date_input("Rango de fechas:", [datetime.now().date()-timedelta(30), datetime.now().date()])
        if len(r)==2:
            q_g = "SELECT g.fecha, v.placa, g.tipo_gasto as concepto, g.monto, g.detalle FROM gastos g JOIN vehiculos v ON g.vehiculo_id=v.id WHERE g.fecha BETWEEN %s AND %s"
            q_v = "SELECT s.fecha, v.placa, s.cliente, s.valor_viaje as monto, s.descripcion FROM ventas s JOIN vehiculos v ON s.vehiculo_id=v.id WHERE s.fecha BETWEEN %s AND %s"
            params = [r[0], r[1]]
            if placa_f != "TODOS":
                q_g += " AND v.placa = %s"; q_v += " AND v.placa = %s"; params.append(placa_f)
            
            df_g = pd.read_sql(q_g, conn, params=params)
            df_v = pd.read_sql(q_v, conn, params=params)

            # Métricas
            utilidad = df_v['monto'].sum() - df_g['monto'].sum()
            c1, c2, c3 = st.columns(3)
            c1.metric("Ingresos", f"${df_v['monto'].sum():,.0f}")
            c2.metric("Gastos", f"${df_g['monto'].sum():,.0f}", delta_color="inverse")
            c3.metric("Utilidad", f"${utilidad:,.0f}", delta=f"{utilidad-target:,.0f}")

            # Gráfico de Barras
            st.plotly_chart(px.bar(df_v.groupby('placa')['monto'].sum().reset_index(), x='placa', y='monto', title="Ingresos por Placa"), use_container_width=True)

            # EXCEL RESTAURADO
            res_v = df_v.groupby('placa')['monto'].sum().reset_index().rename(columns={'monto':'Venta'})
            res_g = df_g.groupby('placa')['monto'].sum().reset_index().rename(columns={'monto':'Gasto'})
            balance_df = pd.merge(res_v, res_g, on='placa', how='outer').fillna(0)
            st.download_button("📥 Descargar Reporte Excel", data=to_excel(balance_df, df_g, df_v), file_name="Reporte_Completo.xlsx")

            with st.expander("🔍 Ver Detalle de Movimientos por Día"):
                st.write("Ventas:"); st.dataframe(df_v, use_container_width=True, hide_index=True)
                st.write("Gastos:"); st.dataframe(df_g, use_container_width=True, hide_index=True)

# --- VENTAS CON FECHA ---
elif menu == "💰 Ventas":
    st.title("💰 Registro de Ventas")
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    if v_data.empty: st.warning("Crea vehículos primero.")
    else:
        with st.form("f_v"):
            v_sel = st.selectbox("Vehículo", v_data['placa'])
            v_id = v_data[v_data['placa']==v_sel]['id'].values[0]
            fec = st.date_input("Fecha", datetime.now().date())
            
            if st.session_state.es_textil:
                tarifas = pd.read_sql("SELECT * FROM tarifario_textil", conn)
                if tarifas.empty: st.error("Faltan tarifas.")
                else:
                    serv = st.selectbox("Servicio", tarifas['servicio'].tolist())
                    cant = st.number_input("Cantidad", min_value=1)
                    monto = cant * tarifas[tarifas['servicio']==serv]['precio_unitario'].values[0]
                    det = f"{serv} ({cant} unds)"
            else:
                det = st.text_input("Cliente")
                monto = st.number_input("Valor", min_value=0)

            if st.form_submit_button("💾 Guardar"):
                cur=conn.cursor(); cur.execute("INSERT INTO ventas (vehiculo_id, cliente, valor_viaje, fecha, descripcion) VALUES (%s,%s,%s,%s,%s)", (int(v_id), det, monto, fec, det))
                conn.commit(); st.success("Guardado"); st.rerun()

# --- HOJA DE VIDA RESTAURADA (7 DOCUMENTOS) ---
elif menu == "📑 Hoja de Vida":
    st.title("📑 Gestión Documental")
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    if not v_data.empty:
        with st.form("f_hv"):
            v_sel = st.selectbox("Vehículo", v_data['placa'])
            v_id = v_data[v_data['placa']==v_sel]['id'].values[0]
            c1, c2 = st.columns(2)
            s_v = c1.date_input("SOAT")
            t_v = c1.date_input("Tecno")
            p_v = c1.date_input("Preventivo")
            pc_v = c2.date_input("Pol. Contractual")
            pe_v = c2.date_input("Pol. Extra")
            ptr_v = c2.date_input("Todo Riesgo")
            to_v = st.date_input("Tarjeta Operación")
            
            if st.form_submit_button("🔄 Actualizar Todo"):
                cur=conn.cursor()
                cur.execute('''INSERT INTO hoja_vida (vehiculo_id, soat_vence, tecno_vence, prev_vence, p_contractual, p_extracontractual, p_todoriesgo, t_operaciones) 
                               VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (vehiculo_id) DO UPDATE SET 
                               soat_vence=EXCLUDED.soat_vence, tecno_vence=EXCLUDED.tecno_vence, prev_vence=EXCLUDED.prev_vence,
                               p_contractual=EXCLUDED.p_contractual, p_extracontractual=EXCLUDED.p_extracontractual,
                               p_todoriesgo=EXCLUDED.p_todoriesgo, t_operaciones=EXCLUDED.t_operaciones''',
                            (int(v_id), s_v, t_v, p_v, pc_v, pe_v, ptr_v, to_v))
                conn.commit(); st.success("¡Documentos actualizados!"); st.rerun()
    st.dataframe(pd.read_sql("SELECT v.placa, h.* FROM vehiculos v LEFT JOIN hoja_vida h ON v.id=h.vehiculo_id", conn), use_container_width=True)

# --- FLOTA COMPLETA ---
elif menu == "🚐 Flota":
    st.title("🚐 Administración de Flota")
    with st.form("f_f"):
        p, m, mod, cond = st.text_input("Placa"), st.text_input("Marca"), st.text_input("Modelo"), st.text_input("Conductor")
        if st.form_submit_button("➕ Registrar"):
            cur=conn.cursor(); cur.execute("INSERT INTO vehiculos (placa, marca, modelo, conductor) VALUES (%s,%s,%s,%s)", (p.upper(), m, mod, cond))
            conn.commit(); st.rerun()
    st.dataframe(pd.read_sql("SELECT * FROM vehiculos", conn), use_container_width=True)

# --- CONFIGURACIÓN ---
elif menu == "⚙️ Configuración":
    if st.session_state.es_textil:
        st.subheader("🧵 Precios de Confección")
        with st.form("f_t"):
            s, p = st.text_input("Servicio"), st.number_input("Precio/U", min_value=0)
            if st.form_submit_button("💾 Guardar"):
                cur=conn.cursor(); cur.execute("INSERT INTO tarifario_textil (servicio, precio_unitario) VALUES (%s,%s) ON CONFLICT (servicio) DO UPDATE SET precio_unitario=EXCLUDED.precio_unitario", (s, p))
                conn.commit(); st.rerun()
        st.table(pd.read_sql("SELECT * FROM tarifario_textil", conn))

conn.close()
