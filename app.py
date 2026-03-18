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
    # Tabla de Vehículos
    cur.execute('CREATE TABLE IF NOT EXISTS vehiculos (id SERIAL PRIMARY KEY, placa TEXT UNIQUE NOT NULL, marca TEXT, modelo TEXT, conductor TEXT)')
    # Tabla de Gastos
    cur.execute('CREATE TABLE IF NOT EXISTS gastos (id SERIAL PRIMARY KEY, vehiculo_id INTEGER REFERENCES vehiculos(id), tipo_gasto TEXT, monto NUMERIC, fecha DATE, detalle TEXT)')
    # Tabla de Ventas
    cur.execute('CREATE TABLE IF NOT EXISTS ventas (id SERIAL PRIMARY KEY, vehiculo_id INTEGER REFERENCES vehiculos(id), cliente TEXT, valor_viaje NUMERIC, fecha DATE, descripcion TEXT)')
    # Tabla Hoja de Vida (CORREGIDA)
    cur.execute('''CREATE TABLE IF NOT EXISTS hoja_vida (
                    id SERIAL PRIMARY KEY, 
                    vehiculo_id INTEGER UNIQUE REFERENCES vehiculos(id), 
                    soat_vence DATE, tecno_vence DATE, prev_vence DATE,
                    p_contractual DATE, p_extracontractual DATE, p_todoriesgo DATE, t_operaciones DATE)''')
    # Tabla de Usuarios
    cur.execute('CREATE TABLE IF NOT EXISTS usuarios (id SERIAL PRIMARY KEY, nombre TEXT, usuario TEXT UNIQUE NOT NULL, clave TEXT NOT NULL, rol TEXT DEFAULT "vendedor")')
    cur.execute("INSERT INTO usuarios (nombre, usuario, clave, rol) VALUES ('Jacobo Admin', 'admin', 'Jacobo2026', 'admin') ON CONFLICT (usuario) DO NOTHING")
    
    # Asegurar que las columnas nuevas existan en Hoja de Vida
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

# --- MÓDULO: DASHBOARD ---
if menu == "📊 Dashboard":
    st.title("📊 Análisis de Operación y Utilidades")
    conn = conectar_db()
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
           st.success(f"### 🏆 ¡META ALCANZADA! \n Utilidad: **${utilidad_neta:,.0f}** | Superas el objetivo por: **${dif_meta:,.0f}**")
           st.balloons()
        else:
           st.error(f"### ⚠️ POR DEBAJO DE LA META \n Utilidad: **${utilidad_neta:,.0f}** | Faltan: **${abs(dif_meta):,.0f}** para el objetivo de ${target:,.0f}")

        m1, m2, m3 = st.columns(3)
        m1.metric("Ingresos (Ventas)", f"${sum_v:,.0f}")
        m2.metric("Egresos (Gastos)", f"${sum_g:,.0f}", delta=f"-{sum_g:,.0f}", delta_color="inverse")
        m3.metric("Utilidad Neta", f"${utilidad_neta:,.0f}", delta=f"{dif_meta:,.0f}")

        st.subheader("📈 Comparativa por Vehículo")
        res_g = df_g.groupby('placa')['monto'].sum().reset_index().rename(columns={'monto': 'Gasto'})
        res_v = df_v.groupby('placa')['monto'].sum().reset_index().rename(columns={'monto': 'Venta'})
        balance_df = pd.merge(res_v, res_g, on='placa', how='outer').fillna(0)
        balance_df['Utilidad'] = balance_df['Venta'] - balance_df['Gasto']
        
        fig = px.bar(balance_df, x='placa', y=['Venta', 'Gasto'], barmode='group', color_discrete_map={'Venta': '#2ecc71', 'Gasto': '#e74c3c'})
        st.plotly_chart(fig, use_container_width=True)

        st.download_button("📥 Descargar Reporte Completo (Excel)", data=to_excel(balance_df, df_g, df_v), file_name=f"Reporte_CE_{rango[0]}_al_{rango[1]}.xlsx")
        
        with st.expander("🔍 Ver detalles de cada movimiento"):
            st.write("**Gastos:**")
            st.dataframe(df_g, use_container_width=True, hide_index=True)
            st.write("**Ventas:**")
            st.dataframe(df_v, use_container_width=True, hide_index=True)
    conn.close()

