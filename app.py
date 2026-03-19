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
    # Tabla de Vehículos
    cur.execute('CREATE TABLE IF NOT EXISTS vehiculos (id SERIAL PRIMARY KEY, placa TEXT UNIQUE NOT NULL, marca TEXT, modelo TEXT, conductor TEXT)')
    # Tabla de Gastos
    cur.execute('CREATE TABLE IF NOT EXISTS gastos (id SERIAL PRIMARY KEY, vehiculo_id INTEGER REFERENCES vehiculos(id), tipo_gasto TEXT, monto NUMERIC, fecha DATE, detalle TEXT)')
    # Tabla de Ventas
    cur.execute('CREATE TABLE IF NOT EXISTS ventas (id SERIAL PRIMARY KEY, vehiculo_id INTEGER REFERENCES vehiculos(id), cliente TEXT, valor_viaje NUMERIC, fecha DATE, descripcion TEXT)')
    # Tabla Hoja de Vida
    cur.execute('''CREATE TABLE IF NOT EXISTS hoja_vida (
                    id SERIAL PRIMARY KEY, 
                    vehiculo_id INTEGER UNIQUE REFERENCES vehiculos(id), 
                    soat_vence DATE, tecno_vence DATE, prev_vence DATE,
                    p_contractual DATE, p_extracontractual DATE, p_todoriesgo DATE, t_operaciones DATE)''')
    # Tabla de Usuarios
    cur.execute('CREATE TABLE IF NOT EXISTS usuarios (id SERIAL PRIMARY KEY, nombre TEXT, usuario TEXT UNIQUE NOT NULL, clave TEXT NOT NULL, rol TEXT DEFAULT "vendedor")')
    # NUEVA TABLA DE CONFIGURACIÓN (ID=1 siempre)
    cur.execute('''CREATE TABLE IF NOT EXISTS configuracion (
                    id INTEGER PRIMARY KEY,
                    email_remitente TEXT, email_clave TEXT, email_destino TEXT,
                    twilio_sid TEXT, twilio_token TEXT, twilio_whatsapp_de TEXT, whatsapp_a TEXT)''')
    
    cur.execute("INSERT INTO usuarios (nombre, usuario, clave, rol) VALUES ('Jacobo Admin', 'admin', 'Jacobo2026', 'admin') ON CONFLICT (usuario) DO NOTHING")
    
    # Asegurar que las columnas nuevas existan en Hoja de Vida
    columnas_extra = ["p_contractual", "p_extracontractual", "p_todoriesgo", "t_operaciones"]
    for col in columnas_extra:
        try: cur.execute(f"ALTER TABLE hoja_vida ADD COLUMN {col} DATE")
        except: conn.rollback()
        
    conn.commit(); conn.close()

# --- 2. LÓGICA DE NOTIFICACIONES ---
def enviar_alertas_sistema(mensaje):
    try:
        conn = conectar_db(); cur = conn.cursor()
        cur.execute("SELECT * FROM configuracion WHERE id = 1")
        conf = cur.fetchone(); conn.close()
        if not conf:
            st.error("⚠️ Configure primero los datos en el módulo 'Config. Alertas'")
            return
        
        # Enviar Correo
        msg = MIMEText(mensaje)
        msg['Subject'] = '⚠️ ALERTA VENCIMIENTOS - C&E Eficiencias'
        msg['From'] = conf[1]; msg['To'] = conf[3]
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(conf[1], conf[2])
            server.sendmail(conf[1], conf[3], msg.as_string())
        
        # Enviar WhatsApp
        if TWILIO_INSTALADO and conf[4]:
            client = Client(conf[4], conf[5])
            client.messages.create(body=mensaje, from_=conf[6], to=conf[7])
        st.success("✅ Alertas enviadas a Correo y WhatsApp.")
    except Exception as e: st.error(f"Error en envío: {e}")

# --- 3. FUNCIONES DE APOYO ---
def to_excel(df_balance, df_g, df_v):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_balance.to_excel(writer, index=False, sheet_name='Balance General')
        df_g.to_excel(writer, index=False, sheet_name='Detalle Gastos')
        df_v.to_excel(writer, index=False, sheet_name='Detalle Ventas')
    return output.getvalue()

# --- 4. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="C&E Eficiencias", layout="wide", page_icon="🚐")
inicializar_db()

# --- 5. SISTEMA DE LOGIN ---
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

