import streamlit as st
import psycopg2
import pandas as pd
from datetime import datetime
import io

# --- 1. CONEXIÓN Y REPARACIÓN ---
DB_URL = "postgresql://neondb_owner:npg_c7Dkwlh1jzGQ@ep-lucky-shadow-ac1thtiq-pooler.sa-east-1.aws.neon.tech/neondb?sslmode=require"

def conectar_db():
    return psycopg2.connect(DB_URL)

def inicializar_db():
    conn = conectar_db(); cur = conn.cursor()
    cur.execute('CREATE TABLE IF NOT EXISTS vehiculos (id SERIAL PRIMARY KEY, placa TEXT UNIQUE NOT NULL, marca TEXT, modelo TEXT, conductor TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS gastos (id SERIAL PRIMARY KEY, vehiculo_id INTEGER REFERENCES vehiculos(id), tipo_gasto TEXT, monto NUMERIC, fecha DATE, detalle TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS ventas (id SERIAL PRIMARY KEY, vehiculo_id INTEGER REFERENCES vehiculos(id), cliente TEXT, valor_viaje NUMERIC, fecha DATE, descripcion TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS hoja_vida (id SERIAL PRIMARY KEY, vehiculo_id INTEGER UNIQUE REFERENCES vehiculos(id), soat_inicio DATE, soat_vence DATE, tecno_inicio DATE, tecno_vence DATE, prev_inicio DATE, prev_vence DATE, km_actual INTEGER, km_llantas_cambio INTEGER)')
    
    # Reparación de columnas por si faltan
    try: cur.execute("ALTER TABLE ventas ADD COLUMN descripcion TEXT")
    except: conn.rollback()
    try: cur.execute("ALTER TABLE gastos ADD COLUMN tipo_gasto TEXT")
    except: conn.rollback()
    
    conn.commit(); conn.close()

def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Reporte')
    return output.getvalue()

# --- 2. DISEÑO ---
st.set_page_config(page_title="C&E Eficiencias", layout="wide", page_icon="📊")
inicializar_db()

st.markdown("""<style>
    .main { background-color: #f5f7f9; }
    .stMetric { background-color: #ffffff; padding: 20px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1); border-left: 5px solid #007bff; }
    div.stButton > button:first-child { background-color: #007bff; color: white; border-radius: 5px; width: 100%; }
    </style>""", unsafe_allow_html=True)

if 'login' not in st.session_state: st.session_state.login = False

# --- ACCESO ---
st.sidebar.title("🔐 Acceso")
if not st.session_state.login:
    pwd = st.sidebar.text_input("Contraseña", type="password")
    if st.sidebar.button("Ingresar"):
        if pwd == "Jacobo2026":
            st.session_state.login = True; st.rerun()
        else: st.sidebar.error("Contraseña incorrecta")
    st.stop()

if st.sidebar.button("🚪 CERRAR SESIÓN"):
    st.session_state.login = False; st.rerun()

menu = st.sidebar.selectbox("📂 MÓDULOS", ["📊 Reporte Mensual", "🚐 Flota", "📑 Hoja de Vida", "💸 Gastos", "💰 Ventas"])

