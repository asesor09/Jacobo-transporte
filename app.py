import streamlit as st
import psycopg2
import pandas as pd
from datetime import datetime, timedelta
import io
import plotly.express as px

# --- 1. CONFIGURACIÓN DE LA BASE DE DATOS (URL PROPORCIONADA) ---
DB_URL = "postgresql://neondb_owner:npg_c7Dkwlh1jzGQ@ep-lucky-shadow-ac1thtiq-pooler.sa-east-1.aws.neon.tech/neondb?sslmode=require"

def conectar_db():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("SET search_path TO public") # GPS para no perderse en la DB
    return conn

def inicializar_db():
    conn = conectar_db(); cur = conn.cursor()
    cur.execute('CREATE TABLE IF NOT EXISTS vehiculos (id SERIAL PRIMARY KEY, placa TEXT UNIQUE NOT NULL, marca TEXT, modelo TEXT, conductor TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS gastos (id SERIAL PRIMARY KEY, vehiculo_id INTEGER REFERENCES vehiculos(id), tipo_gasto TEXT, monto NUMERIC, fecha DATE, detalle TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS ventas (id SERIAL PRIMARY KEY, vehiculo_id INTEGER REFERENCES vehiculos(id), cliente TEXT, valor_viaje NUMERIC, fecha DATE, descripcion TEXT, cantidad INTEGER)')
    cur.execute('CREATE TABLE IF NOT EXISTS tarifario (id SERIAL PRIMARY KEY, servicio TEXT UNIQUE NOT NULL, precio_unidad NUMERIC NOT NULL)')
    cur.execute('''CREATE TABLE IF NOT EXISTS hoja_vida (
                    id SERIAL PRIMARY KEY, vehiculo_id INTEGER UNIQUE REFERENCES vehiculos(id), 
                    soat_vence DATE, tecno_vence DATE, prev_vence DATE,
                    p_contractual DATE, p_extracontractual DATE, p_todoriesgo DATE, t_operaciones DATE)''')
    cur.execute('CREATE TABLE IF NOT EXISTS usuarios (id SERIAL PRIMARY KEY, nombre TEXT, usuario TEXT UNIQUE NOT NULL, clave TEXT NOT NULL, rol TEXT DEFAULT "admin")')
    cur.execute("INSERT INTO usuarios (nombre, usuario, clave, rol) VALUES ('Jacobo Admin', 'admin', 'Jacobo2026', 'admin') ON CONFLICT (usuario) DO NOTHING")
    
    # Asegurar columnas necesarias
    try: cur.execute("ALTER TABLE ventas ADD COLUMN IF NOT EXISTS cantidad INTEGER")
    except: conn.rollback()
    
    conn.commit(); conn.close()

# --- 2. FUNCIONES DE APOYO ---
def to_excel(df_balance, df_g, df_v):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_balance.to_excel(writer, index=False, sheet_name='Balance General')
        df_g.to_excel(writer, index=False, sheet_name='Detalle Gastos')
        df_v.to_excel(writer, index=False, sheet_name='Detalle Ventas')
    return output.getvalue()

st.set_page_config(page_title="C&E Eficiencias", layout="wide", page_icon="🚐")
inicializar_db()

# --- 3. LOGIN ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if not st.session_state.logged_in:
    st.sidebar.title("🔐 Acceso Seguro")
    u_input = st.sidebar.text_input("Usuario")
    p_input = st.sidebar.text_input("Contraseña", type="password")
    if st.sidebar.button("Ingresar"):
        conn = conectar_db(); cur = conn.cursor()
        cur.execute("SELECT nombre, rol FROM usuarios WHERE usuario = %s AND clave = %s", (u_input, p_input))
        res = cur.fetchone(); conn.close()
        if res:
            st.session_state.logged_in = True
            st.session_state.u_name, st.session_state.u_rol = res[0], res[1]
            st.rerun()
        else: st.sidebar.error("Usuario o clave incorrectos")
    st.stop()