# --- MÓDULO: GASTOS ---
elif menu == "💸 Gastos":
    st.title("💸 Registro y Control de Gastos")
    conn = conectar_db(); v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    
    tab1, tab2 = st.tabs(["📝 Nuevo Gasto", "✏️ Gestionar Registros"])
    
    with tab1:
        if not v_data.empty:
            with st.form("form_g"):
                v_sel = st.selectbox("Vehículo", v_data['placa'])
                v_id = v_data[v_data['placa'] == v_sel]['id'].values[0]
                tipo = st.selectbox("Concepto", ["Combustible", "Peaje", "Mantenimiento", "Lavada", "Viáticos", "Otros"])
                monto = st.number_input("Valor ($)", min_value=0)
                fecha = st.date_input("Fecha")
                det = st.text_input("Nota/Detalle")
                if st.form_submit_button("💾 Guardar Gasto"):
                    cur = conn.cursor()
                    cur.execute("INSERT INTO gastos (vehiculo_id, tipo_gasto, monto, fecha, detalle) VALUES (%s,%s,%s,%s,%s)", (int(v_id), tipo, monto, fecha, det))
                    conn.commit(); st.success("Registrado correctamente"); st.rerun()
        else: st.warning("Primero crea vehículos en el módulo Flota.")

    with tab2:
        df_edit = pd.read_sql("SELECT g.id, g.fecha, v.placa, g.tipo_gasto, g.monto, g.detalle FROM gastos g JOIN vehiculos v ON g.vehiculo_id = v.id ORDER BY g.fecha DESC", conn)
        
        st.write("### ✏️ Edición Directa en Tabla")
        st.info("Puedes editar cualquier celda y presionar 'Guardar Cambios' al finalizar.")
        
        # EDITOR DE TABLA (Permite editar todos los campos excepto el ID y la placa que viene de un JOIN)
        edited_df = st.data_editor(df_edit, key="editor_gastos", hide_index=True, use_container_width=True, num_rows="dynamic")
        
        if st.button("💾 Guardar Cambios en Gastos"):
            cur = conn.cursor()
            # Lógica para detectar eliminaciones y actualizaciones
            ids_vivos = edited_df['id'].tolist()
            cur.execute(f"DELETE FROM gastos WHERE id NOT IN ({','.join(map(str, ids_vivos)) if ids_vivos else '0'})")
            for _, row in edited_df.iterrows():
                cur.execute("UPDATE gastos SET fecha=%s, tipo_gasto=%s, monto=%s, detalle=%s WHERE id=%s", 
                           (row['fecha'], row['tipo_gasto'], row['monto'], row['detalle'], int(row['id'])))
            conn.commit(); st.success("¡Base de datos actualizada!"); st.rerun()

# --- MÓDULO: VENTAS ---
elif menu == "💰 Ventas":
    st.title("💰 Control de Ingresos por Viajes")
    conn = conectar_db(); v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    
    tab1, tab2 = st.tabs(["💰 Registrar Venta", "✏️ Gestionar Ventas"])
    
    with tab1:
        with st.form("form_v"):
            v_sel = st.selectbox("Vehículo", v_data['placa'])
            v_id = v_data[v_data['placa'] == v_sel]['id'].values[0]
            cli = st.text_input("Cliente / Empresa")
            val = st.number_input("Valor del Viaje", min_value=0)
            fec = st.date_input("Fecha")
            dsc = st.text_input("Descripción del Viaje")
            if st.form_submit_button("💰 Registrar Venta"):
                cur = conn.cursor()
                cur.execute("INSERT INTO ventas (vehiculo_id, cliente, valor_viaje, fecha, descripcion) VALUES (%s,%s,%s,%s,%s)", (int(v_id), cli, val, fec, dsc))
                conn.commit(); st.success("Venta guardada"); st.rerun()
    
    with tab2:
        df_v_list = pd.read_sql("SELECT s.id, s.fecha, v.placa, s.cliente, s.valor_viaje, s.descripcion FROM ventas s JOIN vehiculos v ON s.vehiculo_id = v.id ORDER BY s.fecha DESC", conn)
        st.write("### ✏️ Edición Directa de Ventas")
        edited_v_df = st.data_editor(df_v_list, key="editor_ventas", hide_index=True, use_container_width=True, num_rows="dynamic")
        
        if st.button("💾 Guardar Cambios en Ventas"):
            cur = conn.cursor()
            ids_vivos_v = edited_v_df['id'].tolist()
            cur.execute(f"DELETE FROM ventas WHERE id NOT IN ({','.join(map(str, ids_vivos_v)) if ids_vivos_v else '0'})")
            for _, row in edited_v_df.iterrows():
                cur.execute("UPDATE ventas SET fecha=%s, cliente=%s, valor_viaje=%s, descripcion=%s WHERE id=%s", 
                           (row['fecha'], row['cliente'], row['valor_viaje'], row['descripcion'], int(row['id'])))
            conn.commit(); st.success("¡Ventas actualizadas!"); st.rerun()
    conn.close()

