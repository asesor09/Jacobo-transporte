import streamlit as st
import psycopg2
import pandas as pd
import plotly.express as px
from datetime import datetime
import io

# --- 1. CONEXIÓN Y SEGURIDAD ---
DB_URL = "postgresql://neondb_owner:npg_c7Dkwlh1jzGQ@ep-lucky-shadow-ac1thtiq-pooler.sa-east-1.aws.neon.tech/neondb?sslmode=require"

def conectar_db():
    return psycopg2.connect(DB_URL)

def inicializar_db():
    conn = conectar_db(); cur = conn.cursor()
    cur.execute('CREATE TABLE IF NOT EXISTS vehiculos (id SERIAL PRIMARY KEY, placa TEXT UNIQUE NOT NULL, marca TEXT, modelo TEXT, conductor TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS gastos (id SERIAL PRIMARY KEY, vehiculo_id INTEGER REFERENCES vehiculos(id), tipo_gasto TEXT, monto NUMERIC, fecha DATE, detalle TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS ventas (id SERIAL PRIMARY KEY, vehiculo_id INTEGER REFERENCES vehiculos(id), cliente TEXT, valor_viaje NUMERIC, fecha DATE, descripcion TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS hoja_vida (id SERIAL PRIMARY KEY, vehiculo_id INTEGER UNIQUE REFERENCES vehiculos(id), soat_inicio DATE, soat_vence DATE, tecno_inicio DATE, tecno_vence DATE, prev_inicio DATE, prev_vence DATE, km_actual INTEGER, km_llantas_cambio INTEGER)')
    conn.commit(); conn.close()

def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Reporte')
    return output.getvalue()

# --- 2. CONFIGURACIÓN VISUAL ---
st.set_page_config(page_title="C&E Eficiencias", layout="wide", page_icon="📊")
inicializar_db()

st.markdown("""<style>
    .main { background-color: #f5f7f9; }
    .stMetric { background-color: #ffffff; padding: 20px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1); border-left: 5px solid #007bff; }
    div.stButton > button:first-child { background-color: #007bff; color: white; border-radius: 5px; width: 100%; }
    </style>""", unsafe_allow_html=True)

if 'login' not in st.session_state: st.session_state.login = False

st.sidebar.title("🔐 Acceso")
if not st.session_state.login:
    pwd = st.sidebar.text_input("Contraseña", type="password")
    if st.sidebar.button("Ingresar"):
        if pwd == "Jacobo2026":
            st.session_state.login = True; st.rerun()
        else: st.sidebar.error("Acceso Denegado")
    st.stop()

if st.sidebar.button("🚪 CERRAR SESIÓN"):
    st.session_state.login = False; st.rerun()

menu = st.sidebar.selectbox("📂 MÓDULOS", ["📊 Dashboard", "🚐 Flota", "📑 Hoja de Vida", "💸 Gastos", "💰 Ventas"])

# --- 📊 DASHBOARD ---
if menu == "📊 Dashboard":
    st.title("📊 Resumen General")
    conn = conectar_db()
    df_g = pd.read_sql("SELECT monto, fecha FROM gastos", conn)
    df_s = pd.read_sql("SELECT valor_viaje, fecha FROM ventas", conn)
    conn.close()
    if not df_g.empty or not df_s.empty:
        df_g['Mes'] = pd.to_datetime(df_g['fecha']).dt.strftime('%Y-%m')
        df_s['Mes'] = pd.to_datetime(df_s['fecha']).dt.strftime('%Y-%m')
        g_m = df_g.groupby('Mes')['monto'].sum().reset_index()
        s_m = df_s.groupby('Mes')['valor_viaje'].sum().reset_index()
        res = pd.merge(s_m, g_m, on='Mes', how='outer').fillna(0)
        res.columns = ['Mes', 'Ventas', 'Gastos']
        st.table(res.sort_values(by='Mes', ascending=False))
        st.plotly_chart(px.bar(res, x='Mes', y=['Ventas', 'Gastos'], barmode='group'), use_container_width=True)

# --- 🚐 FLOTA ---
elif menu == "🚐 Flota":
    st.title("🚐 Gestión de Flota")
    with st.form("v"):
        c1, c2 = st.columns(2)
        placa = c1.text_input("Placa").upper()
        marca = c1.text_input("Marca"); mod = c2.text_input("Modelo"); cond = c2.text_input("Conductor")
        if st.form_submit_button("Guardar"):
            conn = conectar_db(); cur = conn.cursor()
            cur.execute("INSERT INTO vehiculos (placa, marca, modelo, conductor) VALUES (%s,%s,%s,%s)", (placa, marca, mod, cond))
            conn.commit(); conn.close(); st.success("Vehículo Registrado"); st.rerun()
    conn = conectar_db(); st.table(pd.read_sql("SELECT placa, marca, modelo, conductor FROM vehiculos", conn)); conn.close()

