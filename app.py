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
    conn = conectar_db(); cur = conn.cursor()
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
    
    columnas_extra = ["p_contractual", "p_extracontractual", "p_todoriesgo", "t_operaciones"]
    for col in columnas_extra:
        try: cur.execute(f"ALTER TABLE hoja_vida ADD COLUMN {col} DATE")
        except: conn.rollback()
    conn.commit(); conn.close()

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
        else: st.sidebar.error("Usuario o clave incorrectos")
    st.stop()

# --- 5. MENÚ ---
st.sidebar.write(f"👋 Bienvenid@, **{st.session_state.u_name}**")
st.sidebar.divider()
target = st.sidebar.number_input("🎯 Meta Utilidad ($)", value=5000000, step=500000)
menu = st.sidebar.selectbox("📂 MÓDULOS", ["📊 Dashboard", "🚐 Flota", "💸 Gastos", "💰 Ventas", "📑 Hoja de Vida", "⚙️ Usuarios"])
if st.sidebar.button("🚪 CERRAR SESIÓN"): st.session_state.logged_in = False; st.rerun()

conn = conectar_db()
v_query = pd.read_sql("SELECT id, placa FROM vehiculos", conn)

# --- MÓDULO: DASHBOARD ---
if menu == "📊 Dashboard":
    st.title("📊 Análisis de Operación y Utilidades")
    c1, c2 = st.columns(2)
    with c1: placa_f = st.selectbox("Seleccione Vehículo:", ["TODOS"] + v_query['placa'].tolist())
    with c2: rango = st.date_input("Rango de Fechas:", [datetime.now().date() - timedelta(days=30), datetime.now().date()])

    if len(rango) == 2:
        q_g = "SELECT g.fecha, v.placa, g.tipo_gasto as concepto, g.monto, g.detalle FROM gastos g JOIN vehiculos v ON g.vehiculo_id = v.id WHERE g.fecha BETWEEN %s AND %s"
        q_v = "SELECT s.fecha, v.placa, s.cliente, s.valor_viaje as monto, s.descripcion FROM ventas s JOIN vehiculos v ON s.vehiculo_id = v.id WHERE s.fecha BETWEEN %s AND %s"
        params = [rango[0], rango[1]]
        if placa_f != "TODOS":
            q_g += " AND v.placa = %s"; q_v += " AND v.placa = %s"; params.append(placa_f)
        
        df_g = pd.read_sql(q_g, conn, params=params if placa_f == "TODOS" else params + [placa_f])
        df_v = pd.read_sql(q_v, conn, params=params if placa_f == "TODOS" else params + [placa_f])

        utilidad_neta = df_v['monto'].sum() - df_g['monto'].sum()
        dif_meta = utilidad_neta - target

        if utilidad_neta >= target:
            st.success(f"### 🏆 ¡META ALCANZADA! \n Utilidad: **${utilidad_neta:,.0f}** | Superas por: **${dif_meta:,.0f}**"); st.balloons()
        else:
            st.error(f"### ⚠️ POR DEBAJO DE LA META \n Utilidad: **${utilidad_neta:,.0f}** | Faltan: **${abs(dif_meta):,.0f}**")

        m1, m2, m3 = st.columns(3)
        m1.metric("Ingresos", f"${df_v['monto'].sum():,.0f}"); m2.metric("Egresos", f"${df_g['monto'].sum():,.0f}", delta_color="inverse"); m3.metric("Utilidad", f"${utilidad_neta:,.0f}", delta=f"{dif_meta:,.0f}")
        
        res_g = df_g.groupby('placa')['monto'].sum().reset_index().rename(columns={'monto': 'Gasto'})
        res_v = df_v.groupby('placa')['monto'].sum().reset_index().rename(columns={'monto': 'Venta'})
        balance_df = pd.merge(res_v, res_g, on='placa', how='outer').fillna(0)
        st.plotly_chart(px.bar(balance_df, x='placa', y=['Venta', 'Gasto'], barmode='group'), use_container_width=True)
        st.download_button("📥 Excel", data=to_excel(balance_df, df_g, df_v), file_name="Reporte.xlsx")

