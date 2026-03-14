import streamlit as st
import psycopg2
import pandas as pd
from datetime import datetime
import io

# --- 1. CONEXIÓN Y ESTRUCTURA DE USUARIOS ---
DB_URL = "postgresql://neondb_owner:npg_c7Dkwlh1jzGQ@ep-lucky-shadow-ac1thtiq-pooler.sa-east-1.aws.neon.tech/neondb?sslmode=require"

def conectar_db():
    return psycopg2.connect(DB_URL)

def inicializar_db():
    conn = conectar_db(); cur = conn.cursor()
    # Tablas Operativas
    cur.execute('CREATE TABLE IF NOT EXISTS vehiculos (id SERIAL PRIMARY KEY, placa TEXT UNIQUE NOT NULL, marca TEXT, modelo TEXT, conductor TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS gastos (id SERIAL PRIMARY KEY, vehiculo_id INTEGER REFERENCES vehiculos(id), tipo_gasto TEXT, monto NUMERIC, fecha DATE, detalle TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS ventas (id SERIAL PRIMARY KEY, vehiculo_id INTEGER REFERENCES vehiculos(id), cliente TEXT, valor_viaje NUMERIC, fecha DATE, descripcion TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS hoja_vida (id SERIAL PRIMARY KEY, vehiculo_id INTEGER UNIQUE REFERENCES vehiculos(id), soat_vence DATE, tecno_vence DATE, prev_vence DATE)')
    
    # NUEVA: TABLA DE USUARIOS
    cur.execute('''CREATE TABLE IF NOT EXISTS usuarios (
                    id SERIAL PRIMARY KEY, 
                    nombre TEXT, 
                    usuario TEXT UNIQUE NOT NULL, 
                    clave TEXT NOT NULL, 
                    rol TEXT DEFAULT 'vendedor')''')
    
    # Crear usuario administrador inicial (si no existe)
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
if 'user_role' not in st.session_state: st.session_state.user_role = None
if 'user_name' not in st.session_state: st.session_state.user_name = None

# --- LOGIN MULTI-USUARIO ---
st.sidebar.title("🔐 Acceso al Sistema")
if not st.session_state.logged_in:
    user_input = st.sidebar.text_input("Usuario")
    pass_input = st.sidebar.text_input("Contraseña", type="password")
    if st.sidebar.button("Ingresar"):
        conn = conectar_db(); cur = conn.cursor()
        cur.execute("SELECT nombre, rol FROM usuarios WHERE usuario = %s AND clave = %s", (user_input, pass_input))
        result = cur.fetchone()
        conn.close()
        if result:
            st.session_state.logged_in = True
            st.session_state.user_name = result[0]
            st.session_state.user_role = result[1]
            st.rerun()
        else:
            st.sidebar.error("Usuario o clave incorrectos")
    st.title("🚐 C&E Eficiencias")
    st.info("Inicie sesión para gestionar la flota.")
    st.stop()

st.sidebar.write(f"👤 Bienvenido: **{st.session_state.user_name}**")
if st.sidebar.button("🚪 CERRAR SESIÓN"):
    st.session_state.logged_in = False; st.rerun()

# --- MENÚ DINÁMICO ---
opciones = ["📊 Dashboard", "🚐 Flota", "📑 Hoja de Vida", "💸 Gastos", "💰 Ventas"]
if st.session_state.user_role == "admin":
    opciones.append("⚙️ Configuración Usuarios")

menu = st.sidebar.selectbox("📂 MÓDULOS", opciones)

# --- ⚙️ CONFIGURACIÓN DE USUARIOS (SÓLO ADMIN) ---
if menu == "⚙️ Configuración Usuarios":
    st.title("⚙️ Administración de Usuarios")
    with st.expander("➕ Crear Nuevo Usuario"):
        with st.form("new_user"):
            n_nom = st.text_input("Nombre Completo")
            n_usr = st.text_input("Nombre de Usuario (Login)")
            n_cla = st.text_input("Contraseña Temporal")
            n_rol = st.selectbox("Rol", ["vendedor", "admin"])
            if st.form_submit_button("Crear Usuario"):
                try:
                    conn = conectar_db(); cur = conn.cursor()
                    cur.execute("INSERT INTO usuarios (nombre, usuario, clave, rol) VALUES (%s,%s,%s,%s)", (n_nom, n_usr, n_cla, n_rol))
                    conn.commit(); conn.close(); st.success(f"Usuario {n_usr} creado con éxito.")
                except: st.error("El nombre de usuario ya existe.")
    
    conn = conectar_db(); st.subheader("Usuarios Actuales")
    st.table(pd.read_sql("SELECT nombre, usuario, rol FROM usuarios", conn)); conn.close()

