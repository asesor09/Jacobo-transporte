import streamlit as st
import psycopg2
import pandas as pd
from datetime import datetime, timedelta
import io
import plotly.express as px

# --- 1. CONFIGURACIÓN Y CONEXIÓN ---
DB_URL = "postgresql://neondb_owner:npg_c7Dkwlh1jzGQ@ep-lucky-shadow-ac1thtiq-pooler.sa-east-1.aws.neon.tech/neondb?sslmode=require"

def conectar_db():
    return psycopg2.connect(DB_URL)

def inicializar_db():
    conn = conectar_db(); cur = conn.cursor()
    # 1. Tabla de Empresas (La base de todo)
    cur.execute('CREATE TABLE IF NOT EXISTS empresas (id SERIAL PRIMARY KEY, nombre TEXT UNIQUE NOT NULL)')
    
    # 2. Tabla de Vehículos (Ligada a una empresa)
    cur.execute('''CREATE TABLE IF NOT EXISTS vehiculos (
                    id SERIAL PRIMARY KEY, 
                    placa TEXT UNIQUE NOT NULL, 
                    empresa_id INTEGER REFERENCES empresas(id),
                    marca TEXT, modelo TEXT, conductor TEXT)''')
    
    # 3. Tablas de Operación (Se ligan al vehículo, y el vehículo a la empresa)
    cur.execute('CREATE TABLE IF NOT EXISTS gastos (id SERIAL PRIMARY KEY, vehiculo_id INTEGER REFERENCES vehiculos(id), tipo_gasto TEXT, monto NUMERIC, fecha DATE, detalle TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS ventas (id SERIAL PRIMARY KEY, vehiculo_id INTEGER REFERENCES vehiculos(id), cliente TEXT, valor_viaje NUMERIC, fecha DATE, descripcion TEXT)')
    
    cur.execute('''CREATE TABLE IF NOT EXISTS hoja_vida (
                    id SERIAL PRIMARY KEY, 
                    vehiculo_id INTEGER UNIQUE REFERENCES vehiculos(id), 
                    soat_vence DATE, tecno_vence DATE, prev_vence DATE,
                    p_contractual DATE, p_extracontractual DATE, p_todoriesgo DATE, t_operaciones DATE)''')
    
    # 4. Usuarios (Ligados a una empresa)
    cur.execute('''CREATE TABLE IF NOT EXISTS usuarios (
                    id SERIAL PRIMARY KEY, 
                    empresa_id INTEGER REFERENCES empresas(id),
                    nombre TEXT, usuario TEXT UNIQUE NOT NULL, 
                    clave TEXT NOT NULL, rol TEXT DEFAULT 'vendedor')''')

    # CREAR DATOS INICIALES (Si no existen)
    cur.execute("INSERT INTO empresas (nombre) VALUES ('C&E Principal') ON CONFLICT DO NOTHING")
    cur.execute("SELECT id FROM empresas WHERE nombre = 'C&E Principal'")
    id_principal = cur.fetchone()[0]
    
    cur.execute("INSERT INTO usuarios (empresa_id, nombre, usuario, clave, rol) VALUES (%s, 'Admin', 'admin', 'Jacobo2026', 'admin') ON CONFLICT DO NOTHING", (id_principal,))
    
    conn.commit(); conn.close()

def to_excel(df_balance, df_g, df_v):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_balance.to_excel(writer, index=False, sheet_name='Balance')
        df_g.to_excel(writer, index=False, sheet_name='Gastos')
        df_v.to_excel(writer, index=False, sheet_name='Ventas')
    return output.getvalue()

st.set_page_config(page_title="C&E Multi-Empresa", layout="wide")
inicializar_db()

# --- 2. LOGIN ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.sidebar.title("🔐 Acceso")
    u = st.sidebar.text_input("Usuario")
    p = st.sidebar.text_input("Clave", type="password")
    if st.sidebar.button("Entrar"):
        conn = conectar_db(); cur = conn.cursor()
        cur.execute("SELECT nombre, rol, empresa_id FROM usuarios WHERE usuario = %s AND clave = %s", (u, p))
        res = cur.fetchone(); conn.close()
        if res:
            st.session_state.logged_in = True
            st.session_state.u_name, st.session_state.u_rol, st.session_state.u_empresa = res[0], res[1], res[2]
            st.rerun()
        else: st.sidebar.error("Error de credenciales")
    st.stop()

# --- 3. MENÚ ---
st.sidebar.write(f"🏢 Empresa ID: {st.session_state.u_empresa}")
menu = st.sidebar.selectbox("📂 Módulos", ["📊 Dashboard", "🚐 Mis Vehículos", "💸 Gastos", "💰 Ventas", "📑 Hoja de Vida", "🏢 Admin Empresas"])

