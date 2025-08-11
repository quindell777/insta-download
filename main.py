# requirements.txt
# streamlit
# instaloader
# requests

import streamlit as st
import instaloader
import os
import re
import datetime
import base64
import requests
from pathlib import Path

# --- Constantes e Configurações ---

# Diretório para salvar os downloads
DOWNLOAD_DIR = Path("instagram_downloads")
# Garante que o diretório de downloads exista
DOWNLOAD_DIR.mkdir(exist_ok=True)

# Prompt detalhado para a análise de IA com o Gemini
GEMINI_ANALYSIS_PROMPT = """
#### *Instruções Gerais*

Você é um *analista especialista em compliance eleitoral e comunicação pública no Brasil*. Sua tarefa é analisar vídeos de candidatos, gestores ou instituições públicas e **avaliar sua conformidade com as leis eleitorais brasileiras**, incluindo:

- *Lei 9.504/1997* (condutas vedadas em período eleitoral).
- *Constituição Federal, Art. 37, §1º* (vedação à promoção pessoal).
- *LGPD* e *LAI* (transparência e proteção de dados).

Siga estas etapas rigorosamente:

---

### *1. Coletar Informações do Vídeo*
Antes de analisar, pergunte ao usuário (ou extraia dos metadados):
- *Tipo de canal*: Oficial da instituição / Pessoal do gestor / Colab entre ambos / WhatsApp.
- *Período de publicação*: Está dentro dos **3 meses anteriores à eleição**? (Se sim, aplique restrições extras do Art. 73 da Lei 9.504/97).
- *Conteúdo principal*: O vídeo fala de obras, serviços públicos, ou tem tom eleitoral?

---

### *2. Análise de Conformidade*
Verifique os itens abaixo e classifique cada um como *✅ Conforme, ⚠ Parcialmente Conforme* ou *❌ Não Conforme*:

#### *A. Conteúdo Proibido*
- *Promoção pessoal*:
  - Vídeos oficiais que destacam o nome, imagem ou desempenho individual do gestor (ex.: "Prefeito João fez...").
  - Uso de slogans como "Trabalho e Resultados" associados ao gestor.
  - Frases como "Contem comigo!" ou "Vamos juntos!" em períodos vedados.
  - Cores, símbolos ou jingles de campanha.
- *Uso indevido de recursos públicos*:
  - Servidores públicos aparecendo em vídeos com tom partidário.
  - Logotipos oficiais em eventos de campanha.

#### *B. Canal de Divulgação*
- *Perfil oficial*: Deve ser **100% impessoal** (foco em serviços públicos).
- *Perfil pessoal*: Pode mostrar bastidores, mas **sem uso de verba pública** ou apelo eleitoral.
- *Colab (oficial + pessoal)*: Risco altíssimo de violar a **CF/88, Art. 37**.

#### *C. Período Eleitoral*
Se o vídeo será publicado nos *3 meses antes da eleição*:
- *Vedação total* a publicidade institucional (exceto em emergências autorizadas pela Justiça Eleitoral).
- *Proibição* de qualquer conteúdo que beneficie candidatos.
- Apelo partidário ou eleitoral.

---

### *3. Modelo de Resposta*
Entregue o resultado *em tabelas claras*, como no exemplo abaixo:

#### *Tabela 1: Conformidade por Item*
| *Item Analisado* | *Status* | *Risco* | *Fundamento Legal* |
|---|---|---|---|
| Promoção pessoal | ❌ Não conforme | Alto | CF/88, Art. 37, §1º |
| Uso de símbolos partidários | ✅ Conforme | Baixo | Lei 9.504/97, Art. 73 |

#### *Tabela 2: Recomendações*
| *Ação Necessária* | *Prazo* |
|---|---|
| Remover cenas com o gestor | Imediato |
| Alterar canal para perfil pessoal | Antes da publicação |

---

### *4. Exemplos Práticos*
*Caso 1*: Vídeo da prefeitura mostrando uma obra com a frase *"Gestão do Prefeito João"*.
- *Problema*: Viola a **CF/88, Art. 37** (promoção pessoal).
- *Solução*: Substituir por *"Prefeitura de São Paulo entrega nova obra"*.

*Caso 2*: Candidato em perfil pessoal diz *"Preciso do seu voto!"* fora do período eleitoral.
- *Problema*: **Lei 9.504/97** só permite campanha em datas específicas.
- *Solução*: Suspender publicação até o período permitido.

---

### *5. Checklist Final*
Antes de aprovar o vídeo, confirme:
- [ ] *Nenhuma* menção a candidatos em canais oficiais.
- [ ] *Zero* símbolos partidários (cores, logos, músicas).
- [ ] *Nenhum* pedido de voto (direto ou indireto) se fora do período eleitoral.

---

### *6. Regras para Dúvidas*
- Se o vídeo estiver *na fronteira da legalidade*, retorne:
  "Status: ⚠ Análise jurídica necessária. Consulte a equipe jurídica antes de publicar."
- *Nunca* invente interpretações legais.

---

### *7. Resumo*
- *Sempre* forneça uma análise clara e objetiva, com base nas leis brasileiras.
"""

