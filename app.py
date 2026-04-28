import streamlit as st
import pandas as pd
import plotly.express as px
import bcrypt
from sqlalchemy import text
from datetime import datetime
from dateutil.relativedelta import relativedelta

# --- 1. CONFIGURAÇÃO E ESTADO INICIAL ---
st.set_page_config(page_title="Controle Financeiro", layout="wide")

# Inicializa variáveis de estado
if 'logado' not in st.session_state:
    st.session_state.logado = False
if 'email' not in st.session_state:
    st.session_state.email = ''
if 'mes_foco' not in st.session_state:
    st.session_state.mes_foco = None

# Estilização
st.markdown("""
    <style>
        [data-testid="stSidebar"] { background-color: #fcfbf4; }
        div.stButton > button { background-color: #4a4e69; color: white; border-radius: 5px; }
    </style>
""", unsafe_allow_html=True)

# --- 2. CONEXÃO ---
conn = st.connection("supabase", type="sql")

# --- 3. FUNÇÕES DE SEGURANÇA E USUÁRIO ---
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

# --- 4. FUNÇÕES DE DADOS (FINANCEIRO) ---
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

# --- 5. LÓGICA DE ACESSO (LOGIN/CADASTRO) ---
if not st.session_state.logado:
    st.title("🛡️ Sistema Financeiro")
    tab_login, tab_reg = st.tabs(["Entrar", "Cadastrar"])
    
    with tab_login:
        e = st.text_input("E-mail", key="l_email")
        p = st.text_input("Senha", type="password", key="l_pass")
        if st.button("Acessar"):
            if verificar_login(e.lower().strip(), p):
                st.session_state.logado = True
                st.session_state.email = e.lower().strip()
                st.rerun()
            else:
                st.error("E-mail ou senha incorretos.")
                
    with tab_reg:
        ne = st.text_input("Novo E-mail", key="r_email")
        np = st.text_input("Nova Senha", type="password", key="r_pass")
        if st.button("Criar Conta"):
            if criar_usuario(ne.lower().strip(), np):
                st.success("Conta criada! Faça login.")
            else:
                st.error("Erro ao criar conta. E-mail já existe?")
    st.stop()

# --- 6. DASHBOARD (USUÁRIO LOGADO) ---
st.sidebar.markdown(f"**Usuário:** {st.session_state.email}")
if st.sidebar.button("Sair"):
    st.session_state.logado = False
    st.session_state.email = ''
    st.session_state.mes_foco = None
    st.rerun()

TIPOS_TRANSACOES = [
    'Receita', 'Despesa (PIX)', 'Despesa (Cheque Especial)', 
    'Despesa (Crédito C6)', 'Despesa (Crédito Nubank)', 
    'Despesa (Crédito Santander)', 'Despesa (VR)'
]
CATEGORIAS_RECEITA = ['Salário Líquido', 'VR', 'Outras Receitas', 'Resgate (Dinheiro Guardado)']
CATEGORIAS_DESPESA = ['Moradia', 'Transporte', 'Mercado', 'Delivery', 'Lazer', 'Saídas', 'Contas', 'Aplicação (Dinheiro Guardado)']

def criar_card(titulo, valor, cor_texto, cor_fundo):
    st.markdown(f"""
    <div style="background-color: {cor_fundo}; padding: 15px; border-radius: 10px; border-left: 5px solid {cor_texto}; margin-bottom: 15px;">
        <p style="margin: 0; font-size: 14px; color: #555; font-weight: 600;">{titulo}</p>
        <h3 style="margin: 0; color: {cor_texto};">R$ {valor:,.2f}</h3>
    </div>
    """, unsafe_allow_html=True)

def formata_br(valor):
    return f"R$ {valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

# Registro Lateral
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
        
        # Redirecionamento: Foca no mês do registro recém-criado
        st.session_state.mes_foco = comp.strftime('%Y-%m')
        st.rerun()

# Carregamento de Dados e Filtro de Mês
df_atual = carregar_dados(st.session_state.email)

