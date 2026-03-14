import streamlit as st
import psycopg2
import pandas as pd
import plotly.express as px
from datetime import datetime
import io

# --- 1. CONEXIÓN ---
DB_URL = "postgresql://neondb_owner:npg_c7Dkwlh1jzGQ@ep-lucky-shadow-ac1thtiq-pooler.sa-east-1.aws.neon.tech/neondb?sslmode=require"

def conectar_db():
    return psycopg2.connect(DB_URL)

def inicializar_fuerte():
    conn = conectar_db(); cur = conn.cursor()
    # 1. Tablas Base
    cur.execute('CREATE TABLE IF NOT EXISTS vehiculos (id SERIAL PRIMARY KEY, placa TEXT UNIQUE NOT NULL, marca TEXT, modelo TEXT, conductor TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS gastos (id SERIAL PRIMARY KEY, vehiculo_id INTEGER REFERENCES vehiculos(id), tipo_gasto TEXT, monto NUMERIC, fecha DATE, detalle TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS ventas (id SERIAL PRIMARY KEY, vehiculo_id INTEGER REFERENCES vehiculos(id), cliente TEXT, valor_viaje NUMERIC, fecha DATE, descripcion TEXT)')
    
    # 2. ELIMINAR Y RECREAR HOJA DE VIDA (Solo si da error)
    # Esto soluciona el DatabaseError de raíz
    try:
        cur.execute("SELECT prev_vence FROM hoja_vida LIMIT 1")
    except:
        conn.rollback()
        cur.execute("DROP TABLE IF EXISTS hoja_vida")
        cur.execute('''CREATE TABLE hoja_vida (
                        id SERIAL PRIMARY KEY, 
                        vehiculo_id INTEGER UNIQUE REFERENCES vehiculos(id), 
                        soat_inicio DATE, soat_vence DATE, 
                        tecno_inicio DATE, tecno_vence DATE, 
                        prev_inicio DATE, prev_vence DATE,
                        km_actual INTEGER, km_llantas_cambio INTEGER)''')
    
    conn.commit(); conn.close()

def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Reporte')
    return output.getvalue()

# --- 2. INICIO ---
st.set_page_config(page_title="C&E Eficiencias", layout="wide", page_icon="📈")
inicializar_fuerte()

