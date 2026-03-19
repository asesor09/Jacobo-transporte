import streamlit as st
import psycopg2
import pandas as pd
from datetime import datetime, timedelta
import io
import plotly.express as px
import smtplib
from email.mime.text import MIMEText

# --- INTENTO DE IMPORTACIÓN DE TWILIO ---
try:
    from twilio.rest import Client 
    TWILIO_INSTALADO = True
except ImportError:
    TWILIO_INSTALADO = False

# --- 1. CONFIGURACIÓN DE LA BASE DE DATOS ---
DB_URL = "postgresql://neondb_owner:npg_c7Dkwlh1jzGQ@ep-lucky-shadow-ac1thtiq-pooler.sa-east-1.aws.neon.tech/neondb?sslmode=require"

def conectar_db():
    return psycopg2.connect(DB_URL)

def inicializar_db():
    conn = conectar_db(); cur = conn.cursor()
    # Crear tablas en orden
    cur.execute('CREATE TABLE IF NOT EXISTS vehiculos (id SERIAL PRIMARY KEY, placa TEXT UNIQUE NOT NULL, marca TEXT, modelo TEXT, conductor TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS gastos (id SERIAL PRIMARY KEY, vehiculo_id INTEGER REFERENCES vehiculos(id), tipo_gasto TEXT, monto NUMERIC, fecha DATE, detalle TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS ventas (id SERIAL PRIMARY KEY, vehiculo_id INTEGER REFERENCES vehiculos(id), cliente TEXT, valor_viaje NUMERIC, fecha DATE, descripcion TEXT)')
    cur.execute('''CREATE TABLE IF NOT EXISTS hoja_vida (
                    id SERIAL PRIMARY KEY, 
                    vehiculo_id INTEGER UNIQUE REFERENCES vehiculos(id), 
                    soat_vence DATE, tecno_vence DATE, prev_vence DATE,
                    p_contractual DATE, p_extracontractual DATE, p_todoriesgo DATE, t_operaciones DATE)''')
    cur.execute('CREATE TABLE IF NOT EXISTS usuarios (id SERIAL PRIMARY KEY, nombre TEXT, usuario TEXT UNIQUE NOT NULL, clave TEXT NOT NULL, rol TEXT DEFAULT "vendedor")')
    
    # Crear tabla de configuración blindada
    cur.execute('''CREATE TABLE IF NOT EXISTS configuracion (
                    id INTEGER PRIMARY KEY,
                    email_remitente TEXT, email_clave TEXT, email_destino TEXT,
                    twilio_sid TEXT, twilio_token TEXT, twilio_whatsapp_de TEXT, whatsapp_a TEXT)''')
    
    cur.execute("INSERT INTO usuarios (nombre, usuario, clave, rol) VALUES ('Jacobo Admin', 'admin', 'Jacobo2026', 'admin') ON CONFLICT (usuario) DO NOTHING")
    conn.commit(); conn.close()

# --- 2. LÓGICA DE NOTIFICACIONES ---
def enviar_alertas_sistema(mensaje):
    try:
        conn = conectar_db(); cur = conn.cursor()
        cur.execute("SELECT * FROM configuracion WHERE id = 1")
        conf = cur.fetchone(); conn.close()
        if not conf:
            st.error("⚠️ Configure los datos en 'Config. Alertas'")
            return
        # Correo
        msg = MIMEText(mensaje); msg['Subject'] = '⚠️ ALERTA C&E'; msg['From'] = conf[1]; msg['To'] = conf[3]
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(conf[1], conf[2]); server.sendmail(conf[1], conf[3], msg.as_string())
        # WhatsApp
        if TWILIO_INSTALADO and conf[4]:
            client = Client(conf[4], conf[5])
            client.messages.create(body=mensaje, from_=conf[6], to=conf[7])
        st.success("✅ Enviado.")
    except Exception as e: st.error(f"Error: {e}")

# --- 3. FUNCIONES APOYO ---
def to_excel(df_balance, df_g, df_v):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_balance.to_excel(writer, index=False, sheet_name='Balance General')
        df_g.to_excel(writer, index=False, sheet_name='Detalle Gastos')
        df_v.to_excel(writer, index=False, sheet_name='Detalle Ventas')
    return output.getvalue()