if not df_atual.empty:
    df_atual['mes_ano'] = pd.to_datetime(df_atual['competencia']).dt.strftime('%Y-%m')
    meses = sorted(df_atual['mes_ano'].unique())
    
    # Define qual mês mostrar por padrão
    if st.session_state.mes_foco in meses:
        idx_padrao = meses.index(st.session_state.mes_foco)
    else:
        idx_padrao = len(meses) - 1
        
    mes_sel = st.selectbox("Selecione o Mês", meses, index=idx_padrao)
    st.session_state.mes_foco = mes_sel # Mantém o foco se navegar manualmente
    
    df_mes = df_atual[df_atual['mes_ano'] == mes_sel]
    
    # Métricas e Cálculos
    rec_total = df_mes[df_mes['tipo'] == 'Receita']['valor'].sum()
    rec_vr = df_mes[df_mes['categoria'] == 'VR']['valor'].sum()
    desp_pix = df_mes[df_mes['tipo'] == 'Despesa (PIX)']['valor'].sum()
    desp_cred = df_mes[df_mes['tipo'].str.contains('Crédito') | (df_mes['tipo'] == 'Despesa (Cheque Especial)')]['valor'].sum()
    
    df_h = df_atual[df_atual['mes_ano'] <= mes_sel]
    guardado = df_h[df_h['categoria'] == 'Aplicação (Dinheiro Guardado)']['valor'].sum() - \
               df_h[df_h['categoria'] == 'Resgate (Dinheiro Guardado)']['valor'].sum()

    t1, t2 = st.tabs(["💰 Resumo", "📊 Gráficos"])

    with t1:
        st.markdown("### Visão Geral")
        c1, c2, c3 = st.columns(3)
        c1.metric("Rec. Total", f"R$ {rec_total:,.2f}")
        c2.metric("Saída Pix", f"R$ {desp_pix:,.2f}")
        c3.metric("Faturas/Crédito", f"R$ {desp_cred:,.2f}")
        
        st.markdown("### Saldos Calculados")
        c4, c5, c6, c7 = st.columns(4)
        with c4: criar_card("Saldo Conta", rec_total - rec_vr - desp_pix, "#1565c0", "#e3f2fd")
        with c5: criar_card("Saldo VR", rec_vr - df_mes[df_mes['tipo'] == 'Despesa (VR)']['valor'].sum(), "#0277bd", "#e1f5fe")
        with c6: criar_card("Resultado Mês", rec_total - df_mes[df_mes['tipo'] != 'Receita']['valor'].sum(), "#4527a0", "#ede7f6")
        with c7: criar_card("Acumulado Guardado", guardado, "#6a1b9a", "#f3e5f5")

        st.markdown("---")
        st.subheader("Registros Detalhados")
        for _, row in df_mes.sort_values(by='competencia').iterrows():
            col1, col2, col3, col4, col5, col6 = st.columns([1.5, 2.5, 2, 2, 1.5, 0.5])
            col1.write(row['competencia'].strftime('%d/%m/%Y'))
            col2.write(f"{'🟢' if row['tipo'] == 'Receita' else '🟡' if 'Crédito' in row['tipo'] else '🔴'} {row['tipo']}")
            col3.write(row['categoria'])
            col4.write(row['descricao'])
            col5.write(f"R$ {row['valor']:,.2f}")
            if col6.button("🗑️", key=f"del_{row['id']}"):
                excluir_registro(row['id'], st.session_state.email)
                st.rerun()

    with t2:
        df_g = df_mes[df_mes['tipo'] != 'Receita']
        if not df_g.empty:
            cg1, cdiv, cg2 = st.columns([10, 1, 10])
            with cg1:
                df_cat = df_g.groupby('categoria')['valor'].sum().reset_index()
                fig1 = px.bar(df_cat, x='categoria', y='valor', text=df_cat['valor'].apply(formata_br), title="Gastos por Categoria")
                fig1.update_layout(yaxis=dict(visible=False), xaxis_title=None); st.plotly_chart(fig1, use_container_width=True)
            with cg2:
                df_tp = df_g.groupby('tipo')['valor'].sum().reset_index()
                fig2 = px.bar(df_tp, x='tipo', y='valor', text=df_tp['valor'].apply(formata_br), title="Gastos por Fonte")
                fig2.update_layout(yaxis=dict(visible=False), xaxis_title=None); st.plotly_chart(fig2, use_container_width=True)
        
        df_f = df_atual[(df_atual['mes_ano'] >= mes_sel) & (df_atual['tipo'].str.contains('Crédito'))]
        if not df_f.empty:
            st.markdown("### Projeção de Faturas Futuras")
            df_p = df_f.groupby(['mes_ano', 'tipo'])['valor'].sum().reset_index()
            fig3 = px.bar(df_p, x='mes_ano', y='valor', color='tipo', text=df_p['valor'].apply(formata_br), title="Evolução de Crédito")
            fig3.update_layout(xaxis=dict(type='category'), yaxis=dict(visible=False)); st.plotly_chart(fig3, use_container_width=True)
else:
    st.info(f"Logado como {st.session_state.email}. Adicione o primeiro registro para ativar os gráficos!")