# --- Funções Auxiliares ---

def get_credentials(user_key, pass_key, secrets_user_key, secrets_pass_key, default_user, default_pass):
    """Busca credenciais nas variáveis de ambiente, depois nos segredos do Streamlit."""
    user = os.environ.get(user_key)
    password = os.environ.get(pass_key)

    if not all([user, password]):
        try:
            user = st.secrets.get(secrets_user_key)
            password = st.secrets.get(secrets_pass_key)
        except (st.errors.StreamlitAPIException, AttributeError):
            pass # Ignora o erro se os segredos não existirem

    if not all([user, password]):
        st.sidebar.warning(f"Credenciais para '{user_key}' não encontradas. Usando valores padrão. Isso não é recomendado para produção.")
        return default_user, default_pass

    return user, password

def initialize_instaloader():
    """Inicializa e faz login no Instaloader, armazenando a instância no session_state."""
    if 'instaloader_instance' in st.session_state:
        return st.session_state.instaloader_instance

    L = instaloader.Instaloader(
        dirname_pattern=str(DOWNLOAD_DIR),
        filename_pattern="{profile}_{shortcode}",
        save_metadata=False, # Não salva os arquivos .json, .txt
        download_comments=False,
        download_geotags=False,
        download_video_thumbnails=False
    )

    insta_user, insta_pass = get_credentials(
        "INSTAGRAM_USER", "INSTAGRAM_PASSWORD",
        "instagram_user", "instagram_password",
        None, None
    )

    if insta_user and insta_pass:
        try:
            st.sidebar.info(f"Tentando login no Instagram como {insta_user}...")
            L.login(insta_user, insta_pass)
            st.sidebar.success("Login no Instagram realizado com sucesso!")
            st.session_state.insta_logged_in = True
        except Exception as e:
            st.sidebar.error(f"Falha no login do Instagram: {e}")
            st.sidebar.warning("A aplicação continuará em modo anônimo (sujeito a bloqueios).")
            st.session_state.insta_logged_in = False
    else:
        st.sidebar.warning("Nenhuma credencial do Instagram encontrada. Rodando em modo anônimo.")
        st.session_state.insta_logged_in = False

    st.session_state.instaloader_instance = L
    return L

def get_post_shortcode(url):
    """Extrai o shortcode de uma URL do Instagram."""
    match = re.search(r'(?:/p/|/reel/|/tv/)([a-zA-Z0-9_-]+)', url)
    return match.group(1) if match else None

def download_instagram_video(url, instaloader_instance):
    """
    Baixa um vídeo do Instagram usando uma instância do Instaloader.
    Retorna o caminho do arquivo baixado ou None em caso de erro.
    """
    shortcode = get_post_shortcode(url)
    if not shortcode:
        st.error("URL do Instagram inválida. Por favor, insira uma URL de post/reel válida.")
        return None

    try:
        post = instaloader.Post.from_shortcode(instaloader_instance.context, shortcode)

        if not post.is_video:
            st.warning("A URL fornecida não é de um vídeo.")
            return None

        st.info(f"Baixando vídeo do perfil: {post.owner_username}")
        
        # O Instaloader baixa todos os arquivos associados, precisamos encontrar o vídeo
        instaloader_instance.download_post(post, target=shortcode)
        
        # Procura pelo arquivo de vídeo no diretório de download específico do post
        post_dir = DOWNLOAD_DIR / shortcode
        video_files = list(post_dir.glob('*.mp4')) + list(post_dir.glob('*.mov'))

        if not video_files:
            st.error("Não foi possível encontrar o arquivo de vídeo baixado.")
            return None

        # Move o vídeo para o diretório principal e renomeia
        source_path = video_files[0]
        final_filename = f"{post.owner_username}_{shortcode}{source_path.suffix}"
        final_filepath = DOWNLOAD_DIR / final_filename

        # Evita sobrescrever se o arquivo já existir
        if not final_filepath.exists():
            source_path.rename(final_filepath)

        # Limpa o diretório temporário do post
        for f in post_dir.iterdir():
            f.unlink()
        post_dir.rmdir()

        st.success(f"Vídeo baixado com sucesso: {final_filename}")
        return str(final_filepath)

    except instaloader.exceptions.PrivateProfileNotFollowedException:
        st.error("Perfil privado e você não o segue. O login no Instagram é necessário.")
    except instaloader.exceptions.NotFoundException:
        st.error("Post não encontrado (Erro 404). Verifique a URL.")
    except instaloader.exceptions.TooManyRequestsException:
        st.error("Muitas requisições! O Instagram bloqueou temporariamente o acesso. Tente mais tarde.")
    except Exception as e:
        st.error(f"Ocorreu um erro inesperado ao baixar o vídeo: {e}")
    return None