# --- 4. MENÚ ---
st.sidebar.write(f"👋 Bienvenid@, **{st.session_state.u_name}**")
st.sidebar.divider()
target = st.sidebar.number_input("🎯 Meta Utilidad ($)", value=5000000, step=500000)
menu = st.sidebar.selectbox("📂 SELECCIONE UN MÓDULO", ["📊 Resumen Ejecutivo", "🚐 Flota", "💸 Gastos", "💰 Ventas", "📑 Hoja de Vida", "⚙️ Tarifas", "⚙️ Usuarios"])

if st.sidebar.button("🚪 CERRAR SESIÓN"):
    st.session_state.logged_in = False; st.rerun()

conn = conectar_db()

# --- 📊 MÓDULO: RESUMEN EJECUTIVO (ESTILO CAPTURA) ---
if menu == "📊 Resumen Ejecutivo":
    st.title("📊 Tablero de Eficiencia")
    
    # Carga de datos
    df_v_all = pd.read_sql("SELECT fecha, valor_viaje as monto FROM ventas", conn)
    df_g_all = pd.read_sql("SELECT fecha, monto FROM gastos", conn)
    v_activos = pd.read_sql("SELECT COUNT(*) as count FROM vehiculos", conn).iloc[0]['count']
    
    # Métricas Superiores
    c1, c2, c3 = st.columns(3)
    c1.metric("📦 Vehículos Activos", v_activos)
    c2.metric("📉 Egresos (Gastos)", f"$ {df_g_all['monto'].sum():,.0f}")
    c3.metric("📈 Ingresos (Ventas)", f"$ {df_v_all['monto'].sum():,.0f}")

    st.subheader("📅 Totales por Mes")
    if not df_v_all.empty or not df_g_all.empty:
        df_v_all['fecha'] = pd.to_datetime(df_v_all['fecha'])
        df_g_all['fecha'] = pd.to_datetime(df_g_all['fecha'])
        
        # Agrupar por mes
        v_mes = df_v_all.groupby(df_v_all['fecha'].dt.to_period('M'))['monto'].sum().reset_index()
        g_mes = df_g_all.groupby(df_g_all['fecha'].dt.to_period('M'))['monto'].sum().reset_index()
        
        res_mes = pd.merge(v_mes, g_mes, on='fecha', how='outer', suffixes=('_v', '_g')).fillna(0)
        res_mes['Utilidad'] = res_mes['monto_v'] - res_mes['monto_g']
        res_mes.rename(columns={'fecha': 'Mes', 'monto_v': 'Ingresos', 'monto_g': 'Gastos'}, inplace=True)
        res_mes['Mes'] = res_mes['Mes'].astype(str)
        
        # Formatear tabla como la imagen
        st.table(res_mes.style.format({"Ingresos": "$ {:,.0f}", "Gastos": "$ {:,.0f}", "Utilidad": "$ {:,.0f}"}))
        
        # Utilidad Neta Actual (Cuadro Verde)
        utilidad_total = res_mes['Utilidad'].sum()
        st.info(f"### 🚀 Utilidad Neta Actual: $ {utilidad_total:,.0f}")
        
        if utilidad_total >= target: st.balloons()
    else:
        st.info("No hay datos para mostrar en el tablero mensual.")

