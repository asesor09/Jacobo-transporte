import streamlit as st
import psycopg2
import pandas as pd
from datetime import datetime
import io

# --- 1. CONEXIÓN Y ESTRUCTURA ---
DB_URL = "postgresql://neondb_owner:npg_c7Dkwlh1jzGQ@ep-lucky-shadow-ac1thtiq-pooler.sa-east-1.aws.neon.tech/neondb?sslmode=require"

def conectar_db():
    return psycopg2.connect(DB_URL)

def inicializar_db():
    conn = conectar_db(); cur = conn.cursor()
    cur.execute('CREATE TABLE IF NOT EXISTS vehiculos (id SERIAL PRIMARY KEY, placa TEXT UNIQUE NOT NULL, marca TEXT, modelo TEXT, conductor TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS gastos (id SERIAL PRIMARY KEY, vehiculo_id INTEGER REFERENCES vehiculos(id), tipo_gasto TEXT, monto NUMERIC, fecha DATE, detalle TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS ventas (id SERIAL PRIMARY KEY, vehiculo_id INTEGER REFERENCES vehiculos(id), cliente TEXT, valor_viaje NUMERIC, fecha DATE, descripcion TEXT)')
    cur.execute('''CREATE TABLE IF NOT EXISTS hoja_vida (
                    id SERIAL PRIMARY KEY, 
                    vehiculo_id INTEGER UNIQUE REFERENCES vehiculos(id), 
                    soat_vence DATE, tecno_vence DATE, prev_vence DATE,
                    p_contractual DATE, p_extracontractual DATE, p_todoriesgo DATE, t_operaciones DATE)''')
    
    # Asegurar columnas de pólizas
    for col in ["p_contractual", "p_extracontractual", "p_todoriesgo", "t_operaciones"]:
        try: cur.execute(f"ALTER TABLE hoja_vida ADD COLUMN {col} DATE")
        except: conn.rollback()

    cur.execute('CREATE TABLE IF NOT EXISTS usuarios (id SERIAL PRIMARY KEY, nombre TEXT, usuario TEXT UNIQUE NOT NULL, clave TEXT NOT NULL, rol TEXT DEFAULT "vendedor")')
    cur.execute("INSERT INTO usuarios (nombre, usuario, clave, rol) VALUES ('Jacobo Admin', 'admin', 'Jacobo2026', 'admin') ON CONFLICT (usuario) DO NOTHING")
    conn.commit(); conn.close()

def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Reporte')
    return output.getvalue()

# --- 2. CONFIGURACIÓN ---
st.set_page_config(page_title="C&E Eficiencias", layout="wide", page_icon="🚐")
inicializar_db()

if 'logged_in' not in st.session_state: st.session_state.logged_in = False

# --- LOGIN ---
st.sidebar.title("🔐 Acceso")
if not st.session_state.logged_in:
    u_i = st.sidebar.text_input("Usuario")
    p_i = st.sidebar.text_input("Contraseña", type="password")
    if st.sidebar.button("Ingresar"):
        conn = conectar_db(); cur = conn.cursor()
        cur.execute("SELECT nombre, rol FROM usuarios WHERE usuario = %s AND clave = %s", (u_i, p_i))
        res = cur.fetchone(); conn.close()
        if res:
            st.session_state.logged_in = True
            st.session_state.user_name, st.session_state.user_role = res[0], res[1]
            st.rerun()
        else: st.sidebar.error("Datos incorrectos")
    st.stop()

if st.sidebar.button("🚪 CERRAR SESIÓN"):
    st.session_state.logged_in = False; st.rerun()

menu = st.sidebar.selectbox("📂 MÓDULOS", ["📊 Dashboard", "🚐 Flota", "📑 Hoja de Vida", "💸 Gastos", "💰 Ventas", "⚙️ Usuarios"])

