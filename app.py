import streamlit as st
import psycopg2
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
import io

# --- 1. CONFIGURACIÓN DE CONEXIÓN GLOBAL ---
DB_URL = "postgresql://neondb_owner:npg_c7Dkwlh1jzGQ@ep-lucky-shadow-ac1thtiq-pooler.sa-east-1.aws.neon.tech/neondb?sslmode=require"

def conectar_db():
    return psycopg2.connect(DB_URL)

def inicializar_tablas():
    conn = conectar_db(); cur = conn.cursor()
    # Vehículos
    cur.execute('CREATE TABLE IF NOT EXISTS vehiculos (id SERIAL PRIMARY KEY, placa TEXT UNIQUE NOT NULL, marca TEXT, modelo TEXT, conductor TEXT)')
    # Gastos
    cur.execute('CREATE TABLE IF NOT EXISTS gastos (id SERIAL PRIMARY KEY, vehiculo_id INTEGER REFERENCES vehiculos(id), tipo_gasto TEXT, monto NUMERIC, fecha DATE, detalle TEXT)')
    # Ventas
    cur.execute('CREATE TABLE IF NOT EXISTS ventas (id SERIAL PRIMARY KEY, vehiculo_id INTEGER REFERENCES vehiculos(id), cliente TEXT, valor_viaje NUMERIC, fecha DATE, descripcion TEXT)')
    # Hoja de Vida Actualizada
    cur.execute('''CREATE TABLE IF NOT EXISTS hoja_vida (
                    id SERIAL PRIMARY KEY, 
                    vehiculo_id INTEGER UNIQUE REFERENCES vehiculos(id), 
                    soat_inicio DATE, soat_vence DATE, 
                    tecno_inicio DATE, tecno_vence DATE, 
                    prev_inicio DATE, prev_vence DATE,
                    km_actual INTEGER, 
                    km_llantas_cambio INTEGER)''')
    conn.commit(); conn.close()

def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Reporte')
    return output.getvalue()

# --- 2. DISEÑO Y SEGURIDAD ---
st.set_page_config(page_title="C&E Eficiencias", layout="wide", page_icon="📈")
inicializar_tablas()