st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stMetric { background-color: #ffffff; padding: 20px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1); border-left: 5px solid #007bff; }
    div.stButton > button:first-child { background-color: #007bff; color: white; border-radius: 5px; width: 100%; }
    </style>
    """, unsafe_allow_html=True)

if 'login' not in st.session_state: st.session_state.login = False

st.sidebar.markdown("## 🛡️ Acceso Seguro")
if not st.session_state.login:
    pwd = st.sidebar.text_input("Contraseña", type="password")
    if pwd == "Jacobo2026":
        st.session_state.login = True; st.rerun()
    else:
        st.title("🚐 C&E Eficiencias"); st.stop()

if st.sidebar.button("🚪 CERRAR SESIÓN"):
    st.session_state.login = False; st.rerun()

menu = st.sidebar.selectbox("📂 MÓDULOS", ["📊 Dashboard", "🚐 Flota", "📑 Hoja de Vida", "💸 Gastos", "💰 Ventas"])

# --- 📊 DASHBOARD ---
if menu == "📊 Dashboard":
    st.title("📊 Análisis Mensual")
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
        res.columns = ['Mes', 'Ingresos', 'Gastos']
        st.plotly_chart(px.bar(res, x='Mes', y=['Ingresos', 'Gastos'], barmode='group'), use_container_width=True)
        res_v = res.copy()
        for c in ['Ingresos', 'Gastos']: res_v[c] = res_v[c].apply(lambda x: f"$ {x:,.0f}".replace(",", "."))
        st.table(res_v)

# --- 🚐 FLOTA ---
elif menu == "🚐 Flota":
    st.title("🚐 Flota")
    with st.form("v"):
        placa = st.text_input("Placa").upper()
        marca = st.text_input("Marca"); mod = st.text_input("Modelo"); cond = st.text_input("Conductor")
        if st.form_submit_button("Guardar"):
            conn = conectar_db(); cur = conn.cursor()
            cur.execute("INSERT INTO vehiculos (placa, marca, modelo, conductor) VALUES (%s,%s,%s,%s)", (placa, marca, mod, cond))
            conn.commit(); conn.close(); st.success("Guardado"); st.rerun()
    conn = conectar_db(); st.table(pd.read_sql("SELECT placa, marca, modelo, conductor FROM vehiculos", conn)); conn.close()

# --- 📑 HOJA DE VIDA ---
elif menu == "📑 Hoja de Vida":
    st.title("📑 Alertas y Mantenimiento")
    conn = conectar_db(); v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    with st.expander("📝 Actualizar"):
        with st.form("h_v"):
            veh_sel = st.selectbox("Vehículo", v_data['placa'])
            v_id = int(v_data[v_data['placa'] == veh_sel]['id'].values[0])
            c1, c2, c3 = st.columns(3)
            s_i = c1.date_input("Inicio SOAT"); s_v = c1.date_input("Fin SOAT")
            t_i = c2.date_input("Inicio Tecno"); t_v = c2.date_input("Fin Tecno")
            p_i = c3.date_input("Inicio Prev."); p_v = c3.date_input("Fin Prev.")
            km_a = st.number_input("KM Actual", min_value=0); km_ll = st.number_input("KM Cambio Llantas", min_value=0)
            if st.form_submit_button("Actualizar"):
                cur = conn.cursor()
                cur.execute('''INSERT INTO hoja_vida (vehiculo_id, soat_inicio, soat_vence, tecno_inicio, tecno_vence, prev_inicio, prev_vence, km_actual, km_llantas_cambio) 
                               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (vehiculo_id) 
                               DO UPDATE SET soat_inicio=EXCLUDED.soat_inicio, soat_vence=EXCLUDED.soat_vence, tecno_inicio=EXCLUDED.tecno_inicio, tecno_vence=EXCLUDED.tecno_vence, prev_inicio=EXCLUDED.prev_inicio, prev_vence=EXCLUDED.prev_vence, km_actual=EXCLUDED.km_actual, km_llantas_cambio=EXCLUDED.km_llantas_cambio''', 
                            (v_id, s_i, s_v, t_i, t_v, p_i, p_v, km_a, km_ll))
                conn.commit(); st.success("Actualizado"); st.rerun()

    df_h = pd.read_sql('''SELECT v.placa, h.soat_vence, h.tecno_vence, h.prev_vence, h.km_actual, h.km_llantas_cambio FROM hoja_vida h JOIN vehiculos v ON h.vehiculo_id = v.id''', conn)
    hoy = datetime.now().date()
    for _, row in df_h.iterrows():
        st.subheader(f"🚗 {row['placa']}")
        cols = st.columns(4)
        for c, lbl, f in zip(cols, ["SOAT", "TECNO", "PREV"], [row['soat_vence'], row['tecno_vence'], row['prev_vence']]):
            if f:
                d = (f - hoy).days
                if d < 0: c.error(f"❌ {lbl} VENCIDO")
                elif d <= 15: c.warning(f"⚠️ {lbl} en {d} d")
                else: c.success(f"✅ {lbl} OK")
        st.divider()
    conn.close()

# --- 💸 GASTOS ---
elif menu == "💸 Gastos":
    st.title("💸 Gastos")
    conn = conectar_db(); v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    t1, t2 = st.tabs(["Registro", "Editar"])
    with t1:
        with st.form("g"):
            v_id = int(v_data[v_data['placa'] == st.selectbox("Vehículo", v_data['placa'])]['id'].values[0])
            mon = st.number_input("Monto", min_value=0); fec = st.date_input("Fecha"); det = st.text_input("Detalle")
            if st.form_submit_button("Guardar"):
                cur = conn.cursor(); cur.execute("INSERT INTO gastos (vehiculo_id, monto, fecha, detalle) VALUES (%s,%s,%s,%s)", (v_id, mon, fec, det))
                conn.commit(); st.success("Registrado"); st.rerun()
        df = pd.read_sql('SELECT g.fecha, v.placa, g.monto, g.detalle FROM gastos g JOIN vehiculos v ON g.vehiculo_id = v.id ORDER BY g.fecha DESC', conn)
        st.dataframe(df, use_container_width=True)
        st.download_button("📥 Excel", data=to_excel(df), file_name='gastos.xlsx')
    with t2:
        df_e = pd.read_sql("SELECT g.id, g.fecha, v.placa, g.monto, g.detalle FROM gastos g JOIN vehiculos v ON g.vehiculo_id = v.id ORDER BY g.id DESC LIMIT 10", conn)
        if not df_e.empty:
            sel = st.selectbox("Editar", df_e.apply(lambda r: f"ID:{r['id']} | {r['placa']}", axis=1))
            id_ed = int(sel.split("|")[0].split(":")[1].strip())
            with st.form("ed_g"):
                n_m = st.number_input("Nuevo Monto"); n_f = st.date_input("Nueva Fecha"); n_d = st.text_input("Nuevo Detalle")
                if st.form_submit_button("Actualizar"):
                    cur = conn.cursor(); cur.execute("UPDATE gastos SET monto=%s, fecha=%s, detalle=%s WHERE id=%s", (n_m, n_f, n_d, id_ed))
                    conn.commit(); st.warning("Actualizado"); st.rerun()
    conn.close()

# --- 💰 VENTAS ---
elif menu == "💰 Ventas":
    st.title("💰 Ventas")
    conn = conectar_db(); v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    t1, t2 = st.tabs(["Registro", "Editar"])
    with t1:
        with st.form("s"):
            v_id = int(v_data[v_data['placa'] == st.selectbox("Vehículo", v_data['placa'])]['id'].values[0])
            cli = st.text_input("Cliente"); val = st.number_input("Valor", min_value=0); fec = st.date_input("Fecha"); dsc = st.text_input("Descripción")
            if st.form_submit_button("Guardar"):
                cur = conn.cursor(); cur.execute("INSERT INTO ventas (vehiculo_id, cliente, valor_viaje, fecha, descripcion) VALUES (%s,%s,%s,%s,%s)", (v_id, cli, val, fec, dsc))
                conn.commit(); st.success("Registrado"); st.rerun()
        df = pd.read_sql('SELECT s.fecha, v.placa, s.cliente, s.valor_viaje, s.descripcion FROM ventas s JOIN vehiculos v ON s.vehiculo_id = v.id ORDER BY s.fecha DESC', conn)
        st.dataframe(df, use_container_width=True)
    with t2:
        df_e = pd.read_sql("SELECT s.id, s.fecha, v.placa, s.valor_viaje, s.descripcion FROM ventas s JOIN vehiculos v ON s.vehiculo_id = v.id ORDER BY s.id DESC LIMIT 10", conn)
        if not df_e.empty:
            sel = st.selectbox("Editar", df_e.apply(lambda r: f"ID:{r['id']} | {r['placa']}", axis=1))
            id_ed = int(sel.split("|")[0].split(":")[1].strip())
            with st.form("ed_s"):
                n_v = st.number_input("Nuevo Valor"); n_f = st.date_input("Nueva Fecha"); n_d = st.text_input("Nueva Desc.")
                if st.form_submit_button("Actualizar"):
                    cur = conn.cursor(); cur.execute("UPDATE ventas SET valor_viaje=%s, fecha=%s, descripcion=%s WHERE id=%s", (n_v, n_f, n_d, id_ed))
                    conn.commit(); st.warning("Actualizado"); st.rerun()
    conn.close()
