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
    
    # Mantenimiento de columnas para Hoja de Vida
    columnas_extra = [("p_contractual", "DATE"), ("p_extracontractual", "DATE"), ("p_todoriesgo", "DATE"), ("t_operaciones", "DATE")]
    for col, tipo in columnas_extra:
        try:
            cur.execute(f"ALTER TABLE hoja_vida ADD COLUMN {col} {tipo}")
            conn.commit()
        except:
            conn.rollback()
    conn.close()

# --- 2. FUNCIONES DE APOYO (EXCEL Y CÁLCULOS) ---
def to_excel(df_balance, df_g, df_v):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_balance.to_excel(writer, index=False, sheet_name='Balance General')
        df_g.to_excel(writer, index=False, sheet_name='Detalle Gastos')
        df_v.to_excel(writer, index=False, sheet_name='Detalle Ventas')
    return output.getvalue()

# --- 3. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="C&E Eficiencias PRO", layout="wide", page_icon="🚐")
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

# --- 5. SIDEBAR ---
st.sidebar.write(f"👋 **{st.session_state.u_name}**")
target = st.sidebar.number_input("🎯 Meta Utilidad ($)", value=5000000, step=500000)
menu = st.sidebar.selectbox("📂 MÓDULOS", ["📊 Dashboard", "🚐 Flota", "💸 Gastos", "💰 Ventas", "📑 Hoja de Vida", "⚙️ Usuarios"])
if st.sidebar.button("🚪 CERRAR SESIÓN"): st.session_state.logged_in = False; st.rerun()

conn = conectar_db()

# --- MÓDULO: DASHBOARD (TU LÓGICA ORIGINAL RESTAURADA) ---
if menu == "📊 Dashboard":
    st.title("📊 Análisis de Operación y Utilidades")
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    c1, c2 = st.columns(2)
    with c1: placa_f = st.selectbox("Vehículo:", ["TODOS"] + v_data['placa'].tolist())
    with c2: rango = st.date_input("Rango de Fechas:", [datetime.now().date() - timedelta(days=30), datetime.now().date()])

    if len(rango) == 2:
        q_g = "SELECT g.id, g.fecha, v.placa, g.tipo_gasto as concepto, g.monto, g.detalle FROM gastos g JOIN vehiculos v ON g.vehiculo_id = v.id WHERE g.fecha BETWEEN %s AND %s"
        q_v = "SELECT s.id, s.fecha, v.placa, s.cliente, s.valor_viaje as monto, s.descripcion FROM ventas s JOIN vehiculos v ON s.vehiculo_id = v.id WHERE s.fecha BETWEEN %s AND %s"
        params = [rango[0], rango[1]]
        if placa_f != "TODOS":
            q_g += " AND v.placa = %s"; q_v += " AND v.placa = %s"
            params.append(placa_f)

        df_g = pd.read_sql(q_g, conn, params=params if placa_f == "TODOS" else params + [placa_f])
        df_v = pd.read_sql(q_v, conn, params=params if placa_f == "TODOS" else params + [placa_f])

        utilidad_neta = df_v['monto'].sum() - df_g['monto'].sum()
        dif_meta = utilidad_neta - target

        if utilidad_neta >= target:
            st.success(f"### 🏆 ¡META ALCANZADA! \n Utilidad: **${utilidad_neta:,.0f}**"); st.balloons()
        else:
            st.error(f"### ⚠️ POR DEBAJO DE LA META \n Faltan: **${abs(dif_meta):,.0f}**")

        m1, m2, m3 = st.columns(3)
        m1.metric("Ingresos (Ventas)", f"${df_v['monto'].sum():,.0f}")
        m2.metric("Egresos (Gastos)", f"${df_g['monto'].sum():,.0f}", delta_color="inverse")
        m3.metric("Utilidad Neta", f"${utilidad_neta:,.0f}", delta=f"{dif_meta:,.0f}")

        # Gráfico Comparativo
        res_g = df_g.groupby('placa')['monto'].sum().reset_index().rename(columns={'monto': 'Gasto'})
        res_v = df_v.groupby('placa')['monto'].sum().reset_index().rename(columns={'monto': 'Venta'})
        balance_df = pd.merge(res_v, res_g, on='placa', how='outer').fillna(0)
        st.plotly_chart(px.bar(balance_df, x='placa', y=['Venta', 'Gasto'], barmode='group', color_discrete_map={'Venta': '#2ecc71', 'Gasto': '#e74c3c'}))
        
        st.download_button("📥 Descargar Reporte Completo", data=to_excel(balance_df, df_g, df_v), file_name="Reporte_CE.xlsx")

