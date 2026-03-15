import streamlit as st
import psycopg2
import pandas as pd
from datetime import datetime, timedelta
import io
import plotly.express as px

# --- 1. CONFIGURACIÓN DE LA BASE DE DATOS (URL DIRECTA) ---
DB_URL = "postgresql://neondb_owner:npg_c7Dkwlh1jzGQ@ep-lucky-shadow-ac1thtiq-pooler.sa-east-1.aws.neon.tech/neondb?sslmode=require"

def conectar_db():
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        # ESTO ES LO QUE EVITA QUE EL CÓDIGO SE DAÑE:
        cur.execute("SET search_path TO public") 
        return conn
    except Exception as e:
        st.error(f"❌ Error de conexión: {e}")
        return None

def inicializar_db():
    conn = conectar_db()
    if conn:
        cur = conn.cursor()
        # Respetamos todas tus tablas originales
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
    st.sidebar.title("🔐 Acceso C&E")
    u_input = st.sidebar.text_input("Usuario")
    p_input = st.sidebar.text_input("Contraseña", type="password")
    if st.sidebar.button("Ingresar"):
        conn = conectar_db()
        if conn:
            cur = conn.cursor()
            cur.execute("SELECT nombre, rol FROM usuarios WHERE usuario = %s AND clave = %s", (u_input, p_input))
            res = cur.fetchone(); conn.close()
            if res:
                st.session_state.logged_in = True
                st.session_state.u_name, st.session_state.u_rol = res[0], res[1]
                st.rerun()
            else: st.sidebar.error("Usuario o clave incorrectos")
    st.stop()

# --- 4. MENÚ PRINCIPAL (Limpieza de strings para evitar fallos) ---
st.sidebar.write(f"👋 Bienvenid@, **{st.session_state.u_name}**")
st.sidebar.divider()
target = st.sidebar.number_input("🎯 Meta Utilidad ($)", value=5000000, step=500000)

opciones = ["📊 Dashboard", "🚐 Flota", "💸 Gastos", "💰 Ventas", "📑 Hoja de Vida", "⚙️ Tarifas", "⚙️ Usuarios"]
menu = st.sidebar.selectbox("📂 SELECCIONE UN MÓDULO", opciones)

if st.sidebar.button("🚪 CERRAR SESIÓN"):
    st.session_state.logged_in = False; st.rerun()

conn = conectar_db()
if not conn: st.stop()

# --- 📊 LÓGICA DE MÓDULOS ---

if menu == "📊 Dashboard":
    st.title("📊 Tablero de Eficiencia")
    # Cargamos datos para el resumen de la imagen
    df_v_all = pd.read_sql("SELECT fecha, valor_viaje as monto FROM ventas", conn)
    df_g_all = pd.read_sql("SELECT fecha, monto FROM gastos", conn)
    v_act = pd.read_sql("SELECT COUNT(*) as count FROM vehiculos", conn).iloc[0]['count']
    
    # Métricas de cabecera
    c1, c2, c3 = st.columns(3)
    c1.metric("📦 Vehículos Activos", v_act)
    c2.metric("📉 Egresos (Gastos)", f"$ {df_g_all['monto'].sum():,.0f}")
    c3.metric("📈 Ingresos (Ventas)", f"$ {df_v_all['monto'].sum():,.0f}")

    st.subheader("📅 Totales por Mes")
    if not df_v_all.empty or not df_g_all.empty:
        df_v_all['fecha'] = pd.to_datetime(df_v_all['fecha'])
        df_g_all['fecha'] = pd.to_datetime(df_g_all['fecha'])
        v_m = df_v_all.groupby(df_v_all['fecha'].dt.to_period('M'))['monto'].sum().reset_index()
        g_m = df_g_all.groupby(df_g_all['fecha'].dt.to_period('M'))['monto'].sum().reset_index()
        res = pd.merge(v_m, g_m, on='fecha', how='outer', suffixes=('_v', '_g')).fillna(0)
        res['Utilidad'] = res['monto_v'] - res['monto_g']
        res['Mes'] = res['fecha'].astype(str)
        st.table(res[['Mes', 'monto_v', 'monto_g', 'Utilidad']].rename(columns={'monto_v':'Ingresos', 'monto_g':'Gastos'}).style.format("$ {:,.0f}", subset=['Ingresos', 'Gastos', 'Utilidad']))
        
        utilidad_total = res['Utilidad'].sum()
        st.info(f"### 🚀 Utilidad Neta Actual: $ {utilidad_total:,.0f}")
        if utilidad_total >= target: st.balloons()
    else: st.info("No hay datos para el resumen mensual.")

elif menu == "🚐 Flota":
    st.title("🚐 Administración de Vehículos")
    with st.form("f_f"):
        p = st.text_input("Placa").upper(); m = st.text_input("Marca"); mod = st.text_input("Modelo"); cond = st.text_input("Conductor")
        if st.form_submit_button("➕ Añadir"):
            cur = conn.cursor(); cur.execute("INSERT INTO vehiculos (placa, marca, modelo, conductor) VALUES (%s,%s,%s,%s)", (p, m, mod, cond))
            conn.commit(); st.success("Vehículo añadido"); st.rerun()
    st.dataframe(pd.read_sql("SELECT * FROM vehiculos", conn), use_container_width=True, hide_index=True)

