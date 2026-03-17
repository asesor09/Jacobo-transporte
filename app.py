import streamlit as st
import psycopg2
import pandas as pd
from datetime import datetime, timedelta
import io
import plotly.express as px

# --- 1. CONFIGURACIÓN DE LA BASE DE DATOS ---
DB_URL = "postgresql://neondb_owner:npg_c7Dkwlh1jzGQ@ep-lucky-shadow-ac1thtiq-pooler.sa-east-1.aws.neon.tech/neondb?sslmode=require"

def conectar_db():
    return psycopg2.connect(DB_URL)

def inicializar_db():
    conn = conectar_db()
    cur = conn.cursor()
    cur.execute('CREATE TABLE IF NOT EXISTS vehiculos (id SERIAL PRIMARY KEY, placa TEXT UNIQUE NOT NULL, marca TEXT, modelo TEXT, conductor TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS gastos (id SERIAL PRIMARY KEY, vehiculo_id INTEGER REFERENCES vehiculos(id), tipo_gasto TEXT, monto NUMERIC, fecha DATE, detalle TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS ventas (id SERIAL PRIMARY KEY, vehiculo_id INTEGER REFERENCES vehiculos(id), cliente TEXT, valor_viaje NUMERIC, fecha DATE, descripcion TEXT)')
    cur.execute('''CREATE TABLE IF NOT EXISTS hoja_vida (
                    id SERIAL PRIMARY KEY, 
                    vehiculo_id INTEGER UNIQUE REFERENCES vehiculos(id), 
                    soat_vence DATE, tecno_vence DATE, prev_vence DATE,
                    p_contractual DATE, p_extracontractual DATE, p_todoriesgo DATE, t_operaciones DATE)''')
    cur.execute('CREATE TABLE IF NOT EXISTS usuarios (id SERIAL PRIMARY KEY, nombre TEXT, usuario TEXT UNIQUE NOT NULL, clave TEXT NOT NULL, rol TEXT DEFAULT "vendedor")')
    cur.execute("INSERT INTO usuarios (nombre, usuario, clave, rol) VALUES ('Jacobo Admin', 'admin', 'Jacobo2026', 'admin') ON CONFLICT (usuario) DO NOTHING")
    
    columnas_extra = [("p_contractual", "DATE"), ("p_extracontractual", "DATE"), ("p_todoriesgo", "DATE"), ("t_operaciones", "DATE")]
    for col, tipo in columnas_extra:
        try:
            cur.execute(f"ALTER TABLE hoja_vida ADD COLUMN {col} {tipo}")
            conn.commit()
        except:
            conn.rollback()
    conn.close()

# --- 2. FUNCIONES DE APOYO ---
def actualizar_registro(tabla, cambios, id_fila):
    if not cambios: return
    conn = conectar_db(); cur = conn.cursor()
    for campo, nuevo_valor in cambios.items():
        query = f"UPDATE {tabla} SET {campo} = %s WHERE id = %s"
        cur.execute(query, (nuevo_valor, id_fila))
    conn.commit(); conn.close()

# --- 3. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="C&E Eficiencias", layout="wide", page_icon="🚐")
inicializar_db()

# --- 4. LOGIN ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.sidebar.title("🔐 Acceso")
    u_input = st.sidebar.text_input("Usuario")
    p_input = st.sidebar.text_input("Contraseña", type="password")
    if st.sidebar.button("Ingresar"):
        conn = conectar_db(); cur = conn.cursor()
        cur.execute("SELECT nombre, rol FROM usuarios WHERE usuario = %s AND clave = %s", (u_input, p_input))
        res = cur.fetchone(); conn.close()
        if res:
            st.session_state.logged_in, st.session_state.u_name, st.session_state.u_rol = True, res[0], res[1]
            st.rerun()
        else: st.sidebar.error("Error de credenciales")
    st.stop()

# --- 5. MENÚ ---
st.sidebar.write(f"👋 **{st.session_state.u_name}** ({st.session_state.u_rol})")
menu = st.sidebar.selectbox("📂 MÓDULOS", ["📊 Dashboard", "🚐 Flota", "💸 Gastos", "💰 Ventas", "📑 Hoja de Vida", "⚙️ Usuarios"])
if st.sidebar.button("🚪 Salir"): st.session_state.logged_in = False; st.rerun()

