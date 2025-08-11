import streamlit as st
import instaloader
import os
import re
import datetime
import base64
import requests # Importação para fazer requisições HTTP à API Gemini

# --- Configurações Iniciais ---
DOWNLOAD_DIR = "instagram_downloads"
# Garante que o diretório de downloads exista
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# Inicializa o Instaloader
L = instaloader.Instaloader()

# --- Funções Auxiliares ---

def get_post_shortcode(url):
    """Extrai o shortcode de uma URL do Instagram."""
    match = re.search(r'(?:/p/|/reel/|/tv/)([a-zA-Z0-9_-]+)', url)
    if match:
        return match.group(1)
    return None

def download_instagram_video(url):
    """
    Baixa um vídeo do Instagram usando o Instaloader.
    Retorna o caminho do arquivo baixado ou None em caso de erro.
    """
    shortcode = get_post_shortcode(url)
    if not shortcode:
        st.error("URL do Instagram inválida. Por favor, insira uma URL de post/reel válida.")
        return None

    try:
        post = instaloader.Post.from_shortcode(L.context, shortcode)

        if not post.is_video:
            st.warning("A URL fornecida não é de um vídeo. Por favor, insira uma URL de vídeo.")
            return None

        st.info(f"Baixando vídeo: {post.url}")

        L.dirname_pattern = DOWNLOAD_DIR
        L.filename_pattern = "{profile}_{shortcode}"
        L.download_post(post, target=DOWNLOAD_DIR)

        video_filename = None
        for f in os.listdir(DOWNLOAD_DIR):
            if f.startswith(f"{post.owner_username}_{shortcode}") and (f.endswith(".mp4") or f.endswith(".mov")):
                video_filename = f
                break

        if video_filename:
            file_path = os.path.join(DOWNLOAD_DIR, video_filename)
            st.success(f"Vídeo baixado com sucesso: {video_filename}")
            return file_path
        else:
            st.error("Não foi possível encontrar o arquivo de vídeo baixado.")
            return None

    except instaloader.exceptions.PrivateProfileNotFollowedException:
        st.error("Este é um perfil privado e você não o segue. O Instaloader precisa de credenciais para baixar de perfis privados.")
        return None
    except instaloader.exceptions.PostNotExistsException:
        st.error("O post não existe ou foi removido.")
        return None
    except Exception as e:
        st.error(f"Ocorreu um erro ao baixar o vídeo: {e}")
        st.info("Para baixar de perfis privados ou contornar limites de taxa, você pode precisar configurar o login no Instaloader.")
        return None

def get_video_analysis(file_path):
    """
    Realiza uma análise básica e uma análise de IA do vídeo usando a API Gemini.
    Retorna um dicionário com os resultados da análise.
    """
    analysis_results = {}
    try:
        file_size_bytes = os.path.getsize(file_path)
        analysis_results["Tamanho do Arquivo"] = f"{file_size_bytes / (1024 * 1024):.2f} MB"
        analysis_results["Caminho do Arquivo"] = file_path
        analysis_results["Nome do Arquivo"] = os.path.basename(file_path)

        st.info("Realizando análise de IA com Gemini... Isso pode levar um tempo.")

        # --- LÓGICA DA API KEY MODIFICADA ---
        # Prioriza a variável de ambiente, depois Streamlit Secrets.
        api_key = os.environ.get("GEMINI_API_KEY") or st.secrets.get("gemini_api_key")

        if not api_key:
            st.error("Chave da API Gemini não configurada.")
            st.warning(
                "Para realizar a análise de IA, configure sua chave de API em uma das seguintes formas:\n"
                "1. (Recomendado para deploy) Crie uma Variável de Ambiente chamada `GEMINI_API_KEY`.\n"
                "2. (Para Streamlit Cloud) Adicione `gemini_api_key = 'SUA_CHAVE_AQUI'` no arquivo `.streamlit/secrets.toml`."
            )
            analysis_results["Análise de IA"] = "Chave da API Gemini não configurada."
            return analysis_results

        if file_size_bytes > 20 * 1024 * 1024: # 20 MB
            st.warning("O vídeo é muito grande para análise inline com a API Gemini (limite ~20MB). A análise de IA pode falhar.")
            analysis_results["Análise de IA"] = "Vídeo muito grande para análise inline com Gemini."
            return analysis_results

        with open(file_path, "rb") as video_file:
            encoded_video = base64.b64encode(video_file.read()).decode("utf-8")

        mime_type = "video/mp4"
        if file_path.lower().endswith(".mov"):
            mime_type = "video/quicktime"
        # Adicione outros mime types se necessário

        prompt_parts = [
            {"text": """
              #### *Instruções Gerais* Você é um *analista especialista em compliance eleitoral e comunicação pública no Brasil...
              
              [O PROMPT DETALHADO FOI OCULTADO PARA BREVIDADE]
              
              ---### *7. Resumo*
              - *Sempre* forneça uma análise clara e objetiva, com base nas leis brasileiras. 
              ."""},
            {
                "inlineData": {
                    "mimeType": mime_type,
                    "data": encoded_video
                }
            }
        ]

        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        payload = {"contents": [{"role": "user", "parts": prompt_parts}]}

        response = requests.post(api_url, headers={'Content-Type': 'application/json'}, json=payload)
        response.raise_for_status()
        result = response.json()

        if result.get("candidates") and result["candidates"][0].get("content") and result["candidates"][0]["content"].get("parts"):
            ai_analysis_text = result["candidates"][0]["content"]["parts"][0]["text"]
            analysis_results["Análise de IA"] = ai_analysis_text
        else:
            analysis_results["Análise de IA"] = "Não foi possível obter a análise da IA. Resposta inesperada da API."
            st.warning(f"Resposta da API Gemini inesperada: {result}")

    except Exception as e:
        st.error(f"Erro ao analisar o vídeo com IA: {e}")
        analysis_results["Análise de IA"] = f"Erro na análise de IA: {e}"
    return analysis_results