# --- MÓDULO: GASTOS (EDICIÓN REFORZADA) ---
elif menu == "💸 Gastos":
    st.title("💸 Registro y Edición de Gastos")
    t1, t2 = st.tabs(["📝 Nuevo Gasto", "✏️ Editor Maestro"])
    
    with t1:
        with st.form("fg"):
            v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
            v_sel = st.selectbox("Vehículo", v_data['placa'])
            tipo = st.selectbox("Concepto", ["Combustible", "Peaje", "Mantenimiento", "Lavada", "Viáticos", "Otros"])
            monto = st.number_input("Valor ($)", min_value=0)
            fecha = st.date_input("Fecha")
            det = st.text_input("Nota/Detalle")
            if st.form_submit_button("💾 Guardar"):
                v_id = v_data[v_data['placa'] == v_sel]['id'].values[0]
                cur = conn.cursor(); cur.execute("INSERT INTO gastos (vehiculo_id, tipo_gasto, monto, fecha, detalle) VALUES (%s,%s,%s,%s,%s)", (int(v_id), tipo, monto, fecha, det))
                conn.commit(); st.rerun()

    with t2:
        st.info("⚠️ Los cambios realizados en la tabla deben confirmarse con el botón 'Guardar Cambios'.")
        df_g_edit = pd.read_sql("SELECT g.id, v.placa, g.tipo_gasto, g.monto, g.fecha, g.detalle FROM gastos g JOIN vehiculos v ON g.vehiculo_id = v.id ORDER BY g.fecha DESC", conn)
        
        # Editor con configuración de columnas para evitar errores de escritura
        edited_g = st.data_editor(
            df_g_edit,
            column_config={
                "id": None, # Ocultar ID para evitar confusión
                "placa": st.column_config.TextColumn("Vehículo", disabled=True), # No se puede cambiar el vehículo aquí para mantener integridad
                "tipo_gasto": st.column_config.SelectboxColumn("Concepto", options=["Combustible", "Peaje", "Mantenimiento", "Lavada", "Viáticos", "Otros"], required=True),
                "monto": st.column_config.NumberColumn("Monto ($)", min_value=0),
                "fecha": st.column_config.DateColumn("Fecha"),
                "detalle": st.column_config.TextColumn("Detalle")
            },
            key="editor_g", hide_index=True, use_container_width=True
        )
        if st.button("💾 Guardar Cambios en Gastos"):
            cur = conn.cursor()
            for _, row in edited_g.iterrows():
                cur.execute("UPDATE gastos SET tipo_gasto=%s, monto=%s, fecha=%s, detalle=%s WHERE id=%s", (row['tipo_gasto'], row['monto'], row['fecha'], row['detalle'], int(row['id'])))
            conn.commit(); st.success("Datos actualizados"); st.rerun()