# --- 6. MENÚ PRINCIPAL ---
st.sidebar.write(f"👋 Bienvenid@, **{st.session_state.u_name}**")
st.sidebar.divider()
target = st.sidebar.number_input("🎯 Meta Utilidad ($)", value=5000000, step=500000)
opciones = ["📊 Dashboard", "🚐 Flota", "💸 Gastos", "💰 Ventas", "📑 Hoja de Vida", "⚙️ Usuarios"]
if st.session_state.u_rol == "admin": opciones.append("🔒 Config. Alertas")
menu = st.sidebar.selectbox("📂 MÓDULOS", opciones)

if st.sidebar.button("🚪 CERRAR SESIÓN"):
    st.session_state.logged_in = False; st.rerun()

conn = conectar_db()
v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)

# --- MÓDULO: CONFIGURACIÓN ALERTAS ---
if menu == "🔒 Config. Alertas":
    st.title("🔒 Configuración de Alertas (Correo y WhatsApp)")
    cur = conn.cursor()
    cur.execute("SELECT * FROM configuracion WHERE id = 1")
    act = cur.fetchone()
    with st.form("f_config_p"):
        c1, c2 = st.columns(2)
        rem = c1.text_input("Gmail Remitente", value=act[1] if act else "")
        cla = c1.text_input("Clave Aplicación (16 letras)", type="password", value=act[2] if act else "")
        des = c1.text_input("Correo Destino", value=act[3] if act else "")
        sid = c2.text_input("Twilio SID", value=act[4] if act else "")
        tok = c2.text_input("Twilio Token", type="password", value=act[5] if act else "")
        f_w = c2.text_input("WhatsApp DE (whatsapp:+...)", value=act[6] if act else "")
        t_w = c2.text_input("WhatsApp A (whatsapp:+...)", value=act[7] if act else "")
        if st.form_submit_button("💾 Guardar Configuración"):
            cur.execute('''INSERT INTO configuracion (id, email_remitente, email_clave, email_destino, twilio_sid, twilio_token, twilio_whatsapp_de, whatsapp_a)
                           VALUES (1, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO UPDATE SET 
                           email_remitente=EXCLUDED.email_remitente, email_clave=EXCLUDED.email_clave, email_destino=EXCLUDED.email_destino,
                           twilio_sid=EXCLUDED.twilio_sid, twilio_token=EXCLUDED.twilio_token, twilio_whatsapp_de=EXCLUDED.twilio_whatsapp_de, whatsapp_a=EXCLUDED.whatsapp_a''',
                        (rem, cla, des, sid, tok, f_w, t_w))
            conn.commit(); st.success("Configuración guardada correctamente."); st.rerun()

# --- MÓDULO: DASHBOARD (RESTAURADO) ---
elif menu == "📊 Dashboard":
    st.title("📊 Análisis de Operación y Utilidades")
    c1, c2 = st.columns(2)
    with c1: placa_f = st.selectbox("Seleccione Vehículo:", ["TODOS"] + v_data['placa'].tolist())
    with c2: rango = st.date_input("Rango de Fechas:", [datetime.now().date() - timedelta(days=30), datetime.now().date()])

    if len(rango) == 2:
        q_g = "SELECT g.fecha, v.placa, g.tipo_gasto as concepto, g.monto, g.detalle FROM gastos g JOIN vehiculos v ON g.vehiculo_id = v.id WHERE g.fecha BETWEEN %s AND %s"
        q_v = "SELECT s.fecha, v.placa, s.cliente, s.valor_viaje as monto, s.descripcion FROM ventas s JOIN vehiculos v ON s.vehiculo_id = v.id WHERE s.fecha BETWEEN %s AND %s"
        params = [rango[0], rango[1]]
        if placa_f != "TODOS":
            q_g += " AND v.placa = %s"; q_v += " AND v.placa = %s"; params.append(placa_f)
        
        df_g = pd.read_sql(q_g, conn, params=params if placa_f == "TODOS" else params + [placa_f])
        df_v = pd.read_sql(q_v, conn, params=params if placa_f == "TODOS" else params + [placa_f])

        sum_v, sum_g = df_v['monto'].sum(), df_g['monto'].sum()
        utilidad_neta = sum_v - sum_g
        dif_meta = utilidad_neta - target

        st.divider()
        if utilidad_neta >= target:
            st.success(f"### 🏆 ¡META ALCANZADA! \n Utilidad: **${utilidad_neta:,.0f}**"); st.balloons()
        else:
            st.error(f"### ⚠️ POR DEBAJO DE LA META \n Faltan: **${abs(dif_meta):,.0f}**")

        m1, m2, m3 = st.columns(3)
        m1.metric("Ingresos", f"${sum_v:,.0f}"); m2.metric("Egresos", f"${sum_g:,.0f}", delta_color="inverse"); m3.metric("Utilidad", f"${utilidad_neta:,.0f}", delta=f"{dif_meta:,.0f}")
        
        st.subheader("📊 Consolidado de Gastos por Concepto")
        df_con = df_g.groupby('concepto')['monto'].sum().reset_index()
        st.plotly_chart(px.pie(df_con, values='monto', names='concepto', hole=0.4), use_container_width=True)

        with st.expander("🔍 Ver detalles fila por fila"):
            st.write("**Gastos:**"); st.dataframe(df_g, use_container_width=True, hide_index=True)
            st.write("**Ventas:**"); st.dataframe(df_v, use_container_width=True, hide_index=True)
        
        res_g = df_g.groupby('placa')['monto'].sum().reset_index().rename(columns={'monto': 'Gasto'})
        res_v = df_v.groupby('placa')['monto'].sum().reset_index().rename(columns={'monto': 'Venta'})
        balance_df = pd.merge(res_v, res_g, on='placa', how='outer').fillna(0)
        st.download_button("📥 Reporte Excel", data=to_excel(balance_df, df_g, df_v), file_name="Reporte_CE.xlsx")