conn = conectar_db()

# --- MÓDULO: DASHBOARD ---
if menu == "📊 Dashboard":
    st.title("📊 Análisis y Utilidades")
    # (Lógica de Dashboard se mantiene igual para visualización)
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    rango = st.date_input("Rango:", [datetime.now().date() - timedelta(days=30), datetime.now().date()])
    if len(rango) == 2:
        df_v = pd.read_sql("SELECT valor_viaje as monto FROM ventas WHERE fecha BETWEEN %s AND %s", conn, params=[rango[0], rango[1]])
        df_g = pd.read_sql("SELECT monto FROM gastos WHERE fecha BETWEEN %s AND %s", conn, params=[rango[0], rango[1]])
        utilidad = df_v['monto'].sum() - df_g['monto'].sum()
        st.metric("Utilidad Total", f"${utilidad:,.0f}")

# --- MÓDULO: GASTOS ---
elif menu == "💸 Gastos":
    st.title("💸 Gestión de Gastos")
    with st.expander("➕ Registrar Nuevo Gasto"):
        with st.form("n_g"):
            v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
            v_sel = st.selectbox("Vehículo", v_data['placa'])
            tipo = st.selectbox("Concepto", ["Combustible", "Peaje", "Mantenimiento", "Lavada", "Viáticos", "Otros"])
            monto = st.number_input("Valor", min_value=0)
            fec = st.date_input("Fecha")
            det = st.text_input("Detalle")
            if st.form_submit_button("Guardar"):
                v_id = v_data[v_data['placa'] == v_sel]['id'].values[0]
                cur = conn.cursor(); cur.execute("INSERT INTO gastos (vehiculo_id, tipo_gasto, monto, fecha, detalle) VALUES (%s,%s,%s,%s,%s)", (int(v_id), tipo, monto, fec, det))
                conn.commit(); st.rerun()
    
    st.subheader("✏️ Editor de Gastos (Haz clic para editar)")
    df_g = pd.read_sql("SELECT g.id, v.placa, g.tipo_gasto, g.monto, g.fecha, g.detalle FROM gastos g JOIN vehiculos v ON g.vehiculo_id = v.id ORDER BY g.fecha DESC", conn)
    edited_df = st.data_editor(df_g, key="edit_gastos", hide_index=True, use_container_width=True, disabled=["id", "placa"])
    if st.button("💾 Guardar Cambios en Gastos"):
        cur = conn.cursor()
        for i, row in edited_df.iterrows():
            cur.execute("UPDATE gastos SET tipo_gasto=%s, monto=%s, fecha=%s, detalle=%s WHERE id=%s", (row['tipo_gasto'], row['monto'], row['fecha'], row['detalle'], int(row['id'])))
        conn.commit(); st.success("Cambios guardados"); st.rerun()

# --- MÓDULO: VENTAS ---
elif menu == "💰 Ventas":
    st.title("💰 Gestión de Ventas")
    with st.expander("➕ Registrar Nueva Venta"):
        with st.form("n_v"):
            v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
            v_sel = st.selectbox("Vehículo", v_data['placa'])
            cli = st.text_input("Cliente"); val = st.number_input("Valor", min_value=0); fec = st.date_input("Fecha"); dsc = st.text_input("Nota")
            if st.form_submit_button("Registrar"):
                v_id = v_data[v_data['placa'] == v_sel]['id'].values[0]
                cur = conn.cursor(); cur.execute("INSERT INTO ventas (vehiculo_id, cliente, valor_viaje, fecha, descripcion) VALUES (%s,%s,%s,%s,%s)", (int(v_id), cli, val, fec, dsc))
                conn.commit(); st.rerun()
    
    st.subheader("✏️ Editor de Ventas")
    df_v = pd.read_sql("SELECT id, cliente, valor_viaje, fecha, descripcion FROM ventas ORDER BY fecha DESC", conn)
    edited_v = st.data_editor(df_v, key="edit_ventas", hide_index=True, use_container_width=True, disabled=["id"])
    if st.button("💾 Guardar Cambios en Ventas"):
        cur = conn.cursor()
        for _, row in edited_v.iterrows():
            cur.execute("UPDATE ventas SET cliente=%s, valor_viaje=%s, fecha=%s, descripcion=%s WHERE id=%s", (row['cliente'], row['valor_viaje'], row['fecha'], row['descripcion'], int(row['id'])))
        conn.commit(); st.success("Actualizado"); st.rerun()