# --- MÓDULO: FLOTA ---
elif menu == "🚐 Flota":
    st.title("🚐 Administración de Vehículos")
    with st.form("f_f"):
        c1, c2 = st.columns(2)
        p, m = c1.text_input("Placa").upper(), c1.text_input("Marca")
        mod, cond = c2.text_input("Modelo"), c2.text_input("Conductor")
        if st.form_submit_button("➕ Añadir Carro"):
            cur = conn.cursor(); cur.execute("INSERT INTO vehiculos (placa, marca, modelo, conductor) VALUES (%s,%s,%s,%s)", (p, m, mod, cond)); conn.commit(); st.rerun()
    
    st.subheader("✏️ Editor Maestro de Flota")
    df_f = pd.read_sql("SELECT id, placa, marca, modelo, conductor FROM vehiculos", conn)
    ed_f = st.data_editor(df_f, column_config={"id": None}, hide_index=True, use_container_width=True)
    if st.button("💾 Guardar Cambios en Flota"):
        cur = conn.cursor()
        for _, r in ed_f.iterrows():
            cur.execute("UPDATE vehiculos SET placa=%s, marca=%s, modelo=%s, conductor=%s WHERE id=%s", (r['placa'], r['marca'], r['modelo'], r['conductor'], int(r['id'])))
        conn.commit(); st.success("Flota actualizada"); st.rerun()

# --- MÓDULO: GASTOS ---
elif menu == "💸 Gastos":
    st.title("💸 Gestión de Gastos")
    with st.form("f_g"):
        v_sel = st.selectbox("Vehículo", v_query['placa'])
        tipo = st.selectbox("Concepto", ["Combustible", "Peaje", "Mantenimiento", "Lavada", "Viáticos", "Otros"])
        mon, fec, det = st.number_input("Valor"), st.date_input("Fecha"), st.text_input("Nota")
        if st.form_submit_button("💾 Guardar"):
            v_id = v_query[v_query['placa'] == v_sel]['id'].values[0]
            cur = conn.cursor(); cur.execute("INSERT INTO gastos (vehiculo_id, tipo_gasto, monto, fecha, detalle) VALUES (%s,%s,%s,%s,%s)", (int(v_id), tipo, mon, fec, det)); conn.commit(); st.rerun()
    
    st.subheader("✏️ Editor de Gastos")
    df_g_ed = pd.read_sql("SELECT g.id, v.placa, g.tipo_gasto, g.monto, g.fecha, g.detalle FROM gastos g JOIN vehiculos v ON g.vehiculo_id = v.id", conn)
    ed_g = st.data_editor(df_g_ed, column_config={"id": None, "placa": st.column_config.SelectboxColumn("Vehículo", options=v_query['placa'].tolist())}, hide_index=True, use_container_width=True)
    if st.button("💾 Guardar Cambios en Gastos"):
        cur = conn.cursor()
        for _, r in ed_g.iterrows():
            v_id_n = v_query[v_query['placa'] == r['placa']]['id'].values[0]
            cur.execute("UPDATE gastos SET vehiculo_id=%s, tipo_gasto=%s, monto=%s, fecha=%s, detalle=%s WHERE id=%s", (int(v_id_n), r['tipo_gasto'], r['monto'], r['fecha'], r['detalle'], int(r['id'])))
        conn.commit(); st.success("Gastos actualizados"); st.rerun()

# --- MÓDULO: VENTAS ---
elif menu == "💰 Ventas":
    st.title("💰 Gestión de Ventas")
    with st.form("f_v"):
        v_sel = st.selectbox("Vehículo", v_query['placa'])
        cli, val, fec, dsc = st.text_input("Cliente"), st.number_input("Valor"), st.date_input("Fecha"), st.text_input("Nota")
        if st.form_submit_button("💰 Registrar"):
            v_id = v_query[v_query['placa'] == v_sel]['id'].values[0]
            cur = conn.cursor(); cur.execute("INSERT INTO ventas (vehiculo_id, cliente, valor_viaje, fecha, descripcion) VALUES (%s,%s,%s,%s,%s)", (int(v_id), cli, val, fec, dsc)); conn.commit(); st.rerun()
    
    st.subheader("✏️ Editor de Ventas")
    df_v_ed = pd.read_sql("SELECT s.id, v.placa, s.cliente, s.valor_viaje as monto, s.fecha, s.descripcion FROM ventas s JOIN vehiculos v ON s.vehiculo_id = v.id", conn)
    ed_v = st.data_editor(df_v_ed, column_config={"id": None, "placa": st.column_config.SelectboxColumn("Vehículo", options=v_query['placa'].tolist())}, hide_index=True, use_container_width=True)
    if st.button("💾 Guardar Cambios en Ventas"):
        cur = conn.cursor()
        for _, r in ed_v.iterrows():
            v_id_n = v_query[v_query['placa'] == r['placa']]['id'].values[0]
            cur.execute("UPDATE ventas SET vehiculo_id=%s, cliente=%s, valor_viaje=%s, fecha=%s, descripcion=%s WHERE id=%s", (int(v_id_n), r['cliente'], r['monto'], r['fecha'], r['descripcion'], int(r['id'])))
        conn.commit(); st.success("Ventas sincronizadas"); st.rerun()

