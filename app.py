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
    # Tabla de Vehículos
    cur.execute('CREATE TABLE IF NOT EXISTS vehiculos (id SERIAL PRIMARY KEY, placa TEXT UNIQUE NOT NULL, marca TEXT, modelo TEXT, conductor TEXT)')
    # Tabla de Gastos
    cur.execute('CREATE TABLE IF NOT EXISTS gastos (id SERIAL PRIMARY KEY, vehiculo_id INTEGER REFERENCES vehiculos(id), tipo_gasto TEXT, monto NUMERIC, fecha DATE, detalle TEXT)')
    # Tabla de Ventas
    cur.execute('CREATE TABLE IF NOT EXISTS ventas (id SERIAL PRIMARY KEY, vehiculo_id INTEGER REFERENCES vehiculos(id), cliente TEXT, valor_viaje NUMERIC, fecha DATE, descripcion TEXT)')
    # Tabla Hoja de Vida
    cur.execute('''CREATE TABLE IF NOT EXISTS hoja_vida (
                    id SERIAL PRIMARY KEY, 
                    vehiculo_id INTEGER UNIQUE REFERENCES vehiculos(id), 
                    soat_vence DATE, tecno_vence DATE, prev_vence DATE,
                    p_contractual DATE, p_extracontractual DATE, p_todoriesgo DATE, t_operaciones DATE)''')
    # Tabla de Usuarios
    cur.execute('CREATE TABLE IF NOT EXISTS usuarios (id SERIAL PRIMARY KEY, nombre TEXT, usuario TEXT UNIQUE NOT NULL, clave TEXT NOT NULL, rol TEXT DEFAULT "vendedor")')
    cur.execute("INSERT INTO usuarios (nombre, usuario, clave, rol) VALUES ('Jacobo Admin', 'admin', 'Jacobo2026', 'admin') ON CONFLICT (usuario) DO NOTHING")
    
    # Asegurar que las columnas nuevas existan sin romper la transacción
    columnas_extra = [
        ("p_contractual", "DATE"), ("p_extracontractual", "DATE"), 
        ("p_todoriesgo", "DATE"), ("t_operaciones", "DATE")
    ]
    for col, tipo in columnas_extra:
        try:
            cur.execute(f"ALTER TABLE hoja_vida ADD COLUMN {col} {tipo}")
            conn.commit()
        except Exception:
            conn.rollback()
        
    conn.close()

# --- 2. FUNCIONES DE APOYO ---
def to_excel(df_balance, df_g, df_v):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_balance.to_excel(writer, index=False, sheet_name='Balance General')
        df_g.to_excel(writer, index=False, sheet_name='Detalle Gastos')
        df_v.to_excel(writer, index=False, sheet_name='Detalle Ventas')
    return output.getvalue()

# --- 3. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="C&E Eficiencias", layout="wide", page_icon="🚐")
inicializar_db()

# --- 4. SISTEMA DE LOGIN ---
if 'logged_in' not in st.session_state: 
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.sidebar.title("🔐 Acceso al Sistema")
    u_input = st.sidebar.text_input("Usuario")
    p_input = st.sidebar.text_input("Contraseña", type="password")
    if st.sidebar.button("Ingresar"):
        conn = conectar_db(); cur = conn.cursor()
        cur.execute("SELECT nombre, rol FROM usuarios WHERE usuario = %s AND clave = %s", (u_input, p_input))
        res = cur.fetchone(); conn.close()
        if res:
            st.session_state.logged_in = True
            st.session_state.u_name, st.session_state.u_rol = res[0], res[1]
            st.rerun()
        else:
            st.sidebar.error("Usuario o clave incorrectos")
    st.stop()

# --- 5. MENÚ PRINCIPAL ---
st.sidebar.write(f"👋 Bienvenid@, **{st.session_state.u_name}**")
st.sidebar.divider()
target = st.sidebar.number_input("🎯 Meta Utilidad ($)", value=5000000, step=500000)
menu = st.sidebar.selectbox("📂 MÓDULOS", ["📊 Dashboard", "🚐 Flota", "💸 Gastos", "💰 Ventas", "📑 Hoja de Vida", "⚙️ Usuarios"])

if st.sidebar.button("🚪 CERRAR SESIÓN"):
    st.session_state.logged_in = False
    st.rerun()

# --- 6. LÓGICA DE MÓDULOS ---
conn = conectar_db()

# --- MÓDULO: DASHBOARD ---
if menu == "📊 Dashboard":
    st.title("📊 Análisis de Operación")
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    c1, c2 = st.columns(2)
    with c1:
        placa_f = st.selectbox("Seleccione Vehículo:", ["TODOS"] + v_data['placa'].tolist())
    with c2:
        rango = st.date_input("Rango de Fechas:", [datetime.now().date() - timedelta(days=30), datetime.now().date()])

    if len(rango) == 2:
        q_g = "SELECT g.fecha, v.placa, g.tipo_gasto as concepto, g.monto, g.detalle FROM gastos g JOIN vehiculos v ON g.vehiculo_id = v.id WHERE g.fecha BETWEEN %s AND %s"
        q_v = "SELECT s.fecha, v.placa, s.cliente, s.valor_viaje as monto, s.descripcion FROM ventas s JOIN vehiculos v ON s.vehiculo_id = v.id WHERE s.fecha BETWEEN %s AND %s"
        params = [rango[0], rango[1]]
        if placa_f != "TODOS":
            q_g += " AND v.placa = %s"; q_v += " AND v.placa = %s"
            params.append(placa_f); params.append(placa_f)
        
        df_g = pd.read_sql(q_g, conn, params=params)
        df_v = pd.read_sql(q_v, conn, params=params)
        
        utilidad = df_v['monto'].sum() - df_g['monto'].sum()
        st.metric("Utilidad Neta", f"${utilidad:,.0f}", delta=f"{utilidad - target:,.0f}")
        
        # Gráfico
        res_g = df_g.groupby('placa')['monto'].sum().reset_index().rename(columns={'monto': 'Gasto'})
        res_v = df_v.groupby('placa')['monto'].sum().reset_index().rename(columns={'monto': 'Venta'})
        balance_df = pd.merge(res_v, res_g, on='placa', how='outer').fillna(0)
        st.plotly_chart(px.bar(balance_df, x='placa', y=['Venta', 'Gasto'], barmode='group'))
        st.download_button("📥 Descargar Excel", data=to_excel(balance_df, df_g, df_v), file_name="Reporte.xlsx")

