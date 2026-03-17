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
    
    # Asegurar columnas mediante SQL robusto para evitar errores de duplicidad
    columnas_extra = [("p_contractual", "DATE"), ("p_extracontractual", "DATE"), ("p_todoriesgo", "DATE"), ("t_operaciones", "DATE")]
    for col, tipo in columnas_extra:
        try:
            cur.execute(f"ALTER TABLE hoja_vida ADD COLUMN {col} {tipo}")
        except psycopg2.errors.DuplicateColumn:
            conn.rollback()
        except Exception:
            conn.rollback()
    
    conn.commit()
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
if 'logged_in' not in st.session_state: st.session_state.logged_in = False

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
        else: st.sidebar.error("Usuario o clave incorrectos")
    st.stop()

# --- 5. MENÚ PRINCIPAL ---
st.sidebar.write(f"👋 Bienvenid@, **{st.session_state.u_name}**")
st.sidebar.divider()
target = st.sidebar.number_input("🎯 Meta Utilidad ($)", value=5000000, step=500000)
menu = st.sidebar.selectbox("📂 MÓDULOS", ["📊 Dashboard", "🚐 Flota", "💸 Gastos", "💰 Ventas", "📑 Hoja de Vida", "⚙️ Usuarios"])

if st.sidebar.button("🚪 CERRAR SESIÓN"):
    st.session_state.logged_in = False; st.rerun()

# --- 6. LÓGICA DE MÓDULOS ---

conn = conectar_db()

# --- MÓDULO: DASHBOARD ---
if menu == "📊 Dashboard":
    st.title("📊 Análisis de Operación y Utilidades")
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
            params.append(placa_f)
        
        df_g = pd.read_sql(q_g, conn, params=params)
        df_v = pd.read_sql(q_v, conn, params=params)

        sum_v = df_v['monto'].sum()
        sum_g = df_g['monto'].sum()
        utilidad_neta = sum_v - sum_g
        dif_meta = utilidad_neta - target

        st.divider()
        if utilidad_neta >= target:
            st.success(f"### 🏆 ¡META ALCANZADA! \n Utilidad: **${utilidad_neta:,.0f}**")
            st.balloons()
        else:
            st.error(f"### ⚠️ POR DEBAJO DE LA META \n Faltan: **${abs(dif_meta):,.0f}**")

        m1, m2, m3 = st.columns(3)
        m1.metric("Ingresos (Ventas)", f"${sum_v:,.0f}")
        m2.metric("Egresos (Gastos)", f"${sum_g:,.0f}", delta=f"-{sum_g:,.0f}", delta_color="inverse")
        m3.metric("Utilidad Neta", f"${utilidad_neta:,.0f}", delta=f"{dif_meta:,.0f}")

        st.subheader("📈 Comparativa por Vehículo")
        res_g = df_g.groupby('placa')['monto'].sum().reset_index().rename(columns={'monto': 'Gasto'})
        res_v = df_v.groupby('placa')['monto'].sum().reset_index().rename(columns={'monto': 'Venta'})
        balance_df = pd.merge(res_v, res_g, on='placa', how='outer').fillna(0)
        
        fig = px.bar(balance_df, x='placa', y=['Venta', 'Gasto'], barmode='group')
        st.plotly_chart(fig, use_container_width=True)
        st.download_button("📥 Excel", data=to_excel(balance_df, df_g, df_v), file_name="Reporte.xlsx")

