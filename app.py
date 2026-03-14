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
st.set_page_config(page_title="C&E Eficiencias", layout="wide", page_icon="📈")
inicializar_db()

if 'logged_in' not in st.session_state: st.session_state.logged_in = False

# --- SIDEBAR: LOGIN Y METAS ---
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

# --- CONFIGURACIÓN DE META (Solo visible si estás logueado) ---
st.sidebar.divider()
st.sidebar.subheader("🎯 Meta del Periodo")
meta_utilidad = st.sidebar.number_input("Objetivo de Utilidad ($)", value=5000000, step=500000)

if st.sidebar.button("🚪 CERRAR SESIÓN"):
    st.session_state.logged_in = False; st.rerun()

menu = st.sidebar.selectbox("📂 MÓDULOS", ["📊 Dashboard", "🚐 Flota", "📑 Hoja de Vida", "💸 Gastos", "💰 Ventas", "⚙️ Usuarios"])

# --- 📊 1. DASHBOARD ---
if menu == "📊 Dashboard":
    st.title("📊 Control de Metas y Utilidades")
    
    conn = conectar_db()
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    
    # Filtros
    c1, c2 = st.columns(2)
    with c1:
        placa_busqueda = st.selectbox("Filtrar Vehículo:", ["TODOS"] + v_data['placa'].tolist())
    with c2:
        rango = st.date_input("Rango de Análisis:", [datetime.now().date() - timedelta(days=30), datetime.now().date()])

    # Consultas
    q_g = "SELECT g.fecha, v.placa, g.tipo_gasto, g.monto FROM gastos g JOIN vehiculos v ON g.vehiculo_id = v.id WHERE g.fecha BETWEEN %s AND %s"
    q_v = "SELECT s.fecha, v.placa, s.valor_viaje as monto FROM ventas s JOIN vehiculos v ON s.vehiculo_id = v.id WHERE s.fecha BETWEEN %s AND %s"
    params = [rango[0], rango[1]] if len(rango) == 2 else [datetime.now().date(), datetime.now().date()]

    if placa_busqueda != "TODOS":
        q_g += " AND v.placa = %s"; q_v += " AND v.placa = %s"
        params.append(placa_busqueda)

    df_g = pd.read_sql(q_g, conn, params=params)
    df_v = pd.read_sql(q_v, conn, params=params)
    conn.close()

    # Cálculos
    res_g = df_g.groupby('placa')['monto'].sum().reset_index().rename(columns={'monto': 'Gastos'})
    res_v = df_v.groupby('placa')['monto'].sum().reset_index().rename(columns={'monto': 'Ventas'})
    balance = pd.merge(res_v, res_g, on='placa', how='outer').fillna(0)
    balance['Utilidad'] = balance['Ventas'] - balance['Gastos']
    
    total_u = balance['Utilidad'].sum()
    diferencia = total_u - meta_utilidad

    # --- INDICADOR DE META ---
    st.divider()
    if total_u >= meta_utilidad:
        st.balloons()
        st.success(f"### 🎉 ¡META ALCANZADA! \n Utilidad actual: **${total_u:,.0f}** (Exceso: ${diferencia:,.0f})")
    else:
        st.error(f"### ⚠️ META NO ALCANZADA \n Utilidad actual: **${total_u:,.0f}** (Faltan: ${abs(diferencia):,.0f} para el objetivo)")

    # Métricas
    m1, m2, m3 = st.columns(3)
    m1.metric("Ingresos", f"${df_v['monto'].sum():,.0f}")
    m2.metric("Egresos", f"${df_g['monto'].sum():,.0f}", delta_color="inverse")
    m3.metric("Utilidad Neta", f"${total_u:,.0f}", delta=f"{diferencia:,.0f}")

    st.subheader("📋 Balance por Placa")
    st.table(balance.style.format({"Ventas": "${:,.0f}", "Gastos": "${:,.0f}", "Utilidad": "${:,.0f}"}))

    # Botón Excel
    excel_file = to_excel(balance, df_g, df_v)
    st.download_button("📥 Exportar a Excel", data=excel_file, file_name="reporte_utilidades.xlsx")

# --- (Resto de módulos: Flota, Hoja de Vida, Gastos, Ventas, Usuarios se mantienen igual que en la versión anterior) ---
# ... [Incluir aquí el código de los otros módulos del mensaje anterior] ...
