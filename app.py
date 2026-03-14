import streamlit as st
import psycopg2
import pandas as pd
from datetime import datetime, timedelta
import io
import plotly.express as px

# --- 1. CONFIGURACIÓN Y DB ---
DB_URL = "postgresql://neondb_owner:npg_c7Dkwlh1jzGQ@ep-lucky-shadow-ac1thtiq-pooler.sa-east-1.aws.neon.tech/neondb?sslmode=require"

def conectar_db():
    return psycopg2.connect(DB_URL)

def inicializar_db():
    conn = conectar_db(); cur = conn.cursor()
    cur.execute('CREATE TABLE IF NOT EXISTS vehiculos (id SERIAL PRIMARY KEY, placa TEXT UNIQUE NOT NULL, marca TEXT, modelo TEXT, conductor TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS gastos (id SERIAL PRIMARY KEY, vehiculo_id INTEGER REFERENCES vehiculos(id), tipo_gasto TEXT, monto NUMERIC, fecha DATE, detalle TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS ventas (id SERIAL PRIMARY KEY, vehiculo_id INTEGER REFERENCES vehiculos(id), cliente TEXT, valor_viaje NUMERIC, fecha DATE, descripcion TEXT)')
    cur.execute('''CREATE TABLE IF NOT EXISTS hoja_vida (
                    id SERIAL PRIMARY KEY, vehiculo_id UNIQUE REFERENCES vehiculos(id), 
                    soat_vence DATE, tecno_vence DATE, prev_vence DATE,
                    p_contractual DATE, p_extracontractual DATE, p_todoriesgo DATE, t_operaciones DATE)''')
    cur.execute('CREATE TABLE IF NOT EXISTS usuarios (id SERIAL PRIMARY KEY, nombre TEXT, usuario TEXT UNIQUE NOT NULL, clave TEXT NOT NULL, rol TEXT DEFAULT "vendedor")')
    cur.execute("INSERT INTO usuarios (nombre, usuario, clave, rol) VALUES ('Jacobo Admin', 'admin', 'Jacobo2026', 'admin') ON CONFLICT (usuario) DO NOTHING")
    conn.commit(); conn.close()

def to_excel(df_balance, df_g, df_v):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_balance.to_excel(writer, index=False, sheet_name='Balance')
        df_g.to_excel(writer, index=False, sheet_name='Gastos')
        df_v.to_excel(writer, index=False, sheet_name='Ventas')
    return output.getvalue()

st.set_page_config(page_title="C&E Eficiencias", layout="wide")
inicializar_db()

# --- 2. SESIÓN Y LOGIN ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.sidebar.title("🔐 Acceso")
    u = st.sidebar.text_input("Usuario")
    p = st.sidebar.text_input("Clave", type="password")
    if st.sidebar.button("Entrar"):
        conn = conectar_db(); cur = conn.cursor()
        cur.execute("SELECT nombre, rol FROM usuarios WHERE usuario = %s AND clave = %s", (u, p))
        res = cur.fetchone(); conn.close()
        if res:
            st.session_state.logged_in = True
            st.session_state.u_name, st.session_state.u_rol = res[0], res[1]
            st.rerun()
        else: st.sidebar.error("Error de credenciales")
    st.stop()

# --- 3. MENÚ LATERAL ---
st.sidebar.write(f"👤 {st.session_state.u_name} ({st.session_state.u_rol})")
st.sidebar.divider()
meta = st.sidebar.number_input("🎯 Meta Utilidad ($)", value=5000000, step=100000)
menu = st.sidebar.selectbox("📂 Menú", ["📊 Dashboard", "🚐 Flota", "💸 Gastos", "💰 Ventas", "📑 Hoja de Vida", "⚙️ Usuarios"])

if st.sidebar.button("🚪 Salir"):
    st.session_state.logged_in = False; st.rerun()

# --- 4. MÓDULOS ---

# --- DASHBOARD ---
if menu == "📊 Dashboard":
    st.title("📊 Control Operativo")
    conn = conectar_db()
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    
    c1, c2 = st.columns(2)
    with c1:
        placa_sel = st.selectbox("Vehículo:", ["TODOS"] + v_data['placa'].tolist())
    with c2:
        rango = st.date_input("Fechas:", [datetime.now().date() - timedelta(days=30), datetime.now().date()])

    if len(rango) == 2:
        # Gastos
        q_g = "SELECT g.id, g.fecha, v.placa, g.tipo_gasto, g.monto, g.detalle FROM gastos g JOIN vehiculos v ON g.vehiculo_id = v.id WHERE g.fecha BETWEEN %s AND %s"
        # Ventas
        q_v = "SELECT s.id, s.fecha, v.placa, s.cliente, s.valor_viaje as monto, s.descripcion FROM ventas s JOIN vehiculos v ON s.vehiculo_id = v.id WHERE s.fecha BETWEEN %s AND %s"
        params = [rango[0], rango[1]]
        
        if placa_sel != "TODOS":
            q_g += " AND v.placa = %s"; q_v += " AND v.placa = %s"
            params.append(placa_sel)
        
        df_g = pd.read_sql(q_g, conn, params=params)
        df_v = pd.read_sql(q_v, conn, params=params)

        # Totales
        total_v = df_v['monto'].sum()
        total_g = df_g['monto'].sum()
        utilidad = total_v - total_g

        if utilidad >= meta: st.success(f"🏆 ¡Meta superada! Utilidad: ${utilidad:,.0f}"); st.balloons()
        else: st.warning(f"📉 Debajo de la meta. Falta: ${meta - utilidad:,.0f}")

        m1, m2, m3 = st.columns(3)
        m1.metric("Ingresos", f"${total_v:,.0f}")
        m2.metric("Gastos", f"${total_g:,.0f}")
        m3.metric("Utilidad", f"${utilidad:,.0f}")

        # Gráfico
        st.subheader("📈 Comparativa por Placa")
        res_g = df_g.groupby('placa')['monto'].sum().reset_index().rename(columns={'monto': 'Gasto'})
        res_v = df_v.groupby('placa')['monto'].sum().reset_index().rename(columns={'monto': 'Venta'})
        balance = pd.merge(res_v, res_g, on='placa', how='outer').fillna(0)
        balance['Utilidad'] = balance['Venta'] - balance['Gasto']
        
        fig = px.bar(balance, x='placa', y=['Venta', 'Gasto'], barmode='group', title="Ventas vs Gastos por Vehículo")
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("📋 Detalle de Movimientos")
        st.dataframe(df_g if not df_g.empty else "Sin gastos", use_container_width=True)
        
        st.download_button("📥 Enviar a Excel", data=to_excel(balance, df_g, df_v), file_name="Reporte_CE.xlsx")
    conn.close()