elif menu == "💸 Gastos":
    st.title("💸 Registro de Gastos")
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    tab1, tab2 = st.tabs(["📝 Registro", "✏️ Gestionar"])
    with tab1:
        with st.form("f_g"):
            v_sel = st.selectbox("Vehículo", v_data['placa'] if not v_data.empty else [])
            tipo = st.selectbox("Concepto", ["Combustible", "Peaje", "Mantenimiento", "Otros"])
            monto = st.number_input("Valor", min_value=0); fecha = st.date_input("Fecha"); det = st.text_input("Nota")
            if st.form_submit_button("💾 Guardar"):
                v_id = v_data[v_data['placa'] == v_sel]['id'].values[0]
                cur = conn.cursor(); cur.execute("INSERT INTO gastos (vehiculo_id, tipo_gasto, monto, fecha, detalle) VALUES (%s,%s,%s,%s,%s)", (int(v_id), tipo, monto, fecha, det))
                conn.commit(); st.success("Gasto guardado"); st.rerun()
    with tab2:
        df_g = pd.read_sql("SELECT g.id, g.fecha, v.placa, g.tipo_gasto, g.monto, g.detalle FROM gastos g JOIN vehiculos v ON g.vehiculo_id = v.id ORDER BY g.fecha DESC", conn)
        sel = st.dataframe(df_g, use_container_width=True, on_select="rerun", selection_mode="single-row", hide_index=True)
        if len(sel.selection.rows) > 0:
            row = df_g.iloc[sel.selection.rows[0]]
            if st.button("🗑️ Eliminar Seleccionado"):
                cur = conn.cursor(); cur.execute("DELETE FROM gastos WHERE id=%s", (int(row['id']),)); conn.commit(); st.rerun()

elif menu == "💰 Ventas":
    st.title("💰 Control de Ingresos")
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    t_data = pd.read_sql("SELECT servicio, precio_unidad FROM tarifario", conn)
    with st.form("f_v"):
        v_sel = st.selectbox("Vehículo", v_data['placa'] if not v_data.empty else [])
        s_sel = st.selectbox("Servicio", t_data['servicio'].tolist() if not t_data.empty else [])
        cant = st.number_input("Cantidad", min_value=1); fec = st.date_input("Fecha"); desc = st.text_area("Descripción")
        if st.form_submit_button("💰 Registrar"):
            v_id = v_data[v_data['placa'] == v_sel]['id'].values[0]
            val_u = t_data[t_data['servicio'] == s_sel]['precio_unidad'].values[0]
            total = float(cant * val_u)
            cur = conn.cursor(); cur.execute("INSERT INTO ventas (vehiculo_id, cliente, valor_viaje, fecha, descripcion, cantidad) VALUES (%s,%s,%s,%s,%s,%s)", (int(v_id), s_sel, total, fec, desc, int(cant)))
            conn.commit(); st.success(f"Registrado por ${total:,.0f}"); st.rerun()
    st.dataframe(pd.read_sql("SELECT s.fecha, v.placa, s.cliente, s.valor_viaje FROM ventas s JOIN vehiculos v ON s.vehiculo_id = v.id ORDER BY s.fecha DESC", conn), use_container_width=True, hide_index=True)

# --- VENTANA HOJA DE VIDA (RE-ACTIVADA) ---
elif menu == "📑 Hoja de Vida":
    st.title("📑 Documentación y Vencimientos")
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    with st.expander("📅 Actualizar Fechas de Vencimiento"):
        with st.form("f_hv"):
            v_sel = st.selectbox("Vehículo", v_data['placa']); v_id = v_data[v_data['placa'] == v_sel]['id'].values[0]
            c1, c2 = st.columns(2)
            s_v = c1.date_input("SOAT"); t_v = c1.date_input("Tecno"); p_v = c1.date_input("Preventivo")
            pc_v = c2.date_input("Póliza Contractual"); pe_v = c2.date_input("Póliza Extra"); ptr_v = c2.date_input("Todo Riesgo"); to_v = st.date_input("Tarjeta Operaciones")
            if st.form_submit_button("🔄 Actualizar"):
                cur = conn.cursor(); cur.execute('''INSERT INTO hoja_vida (vehiculo_id, soat_vence, tecno_vence, prev_vence, p_contractual, p_extracontractual, p_todoriesgo, t_operaciones) 
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (vehiculo_id) DO UPDATE SET soat_vence=EXCLUDED.soat_vence, tecno_vence=EXCLUDED.tecno_vence, prev_vence=EXCLUDED.prev_vence, p_contractual=EXCLUDED.p_contractual, p_extracontractual=EXCLUDED.p_extracontractual, p_todoriesgo=EXCLUDED.p_todoriesgo, t_operaciones=EXCLUDED.t_operaciones''', (int(v_id), s_v, t_v, p_v, pc_v, pe_v, ptr_v, to_v))
                conn.commit(); st.success("Datos actualizados"); st.rerun()
    
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

elif menu == "⚙️ Tarifas":
    st.title("⚙️ Tarifario")
    with st.form("f_t"):
        s = st.text_input("Servicio"); p = st.number_input("Precio ($)")
        if st.form_submit_button("Guardar"):
            cur = conn.cursor(); cur.execute("INSERT INTO tarifario (servicio, precio_unidad) VALUES (%s,%s) ON CONFLICT (servicio) DO UPDATE SET precio_unidad=EXCLUDED.precio_unidad", (s, p))
            conn.commit(); st.rerun()
    st.table(pd.read_sql("SELECT * FROM tarifario", conn))

elif menu == "⚙️ Usuarios" and st.session_state.u_rol == "admin":
    st.title("⚙️ Gestión de Usuarios")
    with st.form("f_u"):
        nom = st.text_input("Nombre"); u = st.text_input("Usuario"); c = st.text_input("Clave"); r = st.selectbox("Rol", ["admin", "vendedor"])
        if st.form_submit_button("👤 Crear"):
            cur = conn.cursor(); cur.execute("INSERT INTO usuarios (nombre, usuario, clave, rol) VALUES (%s,%s,%s,%s)", (nom, u, c, r))
            conn.commit(); st.success("Usuario creado satisfactoriamente")

conn.close()