# --- 📑 HOJA DE VIDA ---
elif menu == "📑 Hoja de Vida":
    st.title("📑 Alertas")
    conn = conectar_db(); v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    with st.expander("📝 Actualizar Fechas"):
        with st.form("h_v"):
            v_id = int(v_data[v_data['placa'] == st.selectbox("Vehículo", v_data['placa'])]['id'].values[0])
            c1, c2, c3 = st.columns(3)
            s_v = c1.date_input("Fin SOAT"); t_v = c2.date_input("Fin Tecno"); p_v = c3.date_input("Fin Prev.")
            if st.form_submit_button("Actualizar"):
                cur = conn.cursor(); cur.execute('''INSERT INTO hoja_vida (vehiculo_id, soat_vence, tecno_vence, prev_vence) 
                VALUES (%s,%s,%s,%s) ON CONFLICT (vehiculo_id) DO UPDATE SET soat_vence=EXCLUDED.soat_vence, tecno_vence=EXCLUDED.tecno_vence, prev_vence=EXCLUDED.prev_vence''', (v_id, s_v, t_v, p_v))
                conn.commit(); st.success("Alertas Actualizadas"); st.rerun()
    df_h = pd.read_sql('''SELECT v.placa, h.soat_vence, h.tecno_vence, h.prev_vence FROM hoja_vida h JOIN vehiculos v ON h.vehiculo_id = v.id''', conn)
    hoy = datetime.now().date()
    for _, row in df_h.iterrows():
        st.subheader(f"🚗 {row['placa']}")
        col1, col2, col3 = st.columns(3)
        for c, lbl, f in zip([col1, col2, col3], ["SOAT", "TECNO", "PREVENTIVO"], [row['soat_vence'], row['tecno_vence'], row['prev_vence']]):
            if f:
                d = (f - hoy).days
                if d < 0: c.error(f"❌ {lbl} VENCIDO")
                elif d <= 15: c.warning(f"⚠️ {lbl} en {d} d")
                else: c.success(f"✅ {lbl} Al día")
    conn.close()