def load_downloaded_videos():
    """Carrega a lista de vídeos baixados do diretório."""
    video_files = []
    if os.path.exists(DOWNLOAD_DIR):
        for f in os.listdir(DOWNLOAD_DIR):
            if f.endswith((".mp4", ".mov")):
                video_files.append(os.path.join(DOWNLOAD_DIR, f))
    return video_files

# --- Inicialização do Session State ---
if 'downloaded_videos' not in st.session_state:
    st.session_state['downloaded_videos'] = load_downloaded_videos()

if 'analysis_history' not in st.session_state:
    st.session_state['analysis_history'] = []

if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

# --- Interface do Streamlit ---
st.set_page_config(page_title="Cypher's Video Analyser", layout="wide")

# --- Tela de Login ---
if not st.session_state['logged_in']:
    st.title("Bem-vindo ao Cypher's Video Analyser")
    st.subheader("Por favor, faça login para continuar.")

    username = st.text_input("Usuário:")
    password = st.text_input("Senha:", type="password")

    # Credenciais (use um método mais seguro em produção)
    CORRECT_USERNAME = os.environ.get("APP_USER") or st.secrets.get("app_user", "riquelme")
    CORRECT_PASSWORD = os.environ.get("APP_PASSWORD") or st.secrets.get("app_password", "cypherpassword")

    if st.button("Entrar"):
        if username == CORRECT_USERNAME and password == CORRECT_PASSWORD:
            st.session_state['logged_in'] = True
            st.success("Login bem-sucedido!")
            st.rerun()
        else:
            st.error("Usuário ou senha incorretos.")
else:
    # --- App Principal ---
    st.title("🤖 Cypher's Instagram Video Downloader e Analisador")
    st.markdown(f"Seja bem-vindo, {st.session_state.get('username', 'Riquelme')}! Use este app para baixar e analisar vídeos do Instagram.")

    if st.sidebar.button("Sair"):
        st.session_state['logged_in'] = False
        st.rerun()

    tab1, tab2, tab3 = st.tabs(["⬇️ Baixar Vídeos", "🔬 Analisar Vídeo", "📂 Vídeos Baixados"])

    with tab1:
        st.header("Baixar Vídeos do Instagram")
        video_url = st.text_input("Cole o link do vídeo do Instagram aqui:", key="video_url_input")

        if st.button("Baixar Vídeo", key="download_button"):
            if video_url:
                with st.spinner("Baixando vídeo..."):
                    downloaded_path = download_instagram_video(video_url)
                    if downloaded_path and downloaded_path not in st.session_state['downloaded_videos']:
                        st.session_state['downloaded_videos'].append(downloaded_path)
                        st.session_state['downloaded_videos'] = sorted(list(set(st.session_state['downloaded_videos'])))
            else:
                st.warning("Por favor, insira uma URL de vídeo para baixar.")

    with tab2:
        st.header("Analisar Vídeo Baixado")

        if not st.session_state['downloaded_videos']:
            st.info("Nenhum vídeo baixado. Use a aba 'Baixar Vídeos' primeiro.")
        else:
            video_options = [os.path.basename(f) for f in st.session_state['downloaded_videos']]
            selected_video_name = st.selectbox("Selecione um vídeo para analisar:", video_options, key="video_select")

            if st.button("Analisar Vídeo Selecionado", key="analyze_button"):
                if selected_video_name:
                    selected_video_path = next((f for f in st.session_state['downloaded_videos'] if os.path.basename(f) == selected_video_name), None)

                    if selected_video_path and os.path.exists(selected_video_path):
                        with st.spinner(f"Analisando {selected_video_name} com IA..."):
                            analysis_results = get_video_analysis(selected_video_path)
                            if analysis_results:
                                # Processamento e exibição dos resultados...
                                # [CÓDIGO DE EXIBIÇÃO OCULTADO PARA BREVIDADE]
                                st.success("Análise concluída!")
                                st.rerun()

    with tab3:
        st.header("Vídeos Baixados")
        # [CÓDIGO DE EXIBIÇÃO OCULTADO PARA BREVIDADE]