# --- 📊 1. DASHBOARD (Suma de cada uno) ---
if menu == "📊 Dashboard":
    st.title("📊 Resumen Mensual y Gasto por Vehículo")
    conn = conectar_db()
    df_g = pd.read_sql("SELECT g.monto, g.fecha, v.placa FROM gastos g JOIN vehiculos v ON g.vehiculo_id = v.id", conn)
    df_s = pd.read_sql("SELECT s.valor_viaje, s.fecha, v.placa FROM ventas s JOIN vehiculos v ON s.vehiculo_id = v.id", conn)
    conn.close()
    
    if not df_g.empty or not df_s.empty:
        df_g['Mes'] = pd.to_datetime(df_g['fecha']).dt.strftime('%Y-%m')
        df_s['Mes'] = pd.to_datetime(df_s['fecha']).dt.strftime('%Y-%m')
        
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("🗓️ Consolidado por Mes")
            res_m = pd.merge(df_s.groupby('Mes')['valor_viaje'].sum(), df_g.groupby('Mes')['monto'].sum(), on='Mes', how='outer').fillna(0)
            res_m.columns = ['Ventas', 'Gastos']; res_m['Utilidad'] = res_m['Ventas'] - res_m['Gastos']
            st.table(res_m.sort_values(by='Mes', ascending=False).style.format("${:,.0f}"))
        
        with c2:
            st.subheader("🚐 Gasto Total por Placa")
            res_v = df_g.groupby('placa')['monto'].sum().reset_index()
            res_v.columns = ['Placa', 'Total Gastado']
            st.table(res_v.sort_values(by='Total Gastado', ascending=False).style.format({"Total Gastado": "${:,.0f}"}))
    else:
        st.info("Registre datos para ver el balance.")

# --- 🚐 2. FLOTA ---
elif menu == "🚐 Flota":
    st.title("🚐 Gestión de Vehículos")
    with st.form("v"):
        p = st.text_input("Placa").upper(); m = st.text_input("Marca"); mod = st.text_input("Modelo"); cond = st.text_input("Conductor")
        if st.form_submit_button("Guardar Vehículo"):
            conn = conectar_db(); cur = conn.cursor()
            cur.execute("INSERT INTO vehiculos (placa, marca, modelo, conductor) VALUES (%s,%s,%s,%s)", (p, m, mod, cond))
            conn.commit(); conn.close(); st.success("Guardado"); st.rerun()
    conn = conectar_db(); st.table(pd.read_sql("SELECT placa, marca, modelo, conductor FROM vehiculos", conn)); conn.close()