if st.sidebar.button("🚪 Cerrar Sesión"):
    st.session_state.logged_in = False; st.rerun()

# --- 4. LÓGICA DE FILTRADO POR EMPRESA ---
# Esta es la parte más importante: Todas las consultas llevan: WHERE empresa_id = st.session_state.u_empresa

# --- DASHBOARD ---
if menu == "📊 Dashboard":
    st.title(f"📊 Dashboard - {st.session_state.u_name}")
    conn = conectar_db()
    # Solo jalar vehículos de MI empresa
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos WHERE empresa_id = %s", conn, params=(st.session_state.u_empresa,))
    
    c1, c2 = st.columns(2)
    with c1:
        placa_sel = st.selectbox("Vehículo:", ["TODOS"] + v_data['placa'].tolist())
    with c2:
        rango = st.date_input("Fechas:", [datetime.now().date() - timedelta(days=30), datetime.now().date()])

    if len(rango) == 2:
        # Filtro de SQL que une Gastos/Ventas con Vehículos de MI empresa
        q_g = """SELECT g.fecha, v.placa, g.tipo_gasto, g.monto 
                 FROM gastos g JOIN vehiculos v ON g.vehiculo_id = v.id 
                 WHERE v.empresa_id = %s AND g.fecha BETWEEN %s AND %s"""
        
        q_v = """SELECT s.fecha, v.placa, s.valor_viaje as monto 
                 FROM ventas s JOIN vehiculos v ON s.vehiculo_id = v.id 
                 WHERE v.empresa_id = %s AND s.fecha BETWEEN %s AND %s"""
        
        params = [st.session_state.u_empresa, rango[0], rango[1]]
        
        if placa_sel != "TODOS":
            q_g += " AND v.placa = %s"; q_v += " AND v.placa = %s"
            params.append(placa_sel)
        
        df_g = pd.read_sql(q_g, conn, params=params)
        df_v = pd.read_sql(q_v, conn, params=params)

        u_neta = df_v['monto'].sum() - df_g['monto'].sum()
        st.metric("Utilidad del Periodo", f"${u_neta:,.0f}")
        
        fig = px.pie(df_g, values='monto', names='tipo_gasto', title="Distribución de Gastos")
        st.plotly_chart(fig)
    conn.close()

# --- GESTIÓN DE VEHÍCULOS (Filtrado por Empresa) ---
elif menu == "🚐 Mis Vehículos":
    st.title("🚐 Control de Flota")
    with st.form("add_v"):
        placa = st.text_input("Placa").upper()
        marca = st.text_input("Marca")
        if st.form_submit_button("Guardar"):
            conn = conectar_db(); cur = conn.cursor()
            cur.execute("INSERT INTO vehiculos (placa, marca, empresa_id) VALUES (%s, %s, %s)", 
                        (placa, marca, st.session_state.u_empresa))
            conn.commit(); conn.close(); st.success("Vehículo registrado"); st.rerun()

# --- ADMIN EMPRESAS (Solo para Jacobo Admin) ---
elif menu == "🏢 Admin Empresas":
    if st.session_state.u_rol == "admin":
        st.title("🏢 Gestión de Clientes (Empresas)")
        with st.form("new_emp"):
            nombre_e = st.text_input("Nombre de la Nueva Empresa")
            if st.form_submit_button("Crear Empresa"):
                conn = conectar_db(); cur = conn.cursor()
                cur.execute("INSERT INTO empresas (nombre) VALUES (%s)", (nombre_e,))
                conn.commit(); conn.close(); st.success(f"Empresa {nombre_e} creada")
        
        st.subheader("👥 Crear Usuario para Cliente")
        conn = conectar_db()
        empresas = pd.read_sql("SELECT * FROM empresas", conn)
        with st.form("new_user"):
            e_id = st.selectbox("Asignar a Empresa", empresas['nombre'])
            id_e = empresas[empresas['nombre'] == e_id]['id'].values[0]
            nom_u = st.text_input("Nombre")
            usr_u = st.text_input("Usuario (Login)")
            psw_u = st.text_input("Clave")
            if st.form_submit_button("Crear Acceso"):
                cur = conn.cursor()
                cur.execute("INSERT INTO usuarios (empresa_id, nombre, usuario, clave) VALUES (%s, %s, %s, %s)",
                            (int(id_e), nom_u, usr_u, psw_u))
                conn.commit(); conn.close(); st.success("Usuario creado")
    else:
        st.error("No tienes permisos para ver este módulo.")