# --- MÓDULO: GASTOS ---
elif menu == "💸 Gastos":
    st.title("💸 Control de Gastos")
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    t1, t2 = st.tabs(["📝 Nuevo", "✏️ Gestionar"])
    with t1:
        with st.form("f_g"):
            v_sel = st.selectbox("Vehículo", v_data['placa'])
            monto = st.number_input("Monto", min_value=0)
            tipo = st.selectbox("Concepto", ["Combustible", "Peaje", "Lavada", "Repuesto", "Otros"])
            fec = st.date_input("Fecha")
            det = st.text_input("Detalle")
            if st.form_submit_button("Guardar"):
                v_id = v_data[v_data['placa'] == v_sel]['id'].values[0]
                cur = conn.cursor()
                cur.execute("INSERT INTO gastos (vehiculo_id, tipo_gasto, monto, fecha, detalle) VALUES (%s,%s,%s,%s,%s)", (int(v_id), tipo, monto, fec, det))
                conn.commit(); st.success("Registrado"); st.rerun()
    with t2:
        df_g_list = pd.read_sql("SELECT g.id, g.fecha, v.placa, g.tipo_gasto, g.monto FROM gastos g JOIN vehiculos v ON g.vehiculo_id = v.id", conn)
        st.dataframe(df_g_list, use_container_width=True)

# --- MÓDULO: VENTAS ---
elif menu == "💰 Ventas":
    st.title("💰 Ingresos por Viajes")
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    with st.form("f_v"):
        v_sel = st.selectbox("Vehículo", v_data['placa'])
        cli = st.text_input("Cliente")
        val = st.number_input("Valor", min_value=0)
        fec = st.date_input("Fecha")
        if st.form_submit_button("Registrar Venta"):
            v_id = v_data[v_data['placa'] == v_sel]['id'].values[0]
            cur = conn.cursor()
            cur.execute("INSERT INTO ventas (vehiculo_id, cliente, valor_viaje, fecha) VALUES (%s,%s,%s,%s)", (int(v_id), cli, val, fec))
            conn.commit(); st.rerun()
    st.dataframe(pd.read_sql("SELECT v.placa, s.cliente, s.valor_viaje, s.fecha FROM ventas s JOIN vehiculos v ON s.vehiculo_id = v.id", conn))

# --- MÓDULO: FLOTA ---
elif menu == "🚐 Flota":
    st.title("🚐 Administración de Vehículos")
    with st.form("f_f"):
        placa = st.text_input("Placa").upper()
        marca = st.text_input("Marca")
        cond = st.text_input("Conductor")
        if st.form_submit_button("Agregar"):
            cur = conn.cursor()
            cur.execute("INSERT INTO vehiculos (placa, marca, conductor) VALUES (%s,%s,%s)", (placa, marca, cond))
            conn.commit(); st.rerun()
    st.dataframe(pd.read_sql("SELECT * FROM vehiculos", conn))

# --- MÓDULO: HOJA DE VIDA ---
elif menu == "📑 Hoja de Vida":
    st.title("📑 Vencimientos")
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    v_sel = st.selectbox("Vehículo", v_data['placa'])
    with st.form("f_hv"):
        c1, c2 = st.columns(2)
        s_v = c1.date_input("SOAT")
        t_v = c2.date_input("Tecno")
        if st.form_submit_button("Actualizar Fechas"):
            v_id = v_data[v_data['placa'] == v_sel]['id'].values[0]
            cur = conn.cursor()
            cur.execute("INSERT INTO hoja_vida (vehiculo_id, soat_vence, tecno_vence) VALUES (%s,%s,%s) ON CONFLICT (vehiculo_id) DO UPDATE SET soat_vence=EXCLUDED.soat_vence, tecno_vence=EXCLUDED.tecno_vence", (int(v_id), s_v, t_v))
            conn.commit(); st.success("Actualizado")
    # Mostrar alertas visuales
    df_hv = pd.read_sql("SELECT v.placa, h.soat_vence, h.tecno_vence FROM vehiculos v LEFT JOIN hoja_vida h ON v.id = h.vehiculo_id", conn)
    st.table(df_hv)

# --- MÓDULO: USUARIOS ---
elif menu == "⚙️ Usuarios":
    if st.session_state.u_rol == "admin":
        st.title("⚙️ Gestión de Usuarios")
        with st.form("f_u"):
            n = st.text_input("Nombre")
            u = st.text_input("Usuario")
            c = st.text_input("Clave", type="password")
            r = st.selectbox("Rol", ["vendedor", "admin"])
            if st.form_submit_button("Crear Usuario"):
                cur = conn.cursor()
                cur.execute("INSERT INTO usuarios (nombre, usuario, clave, rol) VALUES (%s,%s,%s,%s)", (n, u, c, r))
                conn.commit(); st.success("Usuario creado")
        st.dataframe(pd.read_sql("SELECT nombre, usuario, rol FROM usuarios", conn))
    else:
        st.error("No tienes permisos para ver este módulo.")

conn.close()