# --- 📑 3. HOJA DE VIDA ---
elif menu == "📑 Hoja de Vida":
    st.title("📑 Documentación de la Flota")
    conn = conectar_db(); v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    with st.expander("📝 Actualizar Documentos"):
        if not v_data.empty:
            with st.form("hv"):
                v_sel = st.selectbox("Vehículo", v_data['placa'])
                v_id = int(v_data[v_data['placa'] == v_sel]['id'].values[0])
                c1, c2 = st.columns(2)
                s_v = c1.date_input("SOAT"); t_v = c1.date_input("Tecno"); p_v = c1.date_input("Preventivo")
                pc_v = c2.date_input("Contractual"); pe_v = c2.date_input("Extracontractual")
                ptr_v = c2.date_input("Todo Riesgo"); to_v = st.date_input("Tarjeta Operaciones")
                if st.form_submit_button("Actualizar"):
                    cur = conn.cursor(); cur.execute('''INSERT INTO hoja_vida (vehiculo_id, soat_vence, tecno_vence, prev_vence, p_contractual, p_extracontractual, p_todoriesgo, t_operaciones) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (vehiculo_id) DO UPDATE SET soat_vence=EXCLUDED.soat_vence, tecno_vence=EXCLUDED.tecno_vence, prev_vence=EXCLUDED.prev_vence, p_contractual=EXCLUDED.p_contractual, p_extracontractual=EXCLUDED.p_extracontractual, p_todoriesgo=EXCLUDED.p_todoriesgo, t_operaciones=EXCLUDED.t_operaciones''', (v_id, s_v, t_v, p_v, pc_v, pe_v, ptr_v, to_v))
                    conn.commit(); st.success("Actualizado"); st.rerun()
    df_h = pd.read_sql('''SELECT v.placa, h.soat_vence, h.tecno_vence, h.prev_vence, h.p_contractual, h.p_extracontractual, h.p_todoriesgo, h.t_operaciones FROM vehiculos v LEFT JOIN hoja_vida h ON v.id = h.vehiculo_id''', conn)
    hoy = datetime.now().date()
    for _, row in df_h.iterrows():
        st.subheader(f"🚗 {row['placa']}")
        cols = st.columns(4)
        doc_map = [(cols[0], "SOAT", row['soat_vence']), (cols[1], "TECNO", row['tecno_vence']), (cols[2], "PREV", row['prev_vence']), (cols[3], "T. OPER", row['t_operaciones']), (cols[0], "CONTR", row['p_contractual']), (cols[1], "EXTRA", row['p_extracontractual']), (cols[2], "TODO R", row['p_todoriesgo'])]
        for c, lbl, f in doc_map:
            if f:
                d = (f - hoy).days
                if d < 0: c.error(f"❌ {lbl} VENCIDO")
                elif d <= 15: c.warning(f"⚠️ {lbl} {d}d")
                else: c.success(f"✅ {lbl} OK")
    conn.close()