# --- MÓDULO: FLOTA ---
elif menu == "🚐 Flota":
    st.title("🚐 Administración de Vehículos")
    conn = conectar_db()
    
    tab1, tab2 = st.tabs(["➕ Añadir Carro", "✏️ Editar Flota"])
    
    with tab1:
        with st.form("form_f"):
            p = st.text_input("Placa (Ej: XYZ123)").upper()
            m = st.text_input("Marca"); mod = st.text_input("Modelo"); cond = st.text_input("Conductor Asignado")
            if st.form_submit_button("➕ Añadir Carro"):
                cur = conn.cursor()
                cur.execute("INSERT INTO vehiculos (placa, marca, modelo, conductor) VALUES (%s,%s,%s,%s)", (p, m, mod, cond))
                conn.commit(); st.success("Vehículo añadido"); st.rerun()
    
    with tab2:
        df_f = pd.read_sql("SELECT id, placa, marca, modelo, conductor FROM vehiculos", conn)
        edited_f = st.data_editor(df_f, key="editor_flota", hide_index=True, use_container_width=True, num_rows="dynamic")
        if st.button("💾 Guardar Cambios en Flota"):
            cur = conn.cursor()
            for _, row in edited_f.iterrows():
                cur.execute("UPDATE vehiculos SET placa=%s, marca=%s, modelo=%s, conductor=%s WHERE id=%s", 
                           (row['placa'], row['marca'], row['modelo'], row['conductor'], int(row['id'])))
            conn.commit(); st.success("¡Flota actualizada!"); st.rerun()
    conn.close()

# --- MÓDULO: HOJA DE VIDA ---
elif menu == "📑 Hoja de Vida":
    st.title("📑 Documentación y Vencimientos")
    conn = conectar_db(); v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    
    with st.expander("📅 Actualizar Fechas de Vencimiento"):
        with st.form("form_hv"):
            v_sel = st.selectbox("Vehículo", v_data['placa'])
            v_id = v_data[v_data['placa'] == v_sel]['id'].values[0]
            c1, c2 = st.columns(2)
            s_v = c1.date_input("SOAT"); t_v = c1.date_input("Tecnomecánica"); p_v = c1.date_input("Preventivo")
            pc_v = c2.date_input("Póliza Contractual"); pe_v = c2.date_input("Póliza Extracontractual")
            ptr_v = c2.date_input("Póliza Todo Riesgo"); to_v = st.date_input("Tarjeta de Operaciones")
            if st.form_submit_button("🔄 Actualizar"):
                cur = conn.cursor()
                cur.execute('''INSERT INTO hoja_vida (vehiculo_id, soat_vence, tecno_vence, prev_vence, p_contractual, p_extracontractual, p_todoriesgo, t_operaciones) 
                               VALUES (%s,%s,%s,%s,%s,%s,%s,%s) 
                               ON CONFLICT (vehiculo_id) DO UPDATE SET 
                               soat_vence=EXCLUDED.soat_vence, tecno_vence=EXCLUDED.tecno_vence, prev_vence=EXCLUDED.prev_vence, 
                               p_contractual=EXCLUDED.p_contractual, p_extracontractual=EXCLUDED.p_extracontractual, 
                               p_todoriesgo=EXCLUDED.p_todoriesgo, t_operaciones=EXCLUDED.t_operaciones''', 
                            (int(v_id), s_v, t_v, p_v, pc_v, pe_v, ptr_v, to_v))
                conn.commit(); st.success("Vencimientos actualizados"); st.rerun()

    df_hv = pd.read_sql('''SELECT v.placa, h.soat_vence, h.tecno_vence, h.prev_vence, h.p_contractual, h.p_extracontractual, h.p_todoriesgo, h.t_operaciones 
                           FROM vehiculos v LEFT JOIN hoja_vida h ON v.id = h.vehiculo_id''', conn)
    hoy = datetime.now().date()
    for _, row in df_hv.iterrows():
        with st.container():
            st.subheader(f"Vehículo: {row['placa']}")
            cols = st.columns(4)
            docs = [("SOAT", row['soat_vence']), ("TECNO", row['tecno_vence']), ("PREV", row['prev_vence']), ("T.OPER", row['t_operaciones']),
                    ("POL. CONT", row['p_contractual']), ("POL. EXTRA", row['p_extracontractual']), ("TODO RIESGO", row['p_todoriesgo'])]
            for i, (name, fecha) in enumerate(docs):
                col_idx = i % 4
                if fecha:
                    dias = (fecha - hoy).days
                    if dias < 0: cols[col_idx].error(f"❌ {name} VENCIDO")
                    elif dias <= 15: cols[col_idx].warning(f"⚠️ {name} ({dias} días)")
                    else: cols[col_idx].success(f"✅ {name} OK")
                else: cols[col_idx].info(f"⚪ {name}: Sin fecha")
    conn.close()

# --- MÓDULO: USUARIOS ---
elif menu == "⚙️ Usuarios" and st.session_state.u_rol == "admin":
    st.title("⚙️ Gestión de Personal")
    with st.form("form_u"):
        nom = st.text_input("Nombre Completo"); usr = st.text_input("Usuario"); clv = st.text_input("Clave"); rol = st.selectbox("Rol", ["vendedor", "admin"])
        if st.form_submit_button("👤 Crear Usuario"):
            conn = conectar_db(); cur = conn.cursor()
            cur.execute("INSERT INTO usuarios (nombre, usuario, clave, rol) VALUES (%s,%s,%s,%s)", (nom, usr, clv, rol))
            conn.commit(); conn.close(); st.success("Usuario creado satisfactoriamente")
