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
    # Tabla Hoja de Vida (COMPLETA)
    cur.execute('''CREATE TABLE IF NOT EXISTS hoja_vida (
                    id SERIAL PRIMARY KEY, 
                    vehiculo_id INTEGER UNIQUE REFERENCES vehiculos(id), 
                    soat_vence DATE, tecno_vence DATE, prev_vence DATE,
                    p_contractual DATE, p_extracontractual DATE, p_todoriesgo DATE, t_operaciones DATE)''')
    # Tabla de Usuarios
    cur.execute('CREATE TABLE IF NOT EXISTS usuarios (id SERIAL PRIMARY KEY, nombre TEXT, usuario TEXT UNIQUE NOT NULL, clave TEXT NOT NULL, rol TEXT DEFAULT "vendedor")')
    cur.execute("INSERT INTO usuarios (nombre, usuario, clave, rol) VALUES ('Jacobo Admin', 'admin', 'Jacobo2026', 'admin') ON CONFLICT (usuario) DO NOTHING")
    
    # Asegurar que las columnas nuevas existan (Soporte para actualizaciones de tabla)
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

# --- 6. CONEXIÓN GLOBAL PARA MÓDULOS ---
conn = conectar_db()

# --- MÓDULO: DASHBOARD ---
if menu == "📊 Dashboard":
    st.title("📊 Análisis de Operación y Utilidades")
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    c1, c2 = st.columns(2)
    with c1: placa_f = st.selectbox("Vehículo:", ["TODOS"] + v_data['placa'].tolist())
    with c2: rango = st.date_input("Rango de Fechas:", [datetime.now().date() - timedelta(days=30), datetime.now().date()])

    if len(rango) == 2:
        q_g = "SELECT g.fecha, v.placa, g.tipo_gasto as concepto, g.monto, g.detalle FROM gastos g JOIN vehiculos v ON g.vehiculo_id = v.id WHERE g.fecha BETWEEN %s AND %s"
        q_v = "SELECT s.fecha, v.placa, s.cliente, s.valor_viaje as monto, s.descripcion FROM ventas s JOIN vehiculos v ON s.vehiculo_id = v.id WHERE s.fecha BETWEEN %s AND %s"
        params = [rango[0], rango[1]]
        if placa_f != "TODOS":
            q_g += " AND v.placa = %s"; q_v += " AND v.placa = %s"
            params.append(placa_f)

        df_g = pd.read_sql(q_g, conn, params=params if placa_f == "TODOS" else params + [placa_f])
        df_v = pd.read_sql(q_v, conn, params=params if placa_f == "TODOS" else params + [placa_f])

        utilidad = df_v['monto'].sum() - df_g['monto'].sum()
        dif_meta = utilidad - target

        if utilidad >= target: st.success(f"### 🏆 META ALCANZADA: ${utilidad:,.0f}"); st.balloons()
        else: st.error(f"### ⚠️ FALTAN: ${abs(dif_meta):,.0f} para la meta")

        m1, m2, m3 = st.columns(3)
        m1.metric("Ingresos", f"${df_v['monto'].sum():,.0f}")
        m2.metric("Egresos", f"${df_g['monto'].sum():,.0f}", delta_color="inverse")
        m3.metric("Utilidad", f"${utilidad:,.0f}", delta=f"{dif_meta:,.0f}")

        # Gráfico
        res_g = df_g.groupby('placa')['monto'].sum().reset_index().rename(columns={'monto': 'Gasto'})
        res_v = df_v.groupby('placa')['monto'].sum().reset_index().rename(columns={'monto': 'Venta'})
        balance_df = pd.merge(res_v, res_g, on='placa', how='outer').fillna(0)
        st.plotly_chart(px.bar(balance_df, x='placa', y=['Venta', 'Gasto'], barmode='group', color_discrete_map={'Venta':'#2ecc71','Gasto':'#e74c3c'}))

# --- MÓDULO: GASTOS ---
elif menu == "💸 Gastos":
    st.title("💸 Registro de Gastos")
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    t1, t2 = st.tabs(["📝 Nuevo Gasto", "✏️ Gestionar"])
    with t1:
        with st.form("fg"):
            v_sel = st.selectbox("Vehículo", v_data['placa'])
            tipo = st.selectbox("Concepto", ["Combustible", "Peaje", "Mantenimiento", "Lavada", "Viáticos", "Otros"])
            monto = st.number_input("Valor", min_value=0)
            fecha = st.date_input("Fecha")
            det = st.text_input("Detalle")
            if st.form_submit_button("Guardar"):
                v_id = v_data[v_data['placa'] == v_sel]['id'].values[0]
                cur = conn.cursor(); cur.execute("INSERT INTO gastos (vehiculo_id, tipo_gasto, monto, fecha, detalle) VALUES (%s,%s,%s,%s,%s)", (int(v_id), tipo, monto, fecha, det))
                conn.commit(); st.rerun()
    with t2:
        df_list = pd.read_sql("SELECT g.id, g.fecha, v.placa, g.tipo_gasto, g.monto, g.detalle FROM gastos g JOIN vehiculos v ON g.vehiculo_id = v.id ORDER BY g.fecha DESC", conn)
        event = st.dataframe(df_list, use_container_width=True, on_select="rerun", selection_mode="single-row", hide_index=True)
        if len(event.selection.rows) > 0:
            row = df_list.iloc[event.selection.rows[0]]
            if st.button(f"Eliminar Gasto ID {row['id']}"):
                cur = conn.cursor(); cur.execute("DELETE FROM gastos WHERE id=%s", (int(row['id']),)); conn.commit(); st.rerun()