# --- 📊 1. DASHBOARD (SÓLO TABLAS) ---
if menu == "📊 Reporte Mensual":
    st.title("📊 Resumen Consolidado")
    conn = conectar_db()
    df_g = pd.read_sql("SELECT monto, fecha FROM gastos", conn)
    df_s = pd.read_sql("SELECT valor_viaje, fecha FROM ventas", conn)
    conn.close()

    if not df_g.empty or not df_s.empty:
        df_g['Mes'] = pd.to_datetime(df_g['fecha']).dt.strftime('%Y-%m')
        df_s['Mes'] = pd.to_datetime(df_s['fecha']).dt.strftime('%Y-%m')
        
        g_m = df_g.groupby('Mes')['monto'].sum().reset_index()
        s_m = df_s.groupby('Mes')['valor_viaje'].sum().reset_index()
        res = pd.merge(s_m, g_m, on='Mes', how='outer').fillna(0)
        res.columns = ['Mes', 'Ventas', 'Gastos']
        res['Utilidad'] = res['Ventas'] - res['Gastos']
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Ventas Totales", f"$ {res['Ventas'].sum():,.0f}".replace(",", "."))
        c2.metric("Gastos Totales", f"$ {res['Gastos'].sum():,.0f}".replace(",", "."))
        c3.metric("Utilidad Total", f"$ {res['Utilidad'].sum():,.0f}".replace(",", "."))

        st.divider()
        st.subheader("🗓️ Movimientos por Mes")
        res_v = res.copy().sort_values(by='Mes', ascending=False)
        for c in ['Ventas', 'Gastos', 'Utilidad']:
            res_v[c] = res_v[c].apply(lambda x: f"$ {x:,.0f}".replace(",", "."))
        st.table(res_v)
    else:
        st.info("Sin datos registrados.")

# --- 🚐 2. FLOTA ---
elif menu == "🚐 Flota":
    st.title("🚐 Flota de Vehículos")
    with st.form("v"):
        c1, c2 = st.columns(2)
        placa = c1.text_input("Placa").upper()
        marca = c1.text_input("Marca"); mod = c2.text_input("Modelo"); cond = c2.text_input("Conductor")
        if st.form_submit_button("Guardar"):
            conn = conectar_db(); cur = conn.cursor()
            cur.execute("INSERT INTO vehiculos (placa, marca, modelo, conductor) VALUES (%s,%s,%s,%s)", (placa, marca, mod, cond))
            conn.commit(); conn.close(); st.success("Guardado"); st.rerun()
    conn = conectar_db(); st.table(pd.read_sql("SELECT placa, marca, modelo, conductor FROM vehiculos", conn)); conn.close()

# --- 📑 3. HOJA DE VIDA ---
elif menu == "📑 Hoja de Vida":
    st.title("📑 Alertas")
    conn = conectar_db(); v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    with st.expander("📝 Actualizar"):
        with st.form("h_v"):
            v_id = int(v_data[v_data['placa'] == st.selectbox("Vehículo", v_data['placa'])]['id'].values[0])
            c1, c2, c3 = st.columns(3)
            s_v = c1.date_input("Fin SOAT"); t_v = c2.date_input("Fin Tecno"); p_v = c3.date_input("Fin Prev.")
            if st.form_submit_button("Actualizar"):
                cur = conn.cursor(); cur.execute('''INSERT INTO hoja_vida (vehiculo_id, soat_vence, tecno_vence, prev_vence) 
                VALUES (%s,%s,%s,%s) ON CONFLICT (vehiculo_id) DO UPDATE SET soat_vence=EXCLUDED.soat_vence, tecno_vence=EXCLUDED.tecno_vence, prev_vence=EXCLUDED.prev_vence''', (v_id, s_v, t_v, p_v))
                conn.commit(); st.success("Actualizado"); st.rerun()
    df_h = pd.read_sql('''SELECT v.placa, h.soat_vence, h.tecno_vence, h.prev_vence FROM hoja_vida h JOIN vehiculos v ON h.vehiculo_id = v.id''', conn)
    hoy = datetime.now().date()
    for _, row in df_h.iterrows():
        st.subheader(f"🚗 {row['placa']}")
        col1, col2, col3 = st.columns(3)
        for c, lbl, f in zip([col1, col2, col3], ["SOAT", "TECNO", "PREVENTIVO"], [row['soat_vence'], row['tecno_vence'], row['prev_vence']]):
            if f:
                d = (f - hoy).days
                if d < 0: c.error(f"❌ {lbl} VENCIDO")
                elif d <= 15: c.warning(f"⚠️ {lbl} en {d} d")
                else: c.success(f"✅ {lbl} OK")
    conn.close()