# --- MÓDULO: GASTOS (CON EDICIÓN Y BORRADO) ---
elif menu == "💸 Gastos":
    st.title("💸 Registro y Control de Gastos")
    tab1, tab2 = st.tabs(["📝 Nuevo Gasto", "✏️ Editar/Borrar Registros"])
    with tab1:
        with st.form("form_g"):
            v_sel = st.selectbox("Vehículo", v_data['placa'])
            tipo = st.selectbox("Concepto", ["Combustible", "Peaje", "Mantenimiento", "Lavada", "Viáticos", "Otros"])
            monto, fecha, det = st.number_input("Valor"), st.date_input("Fecha"), st.text_input("Nota")
            if st.form_submit_button("💾 Guardar"):
                v_id = v_data[v_data['placa'] == v_sel]['id'].values[0]
                cur = conn.cursor(); cur.execute("INSERT INTO gastos (vehiculo_id, tipo_gasto, monto, fecha, detalle) VALUES (%s,%s,%s,%s,%s)", (int(v_id), tipo, monto, fecha, det)); conn.commit(); st.rerun()
    with tab2:
        df_g_edit = pd.read_sql("SELECT g.id, g.fecha, v.placa, g.tipo_gasto, g.monto, g.detalle FROM gastos g JOIN vehiculos v ON g.vehiculo_id = v.id ORDER BY g.fecha DESC", conn)
        ed_g = st.data_editor(df_g_edit, column_config={"id": None, "placa": st.column_config.SelectboxColumn("Vehículo", options=v_data['placa'].tolist())}, hide_index=True, use_container_width=True, num_rows="dynamic")
        if st.button("💾 Guardar Cambios en Gastos"):
            cur = conn.cursor()
            ids_vivos = ed_g['id'].tolist()
            cur.execute(f"DELETE FROM gastos WHERE id NOT IN ({','.join(map(str, ids_vivos)) if ids_vivos else '0'})")
            for _, r in ed_g.iterrows():
                v_id_n = v_data[v_data['placa'] == r['placa']]['id'].values[0]
                cur.execute("UPDATE gastos SET vehiculo_id=%s, tipo_gasto=%s, monto=%s, fecha=%s, detalle=%s WHERE id=%s", (int(v_id_n), r['tipo_gasto'], r['monto'], r['fecha'], r['detalle'], int(r['id'])))
            conn.commit(); st.success("Base de datos sincronizada."); st.rerun()

