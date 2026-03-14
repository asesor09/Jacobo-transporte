import streamlit as st
import psycopg2
import pandas as pd
from datetime import datetime, timedelta
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
                    id SERIAL PRIMARY KEY, vehiculo_id INTEGER UNIQUE REFERENCES vehiculos(id), 
                    soat_vence DATE, tecno_vence DATE, prev_vence DATE,
                    p_contractual DATE, p_extracontractual DATE, p_todoriesgo DATE, t_operaciones DATE)''')
    
    for col in ["p_contractual", "p_extracontractual", "p_todoriesgo", "t_operaciones"]:
        try: cur.execute(f"ALTER TABLE hoja_vida ADD COLUMN {col} DATE")
        except: conn.rollback()

    cur.execute('CREATE TABLE IF NOT EXISTS usuarios (id SERIAL PRIMARY KEY, nombre TEXT, usuario TEXT UNIQUE NOT NULL, clave TEXT NOT NULL, rol TEXT DEFAULT "vendedor")')
    cur.execute("INSERT INTO usuarios (nombre, usuario, clave, rol) VALUES ('Jacobo Admin', 'admin', 'Jacobo2026', 'admin') ON CONFLICT (usuario) DO NOTHING")
    conn.commit(); conn.close()

def to_excel(df_summary, df_gastos, df_ventas):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_summary.to_excel(writer, index=False, sheet_name='Balance General')
        df_gastos.to_excel(writer, index=False, sheet_name='Detalle Gastos')
        df_ventas.to_excel(writer, index=False, sheet_name='Detalle Ventas')
    return output.getvalue()

# --- 2. CONFIGURACIÓN ---
st.set_page_config(page_title="C&E Eficiencias", layout="wide", page_icon="💰")
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
        else: st.sidebar.error("Usuario o clave incorrecta")
    st.stop()

if st.sidebar.button("🚪 CERRAR SESIÓN"):
    st.session_state.logged_in = False; st.rerun()

menu = st.sidebar.selectbox("📂 MÓDULOS", ["📊 Dashboard", "🚐 Flota", "📑 Hoja de Vida", "💸 Gastos", "💰 Ventas", "⚙️ Usuarios"])

# --- 📊 1. DASHBOARD DE UTILIDADES ---
if menu == "📊 Dashboard":
    st.title("📊 Balance de Utilidades")
    
    conn = conectar_db()
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    
    # Filtros
    st.subheader("🔍 Filtros de Reporte")
    c1, c2 = st.columns(2)
    with c1:
        placas_lista = ["TODOS"] + v_data['placa'].tolist()
        placa_busqueda = st.selectbox("Vehículo:", placas_lista)
    with c2:
        hoy = datetime.now().date()
        rango = st.date_input("Periodo:", [hoy - timedelta(days=30), hoy])

    # Consultas
    q_g = "SELECT g.fecha, v.placa, g.tipo_gasto, g.monto, g.detalle FROM gastos g JOIN vehiculos v ON g.vehiculo_id = v.id WHERE g.fecha BETWEEN %s AND %s"
    q_v = "SELECT s.fecha, v.placa, s.cliente, s.valor_viaje as monto, s.descripcion FROM ventas s JOIN vehiculos v ON s.vehiculo_id = v.id WHERE s.fecha BETWEEN %s AND %s"
    params = [rango[0], rango[1]] if len(rango) == 2 else [hoy, hoy]

    if placa_busqueda != "TODOS":
        q_g += " AND v.placa = %s"; q_v += " AND v.placa = %s"
        params.append(placa_busqueda)

    df_g = pd.read_sql(q_g, conn, params=params)
    df_v = pd.read_sql(q_v, conn, params=params)
    conn.close()

    # --- CÁLCULO DE UTILIDADES ---
    st.divider()
    
    # Resumen por Placa
    res_g = df_g.groupby('placa')['monto'].sum().reset_index().rename(columns={'monto': 'Gastos'})
    res_v = df_v.groupby('placa')['monto'].sum().reset_index().rename(columns={'monto': 'Ventas'})
    
    # Unir todo en una tabla de utilidad
    balance = pd.merge(res_v, res_g, on='placa', how='outer').fillna(0)
    balance['Utilidad'] = balance['Ventas'] - balance['Gastos']
    
    # Métricas Principales
    m1, m2, m3 = st.columns(3)
    total_v = balance['Ventas'].sum()
    total_g = balance['Gastos'].sum()
    total_u = balance['Utilidad'].sum()
    
    m1.metric("Ingresos Totales", f"${total_v:,.0f}")
    m2.metric("Gastos Totales", f"${total_g:,.0f}", delta=f"-{total_g:,.0f}", delta_color="inverse")
    m3.metric("Utilidad Neta", f"${total_u:,.0f}", delta=f"{total_u:,.0f}")

    st.subheader("📋 Resumen por Vehículo")
    st.table(balance.style.format({"Ventas": "${:,.0f}", "Gastos": "${:,.0f}", "Utilidad": "${:,.0f}"}))

    # Botón Excel
    excel_data = to_excel(balance, df_g, df_v)
    st.download_button(label="📥 Descargar Reporte en Excel", data=excel_data, file_name=f"Reporte_CE_{rango[0]}.xlsx", mime="application/vnd.ms-excel")

    # Tablas Detalladas
    with st.expander("👁️ Ver detalle de movimientos"):
        col_x, col_y = st.columns(2)
        col_x.write("**Gastos**")
        col_x.dataframe(df_g, hide_index=True)
        col_y.write("**Ventas**")
        col_y.dataframe(df_v, hide_index=True)

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
    st.title("📑 Documentación Legal")
    conn = conectar_db(); v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    with st.expander("📝 Actualizar Vencimientos"):
        if not v_data.empty:
            with st.form("hv"):
                v_sel = st.selectbox("Vehículo", v_data['placa'])
                v_id = int(v_data[v_data['placa'] == v_sel]['id'].values[0])
                c1, c2 = st.columns(2)
                s_v = c1.date_input("SOAT"); t_v = c1.date_input("Tecno"); p_v = c1.date_input("Preventivo")
                pc_v = c2.date_input("Póliza Contractual"); pe_v = c2.date_input("Póliza Extracontractual")
                ptr_v = c2.date_input("Póliza Todo Riesgo"); to_v = st.date_input("Tarjeta de Operaciones")
                if st.form_submit_button("Actualizar Todo"):
                    cur = conn.cursor(); cur.execute('''INSERT INTO hoja_vida (vehiculo_id, soat_vence, tecno_vence, prev_vence, p_contractual, p_extracontractual, p_todoriesgo, t_operaciones) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (vehiculo_id) DO UPDATE SET soat_vence=EXCLUDED.soat_vence, tecno_vence=EXCLUDED.tecno_vence, prev_vence=EXCLUDED.prev_vence, p_contractual=EXCLUDED.p_contractual, p_extracontractual=EXCLUDED.p_extracontractual, p_todoriesgo=EXCLUDED.p_todoriesgo, t_operaciones=EXCLUDED.t_operaciones''', (v_id, s_v, t_v, p_v, pc_v, pe_v, ptr_v, to_v))
                    conn.commit(); st.success("Documentos actualizados"); st.rerun()
    
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
    st.title("💸 Gastos")
    conn = conectar_db(); v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    df_g = pd.read_sql('SELECT g.id, g.fecha, v.placa, g.tipo_gasto, g.monto, g.detalle FROM gastos g JOIN vehiculos v ON g.vehiculo_id = v.id ORDER BY g.fecha DESC', conn)
    df_g['Mes'] = pd.to_datetime(df_g['fecha']).dt.strftime('%Y-%m')
    
    mes_sel = st.selectbox("📅 Mes:", sorted(df_g['Mes'].unique().tolist(), reverse=True) if not df_g.empty else [datetime.now().strftime('%Y-%m')])
    df_mes = df_g[df_g['Mes'] == mes_sel]

    t1, t2 = st.tabs(["📝 Registro", "✏️ Editar"])
    with t1:
        with st.form("ng"):
            v_id = int(v_data[v_data['placa'] == st.selectbox("Vehículo", v_data['placa'])]['id'].values[0])
            tipo = st.selectbox("Concepto", ["Combustible", "Peaje", "Mantenimiento", "Lavada", "Viáticos", "Otros"])
            mon = st.number_input("Monto", min_value=0); fec = st.date_input("Fecha"); det = st.text_input("Detalle")
            if st.form_submit_button("Guardar"):
                cur = conn.cursor(); cur.execute("INSERT INTO gastos (vehiculo_id, tipo_gasto, monto, fecha, detalle) VALUES (%s,%s,%s,%s,%s)", (v_id, tipo, mon, fec, det))
                conn.commit(); st.success("Guardado"); st.rerun()
        st.dataframe(df_mes[['fecha', 'placa', 'tipo_gasto', 'monto', 'detalle']], use_container_width=True, hide_index=True)

    with t2:
        event = st.dataframe(df_mes, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")
        if len(event.selection.rows) > 0:
            row = df_mes.iloc[event.selection.rows[0]]
            with st.form("eg"):
                e_mon = st.number_input("Monto", value=float(row['monto']))
                e_fec = st.date_input("Fecha", value=row['fecha'])
                e_det = st.text_input("Detalle", value=row['detalle'])
                if st.form_submit_button("✅ Actualizar"):
                    cur = conn.cursor(); cur.execute("UPDATE gastos SET monto=%s, fecha=%s, detalle=%s WHERE id=%s", (e_mon, e_fec, e_det, int(row['id'])))
                    conn.commit(); st.success("Actualizado"); st.rerun()
                if st.form_submit_button("🗑️ Eliminar Gasto"):
                    cur = conn.cursor(); cur.execute("DELETE FROM gastos WHERE id=%s", (int(row['id']),))
                    conn.commit(); st.warning("Eliminado"); st.rerun()
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
                conn.commit(); st.success("Registrado"); st.rerun()
        st.dataframe(df_v[['fecha', 'placa', 'cliente', 'valor_viaje', 'descripcion']], use_container_width=True, hide_index=True)

# --- ⚙️ 6. USUARIOS ---
elif menu == "⚙️ Usuarios" and st.session_state.user_role == "admin":
    st.title("⚙️ Usuarios")
    with st.form("u"):
        n = st.text_input("Nombre"); u = st.text_input("Usuario"); c = st.text_input("Clave"); r = st.selectbox("Rol", ["vendedor", "admin"])
        if st.form_submit_button("Crear"):
            conn = conectar_db(); cur = conn.cursor()
            cur.execute("INSERT INTO usuarios (nombre, usuario, clave, rol) VALUES (%s,%s,%s,%s)", (n, u, c, r))
            conn.commit(); conn.close(); st.success("Creado")