# --- 💰 MÓDULO: VENTAS (CÁLCULO LUZMA) ---
elif menu == "💰 Ventas":
    st.title("💰 Control de Ingresos")
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    t_data = pd.read_sql("SELECT servicio, precio_unidad FROM tarifario", conn)
    tab1, tab2 = st.tabs(["📝 Registrar", "✏️ Editar/Borrar"])
    
    with tab1:
        with st.form("f_v"):
            v_sel = st.selectbox("Vehículo", v_data['placa'] if not v_data.empty else [])
            s_sel = st.selectbox("Servicio", t_data['servicio'].tolist() if not t_data.empty else [])
            cant = st.number_input("Cantidad", min_value=1)
            desc = st.text_area("Descripción")
            if st.form_submit_button("💰 Guardar"):
                v_id = v_data[v_data['placa'] == v_sel]['id'].values[0]
                precio_u = t_data[t_data['servicio'] == s_sel]['precio_unidad'].values[0]
                total = float(cant * precio_u)
                cur = conn.cursor()
                cur.execute("INSERT INTO ventas (vehiculo_id, cliente, valor_viaje, fecha, descripcion, cantidad) VALUES (%s,%s,%s,%s,%s,%s)", (int(v_id), s_sel, total, datetime.now().date(), desc, int(cant)))
                conn.commit(); st.success(f"Guardado por ${total:,.0f}"); st.rerun()
    with tab2:
        df_v = pd.read_sql("SELECT s.id, s.fecha, v.placa, s.cliente, s.valor_viaje as monto, s.descripcion FROM ventas s JOIN vehiculos v ON s.vehiculo_id = v.id ORDER BY s.id DESC", conn)
        sel = st.dataframe(df_v, use_container_width=True, on_select="rerun", selection_mode="single-row", hide_index=True)
        if len(sel.selection.rows) > 0:
            row = df_v.iloc[sel.selection.rows[0]]
            if st.button("🗑️ Borrar Registro"):
                cur = conn.cursor(); cur.execute("DELETE FROM ventas WHERE id=%s", (int(row['id']),)); conn.commit(); st.rerun()

# --- 💸 MÓDULO: GASTOS (EDICIÓN) ---
elif menu == "💸 Gastos":
    st.title("💸 Control de Gastos")
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    tab1, tab2 = st.tabs(["📝 Registro", "✏️ Editar/Borrar"])
    with tab1:
        with st.form("f_g"):
            v_sel = st.selectbox("Vehículo", v_data['placa'])
            tipo = st.selectbox("Tipo", ["Combustible", "Mantenimiento", "Peaje", "Otros"])
            monto = st.number_input("Valor", min_value=0); det = st.text_input("Nota")
            if st.form_submit_button("💾 Guardar"):
                v_id = v_data[v_data['placa'] == v_sel]['id'].values[0]
                cur = conn.cursor(); cur.execute("INSERT INTO gastos (vehiculo_id, tipo_gasto, monto, fecha, detalle) VALUES (%s,%s,%s,%s,%s)", (int(v_id), tipo, monto, datetime.now().date(), det))
                conn.commit(); st.rerun()
    with tab2:
        df_g = pd.read_sql("SELECT g.id, g.fecha, v.placa, g.tipo_gasto, g.monto, g.detalle FROM gastos g JOIN vehiculos v ON g.vehiculo_id = v.id ORDER BY g.id DESC", conn)
        sel_g = st.dataframe(df_g, use_container_width=True, on_select="rerun", selection_mode="single-row", hide_index=True)
        if len(sel_g.selection.rows) > 0:
            row_g = df_g.iloc[sel_g.selection.rows[0]]
            if st.button("🗑️ Borrar Gasto"):
                cur = conn.cursor(); cur.execute("DELETE FROM gastos WHERE id=%s", (int(row_g['id']),)); conn.commit(); st.rerun()