# --- MÓDULO: GASTOS ---
elif menu == "💸 Gastos":
    st.title("💸 Registro de Gastos")
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    tab1, tab2 = st.tabs(["📝 Nuevo Gasto", "✏️ Gestionar"])
    
    with tab1:
        with st.form("form_g"):
            v_sel = st.selectbox("Vehículo", v_data['placa'])
            v_id = v_data[v_data['placa'] == v_sel]['id'].values[0]
            tipo = st.selectbox("Concepto", ["Combustible", "Peaje", "Mantenimiento", "Lavada", "Otros"])
            monto = st.number_input("Valor", min_value=0)
            fecha = st.date_input("Fecha")
            det = st.text_input("Detalle")
            if st.form_submit_button("Guardar"):
                cur = conn.cursor()
                cur.execute("INSERT INTO gastos (vehiculo_id, tipo_gasto, monto, fecha, detalle) VALUES (%s,%s,%s,%s,%s)", (int(v_id), tipo, monto, fecha, det))
                conn.commit(); st.rerun()

    with tab2:
        df_edit = pd.read_sql("SELECT g.id, g.fecha, v.placa, g.tipo_gasto, g.monto, g.detalle FROM gastos g JOIN vehiculos v ON g.vehiculo_id = v.id ORDER BY g.fecha DESC", conn)
        event = st.dataframe(df_edit, use_container_width=True, on_select="rerun", selection_mode="single-row", hide_index=True)
        if len(event.selection.rows) > 0:
            row = df_edit.iloc[event.selection.rows[0]]
            with st.form("edit_g"):
                n_m = st.number_input("Monto", value=float(row['monto']))
                if st.form_submit_button("Actualizar"):
                    cur = conn.cursor(); cur.execute("UPDATE gastos SET monto=%s WHERE id=%s", (n_m, int(row['id'])))
                    conn.commit(); st.rerun()

# --- MÓDULO: VENTAS ---
elif menu == "💰 Ventas":
    st.title("💰 Registro de Ventas")
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    with st.form("form_v"):
        v_sel = st.selectbox("Vehículo", v_data['placa'])
        v_id = v_data[v_data['placa'] == v_sel]['id'].values[0]
        cli = st.text_input("Cliente")
        val = st.number_input("Valor", min_value=0)
        fec = st.date_input("Fecha")
        if st.form_submit_button("Registrar"):
            cur = conn.cursor(); cur.execute("INSERT INTO ventas (vehiculo_id, cliente, valor_viaje, fecha) VALUES (%s,%s,%s,%s)", (int(v_id), cli, val, fec))
            conn.commit(); st.rerun()
    st.dataframe(pd.read_sql("SELECT v.placa, s.cliente, s.valor_viaje, s.fecha FROM ventas s JOIN vehiculos v ON s.vehiculo_id = v.id", conn), use_container_width=True)

# --- MÓDULO: FLOTA ---
elif menu == "🚐 Flota":
    st.title("🚐 Flota")
    with st.form("form_f"):
        p = st.text_input("Placa").upper()
        m = st.text_input("Marca")
        if st.form_submit_button("Añadir"):
            cur = conn.cursor(); cur.execute("INSERT INTO vehiculos (placa, marca) VALUES (%s,%s)", (p, m))
            conn.commit(); st.rerun()
    st.dataframe(pd.read_sql("SELECT * FROM vehiculos", conn), use_container_width=True)

# --- MÓDULO: HOJA DE VIDA ---
elif menu == "📑 Hoja de Vida":
    st.title("📑 Vencimientos")
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    v_sel = st.selectbox("Vehículo", v_data['placa'])
    v_id = v_data[v_data['placa'] == v_sel]['id'].values[0]
    
    with st.form("form_hv"):
        s_v = st.date_input("SOAT"); t_v = st.date_input("Tecno")
        if st.form_submit_button("Actualizar"):
            cur = conn.cursor()
            cur.execute("INSERT INTO hoja_vida (vehiculo_id, soat_vence, tecno_vence) VALUES (%s,%s,%s) ON CONFLICT (vehiculo_id) DO UPDATE SET soat_vence=EXCLUDED.soat_vence", (int(v_id), s_v, t_v))
            conn.commit(); st.rerun()

# --- MÓDULO: USUARIOS ---
elif menu == "⚙️ Usuarios":
    if st.session_state.u_rol == "admin":
        st.title("⚙️ Usuarios")
        with st.form("u"):
            un = st.text_input("Nombre"); us = st.text_input("User"); cl = st.text_input("Pass"); ro = st.selectbox("Rol", ["vendedor", "admin"])
            if st.form_submit_button("Crear"):
                cur = conn.cursor(); cur.execute("INSERT INTO usuarios (nombre, usuario, clave, rol) VALUES (%s,%s,%s,%s)", (un, us, cl, ro))
                conn.commit(); st.success("Creado")
        st.dataframe(pd.read_sql("SELECT nombre, usuario, rol FROM usuarios", conn))
    else:
        st.error("Acceso restringido a administradores.")

conn.close()