# --- MÓDULO: VENTAS ---
elif menu == "💰 Ventas":
    st.title("💰 Control de Ingresos")
    tab1, tab2 = st.tabs(["💰 Nueva Venta", "✏️ Editar/Borrar Ventas"])
    with tab1:
        with st.form("form_v"):
            v_sel = st.selectbox("Vehículo", v_data['placa'])
            cli, val, fec, dsc = st.text_input("Cliente"), st.number_input("Valor"), st.date_input("Fecha"), st.text_input("Descripción")
            if st.form_submit_button("💰 Registrar"):
                v_id = v_data[v_data['placa'] == v_sel]['id'].values[0]
                cur = conn.cursor(); cur.execute("INSERT INTO ventas (vehiculo_id, cliente, valor_viaje, fecha, descripcion) VALUES (%s,%s,%s,%s,%s)", (int(v_id), cli, val, fec, dsc)); conn.commit(); st.rerun()
    with tab2:
        df_v_edit = pd.read_sql("SELECT s.id, s.fecha, v.placa, s.cliente, s.valor_viaje, s.descripcion FROM ventas s JOIN vehiculos v ON s.vehiculo_id = v.id ORDER BY s.fecha DESC", conn)
        ed_v = st.data_editor(df_v_edit, column_config={"id": None, "placa": st.column_config.SelectboxColumn("Vehículo", options=v_data['placa'].tolist())}, hide_index=True, use_container_width=True, num_rows="dynamic")
        if st.button("💾 Guardar Cambios en Ventas"):
            cur = conn.cursor()
            ids_vivos = ed_v['id'].tolist()
            cur.execute(f"DELETE FROM ventas WHERE id NOT IN ({','.join(map(str, ids_vivos)) if ids_vivos else '0'})")
            for _, r in ed_v.iterrows():
                v_id_n = v_data[v_data['placa'] == r['placa']]['id'].values[0]
                cur.execute("UPDATE ventas SET vehiculo_id=%s, cliente=%s, valor_viaje=%s, fecha=%s, descripcion=%s WHERE id=%s", (int(v_id_n), r['cliente'], r['valor_viaje'], r['fecha'], r['descripcion'], int(r['id'])))
            conn.commit(); st.success("Ventas actualizadas."); st.rerun()

# --- MÓDULO: FLOTA ---
elif menu == "🚐 Flota":
    st.title("🚐 Administración de Vehículos")
    with st.form("f_f"):
        p, m, mod, cond = st.text_input("Placa").upper(), st.text_input("Marca"), st.text_input("Modelo"), st.text_input("Conductor")
        if st.form_submit_button("➕ Añadir"):
            cur = conn.cursor(); cur.execute("INSERT INTO vehiculos (placa, marca, modelo, conductor) VALUES (%s,%s,%s,%s)", (p, m, mod, cond)); conn.commit(); st.rerun()
    st.dataframe(pd.read_sql("SELECT placa, marca, modelo, conductor FROM vehiculos", conn), use_container_width=True)

# --- MÓDULO: HOJA DE VIDA (RESTAURADO COMPLETO) ---
elif menu == "📑 Hoja de Vida":
    st.title("📑 Vencimientos y Documentación")
    if st.button("🔔 Enviar Reporte Ahora a WhatsApp/Correo"):
        hoy = datetime.now().date()
        df_al = pd.read_sql("SELECT v.placa, h.* FROM vehiculos v JOIN hoja_vida h ON v.id = h.vehiculo_id", conn)
        msg, alertas = "🚨 REPORTE VENCIMIENTOS:\n", False
        for _, r in df_al.iterrows():
            for doc, f in [("SOAT", r[2]), ("TECNO", r[3]), ("PREV", r[4])]:
                if f and (f - hoy).days <= 15:
                    msg += f"- {r[0]}: {doc} vence {f}\n"; alertas = True
        if alertas: enviar_alertas_sistema(msg)
        else: st.info("Todo al día.")

    with st.expander("📅 Actualizar Fechas"):
        with st.form("form_hv"):
            v_sel = st.selectbox("Vehículo", v_data['placa'])
            v_id = v_data[v_data['placa'] == v_sel]['id'].values[0]
            c1, c2 = st.columns(2)
            s_v, t_v, p_v = c1.date_input("SOAT"), c1.date_input("Tecno"), c1.date_input("Preventivo")
            pc_v, pe_v, ptr_v, to_v = c2.date_input("Contractual"), c2.date_input("Extra"), c2.date_input("Todo Riesgo"), st.date_input("Tarjeta Operaciones")
            if st.form_submit_button("🔄 Guardar"):
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
    st.title("⚙️ Usuarios")
    with st.form("f_u"):
        nom, usr, clv, rol = st.text_input("Nombre"), st.text_input("Usuario"), st.text_input("Clave"), st.selectbox("Rol", ["vendedor", "admin"])
        if st.form_submit_button("👤 Crear"):
            cur = conn.cursor(); cur.execute("INSERT INTO usuarios (nombre, usuario, clave, rol) VALUES (%s,%s,%s,%s)", (nom, usr, clv, rol)); conn.commit(); st.rerun()
    st.dataframe(pd.read_sql("SELECT nombre, usuario, rol FROM usuarios", conn), use_container_width=True)

conn.close()