# --- 💸 4. GASTOS ---
elif menu == "💸 Gastos":
    st.title("💸 Control de Gastos")
    conn = conectar_db(); v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    df_g = pd.read_sql('SELECT g.id, g.fecha, v.placa, g.tipo_gasto, g.monto, g.detalle FROM gastos g JOIN vehiculos v ON g.vehiculo_id = v.id ORDER BY g.fecha DESC', conn)
    df_g['Mes'] = pd.to_datetime(df_g['fecha']).dt.strftime('%Y-%m')
    
    mes_sel = st.selectbox("📅 Mes:", sorted(df_g['Mes'].unique().tolist(), reverse=True) if not df_g.empty else [datetime.now().strftime('%Y-%m')])
    df_mes = df_g[df_g['Mes'] == mes_sel]

    if not df_mes.empty:
        c1, c2 = st.columns(2)
        with c1:
            st.write(f"**💰 Gasto por Vehículo ({mes_sel}):**")
            st.table(df_mes.groupby('placa')['monto'].sum().apply(lambda x: f"${x:,.0f}"))
        with c2:
            st.write(f"**📂 Gasto por Concepto ({mes_sel}):**")
            st.table(df_mes.groupby('tipo_gasto')['monto'].sum().apply(lambda x: f"${x:,.0f}"))

    st.divider()
    t1, t2 = st.tabs(["📝 Registro", "✏️ Editar"])
    with t1:
        with st.form("ng"):
            c1, c2 = st.columns(2)
            v_id = int(v_data[v_data['placa'] == c1.selectbox("Vehículo", v_data['placa'])]['id'].values[0])
            tipo = c1.selectbox("Concepto", ["Combustible", "Peaje", "Mantenimiento", "Lavada", "Viáticos", "Repuestos", "Otros"])
            mon = c2.number_input("Monto", min_value=0); fec = c2.date_input("Fecha"); det = st.text_input("Detalle")
            if st.form_submit_button("Guardar"):
                cur = conn.cursor(); cur.execute("INSERT INTO gastos (vehiculo_id, tipo_gasto, monto, fecha, detalle) VALUES (%s,%s,%s,%s,%s)", (v_id, tipo, mon, fec, det))
                conn.commit(); st.success("Guardado"); st.rerun()
        st.dataframe(df_mes[['fecha', 'placa', 'tipo_gasto', 'monto', 'detalle']], use_container_width=True, hide_index=True)
        st.download_button("📥 Excel", data=to_excel(df_mes), file_name=f'gastos_{mes_sel}.xlsx')

    with t2:
        event = st.dataframe(df_mes, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")
        if len(event.selection.rows) > 0:
            row = df_mes.iloc[event.selection.rows[0]]
            with st.form("eg"):
                st.subheader("Editando Gasto")
                e_mon = st.number_input("Monto", value=float(row['monto']))
                e_fec = st.date_input("Fecha", value=row['fecha'])
                e_det = st.text_input("Detalle", value=row['detalle'])
                if st.form_submit_button("✅ Actualizar"):
                    cur = conn.cursor(); cur.execute("UPDATE gastos SET monto=%s, fecha=%s, detalle=%s WHERE id=%s", (e_mon, e_fec, e_det, int(row['id'])))
                    conn.commit(); st.success("Actualizado"); st.rerun()
    conn.close()

# --- 💰 5. VENTAS ---
elif menu == "💰 Ventas":
    st.title("💰 Control de Ventas")
    conn = conectar_db(); v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    df_v = pd.read_sql('SELECT s.id, s.fecha, v.placa, s.cliente, s.valor_viaje, s.descripcion FROM ventas s JOIN vehiculos v ON s.vehiculo_id = v.id ORDER BY s.fecha DESC', conn)
    t1, t2 = st.tabs(["📝 Registro", "✏️ Editar"])
    with t1:
        with st.form("ns"):
            v_id = int(v_data[v_data['placa'] == st.selectbox("Vehículo", v_data['placa'])]['id'].values[0])
            cli = st.text_input("Cliente"); val = st.number_input("Valor", min_value=0); fec = st.date_input("Fecha"); dsc = st.text_input("Descripción")
            if st.form_submit_button("Guardar"):
                cur = conn.cursor(); cur.execute("INSERT INTO ventas (vehiculo_id, cliente, valor_viaje, fecha, descripcion) VALUES (%s,%s,%s,%s,%s)", (v_id, cli, val, fec, dsc))
                conn.commit(); st.success("Venta Registrada"); st.rerun()
        st.dataframe(df_v[['fecha', 'placa', 'cliente', 'valor_viaje', 'descripcion']], use_container_width=True, hide_index=True)
        st.download_button("📥 Excel Ventas", data=to_excel(df_v), file_name='ventas_totales.xlsx')
    with t2:
        ev_s = st.dataframe(df_v, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")
        if len(ev_s.selection.rows) > 0:
            row_s = df_v.iloc[ev_s.selection.rows[0]]
            with st.form("es"):
                st.subheader("Editando Venta")
                e_val = st.number_input("Valor", value=float(row_s['valor_viaje']))
                e_cli = st.text_input("Cliente", value=row_s['cliente'])
                e_dsc = st.text_input("Descripción", value=row_s['descripcion'])
                if st.form_submit_button("✅ Actualizar"):
                    cur = conn.cursor(); cur.execute("UPDATE ventas SET cliente=%s, valor_viaje=%s, descripcion=%s WHERE id=%s", (e_cli, e_val, e_dsc, int(row_s['id'])))
                    conn.commit(); st.success("Actualizado"); st.rerun()
    conn.close()

# --- ⚙️ 6. USUARIOS ---
elif menu == "⚙️ Usuarios" and st.session_state.user_role == "admin":
    st.title("⚙️ Gestión de Usuarios")
    with st.form("u"):
        n = st.text_input("Nombre"); u = st.text_input("Usuario"); c = st.text_input("Clave"); r = st.selectbox("Rol", ["vendedor", "admin"])
        if st.form_submit_button("Crear"):
            conn = conectar_db(); cur = conn.cursor()
            cur.execute("INSERT INTO usuarios (nombre, usuario, clave, rol) VALUES (%s,%s,%s,%s)", (n, u, c, r))
            conn.commit(); conn.close(); st.success("Creado")