# --- MÓDULO: VENTAS ---
elif menu == "💰 Ventas":
    st.title("💰 Ingresos por Viajes")
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    with st.form("fv"):
        v_sel = st.selectbox("Vehículo", v_data['placa'])
        cli = st.text_input("Cliente")
        val = st.number_input("Valor del Viaje", min_value=0)
        fec = st.date_input("Fecha")
        dsc = st.text_input("Descripción")
        if st.form_submit_button("Registrar Venta"):
            v_id = v_data[v_data['placa'] == v_sel]['id'].values[0]
            cur = conn.cursor(); cur.execute("INSERT INTO ventas (vehiculo_id, cliente, valor_viaje, fecha, descripcion) VALUES (%s,%s,%s,%s,%s)", (int(v_id), cli, val, fec, dsc))
            conn.commit(); st.rerun()
    st.dataframe(pd.read_sql("SELECT v.placa, s.cliente, s.valor_viaje, s.fecha, s.descripcion FROM ventas s JOIN vehiculos v ON s.vehiculo_id = v.id ORDER BY s.fecha DESC", conn), use_container_width=True)

# --- MÓDULO: FLOTA ---
elif menu == "🚐 Flota":
    st.title("🚐 Administración de Vehículos")
    with st.form("ff"):
        p = st.text_input("Placa").upper(); m = st.text_input("Marca"); mod = st.text_input("Modelo"); cond = st.text_input("Conductor")
        if st.form_submit_button("Añadir Carro"):
            cur = conn.cursor(); cur.execute("INSERT INTO vehiculos (placa, marca, modelo, conductor) VALUES (%s,%s,%s,%s)", (p, m, mod, cond)); conn.commit(); st.rerun()
    st.dataframe(pd.read_sql("SELECT placa, marca, modelo, conductor FROM vehiculos", conn), use_container_width=True)

# --- MÓDULO: HOJA DE VIDA (RESTAURADO) ---
elif menu == "📑 Hoja de Vida":
    st.title("📑 Documentación y Vencimientos")
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    
    with st.expander("📅 Actualizar Fechas de Vencimiento"):
        with st.form("fhv"):
            v_sel = st.selectbox("Vehículo", v_data['placa'])
            c1, c2 = st.columns(2)
            s_v = c1.date_input("SOAT"); t_v = c1.date_input("Tecno"); p_v = c1.date_input("Preventivo")
            pc_v = c2.date_input("Póliza Contractual"); pe_v = c2.date_input("Póliza Extracontractual")
            ptr_v = c2.date_input("Póliza Todo Riesgo"); to_v = st.date_input("Tarjeta de Operaciones")
            if st.form_submit_button("🔄 Actualizar"):
                v_id = v_data[v_data['placa'] == v_sel]['id'].values[0]
                cur = conn.cursor()
                cur.execute('''INSERT INTO hoja_vida (vehiculo_id, soat_vence, tecno_vence, prev_vence, p_contractual, p_extracontractual, p_todoriesgo, t_operaciones) 
                               VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (vehiculo_id) DO UPDATE SET 
                               soat_vence=EXCLUDED.soat_vence, tecno_vence=EXCLUDED.tecno_vence, prev_vence=EXCLUDED.prev_vence,
                               p_contractual=EXCLUDED.p_contractual, p_extracontractual=EXCLUDED.p_extracontractual, 
                               p_todoriesgo=EXCLUDED.p_todoriesgo, t_operaciones=EXCLUDED.t_operaciones''', (int(v_id), s_v, t_v, p_v, pc_v, pe_v, ptr_v, to_v))
                conn.commit(); st.success("Vencimientos actualizados"); st.rerun()

    df_hv = pd.read_sql('''SELECT v.placa, h.soat_vence, h.tecno_vence, h.prev_vence, h.p_contractual, h.p_extracontractual, h.p_todoriesgo, h.t_operaciones 
                           FROM vehiculos v LEFT JOIN hoja_vida h ON v.id = h.vehiculo_id''', conn)
    hoy = datetime.now().date()
    for _, row in df_hv.iterrows():
        st.subheader(f"Vehículo: {row['placa']}")
        cols = st.columns(4)
        docs = [("SOAT", row['soat_vence']), ("TECNO", row['tecno_vence']), ("PREV", row['prev_vence']), ("T.OPER", row['t_operaciones']),
                ("POL. CONT", row['p_contractual']), ("POL. EXTRA", row['p_extracontractual']), ("TODO RIESGO", row['p_todoriesgo'])]
        for i, (name, fecha) in enumerate(docs):
            if fecha:
                dias = (fecha - hoy).days
                if dias < 0: cols[i%4].error(f"❌ {name} VENCIDO")
                elif dias <= 15: cols[i%4].warning(f"⚠️ {name} ({dias} días)")
                else: cols[i%4].success(f"✅ {name} OK")
            else: cols[i%4].info(f"⚪ {name}: Sin fecha")

# --- MÓDULO: USUARIOS ---
elif menu == "⚙️ Usuarios" and st.session_state.u_rol == "admin":
    st.title("⚙️ Gestión de Personal")
    with st.form("fu"):
        nom = st.text_input("Nombre"); usr = st.text_input("Usuario"); clv = st.text_input("Clave"); rol = st.selectbox("Rol", ["vendedor", "admin"])
        if st.form_submit_button("👤 Crear Usuario"):
            cur = conn.cursor(); cur.execute("INSERT INTO usuarios (nombre, usuario, clave, rol) VALUES (%s,%s,%s,%s)", (nom, usr, clv, rol)); conn.commit(); st.success("Usuario creado")
    st.dataframe(pd.read_sql("SELECT nombre, usuario, rol FROM usuarios", conn), use_container_width=True)

conn.close()