st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stMetric { background-color: #ffffff; padding: 20px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1); border-left: 5px solid #007bff; }
    div.stButton > button:first-child { background-color: #007bff; color: white; border-radius: 5px; width: 100%; }
    .st-emotion-cache-12w0qpk { background-color: #dc3545 !important; }
    </style>
    """, unsafe_allow_html=True)

if 'login' not in st.session_state: st.session_state.login = False

st.sidebar.markdown("## 🛡️ Acceso Seguro")
if not st.session_state.login:
    pwd = st.sidebar.text_input("Contraseña", type="password")
    if pwd == "Jacobo2026":
        st.session_state.login = True
        st.rerun()
    else:
        st.title("🚐 C&E Eficiencias"); st.info("Ingrese contraseña."); st.stop()

if st.sidebar.button("🚪 CERRAR SESIÓN"):
    st.session_state.login = False; st.rerun()

# --- 3. MENÚ ---
st.sidebar.divider()
menu = st.sidebar.selectbox("📂 MÓDULOS", ["📊 Dashboard Mensual", "🚐 Flota", "📑 Hoja de Vida", "💸 Gastos", "💰 Ventas"])

# --- 📊 1. DASHBOARD ---
if menu == "📊 Dashboard Mensual":
    st.title("📊 Análisis de Eficiencia")
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
        fig = px.bar(res, x='Mes', y=['Ingresos', 'Gastos'], barmode='group', color_discrete_map={'Ingresos': '#28a745', 'Gastos': '#dc3545'})
        st.plotly_chart(fig, use_container_width=True)
        res_v = res.copy()
        for c in ['Ingresos', 'Gastos']: res_v[c] = res_v[c].apply(lambda x: f"$ {x:,.0f}".replace(",", "."))
        st.table(res_v)

# --- 🚐 2. FLOTA ---
elif menu == "🚐 Flota":
    st.title("🚐 Flota de Vehículos")
    with st.expander("➕ Añadir Vehículo"):
        with st.form("v"):
            c1, c2 = st.columns(2)
            placa = c1.text_input("Placa").upper()
            marca = c1.text_input("Marca"); mod = c2.text_input("Modelo"); cond = c2.text_input("Conductor")
            if st.form_submit_button("Guardar"):
                conn = conectar_db(); cur = conn.cursor()
                cur.execute("INSERT INTO vehiculos (placa, marca, modelo, conductor) VALUES (%s,%s,%s,%s)", (placa, marca, mod, cond))
                conn.commit(); conn.close(); st.success("Guardado"); st.rerun()
    conn = conectar_db(); st.table(pd.read_sql("SELECT placa, marca, modelo, conductor FROM vehiculos", conn)); conn.close()

# --- 📑 3. HOJA DE VIDA (ACTUALIZADO CON PREVENTIVO Y FECHAS INICIO/FIN) ---
elif menu == "📑 Hoja de Vida":
    st.title("📑 Hoja de Vida y Alertas")
    conn = conectar_db(); v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    
    with st.expander("📝 Actualizar Documentación, Preventivos y KM"):
        with st.form("h_v"):
            veh_sel = st.selectbox("Vehículo", v_data['placa'])
            v_id = int(v_data[v_data['placa'] == veh_sel]['id'].values[0])
            st.markdown("### Vigencia de Documentos")
            c1, c2, c3 = st.columns(3)
            # SOAT
            c1.write("**SOAT**")
            s_i = c1.date_input("Fecha Inicio SOAT")
            s_v = c1.date_input("Fecha Fin SOAT")
            # TECNO
            c2.write("**Técnico-Mecánica**")
            t_i = c2.date_input("Fecha Inicio Tecno")
            t_v = c2.date_input("Fecha Fin Tecno")
            # PREVENTIVO
            c3.write("**Mantenimiento Preventivo**")
            p_i = c3.date_input("Fecha Inicio Preventivo")
            p_v = c3.date_input("Fecha Fin Preventivo")
            
            st.markdown("### Control de Kilometraje")
            ck1, ck2 = st.columns(2)
            km_a = ck1.number_input("Kilometraje Actual", min_value=0)
            km_ll = ck2.number_input("Próximo Cambio Llantas (KM)", min_value=0)
            
            if st.form_submit_button("Actualizar Hoja de Vida"):
                cur = conn.cursor()
                cur.execute('''INSERT INTO hoja_vida (vehiculo_id, soat_inicio, soat_vence, tecno_inicio, tecno_vence, prev_inicio, prev_vence, km_actual, km_llantas_cambio) 
                               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (vehiculo_id) 
                               DO UPDATE SET soat_inicio=EXCLUDED.soat_inicio, soat_vence=EXCLUDED.soat_vence, 
                               tecno_inicio=EXCLUDED.tecno_inicio, tecno_vence=EXCLUDED.tecno_vence,
                               prev_inicio=EXCLUDED.prev_inicio, prev_vence=EXCLUDED.prev_vence, 
                               km_actual=EXCLUDED.km_actual, km_llantas_cambio=EXCLUDED.km_llantas_cambio''', 
                            (v_id, s_i, s_v, t_i, t_v, p_i, p_v, km_a, km_ll))
                conn.commit(); st.success("Hoja de Vida Actualizada"); st.rerun()

    st.divider()
    df_h = pd.read_sql('''SELECT v.placa, h.soat_vence, h.tecno_vence, h.prev_vence, h.km_actual, h.km_llantas_cambio 
                          FROM hoja_vida h JOIN vehiculos v ON h.vehiculo_id = v.id''', conn)
    
    hoy = datetime.now().date()
    for index, row in df_h.iterrows():
        st.subheader(f"🚗 Vehículo: {row['placa']}")
        col1, col2, col3, col4 = st.columns(4)
        
        # Alerta SOAT
        d_s = (row['soat_vence'] - hoy).days
        if d_s < 0: col1.error(f"❌ SOAT VENCIDO\n({row['soat_vence']})")
        elif d_s <= 15: col1.warning(f"⚠️ SOAT por vencer\n({d_s} días)")
        else: col1.success(f"✅ SOAT Al día\n({row['soat_vence']})")
        
        # Alerta Tecno
        d_t = (row['tecno_vence'] - hoy).days
        if d_t < 0: col2.error(f"❌ TECNO VENCIDA\n({row['tecno_vence']})")
        elif d_t <= 15: col2.warning(f"⚠️ TECNO por vencer\n({d_t} días)")
        else: col2.success(f"✅ TECNO Al día\n({row['tecno_vence']})")
        
        # Alerta Preventivo
        d_p = (row['prev_vence'] - hoy).days
        if d_p < 0: col3.error(f"❌ PREVENTIVO VENCIDO\n({row['prev_vence']})")
        elif d_p <= 15: col3.warning(f"⚠️ PREVENTIVO por vencer\n({d_p} días)")
        else: col3.success(f"✅ PREVENTIVO Al día\n({row['prev_vence']})")
        
        # Alerta Llantas
        km_r = row['km_llantas_cambio'] - row['km_actual']
        if km_r <= 0: col4.error(f"❌ CAMBIO LLANTAS\n(Excedido {abs(km_r)} KM)")
        elif km_r <= 1000: col4.warning(f"⚠️ Llantas en {km_r} KM")
        else: col4.success(f"✅ Llantas OK\n({km_r} KM faltantes)")
    conn.close()

# --- 💸 4. GASTOS ---
elif menu == "💸 Gastos":
    st.title("💸 Registro de Gastos")
    conn = conectar_db(); v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    t1, t2 = st.tabs(["📝 Registro", "✏️ Editar"])
    with t1:
        with st.form("g"):
            c1, c2 = st.columns(2)
            v_id = int(v_data[v_data['placa'] == c1.selectbox("Vehículo", v_data['placa'])]['id'].values[0])
            tipo = c1.selectbox("Concepto", ["Combustible", "Peaje", "Mantenimiento", "Lavada", "Otros"])
            mon = c2.number_input("Monto", min_value=0); fec = c2.date_input("Fecha"); det = st.text_input("Detalle")
            if st.form_submit_button("Guardar"):
                cur = conn.cursor(); cur.execute("INSERT INTO gastos (vehiculo_id, tipo_gasto, monto, fecha, detalle) VALUES (%s,%s,%s,%s,%s)", (v_id, tipo, mon, fec, det))
                conn.commit(); st.success("Registrado"); st.rerun()
        df_l = pd.read_sql('SELECT g.fecha, v.placa, g.tipo_gasto, g.monto, g.detalle FROM gastos g JOIN vehiculos v ON g.vehiculo_id = v.id ORDER BY g.fecha DESC', conn)
        df_v = df_l.copy(); df_v["monto"] = df_v["monto"].apply(lambda x: f"$ {x:,.0f}".replace(",", "."))
        st.dataframe(df_v, use_container_width=True)
    with t2:
        df_e = pd.read_sql("SELECT g.id, g.fecha, v.placa, g.monto FROM gastos g JOIN vehiculos v ON g.vehiculo_id = v.id ORDER BY g.id DESC LIMIT 10", conn)
        if not df_e.empty:
            sel = st.selectbox("Gasto a editar", df_e.apply(lambda r: f"ID:{r['id']} | {r['placa']} | {r['fecha']}", axis=1))
            id_ed = int(sel.split("|")[0].split(":")[1].strip())
            with st.form("ed_g"):
                n_m = st.number_input("Nuevo Monto", min_value=0); n_f = st.date_input("Nueva Fecha"); n_d = st.text_input("Nuevo Detalle")
                if st.form_submit_button("Actualizar"):
                    cur = conn.cursor(); cur.execute("UPDATE gastos SET monto=%s, fecha=%s, detalle=%s WHERE id=%s", (n_m, n_f, n_d, id_ed))
                    conn.commit(); st.warning("Actualizado"); st.rerun()
    conn.close()

# --- 💰 5. VENTAS ---
elif menu == "💰 Ventas":
    st.title("💰 Registro de Ventas")
    conn = conectar_db(); v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    t1, t2 = st.tabs(["📝 Registro", "✏️ Editar"])
    with t1:
        with st.form("s"):
            c1, c2 = st.columns(2)
            v_id = int(v_data[v_data['placa'] == c1.selectbox("Vehículo", v_data['placa'])]['id'].values[0])
            cli = c1.text_input("Cliente"); val = c2.number_input("Valor", min_value=0); fec = c2.date_input("Fecha"); desc = st.text_input("Descripción")
            if st.form_submit_button("Guardar"):
                cur = conn.cursor(); cur.execute("INSERT INTO ventas (vehiculo_id, cliente, valor_viaje, fecha, descripcion) VALUES (%s,%s,%s,%s,%s)", (v_id, cli, val, fec, desc))
                conn.commit(); st.success("Registrado"); st.rerun()
        df_l = pd.read_sql('SELECT s.fecha, v.placa, s.cliente, s.valor_viaje, s.descripcion FROM ventas s JOIN vehiculos v ON s.vehiculo_id = v.id ORDER BY s.fecha DESC', conn)
        df_v = df_l.copy(); df_v["valor_viaje"] = df_v["valor_viaje"].apply(lambda x: f"$ {x:,.0f}".replace(",", "."))
        st.dataframe(df_v, use_container_width=True)
    with t2:
        df_e = pd.read_sql("SELECT s.id, s.fecha, v.placa, s.valor_viaje FROM ventas s JOIN vehiculos v ON s.vehiculo_id = v.id ORDER BY s.id DESC LIMIT 10", conn)
        if not df_e.empty:
            sel = st.selectbox("Venta a editar", df_e.apply(lambda r: f"ID:{r['id']} | {r['placa']} | {r['fecha']}", axis=1))
            id_ed = int(sel.split("|")[0].split(":")[1].strip())
            with st.form("ed_s"):
                n_v = st.number_input("Nuevo Valor", min_value=0); n_f = st.date_input("Nueva Fecha"); n_d = st.text_input("Nueva Descripción")
                if st.form_submit_button("Actualizar"):
                    cur = conn.cursor(); cur.execute("UPDATE ventas SET valor_viaje=%s, fecha=%s, descripcion=%s WHERE id=%s", (n_v, n_f, n_d, id_ed))
                    conn.commit(); st.warning("Actualizado"); st.rerun()
    conn.close()