# --- 4. CONFIGURACIÓN PÁGINA ---
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

# --- 6. MENÚ ---
st.sidebar.write(f"👋 **{st.session_state.u_name}**")
st.sidebar.divider()
target = st.sidebar.number_input("Meta Utilidad ($)", value=5000000, step=500000)
opciones = ["📊 Dashboard", "🚐 Flota", "💸 Gastos", "💰 Ventas", "📑 Hoja de Vida", "⚙️ Usuarios"]
if st.session_state.u_rol == "admin": opciones.append("🔒 Config. Alertas")
menu = st.sidebar.selectbox("MÓDULOS", opciones)
if st.sidebar.button("🚪 CERRAR SESIÓN"): st.session_state.logged_in = False; st.rerun()

conn = conectar_db()
v_query = pd.read_sql("SELECT id, placa FROM vehiculos", conn)

# --- MÓDULO: CONFIGURACIÓN ALERTAS (CORREGIDO) ---
if menu == "🔒 Config. Alertas":
    st.title("🔒 Configuración de Alertas")
    # Lectura protegida para evitar el error UndefinedTable
    act = None
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM configuracion WHERE id = 1")
        act = cur.fetchone()
    except: pass

    with st.form("f_conf"):
        c1, c2 = st.columns(2)
        rem = c1.text_input("Gmail Remitente", value=act[1] if act else "")
        cla = c1.text_input("Clave Gmail (16 letras)", type="password", value=act[2] if act else "")
        des = c1.text_input("Correo Destino", value=act[3] if act else "")
        sid = c2.text_input("Twilio SID", value=act[4] if act else "")
        tok = c2.text_input("Twilio Token", type="password", value=act[5] if act else "")
        f_w = c2.text_input("WhatsApp DE", value=act[6] if act else "")
        t_w = c2.text_input("WhatsApp A", value=act[7] if act else "")
        if st.form_submit_button("💾 Guardar"):
            cur = conn.cursor()
            cur.execute('''INSERT INTO configuracion (id, email_remitente, email_clave, email_destino, twilio_sid, twilio_token, twilio_whatsapp_de, whatsapp_a)
                           VALUES (1, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO UPDATE SET 
                           email_remitente=EXCLUDED.email_remitente, email_clave=EXCLUDED.email_clave, email_destino=EXCLUDED.email_destino,
                           twilio_sid=EXCLUDED.twilio_sid, twilio_token=EXCLUDED.twilio_token, twilio_whatsapp_de=EXCLUDED.twilio_whatsapp_de, whatsapp_a=EXCLUDED.whatsapp_a''',
                        (rem, cla, des, sid, tok, f_w, t_w))
            conn.commit(); st.success("Guardado."); st.rerun()

# --- MÓDULO: DASHBOARD (RESTAURADO) ---
elif menu == "📊 Dashboard":
    st.title("📊 Análisis de Operación")
    c1, c2 = st.columns(2)
    with c1: placa_f = st.selectbox("Vehículo:", ["TODOS"] + v_query['placa'].tolist())
    with c2: rango = st.date_input("Rango:", [datetime.now().date() - timedelta(days=30), datetime.now().date()])

    if len(rango) == 2:
        df_g = pd.read_sql("SELECT g.fecha, v.placa, g.tipo_gasto as concepto, g.monto, g.detalle FROM gastos g JOIN vehiculos v ON g.vehiculo_id = v.id WHERE g.fecha BETWEEN %s AND %s", conn, params=[rango[0], rango[1]])
        df_v = pd.read_sql("SELECT s.fecha, v.placa, s.cliente, s.valor_viaje as monto, s.descripcion FROM ventas s JOIN vehiculos v ON s.vehiculo_id = v.id WHERE s.fecha BETWEEN %s AND %s", conn, params=[rango[0], rango[1]])
        if placa_f != "TODOS":
            df_g = df_g[df_g['placa'] == placa_f]; df_v = df_v[df_v['placa'] == placa_f]

        utilidad = df_v['monto'].sum() - df_g['monto'].sum()
        if utilidad >= target: st.success(f"🏆 META ALCANZADA! Utilidad: ${utilidad:,.0f}"); st.balloons()
        else: st.error(f"⚠️ POR DEBAJO. Faltan: ${abs(utilidad-target):,.0f}")
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Ingresos", f"${df_v['monto'].sum():,.0f}"); m2.metric("Egresos", f"${df_g['monto'].sum():,.0f}", delta_color="inverse"); m3.metric("Utilidad", f"${utilidad:,.0f}", delta=f"{utilidad-target:,.0f}")
        
        st.subheader("📊 Consolidado de Gastos por Concepto")
        df_con = df_g.groupby('concepto')['monto'].sum().reset_index().sort_values(by='monto', ascending=False)
        st.dataframe(df_con.style.format({'monto': '${:,.0f}'}), use_container_width=True, hide_index=True)
        st.plotly_chart(px.pie(df_con, values='monto', names='concepto', hole=0.4), use_container_width=True)
        
        with st.expander("🔍 Ver detalles fila por fila"):
            st.write("**Gastos:**"); st.dataframe(df_g, use_container_width=True, hide_index=True)
            st.write("**Ventas:**"); st.dataframe(df_v, use_container_width=True, hide_index=True)

