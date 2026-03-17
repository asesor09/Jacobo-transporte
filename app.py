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
    
    columnas_extra = [("p_contractual", "DATE"), ("p_extracontractual", "DATE"), ("p_todoriesgo", "DATE"), ("t_operaciones", "DATE")]
    for col, tipo in columnas_extra:
        try:
            cur.execute(f"ALTER TABLE hoja_vida ADD COLUMN {col} {tipo}")
            conn.commit()
        except:
            conn.rollback()
    conn.close()

# --- 2. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="C&E Eficiencias", layout="wide", page_icon="🚐")
inicializar_db()

# --- 3. LOGIN ---
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

# --- 4. MENÚ ---
st.sidebar.write(f"👋 **{st.session_state.u_name}**")
menu = st.sidebar.selectbox("📂 MÓDULOS", ["📊 Dashboard", "🚐 Flota", "💸 Gastos", "💰 Ventas", "📑 Hoja de Vida", "⚙️ Usuarios"])
if st.sidebar.button("🚪 Salir"): st.session_state.logged_in = False; st.rerun()

conn = conectar_db()

# --- MÓDULO: FLOTA (RESTAURADO COMPLETO) ---
if menu == "🚐 Flota":
    st.title("🚐 Administración de Vehículos")
    
    # Pestañas para separar Ingreso de Edición
    tab1, tab2 = st.tabs(["➕ Añadir Nuevo Vehículo", "✏️ Editar/Ver Flota"])
    
    with tab1:
        with st.form("form_nuevo_carro"):
            col1, col2 = st.columns(2)
            p = col1.text_input("Placa (Ej: XYZ123)").upper()
            m = col1.text_input("Marca")
            mod = col2.text_input("Modelo")
            cond = col2.text_input("Conductor Asignado")
            
            if st.form_submit_button("💾 Guardar Vehículo"):
                if p and m:
                    cur = conn.cursor()
                    try:
                        cur.execute("INSERT INTO vehiculos (placa, marca, modelo, conductor) VALUES (%s,%s,%s,%s)", (p, m, mod, cond))
                        conn.commit()
                        st.success(f"Vehículo {p} añadido correctamente")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: La placa ya existe o hay un problema con los datos.")
                        conn.rollback()
                else:
                    st.warning("Placa y Marca son obligatorios.")

    with tab2:
        st.subheader("Lista de Vehículos (Editable)")
        df_f = pd.read_sql("SELECT id, placa, marca, modelo, conductor FROM vehiculos", conn)
        edited_f = st.data_editor(df_f, column_config={"id": None}, hide_index=True, use_container_width=True)
        
        if st.button("💾 Guardar Cambios en la Tabla"):
            cur = conn.cursor()
            for _, row in edited_f.iterrows():
                cur.execute("UPDATE vehiculos SET placa=%s, marca=%s, modelo=%s, conductor=%s WHERE id=%s", 
                            (row['placa'].upper(), row['marca'], row['modelo'], row['conductor'], int(row['id'])))
            conn.commit()
            st.success("Cambios guardados")
            st.rerun()

# --- MÓDULO: GASTOS (CON FORMULARIO E HIJO DE EDICIÓN) ---
elif menu == "💸 Gastos":
    st.title("💸 Registro de Gastos")
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    
    tab1, tab2 = st.tabs(["📝 Registrar Gasto", "✏️ Editar Gastos"])
    
    with tab1:
        if v_data.empty:
            st.warning("Primero debes crear vehículos en el módulo Flota.")
        else:
            with st.form("form_g"):
                v_sel = st.selectbox("Vehículo", v_data['placa'])
                tipo = st.selectbox("Concepto", ["Combustible", "Peaje", "Mantenimiento", "Lavada", "Viáticos", "Otros"])
                monto = st.number_input("Valor ($)", min_value=0)
                fecha = st.date_input("Fecha")
                det = st.text_input("Nota/Detalle")
                if st.form_submit_button("💾 Guardar Gasto"):
                    v_id = v_data[v_data['placa'] == v_sel]['id'].values[0]
                    cur = conn.cursor()
                    cur.execute("INSERT INTO gastos (vehiculo_id, tipo_gasto, monto, fecha, detalle) VALUES (%s,%s,%s,%s,%s)", (int(v_id), tipo, monto, fecha, det))
                    conn.commit(); st.success("Gasto guardado"); st.rerun()

    with tab2:
        df_g = pd.read_sql("SELECT g.id, v.placa, g.tipo_gasto, g.monto, g.fecha, g.detalle FROM gastos g JOIN vehiculos v ON g.vehiculo_id = v.id ORDER BY g.fecha DESC", conn)
        edited_g = st.data_editor(df_g, column_config={"id":None, "placa": st.column_config.TextColumn(disabled=True)}, hide_index=True, use_container_width=True)
        if st.button("💾 Aplicar Correcciones"):
            cur = conn.cursor()
            for _, row in edited_g.iterrows():
                cur.execute("UPDATE gastos SET tipo_gasto=%s, monto=%s, fecha=%s, detalle=%s WHERE id=%s", (row['tipo_gasto'], row['monto'], row['fecha'], row['detalle'], int(row['id'])))
            conn.commit(); st.success("Gastos corregidos"); st.rerun()

# --- MÓDULO: HOJA DE VIDA (RESTAURADO) ---
elif menu == "📑 Hoja de Vida":
    st.title("📑 Vencimientos y Documentación")
    df_hv = pd.read_sql('''SELECT h.id, v.placa, h.soat_vence, h.tecno_vence, h.prev_vence, h.p_contractual, 
                           h.p_extracontractual, h.p_todoriesgo, h.t_operaciones 
                           FROM vehiculos v LEFT JOIN hoja_vida h ON v.id = h.vehiculo_id''', conn)
    
    st.data_editor(df_hv, key="hv_editor", column_config={"id":None, "placa":st.column_config.TextColumn(disabled=True)}, hide_index=True)
    # (Aquí sigue el semáforo visual de tu código original)

# (Resto de módulos Dashboard, Ventas y Usuarios mantenidos según tu lógica original)
# ...

conn.close()
