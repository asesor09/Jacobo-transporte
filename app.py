import streamlit as st
import psycopg2
import pandas as pd
import plotly.express as px
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

# --- 2. CONFIGURACIÓN ---
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

menu = st.sidebar.selectbox("📂 MÓDULOS", ["📊 Dashboard", "🚐 Flota", "📑 Hoja de Vida", "💸 Gastos", "💰 Ventas"])

# --- 📊 1. DASHBOARD ---
if menu == "📊 Dashboard":
    st.title("📊 Análisis de Eficiencia")
    conn = conectar_db()
    df_g = pd.read_sql("SELECT monto, fecha FROM gastos", conn)
    df_s = pd.read_sql("SELECT valor_viaje, fecha FROM ventas", conn)
    conn.close()

    if not df_g.empty or not df_s.empty:
        df_g['Mes'] = pd.to_datetime(df_g['fecha']).dt.strftime('%Y-%m')
        df_s['Mes'] = pd.to_datetime(df_s['fecha']).dt.strftime('%Y-%m')
        
        # Filtro de Mes Global
        meses_disp = sorted(list(set(df_g['Mes'].tolist() + df_s['Mes'].tolist())), reverse=True)
        mes_filtro = st.selectbox("Seleccione Mes para el reporte", ["Todos"] + meses_disp)

        if mes_filtro != "Todos":
            df_g = df_g[df_g['Mes'] == mes_filtro]
            df_s = df_s[df_s['Mes'] == mes_filtro]

        g_m = df_g.groupby('Mes')['monto'].sum().reset_index()
        s_m = df_s.groupby('Mes')['valor_viaje'].sum().reset_index()
        resumen = pd.merge(s_m, g_m, on='Mes', how='outer').fillna(0)
        resumen.columns = ['Mes', 'Ventas', 'Gastos']
        resumen['Utilidad'] = resumen['Ventas'] - resumen['Gastos']
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Ventas", f"$ {resumen['Ventas'].sum():,.0f}".replace(",", "."))
        c2.metric("Gastos", f"$ {resumen['Gastos'].sum():,.0f}".replace(",", "."))
        c3.metric("Utilidad", f"$ {resumen['Utilidad'].sum():,.0f}".replace(",", "."), delta=f"$ {resumen['Utilidad'].sum():,.0f}")

        st.plotly_chart(px.bar(resumen, x='Mes', y=['Ventas', 'Gastos'], barmode='group', color_discrete_map={'Ventas':'#28a745','Gastos':'#dc3545'}), use_container_width=True)
        
        res_v = resumen.copy()
        for c in ['Ventas', 'Gastos', 'Utilidad']: res_v[c] = res_v[c].apply(lambda x: f"$ {x:,.0f}".replace(",", "."))
        st.table(res_v)
    else:
        st.info("Registre datos para ver el balance.")

# --- 🚐 2. FLOTA ---
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

# --- 📑 3. HOJA DE VIDA ---
elif menu == "📑 Hoja de Vida":
    st.title("📑 Alertas")
    conn = conectar_db(); v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    with st.expander("📝 Actualizar"):
        with st.form("h_v"):
            v_id = int(v_data[v_data['placa'] == st.selectbox("Vehículo", v_data['placa'])]['id'].values[0])
            c1, c2, c3 = st.columns(3)
            s_i = c1.date_input("Inicio SOAT"); s_v = c1.date_input("Fin SOAT")
            t_i = c2.date_input("Inicio Tecno"); t_v = c2.date_input("Fin Tecno")
            p_i = c3.date_input("Inicio Prev."); p_v = c3.date_input("Fin Prev.")
            if st.form_submit_button("Actualizar"):
                cur = conn.cursor(); cur.execute('''INSERT INTO hoja_vida (vehiculo_id, soat_inicio, soat_vence, tecno_inicio, tecno_vence, prev_inicio, prev_vence) 
                VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (vehiculo_id) DO UPDATE SET soat_vence=EXCLUDED.soat_vence, tecno_vence=EXCLUDED.tecno_vence, prev_vence=EXCLUDED.prev_vence''', (v_id, s_i, s_v, t_i, t_v, p_i, p_v))
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