# --- MÓDULO: GASTOS (CON EDICIÓN) ---
elif menu == "💸 Gastos":
    st.title("💸 Gastos")
    tab1, tab2 = st.tabs(["📝 Nuevo", "✏️ Editar/Borrar"])
    with tab1:
        with st.form("fg"):
            v_sel = st.selectbox("Vehículo", v_query['placa'])
            tipo = st.selectbox("Concepto", ["Combustible", "Peaje", "Mantenimiento", "Lavada", "Viáticos", "Otros"])
            mon, fec, det = st.number_input("Valor"), st.date_input("Fecha"), st.text_input("Nota")
            if st.form_submit_button("💾 Guardar"):
                v_id = v_query[v_query['placa'] == v_sel]['id'].values[0]
                cur = conn.cursor(); cur.execute("INSERT INTO gastos (vehiculo_id, tipo_gasto, monto, fecha, detalle) VALUES (%s,%s,%s,%s,%s)", (int(v_id), tipo, mon, fec, det)); conn.commit(); st.rerun()
    with tab2:
        df_ge = pd.read_sql("SELECT g.id, g.fecha, v.placa, g.tipo_gasto, g.monto, g.detalle FROM gastos g JOIN vehiculos v ON g.vehiculo_id = v.id ORDER BY g.fecha DESC", conn)
        ed_g = st.data_editor(df_ge, column_config={"id": None, "placa": st.column_config.SelectboxColumn("Vehículo", options=v_query['placa'].tolist())}, hide_index=True, use_container_width=True, num_rows="dynamic")
        if st.button("💾 Guardar Cambios"):
            cur = conn.cursor(); ids_vivos = ed_g['id'].tolist()
            cur.execute(f"DELETE FROM gastos WHERE id NOT IN ({','.join(map(str, ids_vivos)) if ids_vivos else '0'})")
            for _, r in ed_g.iterrows():
                v_id_n = v_query[v_query['placa'] == r['placa']]['id'].values[0]
                cur.execute("UPDATE gastos SET vehiculo_id=%s, tipo_gasto=%s, monto=%s, fecha=%s, detalle=%s WHERE id=%s", (int(v_id_n), r['tipo_gasto'], r['monto'], r['fecha'], r['detalle'], int(r['id'])))
            conn.commit(); st.rerun()

# --- MÓDULO: HOJA DE VIDA ---
elif menu == "📑 Hoja de Vida":
    st.title("📑 Vencimientos")
    if st.button("🔔 Enviar Reporte Ahora"):
        hoy = datetime.now().date()
        df_al = pd.read_sql("SELECT v.placa, h.* FROM vehiculos v JOIN hoja_vida h ON v.id = h.vehiculo_id", conn)
        msg, alertas = "🚨 REPORTE:\n", False
        for _, r in df_al.iterrows():
            for doc, f in [("SOAT", r[2]), ("TECNO", r[3]), ("PREV", r[4])]:
                if f and (f - hoy).days <= 15:
                    msg += f"- {r[0]}: {doc} vence {f}\n"; alertas = True
        if alertas: enviar_alertas_sistema(msg)
        else: st.info("Todo al día.")

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

conn.close()