# --- 💸 GASTOS (CON FILTRO POR MES Y SUBTOTALES) ---
elif menu == "💸 Gastos":
    st.title("💸 Control de Gastos")
    conn = conectar_db()
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    
    # 1. Obtener todos los gastos para crear el filtro de meses
    df_all_g = pd.read_sql('''SELECT g.id, g.fecha, v.placa, g.tipo_gasto, g.monto, g.detalle 
                              FROM gastos g JOIN vehiculos v ON g.vehiculo_id = v.id ORDER BY g.fecha DESC''', conn)
    df_all_g['Mes'] = pd.to_datetime(df_all_g['fecha']).dt.strftime('%Y-%m')
    
    # --- FILTRO POR MES VISIBLE ---
    meses_lista = sorted(df_all_g['Mes'].unique().tolist(), reverse=True)
    mes_seleccionado = st.selectbox("📅 Seleccione el Mes para visualizar:", meses_lista if meses_lista else [datetime.now().strftime('%Y-%m')])
    
    df_filtrado = df_all_g[df_all_g['Mes'] == mes_seleccionado]

    # --- SUBTOTALES POR CONCEPTO ---
    st.subheader(f"💰 Resumen de Gastos: {mes_seleccionado}")
    if not df_filtrado.empty:
        subtotales = df_filtrado.groupby('tipo_gasto')['monto'].sum().reset_index()
        subtotales.columns = ['Concepto', 'Total Gastado']
        # Formato de moneda
        subtotales_view = subtotales.copy()
        subtotales_view['Total Gastado'] = subtotales_view['Total Gastado'].apply(lambda x: f"$ {x:,.0f}".replace(",", "."))
        
        col_tabla, col_grafica = st.columns([1, 1])
        col_tabla.table(subtotales_view)
        col_grafica.plotly_chart(px.pie(subtotales, values='Total Gastado', names='Concepto', hole=.3), use_container_width=True)
    
    st.divider()

    t1, t2 = st.tabs(["📝 Registro de Gastos", "✏️ Editar/Corregir Gasto"])
    
    with t1:
        with st.form("g"):
            c1, c2 = st.columns(2)
            v_id = int(v_data[v_data['placa'] == c1.selectbox("Vehículo", v_data['placa'])]['id'].values[0])
            tipo = c1.selectbox("Concepto", ["Combustible", "Peaje", "Mantenimiento", "Lavada", "Viáticos", "Otros"])
            mon = c2.number_input("Monto ($)", min_value=0)
            fec = c2.date_input("Fecha")
            det = st.text_input("Detalle (Ej: Factura #123)")
            if st.form_submit_button("💾 Guardar Gasto"):
                cur = conn.cursor(); cur.execute("INSERT INTO gastos (vehiculo_id, tipo_gasto, monto, fecha, detalle) VALUES (%s,%s,%s,%s,%s)", (v_id, tipo, mon, fec, det))
                conn.commit(); st.success("Gasto Guardado"); st.rerun()
        
        # Mostrar historial filtrado
        df_view = df_filtrado.copy()
        df_view["monto"] = df_view["monto"].apply(lambda x: f"$ {x:,.0f}".replace(",", "."))
        st.dataframe(df_view[['fecha', 'placa', 'tipo_gasto', 'monto', 'detalle']], use_container_width=True)
        st.download_button("📥 Descargar este mes (Excel)", data=to_excel(df_filtrado), file_name=f'gastos_{mes_seleccionado}.xlsx')

    with t2:
        st.subheader("✏️ Corregir Información")
        if not df_all_g.empty:
            # Lista desplegable para elegir qué editar
            sel_edit = st.selectbox("Seleccione el registro a corregir (ID | Placa | Fecha | Monto)", 
                                   df_all_g.apply(lambda r: f"{r['id']} | {r['placa']} | {r['fecha']} | $ {r['monto']:,.0f}", axis=1))
            id_ed = int(sel_edit.split(" | ")[0])
            
            # OBTENER DATOS ACTUALES PARA MOSTRAR AL USUARIO
            registro_actual = df_all_g[df_all_g['id'] == id_ed].iloc[0]
            
            st.info(f"**Datos actuales:** {registro_actual['tipo_gasto']} de la placa {registro_actual['placa']} por valor de $ {registro_actual['monto']:,.0f}")
            
            with st.form("ed_g"):
                c1, c2 = st.columns(2)
                # Cargamos los valores actuales en los inputs
                n_m = c1.number_input("Nuevo Monto", value=float(registro_actual['monto']))
                n_f = c1.date_input("Nueva Fecha", value=registro_actual['fecha'])
                n_t = c2.selectbox("Nuevo Concepto", ["Combustible", "Peaje", "Mantenimiento", "Lavada", "Viáticos", "Otros"], 
                                   index=["Combustible", "Peaje", "Mantenimiento", "Lavada", "Viáticos", "Otros"].index(registro_actual['tipo_gasto']))
                n_d = c2.text_input("Nuevo Detalle", value=registro_actual['detalle'])
                
                if st.form_submit_button("✅ Confirmar Cambios"):
                    cur = conn.cursor()
                    cur.execute("UPDATE gastos SET monto=%s, fecha=%s, tipo_gasto=%s, detalle=%s WHERE id=%s", (n_m, n_f, n_t, n_d, id_ed))
                    conn.commit(); st.warning(f"Registro {id_ed} actualizado con éxito"); st.rerun()
    conn.close()

# --- 💰 VENTAS ---
elif menu == "💰 Ventas":
    st.title("💰 Ventas")
    conn = conectar_db(); v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    with st.form("s"):
        v_id = int(v_data[v_data['placa'] == st.selectbox("Vehículo", v_data['placa'])]['id'].values[0])
        cli = st.text_input("Cliente"); val = st.number_input("Valor", min_value=0); fec = st.date_input("Fecha"); dsc = st.text_input("Descripción")
        if st.form_submit_button("Guardar"):
            cur = conn.cursor(); cur.execute("INSERT INTO ventas (vehiculo_id, cliente, valor_viaje, fecha, descripcion) VALUES (%s,%s,%s,%s,%s)", (v_id, cli, val, fec, dsc))
            conn.commit(); st.success("Venta Registrada"); st.rerun()
    df_s = pd.read_sql('SELECT s.fecha, v.placa, s.cliente, s.valor_viaje FROM ventas s JOIN vehiculos v ON s.vehiculo_id = v.id ORDER BY s.fecha DESC', conn)
    st.dataframe(df_s, use_container_width=True); conn.close()