# --- MÓDULO: HOJA DE VIDA (RESTAURADO COMPLETO + EDITOR) ---
elif menu == "📑 Hoja de Vida":
    st.title("📑 Documentación y Vencimientos")
    
    df_hv = pd.read_sql('''SELECT h.id, v.placa, h.soat_vence, h.tecno_vence, h.prev_vence, h.p_contractual, 
                           h.p_extracontractual, h.p_todoriesgo, h.t_operaciones 
                           FROM vehiculos v LEFT JOIN hoja_vida h ON v.id = h.vehiculo_id''', conn)
    
    st.subheader("✏️ Editor de Fechas de Documentos")
    edited_hv = st.data_editor(
        df_hv,
        column_config={
            "id": None,
            "placa": st.column_config.TextColumn("Vehículo", disabled=True),
            "soat_vence": st.column_config.DateColumn("SOAT"),
            "tecno_vence": st.column_config.DateColumn("Tecnomecánica"),
            "prev_vence": st.column_config.DateColumn("Preventiva"),
            "p_contractual": st.column_config.DateColumn("Pol. Contractual"),
            "p_extracontractual": st.column_config.DateColumn("Pol. Extra"),
            "p_todoriesgo": st.column_config.DateColumn("Todo Riesgo"),
            "t_operaciones": st.column_config.DateColumn("T. Operaciones")
        },
        hide_index=True, use_container_width=True
    )
    
    if st.button("🔄 Sincronizar Vencimientos"):
        cur = conn.cursor()
        for _, row in edited_hv.iterrows():
            cur.execute("SELECT id FROM vehiculos WHERE placa = %s", (row['placa'],))
            v_id = cur.fetchone()[0]
            cur.execute('''INSERT INTO hoja_vida (vehiculo_id, soat_vence, tecno_vence, prev_vence, p_contractual, p_extracontractual, p_todoriesgo, t_operaciones) 
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (vehiculo_id) DO UPDATE SET 
                           soat_vence=EXCLUDED.soat_vence, tecno_vence=EXCLUDED.tecno_vence, prev_vence=EXCLUDED.prev_vence,
                           p_contractual=EXCLUDED.p_contractual, p_extracontractual=EXCLUDED.p_extracontractual, 
                           p_todoriesgo=EXCLUDED.p_todoriesgo, t_operaciones=EXCLUDED.t_operaciones''', 
                        (v_id, row['soat_vence'], row['tecno_vence'], row['prev_vence'], row['p_contractual'], row['p_extracontractual'], row['p_todoriesgo'], row['t_operaciones']))
        conn.commit(); st.success("Documentación sincronizada"); st.rerun()

    # Semáforo de alarmas (Tu diseño original de colores)
    st.divider()
    hoy = datetime.now().date()
    for _, row in df_hv.iterrows():
        st.caption(f"🏁 **{row['placa']}**")
        cols = st.columns(4)
        docs = [("SOAT", row['soat_vence']), ("TECNO", row['tecno_vence']), ("PREVENTIVA", row['prev_vence']), ("T.OPER", row['t_operaciones'])]
        for i, (name, fecha) in enumerate(docs):
            if fecha:
                d = (fecha - hoy).days
                if d < 0: cols[i].error(f"❌ {name} Vencido")
                elif d <= 15: cols[i].warning(f"⚠️ {name}: {d} días")
                else: cols[i].success(f"✅ {name} OK")
            else: cols[i].info(f"⚪ {name}: S/D")

# (Los módulos de Ventas, Flota y Usuarios siguen la misma estructura protegida)
elif menu == "🚐 Flota":
    st.title("🚐 Administración de Flota")
    df_f = pd.read_sql("SELECT id, placa, marca, modelo, conductor FROM vehiculos", conn)
    edited_f = st.data_editor(df_f, column_config={"id":None}, hide_index=True, use_container_width=True)
    if st.button("💾 Guardar Cambios en Flota"):
        cur = conn.cursor()
        for _, row in edited_f.iterrows():
            cur.execute("UPDATE vehiculos SET placa=%s, marca=%s, modelo=%s, conductor=%s WHERE id=%s", (row['placa'].upper(), row['marca'], row['modelo'], row['conductor'], int(row['id'])))
        conn.commit(); st.rerun()

elif menu == "💰 Ventas":
    st.title("💰 Control de Ingresos")
    df_v = pd.read_sql("SELECT s.id, v.placa, s.cliente, s.valor_viaje as monto, s.fecha, s.descripcion FROM ventas s JOIN vehiculos v ON s.vehiculo_id = v.id", conn)
    edited_v = st.data_editor(df_v, column_config={"id":None, "placa":st.column_config.TextColumn(disabled=True)}, hide_index=True, use_container_width=True)
    if st.button("💾 Guardar Ventas"):
        cur = conn.cursor()
        for _, row in edited_v.iterrows():
            cur.execute("UPDATE ventas SET cliente=%s, valor_viaje=%s, fecha=%s, descripcion=%s WHERE id=%s", (row['cliente'], row['monto'], row['fecha'], row['descripcion'], int(row['id'])))
        conn.commit(); st.rerun()

elif menu == "⚙️ Usuarios" and st.session_state.u_rol == "admin":
    st.title("⚙️ Gestión de Usuarios")
    df_u = pd.read_sql("SELECT id, nombre, usuario, clave, rol FROM usuarios", conn)
    edited_u = st.data_editor(df_u, column_config={"id":None, "rol":st.column_config.SelectboxColumn(options=["admin", "vendedor"])}, hide_index=True)
    if st.button("💾 Guardar Usuarios"):
        cur = conn.cursor()
        for _, row in edited_u.iterrows():
            cur.execute("UPDATE usuarios SET nombre=%s, usuario=%s, clave=%s, rol=%s WHERE id=%s", (row['nombre'], row['usuario'], row['clave'], row['rol'], int(row['id'])))
        conn.commit(); st.rerun()

conn.close()