# --- 💸 4. GASTOS (CON FILTRO DETALLADO Y EDICIÓN COMPLETA) ---
elif menu == "💸 Gastos":
    st.title("💸 Gestión de Gastos")
    conn = conectar_db()
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    
    # Obtener historial completo para el filtro
    df_full = pd.read_sql('''SELECT g.id, g.fecha, v.placa, g.tipo_gasto, g.monto, g.detalle 
                             FROM gastos g JOIN vehiculos v ON g.vehiculo_id = v.id ORDER BY g.fecha DESC''', conn)
    df_full['Mes'] = pd.to_datetime(df_full['fecha']).dt.strftime('%Y-%m')
    
    # FILTRO POR MES
    meses = sorted(df_full['Mes'].unique().tolist(), reverse=True)
    mes_sel = st.selectbox("📅 Seleccione Mes para ver detalle y subtotales:", meses if meses else ["Sin datos"])
    
    df_mes = df_full[df_full['Mes'] == mes_sel]

    # SUBTOTALES POR CONCEPTO
    if not df_mes.empty:
        st.subheader(f"💰 Subtotales por Concepto - {mes_sel}")
        sub = df_mes.groupby('tipo_gasto')['monto'].sum().reset_index()
        sub['monto'] = sub['monto'].apply(lambda x: f"$ {x:,.0f}".replace(",", "."))
        st.table(sub)

    t1, t2 = st.tabs(["📝 Registro", "✏️ Editar Gasto"])
    
    with t1:
        with st.form("g"):
            c1, c2 = st.columns(2)
            v_id = int(v_data[v_data['placa'] == c1.selectbox("Vehículo", v_data['placa'])]['id'].values[0])
            tipo = c1.selectbox("Concepto", ["Combustible", "Peaje", "Mantenimiento", "Lavada", "Viáticos", "Otros"])
            mon = c2.number_input("Monto", min_value=0); fec = c2.date_input("Fecha"); det = st.text_input("Detalle")
            if st.form_submit_button("Guardar"):
                cur = conn.cursor(); cur.execute("INSERT INTO gastos (vehiculo_id, tipo_gasto, monto, fecha, detalle) VALUES (%s,%s,%s,%s,%s)", (v_id, tipo, mon, fec, det))
                conn.commit(); st.success("Gasto registrado"); st.rerun()
        
        # TABLA DETALLADA DEL MES
        st.subheader(f"📋 Listado Detallado - {mes_sel}")
        df_view = df_mes.copy()
        df_view["monto"] = df_view["monto"].apply(lambda x: f"$ {x:,.0f}".replace(",", "."))
        st.dataframe(df_view[['fecha', 'placa', 'tipo_gasto', 'monto', 'detalle']], use_container_width=True)
        st.download_button("📥 Excel", data=to_excel(df_mes), file_name=f'gastos_{mes_sel}.xlsx')

    with t2:
        if not df_full.empty:
            sel = st.selectbox("Elija el gasto a corregir:", df_full.apply(lambda r: f"ID:{r['id']} | {r['placa']} | {r['tipo_gasto']} | $ {r['monto']:,.0f}", axis=1))
            id_ed = int(sel.split("|")[0].split(":")[1].strip())
            reg = df_full[df_full['id'] == id_ed].iloc[0]
            
            st.info(f"**Editando:** {reg['tipo_gasto']} | {reg['placa']} | Detalle actual: {reg['detalle']}")
            
            with st.form("ed_g"):
                n_m = st.number_input("Monto", value=float(reg['monto']))
                n_f = st.date_input("Fecha", value=reg['fecha'])
                n_t = st.selectbox("Concepto", ["Combustible", "Peaje", "Mantenimiento", "Lavada", "Viáticos", "Otros"], index=["Combustible", "Peaje", "Mantenimiento", "Lavada", "Viáticos", "Otros"].index(reg['tipo_gasto']))
                n_d = st.text_input("Detalle", value=reg['detalle'])
                if st.form_submit_button("Actualizar Todo"):
                    cur = conn.cursor(); cur.execute("UPDATE gastos SET monto=%s, fecha=%s, tipo_gasto=%s, detalle=%s WHERE id=%s", (n_m, n_f, n_t, n_d, id_ed))
                    conn.commit(); st.success("Gasto actualizado"); st.rerun()
    conn.close()