# --- MÓDULO: FLOTA ---
elif menu == "🚐 Flota":
    st.title("🚐 Gestión de Flota")
    with st.form("n_f"):
        p = st.text_input("Placa").upper(); m = st.text_input("Marca"); mod = st.text_input("Modelo"); cnd = st.text_input("Conductor")
        if st.form_submit_button("Añadir"):
            cur = conn.cursor(); cur.execute("INSERT INTO vehiculos (placa, marca, modelo, conductor) VALUES (%s,%s,%s,%s)", (p, m, mod, cnd)); conn.commit(); st.rerun()
    
    df_f = pd.read_sql("SELECT id, placa, marca, modelo, conductor FROM vehiculos", conn)
    edited_f = st.data_editor(df_f, key="edit_flota", hide_index=True, use_container_width=True, disabled=["id"])
    if st.button("💾 Guardar Cambios en Vehículos"):
        cur = conn.cursor()
        for _, row in edited_f.iterrows():
            cur.execute("UPDATE vehiculos SET placa=%s, marca=%s, modelo=%s, conductor=%s WHERE id=%s", (row['placa'], row['marca'], row['modelo'], row['conductor'], int(row['id'])))
        conn.commit(); st.rerun()

# --- MÓDULO: HOJA DE VIDA ---
elif menu == "📑 Hoja de Vida":
    st.title("📑 Editor de Vencimientos")
    df_hv = pd.read_sql('''SELECT h.id, v.placa, h.soat_vence, h.tecno_vence, h.prev_vence, h.p_contractual, h.p_extracontractual, h.p_todoriesgo, h.t_operaciones 
                           FROM vehiculos v LEFT JOIN hoja_vida h ON v.id = h.vehiculo_id''', conn)
    
    st.info("💡 Puedes editar las fechas directamente en la tabla.")
    edited_hv = st.data_editor(df_hv, key="edit_hv", hide_index=True, use_container_width=True, disabled=["placa"])
    
    if st.button("💾 Guardar Cambios en Hoja de Vida"):
        cur = conn.cursor()
        for _, row in edited_hv.iterrows():
            if pd.notnull(row['id']):
                cur.execute('''UPDATE hoja_vida SET soat_vence=%s, tecno_vence=%s, prev_vence=%s, p_contractual=%s, 
                               p_extracontractual=%s, p_todoriesgo=%s, t_operaciones=%s WHERE id=%s''', 
                            (row['soat_vence'], row['tecno_vence'], row['prev_vence'], row['p_contractual'], 
                             row['p_extracontractual'], row['p_todoriesgo'], row['t_operaciones'], int(row['id'])))
        conn.commit(); st.success("Vencimientos actualizados"); st.rerun()

    # Semáforo visual (Se mantiene debajo para referencia rápida)
    hoy = datetime.now().date()
    for _, row in df_hv.iterrows():
        if pd.notnull(row['soat_vence']):
            st.caption(f"**Estado: {row['placa']}**")
            dias = (row['soat_vence'] - hoy).days
            if dias < 0: st.error(f"SOAT vencido ({row['placa']})")

# --- MÓDULO: USUARIOS ---
elif menu == "⚙️ Usuarios" and st.session_state.u_rol == "admin":
    st.title("⚙️ Gestión de Usuarios")
    df_u = pd.read_sql("SELECT id, nombre, usuario, clave, rol FROM usuarios", conn)
    edited_u = st.data_editor(df_u, key="edit_users", hide_index=True, use_container_width=True, disabled=["id"])
    if st.button("💾 Aplicar Cambios en Usuarios"):
        cur = conn.cursor()
        for _, row in edited_u.iterrows():
            cur.execute("UPDATE usuarios SET nombre=%s, usuario=%s, clave=%s, rol=%s WHERE id=%s", (row['nombre'], row['usuario'], row['clave'], row['rol'], int(row['id'])))
        conn.commit(); st.rerun()

conn.close()
