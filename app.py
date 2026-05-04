import streamlit as st
import pandas as pd
import plotly.express as px
import bcrypt
from sqlalchemy import text
from datetime import datetime
from dateutil.relativedelta import relativedelta
from streamlit_cookies_controller import CookieController

PASTEL_COLORS = ['#A1C9F4', '#FFB482', '#8DE5A1', '#FF9F9B', '#D0BBFF', 
                 '#DEBB9B', '#FAB0E4', '#CFCFCF', '#FFFEA3', '#B9F2F0']

st.set_page_config(page_title="Controle Financeiro", layout="wide")

cookie_controller = CookieController()

if 'logado' not in st.session_state:
    st.session_state.logado = False
if 'email' not in st.session_state:
    st.session_state.email = ''

if not st.session_state.logado:
    sessao_salva = cookie_controller.get('user_session')
    if sessao_salva:
        st.session_state.logado = True
        st.session_state.email = sessao_salva

st.markdown("""
    <style>
        [data-testid="stSidebar"] { background-color: transparent; }
        div.stButton > button { background-color: #4a4e69; color: white; border-radius: 5px; }
    </style>
""", unsafe_allow_html=True)

conn = st.connection("supabase", type="sql")

def gerar_hash(senha):
    return bcrypt.hashpw(senha.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verificar_senha(senha, hash_banco):
    return bcrypt.checkpw(senha.encode('utf-8'), hash_banco.encode('utf-8'))

def verificar_login(email, senha):
    query = "SELECT senha_hash FROM usuarios WHERE email = :email"
    res = conn.query(query, params={"email": email}, ttl=0)
    if not res.empty:
        hash_banco = res.iloc[0]['senha_hash']
        return verificar_senha(senha, hash_banco)
    return False

def criar_usuario(email, senha):
    hash_senha = gerar_hash(senha)
    try:
        with conn.session as s:
            s.execute(
                text("INSERT INTO usuarios (email, senha_hash) VALUES (:email, :hash)"),
                {"email": email, "hash": hash_senha}
            )
            s.commit()
        return True
    except:
        return False

def carregar_dados(email):
    query = "SELECT * FROM registros_financeiros WHERE usuario_email = :email"
    df = conn.query(query, params={"email": email}, ttl=0)
    if not df.empty:
        df['competencia'] = pd.to_datetime(df['competencia']).dt.date
    return df

def adicionar_registro(registro):
    with conn.session as s:
        s.execute(
            text("""
            INSERT INTO registros_financeiros 
            (tipo, categoria, descricao, valor, parcela_atual, total_parcelas, competencia, usuario_email) 
            VALUES (:tipo, :categoria, :descricao, :valor, :parcela_atual, :total_parcelas, :competencia, :usuario_email)
            """),
            registro
        )
        s.commit()

def excluir_registro(id_registro, email):
    with conn.session as s:
        s.execute(
            text("DELETE FROM registros_financeiros WHERE id = :id AND usuario_email = :email"),
            {"id": id_registro, "email": email}
        )
        s.commit()

def atualizar_registro_db(id_registro, coluna, novo_valor, email):
    query = f"UPDATE registros_financeiros SET {coluna} = :valor WHERE id = :id AND usuario_email = :email"
    with conn.session as s:
        s.execute(text(query), {"valor": novo_valor, "id": id_registro, "email": email})
        s.commit()

if not st.session_state.logado:
    st.title("🛡️ Sistema Financeiro")
    tab_login, tab_reg = st.tabs(["Entrar", "Cadastrar"])
    
    with tab_login:
        e = st.text_input("E-mail", key="l_email")
        p = st.text_input("Senha", type="password", key="l_pass")
        lembrar = st.checkbox("Lembrar-me", value=True)
        
        if st.button("Acessar"):
            if verificar_login(e.lower().strip(), p):
                st.session_state.logado = True
                st.session_state.email = e.lower().strip()
                if lembrar:
                    cookie_controller.set('user_session', st.session_state.email, max_age=30*24*60*60)
                st.rerun()
            else:
                st.error("E-mail ou senha incorretos.")
                
    with tab_reg:
        ne = st.text_input("Novo E-mail", key="r_email")
        np = st.text_input("Nova Senha", type="password", key="r_pass")
        if st.button("Criar Conta"):
            if criar_usuario(ne.lower().strip(), np):
                st.success("Conta criada. Faça login.")
            else:
                st.error("Erro ao criar conta.")
    st.stop()

st.sidebar.markdown(f"**Usuário:** {st.session_state.email}")
if st.sidebar.button("Sair"):
    st.session_state.logado = False
    st.session_state.email = ''
    cookie_controller.remove('user_session')
    st.rerun()

TIPOS_TRANSACOES = [
    'Receita', 'Despesa (PIX)', 'Despesa (Cheque Especial)', 
    'Despesa (Crédito C6)', 'Despesa (Crédito Nubank)', 
    'Despesa (Crédito Santander)', 'Despesa (VR)'
]
CATEGORIAS_RECEITA = ['Salário Líquido', 'VR', 'Outras Receitas', 'Resgate (Dinheiro Guardado)']
CATEGORIAS_DESPESA = ['Moradia', 'Transporte', 'Mercado', 'Delivery', 'Lazer', 'Saídas', 'Contas', 'Aplicação (Dinheiro Guardado)']

def formata_br(valor):
    return f"R$ {valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

st.sidebar.header("Novo Registro")
tipo_sel = st.sidebar.selectbox("Tipo", TIPOS_TRANSACOES)

with st.sidebar.form("form_registro", clear_on_submit=True):
    lista_cat = CATEGORIAS_RECEITA if tipo_sel == 'Receita' else CATEGORIAS_DESPESA
    cat = st.selectbox("Categoria", lista_cat)
    desc = st.text_input("Descrição")
    val = st.number_input("Valor Total", min_value=0.01, format="%.2f")
    comp = st.date_input("Mês de Competência")
    parc = st.number_input("Parcelas", min_value=1, step=1, value=1) if 'Crédito' in tipo_sel else 1
    
    if st.form_submit_button("Registrar"):
        for i in range(parc):
            reg = {
                'tipo': tipo_sel, 'categoria': cat, 'descricao': desc,
                'valor': val / parc, 'parcela_atual': i + 1, 'total_parcelas': parc,
                'competencia': comp + relativedelta(months=i),
                'usuario_email': st.session_state.email
            }
            adicionar_registro(reg)
        st.rerun()

df_atual = carregar_dados(st.session_state.email)

if not df_atual.empty:
    df_atual['mes_ano'] = pd.to_datetime(df_atual['competencia']).dt.strftime('%Y-%m')
    
    # Filtro de Período
    hoje = datetime.today().date()
    inicio_padrao = hoje.replace(day=1)
    fim_padrao = (inicio_padrao + relativedelta(months=1)) - relativedelta(days=1)
    
    datas = st.date_input("Filtrar Período", value=(inicio_padrao, fim_padrao))
    
    if isinstance(datas, tuple) and len(datas) == 2:
        data_inicio, data_fim = datas
    elif isinstance(datas, tuple) and len(datas) == 1:
        data_inicio = data_fim = datas[0]
    else:
        data_inicio = data_fim = datas
        
    df_periodo = df_atual[(df_atual['competencia'] >= data_inicio) & (df_atual['competencia'] <= data_fim)].copy()
    
    rec_total = df_periodo[df_periodo['tipo'] == 'Receita']['valor'].sum()
    rec_vr = df_periodo[df_periodo['categoria'] == 'VR']['valor'].sum()
    desp_pix = df_periodo[df_periodo['tipo'] == 'Despesa (PIX)']['valor'].sum()
    desp_cred = df_periodo[df_periodo['tipo'].str.contains('Crédito') | (df_periodo['tipo'] == 'Despesa (Cheque Especial)')]['valor'].sum()
    
    df_h = df_atual[df_atual['competencia'] <= data_fim]
    guardado = df_h[df_h['categoria'] == 'Aplicação (Dinheiro Guardado)']['valor'].sum() - \
               df_h[df_h['categoria'] == 'Resgate (Dinheiro Guardado)']['valor'].sum()

    t1, t2, t3 = st.tabs(["💰 Resumo", "📊 Gráficos", "💳 Faturas"])

    with t1:
        st.markdown("### Visão Geral")
        c1, c2, c3 = st.columns(3)
        with st.container(border=True): c1.metric("Rec. Total", formata_br(rec_total))
        with st.container(border=True): c2.metric("Saída Pix", formata_br(desp_pix))
        with st.container(border=True): c3.metric("Faturas/Crédito", formata_br(desp_cred))
        
        st.markdown("### Saldos Calculados")
        c4, c5, c6, c7 = st.columns(4)
        with c4: 
            with st.container(border=True): st.metric("Saldo Conta", formata_br(rec_total - rec_vr - desp_pix))
        with c5: 
            with st.container(border=True): st.metric("Saldo VR", formata_br(rec_vr - df_periodo[df_periodo['tipo'] == 'Despesa (VR)']['valor'].sum()))
        with c6: 
            with st.container(border=True): st.metric("Resultado Mês", formata_br(rec_total - df_periodo[df_periodo['tipo'] != 'Receita']['valor'].sum()))
        with c7: 
            with st.container(border=True): st.metric("Acumulado Guardado", formata_br(guardado))

        st.markdown("---")
        st.subheader("Registros Detalhados")
        
        df_editavel = df_periodo.reset_index(drop=True)
        
        config_colunas = {
            "id": None,
            "usuario_email": None,
            "mes_ano": None,
            "parcela_atual": None,
            "total_parcelas": None,
            "competencia": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
            "tipo": st.column_config.SelectboxColumn("Fonte/Saída", options=TIPOS_TRANSACOES),
            "categoria": st.column_config.SelectboxColumn("Categoria", options=CATEGORIAS_RECEITA + CATEGORIAS_DESPESA),
            "descricao": st.column_config.TextColumn("Descrição"),
            "valor": st.column_config.NumberColumn("Valor", format="R$ %.2f")
        }

        st.data_editor(
            df_editavel,
            column_config=config_colunas,
            use_container_width=True,
            num_rows="dynamic",
            key="editor_registros"
        )

        if st.button("Salvar Alterações da Tabela"):
            mudancas = st.session_state.editor_registros
            
            if mudancas.get("deleted_rows"):
                for row_idx in mudancas["deleted_rows"]:
                    id_del = df_editavel.loc[row_idx, 'id']
                    excluir_registro(int(id_del), st.session_state.email)
                    
            if mudancas.get("edited_rows"):
                for row_idx_str, alteracoes in mudancas["edited_rows"].items():
                    row_idx = int(row_idx_str)
                    id_edit = df_editavel.loc[row_idx, 'id']
                    for col, val in alteracoes.items():
                        atualizar_registro_db(int(id_edit), col, val, st.session_state.email)
            st.rerun()

    with t2:
        TEXT_SIZE = 16
        FONT_FAMILY = "Arial"
        
        df_g = df_periodo[df_periodo['tipo'] != 'Receita']
        if not df_g.empty:
            cg1, cg2 = st.columns(2)
            
            with cg1:
                df_cat = df_g.groupby('categoria')['valor'].sum().sort_values(ascending=False).reset_index()
                fig1 = px.bar(df_cat, x='categoria', y='valor', 
                              text=df_cat['valor'].apply(formata_br),
                              title="<b>Gastos por Categoria</b>",
                              color_discrete_sequence=[PASTEL_COLORS[0]])
                fig1.update_traces(textposition='outside', textfont_size=TEXT_SIZE, opacity=0.8)
                fig1.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', yaxis=dict(visible=False))
                st.plotly_chart(fig1, use_container_width=True)

            with cg2:
                df_tp = df_g.groupby('tipo')['valor'].sum().sort_values(ascending=False).reset_index()
                fig2 = px.bar(df_tp, x='tipo', y='valor', 
                              text=df_tp['valor'].apply(formata_br),
                              title="<b>Gastos por Fonte</b>",
                              color_discrete_sequence=[PASTEL_COLORS[1]])
                fig2.update_traces(textposition='outside', textfont_size=TEXT_SIZE, opacity=0.8)
                fig2.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', yaxis=dict(visible=False))
                st.plotly_chart(fig2, use_container_width=True)

    with t3:
        st.markdown("### Resumo de Faturas")
        df_credito = df_atual[df_atual['tipo'].str.contains('Crédito')].copy()
        
        if not df_credito.empty:
            df_faturas = df_credito.groupby(['mes_ano', 'tipo'])['valor'].sum().reset_index()
            df_faturas = df_faturas.sort_values(by='mes_ano')
            
            df_pivot = df_faturas.pivot(index='mes_ano', columns='tipo', values='valor').fillna(0)
            df_pivot['Total Mês'] = df_pivot.sum(axis=1)
            
            # Formatação visual do dataframe
            st.dataframe(
                df_pivot.style.format(formata_br),
                use_container_width=True
            )
        else:
            st.info("Nenhum registro de crédito encontrado.")
else:
    st.info("Adicione o primeiro registro para ativar os gráficos e o detalhamento.")