# --- 💰 5. VENTAS (CON FILTRO DETALLADO Y EDICIÓN COMPLETA) ---
elif menu == "💰 Ventas":
    st.title("💰 Gestión de Ventas")
    conn = conectar_db(); v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    
    df_s_full = pd.read_sql('''SELECT s.id, s.fecha, v.placa, s.cliente, s.valor_viaje, s.descripcion 
                               FROM ventas s JOIN vehiculos v ON s.vehiculo_id = v.id ORDER BY s.fecha DESC''', conn)
    df_s_full['Mes'] = pd.to_datetime(df_s_full['fecha']).dt.strftime('%Y-%m')
    
    meses_s = sorted(df_s_full['Mes'].unique().tolist(), reverse=True)
    mes_sel_s = st.selectbox("📅 Seleccione Mes para ver ventas:", meses_s if meses_s else ["Sin datos"])
    df_mes_s = df_s_full[df_s_full['Mes'] == mes_sel_s]

    t1, t2 = st.tabs(["📝 Registro", "✏️ Editar Venta"])
    
    with t1:
        with st.form("s"):
            c1, c2 = st.columns(2)
            v_id = int(v_data[v_data['placa'] == st.selectbox("Vehículo", v_data['placa'])]['id'].values[0])
            cli = c1.text_input("Cliente"); val = c2.number_input("Valor", min_value=0); fec = c2.date_input("Fecha"); dsc = st.text_input("Descripción")
            if st.form_submit_button("Guardar"):
                cur = conn.cursor(); cur.execute("INSERT INTO ventas (vehiculo_id, cliente, valor_viaje, fecha, descripcion) VALUES (%s,%s,%s,%s,%s)", (v_id, cli, val, fec, dsc))
                conn.commit(); st.success("Registrado"); st.rerun()
        
        st.subheader(f"📋 Listado de Ventas - {mes_sel_s}")
        df_v_s = df_mes_s.copy()
        df_v_s["valor_viaje"] = df_v_s["valor_viaje"].apply(lambda x: f"$ {x:,.0f}".replace(",", "."))
        st.dataframe(df_v_s[['fecha', 'placa', 'cliente', 'valor_viaje', 'descripcion']], use_container_width=True)

    with t2:
        if not df_s_full.empty:
            sel_s = st.selectbox("Elija la venta a corregir:", df_s_full.apply(lambda r: f"ID:{r['id']} | {r['placa']} | {r['cliente']} | $ {r['valor_viaje']:,.0f}", axis=1))
            id_ed_s = int(sel_s.split("|")[0].split(":")[1].strip())
            reg_s = df_s_full[df_s_full['id'] == id_ed_s].iloc[0]
            
            st.info(f"**Editando:** {reg_s['placa']} | Cliente: {reg_s['cliente']} | Descripción actual: {reg_s['descripcion']}")
            
            with st.form("ed_s"):
                n_v = st.number_input("Valor", value=float(reg_s['valor_viaje']))
                n_fs = st.date_input("Fecha", value=reg_s['fecha'])
                n_cli = st.text_input("Cliente", value=reg_s['cliente'])
                n_ds = st.text_input("Descripción", value=reg_s['descripcion'])
                if st.form_submit_button("Actualizar Todo"):
                    cur = conn.cursor(); cur.execute("UPDATE ventas SET valor_viaje=%s, fecha=%s, cliente=%s, descripcion=%s WHERE id=%s", (n_v, n_fs, n_cli, n_ds, id_ed_s))
                    conn.commit(); st.success("Venta actualizada"); st.rerun()
    conn.close()