# --- 📑 HOJA DE VIDA (INTACTA) ---
elif menu == "📑 Hoja de Vida":
    st.title("📑 Documentación y Vencimientos")
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    with st.expander("📅 Actualizar"):
        with st.form("f_hv"):
            v_sel = st.selectbox("Vehículo", v_data['placa']); v_id = v_data[v_data['placa'] == v_sel]['id'].values[0]
            c1, c2 = st.columns(2)
            s_v = c1.date_input("SOAT"); t_v = c1.date_input("Tecno"); p_v = c1.date_input("Preventivo")
            pc_v = c2.date_input("P. Contractual"); pe_v = c2.date_input("P. Extra"); ptr_v = c2.date_input("Todo Riesgo"); to_v = st.date_input("T. Operaciones")
            if st.form_submit_button("🔄 Actualizar"):
                cur = conn.cursor(); cur.execute('''INSERT INTO hoja_vida (vehiculo_id, soat_vence, tecno_vence, prev_vence, p_contractual, p_extracontractual, p_todoriesgo, t_operaciones) 
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (vehiculo_id) DO UPDATE SET soat_vence=EXCLUDED.soat_vence, tecno_vence=EXCLUDED.tecno_vence, prev_vence=EXCLUDED.prev_vence, p_contractual=EXCLUDED.p_contractual, p_extracontractual=EXCLUDED.p_extracontractual, p_todoriesgo=EXCLUDED.p_todoriesgo, t_operaciones=EXCLUDED.t_operaciones''', (int(v_id), s_v, t_v, p_v, pc_v, pe_v, ptr_v, to_v))
                conn.commit(); st.rerun()
    df_hv = pd.read_sql('''SELECT v.placa, h.soat_vence, h.tecno_vence, h.prev_vence, h.p_contractual, h.p_extracontractual, h.p_todoriesgo, h.t_operaciones FROM vehiculos v LEFT JOIN hoja_vida h ON v.id = h.vehiculo_id''', conn)
    hoy = datetime.now().date()
    for _, row in df_hv.iterrows():
        st.subheader(f"Vehículo: {row['placa']}")
        cols = st.columns(4); docs = [("SOAT", row['soat_vence']), ("TECNO", row['tecno_vence']), ("PREV", row['prev_vence']), ("T.OPER", row['t_operaciones']), ("POL. CONT", row['p_contractual']), ("POL. EXTRA", row['p_extracontractual']), ("TODO RIESGO", row['p_todoriesgo'])]
        for i, (name, fecha) in enumerate(docs):
            if fecha:
                d = (fecha - hoy).days
                if d < 0: cols[i % 4].error(f"❌ {name} VENCIDO")
                elif d <= 15: cols[i % 4].warning(f"⚠️ {name} ({d} d)")
                else: cols[i % 4].success(f"✅ {name} OK")
            else: cols[i % 4].info(f"⚪ {name}: S/D")

# --- ⚙️ TARIFAS ---
elif menu == "⚙️ Tarifas":
    st.title("⚙️ Precios por Servicio")
    with st.form("f_t"):
        s = st.text_input("Servicio"); p = st.number_input("Precio ($)")
        if st.form_submit_button("Guardar"):
            cur = conn.cursor(); cur.execute("INSERT INTO tarifario (servicio, precio_unidad) VALUES (%s,%s) ON CONFLICT (servicio) DO UPDATE SET precio_unidad=EXCLUDED.precio_unidad", (s, p))
            conn.commit(); st.rerun()
    st.table(pd.read_sql("SELECT * FROM tarifario", conn))

# --- 🚐 FLOTA ---
elif menu == "🚐 Flota":
    st.title("🚐 Flota")
    with st.form("f_f"):
        p = st.text_input("Placa").upper(); m = st.text_input("Marca"); mod = st.text_input("Modelo"); cond = st.text_input("Conductor")
        if st.form_submit_button("➕ Añadir"):
            cur = conn.cursor(); cur.execute("INSERT INTO vehiculos (placa, marca, modelo, conductor) VALUES (%s,%s,%s,%s)", (p, m, mod, cond))
            conn.commit(); st.rerun()
    st.dataframe(pd.read_sql("SELECT * FROM vehiculos", conn), use_container_width=True)

# --- ⚙️ USUARIOS ---
elif menu == "⚙️ Usuarios" and st.session_state.u_rol == "admin":
    st.title("⚙️ Personal")
    with st.form("f_u"):
        nom = st.text_input("Nombre"); u = st.text_input("Usuario"); c = st.text_input("Clave"); r = st.selectbox("Rol", ["admin", "vendedor"])
        if st.form_submit_button("👤 Crear"):
            cur = conn.cursor(); cur.execute("INSERT INTO usuarios (nombre, usuario, clave, rol) VALUES (%s,%s,%s,%s)", (nom, u, c, r))
            conn.commit(); st.success("Creado")

conn.close()