# --- GASTOS ---
elif menu == "💸 Gastos":
    st.title("💸 Registro de Gastos")
    conn = conectar_db(); v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    
    with st.form("nuevo_gasto"):
        v_id = v_data[v_data['placa'] == st.selectbox("Vehículo", v_data['placa'])]['id'].values[0]
        tipo = st.selectbox("Concepto", ["Combustible", "Peaje", "Mantenimiento", "Lavada", "Viáticos", "Otros"])
        monto = st.number_input("Monto", min_value=0); fecha = st.date_input("Fecha"); det = st.text_input("Detalle")
        if st.form_submit_button("Guardar Gasto"):
            cur = conn.cursor(); cur.execute("INSERT INTO gastos (vehiculo_id, tipo_gasto, monto, fecha, detalle) VALUES (%s,%s,%s,%s,%s)", (int(v_id), tipo, monto, fecha, det))
            conn.commit(); st.success("Registrado"); st.rerun()

    df_edit = pd.read_sql("SELECT g.id, g.fecha, v.placa, g.tipo_gasto, g.monto, g.detalle FROM gastos g JOIN vehiculos v ON g.vehiculo_id = v.id ORDER BY g.fecha DESC", conn)
    sel = st.dataframe(df_edit, use_container_width=True, on_select="rerun", selection_mode="single-row")
    
    if len(sel.selection.rows) > 0:
        row = df_edit.iloc[sel.selection.rows[0]]
        with st.form("edit_g"):
            new_m = st.number_input("Monto", value=float(row['monto']))
            if st.form_submit_button("Actualizar"):
                cur = conn.cursor(); cur.execute("UPDATE gastos SET monto=%s WHERE id=%s", (new_m, int(row['id'])))
                conn.commit(); st.rerun()
            if st.form_submit_button("🗑️ Eliminar"):
                cur = conn.cursor(); cur.execute("DELETE FROM gastos WHERE id=%s", (int(row['id']),))
                conn.commit(); st.rerun()
    conn.close()

# --- VENTAS ---
elif menu == "💰 Ventas":
    st.title("💰 Registro de Ventas")
    conn = conectar_db(); v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    with st.form("nueva_v"):
        v_id = v_data[v_data['placa'] == st.selectbox("Vehículo", v_data['placa'])]['id'].values[0]
        cli = st.text_input("Cliente"); val = st.number_input("Valor Viaje", min_value=0); fec = st.date_input("Fecha"); dsc = st.text_input("Descripción")
        if st.form_submit_button("Guardar Venta"):
            cur = conn.cursor(); cur.execute("INSERT INTO ventas (vehiculo_id, cliente, valor_viaje, fecha, descripcion) VALUES (%s,%s,%s,%s,%s)", (int(v_id), cli, val, fec, dsc))
            conn.commit(); st.success("Venta guardada"); st.rerun()
    conn.close()

# --- FLOTA ---
elif menu == "🚐 Flota":
    st.title("🚐 Control de Flota")
    with st.form("f"):
        p = st.text_input("Placa").upper(); m = st.text_input("Marca"); mod = st.text_input("Modelo"); c = st.text_input("Conductor")
        if st.form_submit_button("Añadir Vehículo"):
            conn = conectar_db(); cur = conn.cursor()
            cur.execute("INSERT INTO vehiculos (placa, marca, modelo, conductor) VALUES (%s,%s,%s,%s)", (p, m, mod, c))
            conn.commit(); conn.close(); st.rerun()

# --- USUARIOS ---
elif menu == "⚙️ Usuarios" and st.session_state.u_rol == "admin":
    st.title("⚙️ Gestión de Usuarios")
    with st.form("u"):
        nom = st.text_input("Nombre Full"); usr = st.text_input("Usuario"); clv = st.text_input("Clave"); rol = st.selectbox("Rol", ["vendedor", "admin"])
        if st.form_submit_button("Crear"):
            conn = conectar_db(); cur = conn.cursor()
            cur.execute("INSERT INTO usuarios (nombre, usuario, clave, rol) VALUES (%s,%s,%s,%s)", (nom, usr, clv, rol))
            conn.commit(); conn.close(); st.success("Usuario creado")