def get_video_analysis(file_path_str):
    """
    Realiza análises básica e de IA do vídeo usando a API Gemini.
    Retorna um dicionário com os resultados.
    """
    file_path = Path(file_path_str)
    analysis_results = {}
    
    try:
        file_size_bytes = file_path.stat().st_size
        analysis_results["Tamanho do Arquivo"] = f"{file_size_bytes / (1024 * 1024):.2f} MB"
        analysis_results["Nome do Arquivo"] = file_path.name

        # --- Análise com Gemini ---
        st.info("Realizando análise de IA com Gemini... Isso pode levar um momento.")

        api_key, _ = get_credentials("GEMINI_API_KEY", None, "gemini_api_key", None, None, None)

        if not api_key:
            st.error("Chave da API Gemini não configurada.")
            st.warning(
                "Para usar a análise de IA, configure a `GEMINI_API_KEY` como uma "
                "variável de ambiente ou em `secrets.toml`."
            )
            analysis_results["Análise de IA"] = "Chave da API não configurada."
            return analysis_results

        # Limite de tamanho para upload direto (aproximadamente 20MB)
        if file_size_bytes > 20 * 1024 * 1024:
            st.warning("O vídeo é muito grande (> 20MB) para análise inline com a API Gemini.")
            analysis_results["Análise de IA"] = "Vídeo muito grande para análise."
            return analysis_results

        with open(file_path, "rb") as video_file:
            encoded_video = base64.b64encode(video_file.read()).decode("utf-8")

        mime_type = "video/mp4" if file_path.suffix.lower() == ".mp4" else "video/quicktime"

        prompt_parts = [
            {"text": GEMINI_ANALYSIS_PROMPT},
            {"inlineData": {"mimeType": mime_type, "data": encoded_video}}
        ]

        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        payload = {"contents": [{"role": "user", "parts": prompt_parts}]}
        
        response = requests.post(api_url, headers={'Content-Type': 'application/json'}, json=payload)
        response.raise_for_status() # Lança um erro para respostas HTTP 4xx/5xx
        
        result = response.json()

        if candidate := result.get("candidates"):
            ai_analysis_text = candidate[0]["content"]["parts"][0]["text"]
            analysis_results["Análise de IA"] = ai_analysis_text
        else:
            analysis_results["Análise de IA"] = "Não foi possível obter a análise da IA."
            st.warning(f"Resposta inesperada da API Gemini: {result}")

    except requests.exceptions.HTTPError as http_err:
        st.error(f"Erro na API Gemini (HTTP {http_err.response.status_code}): {http_err.response.text}")
        analysis_results["Análise de IA"] = f"Erro na API: {http_err.response.text}"
    except Exception as e:
        st.error(f"Erro ao analisar o vídeo com IA: {e}")
        analysis_results["Análise de IA"] = f"Erro na análise de IA: {e}"
        
    return analysis_results

def load_downloaded_videos():
    """Carrega a lista de vídeos baixados do diretório."""
    if not DOWNLOAD_DIR.exists():
        return []
    return sorted(
        [str(f) for f in DOWNLOAD_DIR.iterdir() if f.is_file() and f.suffix in [".mp4", ".mov"]],
        key=os.path.getmtime,
        reverse=True
    )

# --- Configuração da Página e Estado da Sessão ---
st.set_page_config(page_title="Cypher's Video Analyser", layout="wide", initial_sidebar_state="expanded")

# Inicializa o estado da sessão
if 'app_logged_in' not in st.session_state:
    st.session_state.app_logged_in = False
if 'downloaded_videos' not in st.session_state:
    st.session_state.downloaded_videos = load_downloaded_videos()
if 'analysis_history' not in st.session_state:
    st.session_state.analysis_history = []