# --- 📊 DASHBOARD ---
elif menu == "📊 Dashboard":
    st.title("📊 Resumen Mensual")
    conn = conectar_db()
    df_g = pd.read_sql("SELECT monto, fecha FROM gastos", conn)
    df_s = pd.read_sql("SELECT valor_viaje, fecha FROM ventas", conn)
    conn.close()
    if not df_g.empty or not df_s.empty:
        df_g['Mes'] = pd.to_datetime(df_g['fecha']).dt.strftime('%Y-%m')
        df_s['Mes'] = pd.to_datetime(df_s['fecha']).dt.strftime('%Y-%m')
        g_m = df_g.groupby('Mes')['monto'].sum().reset_index(); s_m = df_s.groupby('Mes')['valor_viaje'].sum().reset_index()
        res = pd.merge(s_m, g_m, on='Mes', how='outer').fillna(0)
        res.columns = ['Mes', 'Ventas', 'Gastos']
        res['Utilidad'] = res['Ventas'] - res['Gastos']
        st.table(res.sort_values(by='Mes', ascending=False).style.format({"Ventas": "${:,.0f}", "Gastos": "${:,.0f}", "Utilidad": "${:,.0f}"}))

# --- 🚐 FLOTA ---
elif menu == "🚐 Flota":
    st.title("🚐 Flota")
    with st.form("v"):
        placa = st.text_input("Placa").upper()
        marca = st.text_input("Marca"); mod = st.text_input("Modelo"); cond = st.text_input("Conductor")
        if st.form_submit_button("Guardar Vehículo"):
            conn = conectar_db(); cur = conn.cursor()
            cur.execute("INSERT INTO vehiculos (placa, marca, modelo, conductor) VALUES (%s,%s,%s,%s)", (placa, marca, mod, cond))
            conn.commit(); conn.close(); st.success("Registrado"); st.rerun()
    conn = conectar_db(); st.table(pd.read_sql("SELECT placa, marca, modelo, conductor FROM vehiculos", conn)); conn.close()

# --- 📑 HOJA DE VIDA ---
elif menu == "📑 Hoja de Vida":
    st.title("📑 Alertas")
    conn = conectar_db(); v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    with st.form("h_v"):
        v_sel = st.selectbox("Vehículo", v_data['placa'])
        v_id = int(v_data[v_data['placa'] == v_sel]['id'].values[0])
        c1, c2, c3 = st.columns(3)
        s_v = c1.date_input("Vence SOAT"); t_v = c2.date_input("Vence Tecno"); p_v = c3.date_input("Vence Prev.")
        if st.form_submit_button("Actualizar Alertas"):
            cur = conn.cursor(); cur.execute('''INSERT INTO hoja_vida (vehiculo_id, soat_vence, tecno_vence, prev_vence) VALUES (%s,%s,%s,%s) ON CONFLICT (vehiculo_id) DO UPDATE SET soat_vence=EXCLUDED.soat_vence, tecno_vence=EXCLUDED.tecno_vence, prev_vence=EXCLUDED.prev_vence''', (v_id, s_v, t_v, p_v))
            conn.commit(); st.success("Actualizado"); st.rerun()
    df_h = pd.read_sql('''SELECT v.placa, h.soat_vence, h.tecno_vence, h.prev_vence FROM hoja_vida h JOIN vehiculos v ON h.vehiculo_id = v.id''', conn)
    st.table(df_h); conn.close()