# --- MÓDULO: HOJA DE VIDA ---
elif menu == "📑 Hoja de Vida":
    st.title("📑 Documentación y Alertas")
    with st.expander("📅 Actualizar Fechas"):
        with st.form("f_hv"):
            v_sel = st.selectbox("Vehículo", v_query['placa'])
            v_id = v_query[v_query['placa'] == v_sel]['id'].values[0]
            c1, c2 = st.columns(2)
            s_v, t_v, p_v = c1.date_input("SOAT"), c1.date_input("Tecno"), c1.date_input("Preventivo")
            pc_v, pe_v, ptr_v, to_v = c2.date_input("Contractual"), c2.date_input("Extra"), c2.date_input("Todo Riesgo"), st.date_input("T. Operaciones")
            if st.form_submit_button("🔄 Actualizar"):
                cur = conn.cursor(); cur.execute("INSERT INTO hoja_vida (vehiculo_id, soat_vence, tecno_vence, prev_vence, p_contractual, p_extracontractual, p_todoriesgo, t_operaciones) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (vehiculo_id) DO UPDATE SET soat_vence=EXCLUDED.soat_vence, tecno_vence=EXCLUDED.tecno_vence, prev_vence=EXCLUDED.prev_vence, p_contractual=EXCLUDED.p_contractual, p_extracontractual=EXCLUDED.p_extracontractual, p_todoriesgo=EXCLUDED.p_todoriesgo, t_operaciones=EXCLUDED.t_operaciones", (int(v_id), s_v, t_v, p_v, pc_v, pe_v, ptr_v, to_v)); conn.commit(); st.rerun()

    df_hv = pd.read_sql("SELECT v.placa, h.* FROM vehiculos v LEFT JOIN hoja_vida h ON v.id = h.vehiculo_id", conn)
    hoy = datetime.now().date()
    for _, r in df_hv.iterrows():
        st.subheader(f"Vehículo: {r['placa']}")
        cols = st.columns(4)
        docs = [("SOAT", r['soat_vence']), ("TECNO", r['tecno_vence']), ("PREV", r['prev_vence']), ("T.OPER", r['t_operaciones']), ("POL. CONT", r['p_contractual']), ("POL. EXTRA", r['p_extracontractual']), ("TODO RIESGO", r['p_todoriesgo'])]
        for i, (n, f) in enumerate(docs):
            if f:
                d = (f - hoy).days
                if d < 0: cols[i%4].error(f"❌ {n} VENCIDO")
                elif d <= 15: cols[i%4].warning(f"⚠️ {n} ({d} d)")
                else: cols[i%4].success(f"✅ {n} OK")
            else: cols[i%4].info(f"⚪ {n}: S/D")

# --- MÓDULO: USUARIOS ---
elif menu == "⚙️ Usuarios" and st.session_state.u_rol == "admin":
    st.title("⚙️ Gestión de Personal")
    with st.form("f_u"):
        nom, usr, clv, rol = st.text_input("Nombre"), st.text_input("Usuario"), st.text_input("Clave"), st.selectbox("Rol", ["vendedor", "admin"])
        if st.form_submit_button("👤 Crear"):
            cur = conn.cursor(); cur.execute("INSERT INTO usuarios (nombre, usuario, clave, rol) VALUES (%s,%s,%s,%s)", (nom, usr, clv, rol)); conn.commit(); st.rerun()
    st.dataframe(pd.read_sql("SELECT nombre, usuario, rol FROM usuarios", conn), use_container_width=True)

conn.close()
