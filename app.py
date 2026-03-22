import streamlit as st
import psycopg2
import pandas as pd
from datetime import datetime, timedelta
import io
import plotly.express as px
import smtplib
from email.mime.text import MIMEText

# --- 1. CONFIGURACIÓN DE LA BASE DE DATOS ---
DB_URL = "postgresql://neondb_owner:npg_c7Dkwlh1jzGQ@ep-lucky-shadow-ac1thtiq-pooler.sa-east-1.aws.neon.tech/neondb?sslmode=require"

def conectar_db():
    return psycopg2.connect(DB_URL)

def inicializar_db():
    conn = conectar_db(); cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS configuracion (
                    id INTEGER PRIMARY KEY,
                    email_remitente TEXT, email_clave TEXT, email_destino TEXT,
                    twilio_sid TEXT, twilio_token TEXT, twilio_whatsapp_de TEXT, whatsapp_a TEXT)''')
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
    conn.commit(); conn.close()

# --- 2. LÓGICA DE ENVÍO ---
def enviar_alertas_sistema(mensaje):
    try:
        conn = conectar_db(); cur = conn.cursor()
        cur.execute("SELECT * FROM configuracion WHERE id = 1")
        conf = cur.fetchone(); conn.close()
        remitente = "".join(conf[1].split()); clave = "".join(conf[2].split()); destino = "".join(conf[3].split())
        msg = MIMEText(mensaje); msg['Subject'] = '🚨 REPORTE VENCIMIENTOS - C&E'; msg['From'] = remitente; msg['To'] = destino
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(remitente, clave); server.sendmail(remitente, destino, msg.as_string())
        st.success(f"✅ Reporte enviado con éxito")
    except Exception as e: st.error(f"❌ Error: {e}")

# --- 3. FUNCIONES APOYO ---
def to_excel(df_balance, df_g, df_v):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_balance.to_excel(writer, index=False, sheet_name='Balance General')
        df_g.to_excel(writer, index=False, sheet_name='Detalle Gastos')
        df_v.to_excel(writer, index=False, sheet_name='Detalle Ventas')
    return output.getvalue()

# --- 4. CONFIG PÁGINA ---
st.set_page_config(page_title="C&E Eficiencias", layout="wide", page_icon="🚐")
inicializar_db()

# --- 5. LOGIN ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if not st.session_state.logged_in:
    st.sidebar.title("🔐 Acceso")
    u_in = st.sidebar.text_input("Usuario")
    p_in = st.sidebar.text_input("Contraseña", type="password")
    if st.sidebar.button("Ingresar"):
        conn = conectar_db(); cur = conn.cursor()
        cur.execute("SELECT nombre, rol FROM usuarios WHERE usuario = %s AND clave = %s", (u_in, p_in))
        res = cur.fetchone(); conn.close()
        if res:
            st.session_state.logged_in, st.session_state.u_name, st.session_state.u_rol = True, res[0], res[1]
            st.rerun()
    st.stop()

# --- 6. MENÚ Y BOTÓN CERRAR ---
st.sidebar.write(f"👋 **{st.session_state.u_name}**")
target = st.sidebar.number_input("🎯 Meta Utilidad", value=5000000, step=500000)
opciones = ["📊 Dashboard", "🚐 Flota", "💸 Gastos", "💰 Ventas", "📑 Hoja de Vida", "⚙️ Usuarios"]
if st.session_state.u_rol == "admin": opciones.append("🔒 Config. Alertas")
menu = st.sidebar.selectbox("📂 MÓDULOS", opciones)

st.sidebar.divider()
if st.sidebar.button("🚪 CERRAR SESIÓN"):
    st.session_state.logged_in = False
    st.rerun()

conn = conectar_db()
v_query = pd.read_sql("SELECT id, placa FROM vehiculos", conn)

# --- DASHBOARD ---
if menu == "📊 Dashboard":
    st.title("📊 Análisis de Operación")
    c1, c2 = st.columns(2)
    with c1: placa_f = st.selectbox("Vehículo:", ["TODOS"] + v_query['placa'].tolist())
    with c2: rango = st.date_input("Rango de Fechas:", [datetime.now().date() - timedelta(days=30), datetime.now().date()])
    if len(rango) == 2:
        df_g = pd.read_sql("SELECT g.fecha, v.placa, g.tipo_gasto as concepto, g.monto, g.detalle FROM gastos g JOIN vehiculos v ON g.vehiculo_id = v.id WHERE g.fecha BETWEEN %s AND %s", conn, params=[rango[0], rango[1]])
        df_v = pd.read_sql("SELECT s.fecha, v.placa, s.cliente, s.valor_viaje as monto, s.descripcion FROM ventas s JOIN vehiculos v ON s.vehiculo_id = v.id WHERE s.fecha BETWEEN %s AND %s", conn, params=[rango[0], rango[1]])
        if placa_f != "TODOS":
            df_g = df_g[df_g['placa'] == placa_f]; df_v = df_v[df_v['placa'] == placa_f]
        utilidad = df_v['monto'].sum() - df_g['monto'].sum()
        dif = utilidad - target
        if utilidad >= target: st.success(f"### 🏆 META ALCANZADA! Utilidad: ${utilidad:,.0f}"); st.balloons()
        else: st.error(f"### ⚠️ POR DEBAJO DE LA META \n Faltan: **${abs(dif):,.0f}**")
        m1, m2, m3 = st.columns(3)
        m1.metric("Ingresos", f"${df_v['monto'].sum():,.0f}"); m2.metric("Egresos", f"${df_g['monto'].sum():,.0f}", delta_color="inverse"); m3.metric("Utilidad", f"${utilidad:,.0f}", delta=f"{dif:,.0f}")
        st.subheader("📊 Consolidado de Gastos por Concepto")
        df_con = df_g.groupby('concepto')['monto'].sum().reset_index().sort_values(by='monto', ascending=False)
        st.dataframe(df_con.style.format({'monto': '${:,.0f}'}), use_container_width=True, hide_index=True)
        st.plotly_chart(px.pie(df_con, values='monto', names='concepto', hole=0.4), use_container_width=True)
        res_g = df_g.groupby('placa')['monto'].sum().reset_index().rename(columns={'monto': 'Gasto'}); res_v = df_v.groupby('placa')['monto'].sum().reset_index().rename(columns={'monto': 'Venta'})
        balance_df = pd.merge(res_v, res_g, on='placa', how='outer').fillna(0)
        st.download_button("📥 Descargar Reporte Excel", data=to_excel(balance_df, df_g, df_v), file_name="Reporte_CE.xlsx")
        with st.expander("🔍 Ver detalles fila por fila"):
            st.write("**Gastos:**"); st.dataframe(df_g, use_container_width=True, hide_index=True)
            st.write("**Ventas:**"); st.dataframe(df_v, use_container_width=True, hide_index=True)

# --- FLOTA ---
elif menu == "🚐 Flota":
    st.title("🚐 Flota")
    with st.form("f_flota"):
        p, m, mod, cond = st.text_input("Placa").upper(), st.text_input("Marca"), st.text_input("Modelo"), st.text_input("Conductor")
        if st.form_submit_button("➕ Añadir Carro"):
            cur = conn.cursor(); cur.execute("INSERT INTO vehiculos (placa, marca, modelo, conductor) VALUES (%s,%s,%s,%s)", (p, m, mod, cond)); conn.commit(); st.rerun()
    df_f = pd.read_sql("SELECT id, placa, marca, modelo, conductor FROM vehiculos", conn)
    st.data_editor(df_f, column_config={"id": None}, hide_index=True, use_container_width=True)

# --- GASTOS ---
elif menu == "💸 Gastos":
    st.title("💸 Gastos")
    with st.form("fg"):
        v_sel = st.selectbox("Vehículo", v_query['placa'])
        tipo = st.selectbox("Concepto", ["Combustible", "Peaje", "Mantenimiento", "Lavada", "Viáticos", "Otros"])
        mon, fec, det = st.number_input("Valor"), st.date_input("Fecha"), st.text_input("Nota")
        if st.form_submit_button("💾 Guardar"):
            v_id = v_query[v_query['placa'] == v_sel]['id'].values[0]
            cur = conn.cursor(); cur.execute("INSERT INTO gastos (vehiculo_id, tipo_gasto, monto, fecha, detalle) VALUES (%s,%s,%s,%s,%s)", (int(v_id), tipo, mon, fec, det)); conn.commit(); st.rerun()

# --- VENTAS ---
elif menu == "💰 Ventas":
    st.title("💰 Ventas")
    with st.form("fv"):
        v_sel = st.selectbox("Vehículo", v_query['placa'])
        cli, val, fec, dsc = st.text_input("Cliente"), st.number_input("Valor"), st.date_input("Fecha"), st.text_input("Nota")
        if st.form_submit_button("💰 Registrar"):
            v_id = v_query[v_query['placa'] == v_sel]['id'].values[0]
            cur = conn.cursor(); cur.execute("INSERT INTO ventas (vehiculo_id, cliente, valor_viaje, fecha, descripcion) VALUES (%s,%s,%s,%s,%s)", (int(v_id), cli, val, fec, dsc)); conn.commit(); st.rerun()

# --- HOJA DE VIDA (RESTAURADO CON FORMULARIO) ---
elif menu == "📑 Hoja de Vida":
    st.title("📑 Vencimientos")
    if st.button("🔔 Enviar Reporte Ahora"):
        hoy = datetime.now().date(); df_al = pd.read_sql("SELECT v.placa, h.* FROM vehiculos v JOIN hoja_vida h ON v.id = h.vehiculo_id", conn)
        msg, alert = "🚨 REPORTE:\n", False
        for _, r in df_al.iterrows():
            for doc, f in [("SOAT", r[2]), ("TECNO", r[3]), ("PREV", r[4])]:
                if f:
                    f_dt = pd.to_datetime(f).date()
                    if (f_dt - hoy).days <= 15: msg += f"- {r[0]}: {doc} vence {f_dt}\n"; alert = True
        if alert: enviar_alertas_sistema(msg)
        else: st.info("Todo al día.")

    # ESTA PARTE ES LA QUE ACTUALIZA LA HOJA DE VIDA
    with st.expander("📅 ACTUALIZAR FECHAS DE DOCUMENTOS"):
        with st.form("fhv"):
            v_sel = st.selectbox("Seleccione Vehículo", v_query['placa'])
            v_id = v_query[v_query['placa'] == v_sel]['id'].values[0]
            c1, c2 = st.columns(2)
            s_v, t_v, p_v = c1.date_input("SOAT"), c1.date_input("Tecno"), c1.date_input("Preventivo")
            pc_v, pe_v, ptr_v, to_v = c2.date_input("P. Contractual"), c2.date_input("P. Extra"), c2.date_input("P. Todo Riesgo"), st.date_input("Tarjeta Operaciones")
            if st.form_submit_button("🔄 GUARDAR ACTUALIZACIÓN"):
                cur = conn.cursor()
                cur.execute('''INSERT INTO hoja_vida (vehiculo_id, soat_vence, tecno_vence, prev_vence, p_contractual, p_extracontractual, p_todoriesgo, t_operaciones)
                               VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (vehiculo_id) DO UPDATE SET 
                               soat_vence=EXCLUDED.soat_vence, tecno_vence=EXCLUDED.tecno_vence, prev_vence=EXCLUDED.prev_vence, 
                               p_contractual=EXCLUDED.p_contractual, p_extracontractual=EXCLUDED.p_extracontractual, 
                               p_todoriesgo=EXCLUDED.p_todoriesgo, t_operaciones=EXCLUDED.t_operaciones''', 
                            (int(v_id), s_v, t_v, p_v, pc_v, pe_v, ptr_v, to_v))
                conn.commit(); st.success("Fechas actualizadas correctamente."); st.rerun()

    df_hv = pd.read_sql("SELECT v.placa, h.* FROM vehiculos v LEFT JOIN hoja_vida h ON v.id = h.vehiculo_id", conn); hoy = datetime.now().date()
    for _, r in df_hv.iterrows():
        st.subheader(f"Vehículo: {r['placa']}"); cols = st.columns(4)
        docs = [("SOAT", r['soat_vence']), ("TECNO", r['tecno_vence']), ("PREV", r['prev_vence']), ("T.OPER", r['t_operaciones']), ("POL. CONT", r['p_contractual']), ("POL. EXTRA", r['p_extracontractual']), ("TODO RIESGO", r['p_todoriesgo'])]
        for i, (n, f) in enumerate(docs):
            if f:
                f_dt = pd.to_datetime(f).date(); d = (f_dt - hoy).days
                if d < 0: cols[i%4].error(f"❌ {n} VENCIDO")
                elif d <= 15: cols[i%4].warning(f"⚠️ {n} ({d} d)")
                else: cols[i%4].success(f"✅ {n} OK")
            else: cols[i%4].info(f"⚪ {n}: S/D")

# --- USUARIOS ---
elif menu == "⚙️ Usuarios" and st.session_state.u_rol == "admin":
    st.title("⚙️ Usuarios")
    with st.form("fu"):
        nom, usr, clv, rol = st.text_input("Nombre"), st.text_input("Usuario"), st.text_input("Clave"), st.selectbox("Rol", ["vendedor", "admin"])
        if st.form_submit_button("👤 Crear"):
            cur = conn.cursor(); cur.execute("INSERT INTO usuarios (nombre, usuario, clave, rol) VALUES (%s,%s,%s,%s)", (nom, usr, clv, rol)); conn.commit(); st.rerun()
    df_u = pd.read_sql("SELECT nombre, usuario, rol FROM usuarios", conn)
    st.dataframe(df_u, use_container_width=True)

# --- CONFIGURACIÓN ---
elif menu == "🔒 Config. Alertas":
    st.title("🔒 Configuración Segura")
    cur = conn.cursor(); cur.execute("SELECT * FROM configuracion WHERE id = 1"); act = cur.fetchone()
    with st.form("f_conf"):
        rem = st.text_input("Gmail Remitente", value=act[1] if act else "")
        cla = st.text_input("Clave Gmail (16 letras)", type="password", value=act[2] if act else "")
        des = st.text_input("Correo Destino", value=act[3] if act else "")
        if st.form_submit_button("💾 Guardar"):
            cur.execute('''INSERT INTO configuracion (id, email_remitente, email_clave, email_destino)
                           VALUES (1, %s, %s, %s) ON CONFLICT (id) DO UPDATE SET 
                           email_remitente=EXCLUDED.email_remitente, email_clave=EXCLUDED.email_clave, email_destino=EXCLUDED.email_destino''',
                        (rem, cla, des))
            conn.commit(); st.success("Guardado."); st.rerun()

conn.close()