# --- Tela de Login do Aplicativo ---
if not st.session_state.app_logged_in:
    st.title("Bem-vindo ao Cypher's Video Analyser")
    st.subheader("Por favor, faça login para continuar.")

    app_user, app_pass = get_credentials(
        "APP_USER", "APP_PASSWORD",
        "app_user", "app_password",
        "riquelme", "cypherpassword"
    )

    with st.form("login_form"):
        username = st.text_input("Usuário:", value="riquelme")
        password = st.text_input("Senha:", type="password")
        submitted = st.form_submit_button("Entrar")

        if submitted:
            if username == app_user and password == app_pass:
                st.session_state.app_logged_in = True
                st.success("Login bem-sucedido!")
                st.rerun()
            else:
                st.error("Usuário ou senha incorretos.")
else:
    # --- Aplicativo Principal ---
    
    # Inicializa o Instaloader após o login no app
    L = initialize_instaloader()

    st.sidebar.title("Cypher's Analyser")
    st.sidebar.markdown(f"Bem-vindo, **Riquelme**!")
    if st.sidebar.button("Sair do App"):
        # Limpa o estado da sessão para um logout completo
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

    st.title("🤖 Analisador de Vídeos do Instagram")
    
    tab1, tab2, tab3 = st.tabs(["⬇️ Baixar Vídeos", "🔬 Analisar Vídeo", "📂 Vídeos Baixados"])

    with tab1:
        st.header("Baixar Vídeo do Instagram")
        video_url = st.text_input("Cole o link do vídeo do Instagram aqui:", key="video_url_input")

        if st.button("Baixar Vídeo", key="download_button"):
            if video_url:
                with st.spinner("Conectando ao Instagram e baixando..."):
                    downloaded_path = download_instagram_video(video_url, L)
                    if downloaded_path:
                        # Recarrega a lista de vídeos
                        st.session_state.downloaded_videos = load_downloaded_videos()
                        st.rerun() # Atualiza a UI para mostrar o novo vídeo nas outras abas
            else:
                st.warning("Por favor, insira uma URL de vídeo para baixar.")

    with tab2:
        st.header("Analisar Vídeo Baixado")

        if not st.session_state.downloaded_videos:
            st.info("Nenhum vídeo baixado. Use a aba 'Baixar Vídeos' primeiro.")
        else:
            video_options = {os.path.basename(f): f for f in st.session_state.downloaded_videos}
            selected_video_name = st.selectbox(
                "Selecione um vídeo para analisar:",
                options=video_options.keys(),
                key="video_select"
            )

            if st.button("Analisar Vídeo Selecionado", key="analyze_button"):
                if selected_video_name:
                    selected_video_path = video_options[selected_video_name]
                    
                    with st.spinner(f"Analisando '{selected_video_name}'..."):
                        analysis_results = get_video_analysis(selected_video_path)
                        
                        if analysis_results:
                            # Formata o texto para o histórico
                            now = datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')
                            history_entry = (
                                f"### Análise de: {analysis_results.get('Nome do Arquivo', 'N/A')} ({now})\n\n"
                                f"**Tamanho:** {analysis_results.get('Tamanho do Arquivo', 'N/A')}\n\n"
                                f"**Análise de IA (Gemini):**\n\n"
                                f"{analysis_results.get('Análise de IA', 'Nenhuma análise disponível.')}\n\n"
                                "---\n"
                            )
                            st.session_state.analysis_history.insert(0, history_entry)
                            st.success("Análise concluída!")
                            # Exibe a análise mais recente imediatamente
                            st.markdown(history_entry)

        st.subheader("Histórico de Análises")
        if st.session_state.analysis_history:
            full_history = "".join(st.session_state.analysis_history)
            st.markdown(full_history)
        else:
            st.info("O histórico de análises está vazio.")

    with tab3:
        st.header("Galeria de Vídeos Baixados")
        st.session_state.downloaded_videos = load_downloaded_videos() # Garante que a lista está atualizada

        if not st.session_state.downloaded_videos:
            st.info("Nenhum vídeo baixado ainda.")
        else:
            st.write(f"Total de vídeos: {len(st.session_state.downloaded_videos)}")
            for video_path in st.session_state.downloaded_videos:
                video_name = os.path.basename(video_path)
                try:
                    file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
                    with st.expander(f"**{video_name}** ({file_size_mb:.2f} MB)"):
                        st.video(video_path)
                except Exception as e:
                    st.warning(f"Não foi possível carregar o vídeo {video_name}: {e}")