# --- 💸 4. GASTOS ---
elif menu == "💸 Gastos":
    st.title("💸 Control de Gastos")
    conn = conectar_db()
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    
    # --- FILTRO POR MES ---
    df_full_g = pd.read_sql('SELECT g.fecha, v.placa, g.tipo_gasto, g.monto, g.detalle FROM gastos g JOIN vehiculos v ON g.vehiculo_id = v.id ORDER BY g.fecha DESC', conn)
    df_full_g['Mes'] = pd.to_datetime(df_full_g['fecha']).dt.strftime('%Y-%m')
    meses_g = sorted(df_full_g['Mes'].unique().tolist(), reverse=True)
    mes_g = st.selectbox("Filtrar Historial por Mes", ["Todos"] + meses_g)
    
    df_g_filtrado = df_full_g if mes_g == "Todos" else df_full_g[df_full_g['Mes'] == mes_g]

    # --- SUBTOTALES POR CONCEPTO ---
    st.subheader(f"💰 Subtotales por Concepto ({mes_g})")
    sub_conceptos = df_g_filtrado.groupby('tipo_gasto')['monto'].sum().reset_index()
    sub_conceptos['Total'] = sub_conceptos['monto'].apply(lambda x: f"$ {x:,.0f}".replace(",", "."))
    st.table(sub_conceptos[['tipo_gasto', 'Total']])

    t1, t2 = st.tabs(["📝 Registro", "✏️ Editar"])
    with t1:
        with st.form("g"):
            c1, c2 = st.columns(2)
            v_id = int(v_data[v_data['placa'] == c1.selectbox("Vehículo", v_data['placa'])]['id'].values[0])
            tipo = c1.selectbox("Concepto (Tipo)", ["Combustible", "Peaje", "Mantenimiento", "Lavada", "Viáticos", "Otros"])
            mon = c2.number_input("Monto", min_value=0); fec = c2.date_input("Fecha"); det = st.text_input("Detalle Extra")
            if st.form_submit_button("Guardar Gasto"):
                cur = conn.cursor(); cur.execute("INSERT INTO gastos (vehiculo_id, tipo_gasto, monto, fecha, detalle) VALUES (%s,%s,%s,%s,%s)", (v_id, tipo, mon, fec, det))
                conn.commit(); st.success("Gasto Guardado"); st.rerun()
        
        df_visto = df_g_filtrado.copy()
        df_visto["monto"] = df_visto["monto"].apply(lambda x: f"$ {x:,.0f}".replace(",", "."))
        st.dataframe(df_visto[['fecha', 'placa', 'tipo_gasto', 'monto', 'detalle']], use_container_width=True)
        st.download_button("📥 Excel", data=to_excel(df_g_filtrado), file_name=f'gastos_{mes_g}.xlsx')
    
    with t2:
        df_edit = pd.read_sql("SELECT g.id, g.fecha, v.placa, g.tipo_gasto, g.monto, g.detalle FROM gastos g JOIN vehiculos v ON g.vehiculo_id = v.id ORDER BY g.id DESC LIMIT 15", conn)
        if not df_edit.empty:
            sel_g = st.selectbox("Seleccione Gasto a corregir", df_edit.apply(lambda r: f"ID:{r['id']} | {r['placa']} | {r['fecha']} | $ {r['monto']}", axis=1))
            id_ed = int(sel_g.split("|")[0].split(":")[1].strip())
            
            # --- INFO DE LO QUE SE VA A EDITAR ---
            item_ed = df_edit[df_edit['id'] == id_ed].iloc[0]
            st.warning(f"**Editando:** {item_ed['tipo_gasto']} de {item_ed['placa']} por $ {item_ed['monto']:,.0f} del {item_ed['fecha']}")

            with st.form("ed_g"):
                n_m = st.number_input("Corregir Monto", value=float(item_ed['monto'])); n_f = st.date_input("Corregir Fecha", value=item_ed['fecha'])
                n_d = st.text_input("Corregir Detalle", value=item_ed['detalle'])
                if st.form_submit_button("Confirmar Cambios"):
                    cur = conn.cursor(); cur.execute("UPDATE gastos SET monto=%s, fecha=%s, detalle=%s WHERE id=%s", (n_m, n_f, n_d, id_ed))
                    conn.commit(); st.success("Actualizado"); st.rerun()
    conn.close()