# --- 💸 GASTOS ---
elif menu == "💸 Gastos":
    st.title("💸 Gastos")
    conn = conectar_db(); v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    df_g = pd.read_sql('SELECT g.id, g.fecha, v.placa, g.tipo_gasto, g.monto, g.detalle FROM gastos g JOIN vehiculos v ON g.vehiculo_id = v.id ORDER BY g.fecha DESC', conn)
    df_g['Mes'] = pd.to_datetime(df_g['fecha']).dt.strftime('%Y-%m')
    
    meses = sorted(df_g['Mes'].unique().tolist(), reverse=True)
    mes_sel = st.selectbox("📅 Mes:", meses if meses else [datetime.now().strftime('%Y-%m')])
    df_mes = df_g[df_g['Mes'] == mes_sel]

    # Subtotales
    if not df_mes.empty:
        sub = df_mes.groupby('tipo_gasto')['monto'].sum().reset_index()
        st.table(sub.style.format({"monto": "${:,.0f}"}))

    st.divider()
    t1, t2 = st.tabs(["📝 Registro", "✏️ Editar"])
    with t1:
        with st.form("nuevo_g"):
            c1, c2 = st.columns(2)
            v_id = int(v_data[v_data['placa'] == c1.selectbox("Vehículo", v_data['placa'])]['id'].values[0])
            tipo = c1.selectbox("Concepto", ["Combustible", "Peaje", "Mantenimiento", "Lavada", "Viáticos", "Repuestos", "Otros"])
            mon = c2.number_input("Monto", min_value=0); fec = c2.date_input("Fecha"); det = st.text_input("Detalle")
            if st.form_submit_button("💾 Guardar"):
                cur = conn.cursor(); cur.execute("INSERT INTO gastos (vehiculo_id, tipo_gasto, monto, fecha, detalle) VALUES (%s,%s,%s,%s,%s)", (v_id, tipo, mon, fec, det))
                conn.commit(); st.success("Guardado"); st.rerun()
        st.dataframe(df_mes[['fecha', 'placa', 'tipo_gasto', 'monto', 'detalle']], use_container_width=True, hide_index=True)
        st.download_button("📥 Excel", data=to_excel(df_mes), file_name=f'gastos_{mes_sel}.xlsx')

    with t2:
        event = st.dataframe(df_mes, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")
        if len(event.selection.rows) > 0:
            row = df_mes.iloc[event.selection.rows[0]]
            with st.form("edit_g"):
                e_mon = st.number_input("Monto", value=float(row['monto']))
                e_fec = st.date_input("Fecha", value=row['fecha'])
                e_det = st.text_input("Detalle", value=row['detalle'])
                if st.form_submit_button("✅ Actualizar"):
                    cur = conn.cursor(); cur.execute("UPDATE gastos SET monto=%s, fecha=%s, detalle=%s WHERE id=%s", (e_mon, e_fec, e_det, int(row['id'])))
                    conn.commit(); st.success("Actualizado"); st.rerun()
    conn.close()

# --- 💰 VENTAS ---
elif menu == "💰 Ventas":
    st.title("💰 Ventas")
    conn = conectar_db(); v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    df_v = pd.read_sql('SELECT s.id, s.fecha, v.placa, s.cliente, s.valor_viaje, s.descripcion FROM ventas s JOIN vehiculos v ON s.vehiculo_id = v.id ORDER BY s.fecha DESC', conn)
    t1, t2 = st.tabs(["📝 Registro", "✏️ Editar"])
    with t1:
        with st.form("nueva_s"):
            v_id = int(v_data[v_data['placa'] == st.selectbox("Vehículo", v_data['placa'])]['id'].values[0])
            cli = st.text_input("Cliente"); val = st.number_input("Valor", min_value=0); fec = st.date_input("Fecha"); dsc = st.text_input("Descripción")
            if st.form_submit_button("Guardar"):
                cur = conn.cursor(); cur.execute("INSERT INTO ventas (vehiculo_id, cliente, valor_viaje, fecha, descripcion) VALUES (%s,%s,%s,%s,%s)", (v_id, cli, val, fec, dsc))
                conn.commit(); st.success("Venta Guardada"); st.rerun()
        st.dataframe(df_v[['fecha', 'placa', 'cliente', 'valor_viaje', 'descripcion']], use_container_width=True, hide_index=True)
    with t2:
        event_s = st.dataframe(df_v, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")
        if len(event_s.selection.rows) > 0:
            row_s = df_v.iloc[event_s.selection.rows[0]]
            with st.form("edit_s"):
                e_val = st.number_input("Valor", value=float(row_s['valor_viaje']))
                e_cli = st.text_input("Cliente", value=row_s['cliente'])
                e_dsc = st.text_input("Descripción", value=row_s['descripcion'])
                if st.form_submit_button("✅ Actualizar"):
                    cur = conn.cursor(); cur.execute("UPDATE ventas SET cliente=%s, valor_viaje=%s, descripcion=%s WHERE id=%s", (e_cli, e_val, e_dsc, int(row_s['id'])))
                    conn.commit(); st.success("Venta Corregida"); st.rerun()
    conn.close()
