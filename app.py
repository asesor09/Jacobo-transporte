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

# --- 4. SISTEMA DE LOGIN ---
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
            st.session_state.logged_in = True
            st.session_state.u_name, st.session_state.u_rol = res[0], res[1]
            st.rerun()
        else: st.sidebar.error("Usuario o clave incorrectos")
    st.stop()

# --- 5. MENÚ ---
st.sidebar.write(f"👋 Bienvenid@, **{st.session_state.u_name}**")
menu = st.sidebar.selectbox("📂 MÓDULOS", ["📊 Dashboard", "🚐 Flota", "💸 Gastos", "💰 Ventas", "📑 Hoja de Vida", "⚙️ Usuarios"])
if st.sidebar.button("🚪 CERRAR SESIÓN"): st.session_state.logged_in = False; st.rerun()

conn = conectar_db()

# --- MÓDULO: GASTOS (CON EDICIÓN TOTAL) ---
if menu == "💸 Gastos":
    st.title("💸 Registro y Control de Gastos")
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    tab1, tab2 = st.tabs(["📝 Nuevo Gasto", "✏️ Editar Registros"])

    with tab1:
        with st.form("f_g"):
            v_sel = st.selectbox("Vehículo", v_data['placa'])
            tipo = st.selectbox("Concepto", ["Combustible", "Peaje", "Mantenimiento", "Lavada", "Viáticos", "Otros"])
            monto = st.number_input("Valor ($)", min_value=0)
            fecha = st.date_input("Fecha")
            det = st.text_input("Detalle")
            if st.form_submit_button("💾 Guardar Gasto"):
                v_id = v_data[v_data['placa'] == v_sel]['id'].values[0]
                cur = conn.cursor()
                cur.execute("INSERT INTO gastos (vehiculo_id, tipo_gasto, monto, fecha, detalle) VALUES (%s,%s,%s,%s,%s)", (int(v_id), tipo, monto, fecha, det))
                conn.commit(); st.success("Registrado"); st.rerun()

    with tab2:
        st.subheader("Editor Maestro de Gastos")
        # Obtenemos los datos con la placa para que el usuario entienda, pero guardamos el ID oculto
        df_g = pd.read_sql("SELECT g.id, v.placa, g.tipo_gasto, g.monto, g.fecha, g.detalle FROM gastos g JOIN vehiculos v ON g.vehiculo_id = v.id ORDER BY g.fecha DESC", conn)
        
        # El data_editor permite editar CUALQUIER campo
        edited_df = st.data_editor(df_g, key="editor_gastos", hide_index=True, use_container_width=True,
                                   column_config={
                                       "placa": st.column_config.SelectboxColumn("Vehículo", options=v_data['placa'].tolist(), required=True),
                                       "tipo_gasto": st.column_config.SelectboxColumn("Concepto", options=["Combustible", "Peaje", "Mantenimiento", "Lavada", "Viáticos", "Otros"]),
                                       "monto": st.column_config.NumberColumn("Valor ($)", min_value=0),
                                       "fecha": st.column_config.DateColumn("Fecha"),
                                       "id": None # Ocultamos el ID
                                   })

        if st.button("💾 Guardar todos los cambios en Gastos"):
            cur = conn.cursor()
            for index, row in edited_df.iterrows():
                # Buscamos el ID real del vehículo por la placa seleccionada
                v_id_new = v_data[v_data['placa'] == row['placa']]['id'].values[0]
                cur.execute("""UPDATE gastos SET vehiculo_id=%s, tipo_gasto=%s, monto=%s, fecha=%s, detalle=%s 
                               WHERE id=%s""", (int(v_id_new), row['tipo_gasto'], row['monto'], row['fecha'], row['detalle'], int(row['id'])))
            conn.commit(); st.success("Base de datos actualizada correctamente"); st.rerun()

# --- MÓDULO: VENTAS (CON EDICIÓN TOTAL) ---
elif menu == "💰 Ventas":
    st.title("💰 Control de Ingresos")
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    tab1, tab2 = st.tabs(["💰 Registrar Venta", "✏️ Editar Ventas"])

    with tab1:
        with st.form("f_v"):
            v_sel = st.selectbox("Vehículo", v_data['placa'])
            cli = st.text_input("Cliente / Empresa")
            val = st.number_input("Valor del Viaje", min_value=0)
            fec = st.date_input("Fecha")
            dsc = st.text_input("Descripción")
            if st.form_submit_button("💰 Guardar Venta"):
                v_id = v_data[v_data['placa'] == v_sel]['id'].values[0]
                cur = conn.cursor()
                cur.execute("INSERT INTO ventas (vehiculo_id, cliente, valor_viaje, fecha, descripcion) VALUES (%s,%s,%s,%s,%s)", (int(v_id), cli, val, fec, dsc))
                conn.commit(); st.success("Venta registrada"); st.rerun()

    with tab2:
        df_v = pd.read_sql("SELECT s.id, v.placa, s.cliente, s.valor_viaje, s.fecha, s.descripcion FROM ventas s JOIN vehiculos v ON s.vehiculo_id = v.id ORDER BY s.fecha DESC", conn)
        edited_v = st.data_editor(df_v, key="editor_ventas", hide_index=True, use_container_width=True,
                                  column_config={
                                      "placa": st.column_config.SelectboxColumn("Vehículo", options=v_data['placa'].tolist(), required=True),
                                      "valor_viaje": st.column_config.NumberColumn("Valor ($)", min_value=0),
                                      "id": None
                                  })

        if st.button("💾 Guardar todos los cambios en Ventas"):
            cur = conn.cursor()
            for index, row in edited_v.iterrows():
                v_id_new = v_data[v_data['placa'] == row['placa']]['id'].values[0]
                cur.execute("""UPDATE ventas SET vehiculo_id=%s, cliente=%s, valor_viaje=%s, fecha=%s, descripcion=%s 
                               WHERE id=%s""", (int(v_id_new), row['cliente'], row['valor_viaje'], row['fecha'], row['descripcion'], int(row['id'])))
            conn.commit(); st.success("Ventas actualizadas"); st.rerun()

# --- MANTENER LOS DEMÁS MÓDULOS (Dashboard, Flota, Hoja de Vida, Usuarios) ---
# ... (Se mantiene el código original para los otros módulos)
elif menu == "📊 Dashboard":
    # (Tu código original de Dashboard aquí)
    pass
elif menu == "🚐 Flota":
    # (Tu código original de Flota aquí)
    pass

conn.close()