# --- 💰 5. VENTAS ---
elif menu == "💰 Ventas":
    st.title("💰 Control de Ventas")
    conn = conectar_db(); v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    
    # --- FILTRO POR MES ---
    df_full_s = pd.read_sql('SELECT s.id, s.fecha, v.placa, s.cliente, s.valor_viaje, s.descripcion FROM ventas s JOIN vehiculos v ON s.vehiculo_id = v.id ORDER BY s.fecha DESC', conn)
    df_full_s['Mes'] = pd.to_datetime(df_full_s['fecha']).dt.strftime('%Y-%m')
    meses_s = sorted(df_full_s['Mes'].unique().tolist(), reverse=True)
    mes_s = st.selectbox("Filtrar por Mes", ["Todos"] + meses_s)
    df_s_filtrado = df_full_s if mes_s == "Todos" else df_full_s[df_full_s['Mes'] == mes_s]

    t1, t2 = st.tabs(["📝 Registro", "✏️ Editar"])
    with t1:
        with st.form("s"):
            c1, c2 = st.columns(2)
            v_id = int(v_data[v_data['placa'] == c1.selectbox("Vehículo", v_data['placa'])]['id'].values[0])
            cli = c1.text_input("Cliente/Empresa"); val = c2.number_input("Valor Facturado", min_value=0)
            fec = c2.date_input("Fecha"); dsc = st.text_input("Descripción Viaje")
            if st.form_submit_button("Guardar Venta"):
                cur = conn.cursor(); cur.execute("INSERT INTO ventas (vehiculo_id, cliente, valor_viaje, fecha, descripcion) VALUES (%s,%s,%s,%s,%s)", (v_id, cli, val, fec, dsc))
                conn.commit(); st.success("Venta Registrada"); st.rerun()
        
        df_disp = df_s_filtrado.copy()
        df_disp["valor_viaje"] = df_disp["valor_viaje"].apply(lambda x: f"$ {x:,.0f}".replace(",", "."))
        st.dataframe(df_disp[['fecha', 'placa', 'cliente', 'valor_viaje', 'descripcion']], use_container_width=True)
        st.download_button("📥 Excel Ventas", data=to_excel(df_s_filtrado), file_name=f'ventas_{mes_s}.xlsx')
    
    with t2:
        if not df_s_filtrado.empty:
            sel_v = st.selectbox("Seleccione Venta a corregir", df_s_filtrado.apply(lambda r: f"ID:{r['id']} | {r['placa']} | {r['cliente']} | $ {r['valor_viaje']}", axis=1))
            id_ed_v = int(sel_v.split("|")[0].split(":")[1].strip())
            item_v = df_s_filtrado[df_s_filtrado['id'] == id_ed_v].iloc[0]
            st.warning(f"**Editando:** Viaje de {item_v['placa']} a {item_v['cliente']} por $ {item_v['valor_viaje']:,.0f}")
            with st.form("ed_s"):
                n_v = st.number_input("Corregir Valor", value=float(item_v['valor_viaje']))
                n_f = st.date_input("Corregir Fecha", value=item_v['fecha'])
                n_d = st.text_input("Corregir Descripción", value=item_v['descripcion'])
                if st.form_submit_button("Confirmar"):
                    cur = conn.cursor(); cur.execute("UPDATE ventas SET valor_viaje=%s, fecha=%s, descripcion=%s WHERE id=%s", (n_v, n_f, n_d, id_ed_v))
                    conn.commit(); st.success("Actualizado"); st.rerun()
    conn.close()
