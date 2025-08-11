import streamlit as st
import instaloader
import os
import re
# Removed: from moviepy.editor import VideoFileClip
import datetime
import base64
import io
# Removed: from PIL import Image # No longer needed for frame extraction
import requests # Importação para fazer requisições HTTP à API Gemini

# --- Configurações Iniciais ---
DOWNLOAD_DIR = "instagram_downloads"
# Garante que o diretório de downloads exista
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# Inicializa o Instaloader (sem login por padrão para posts públicos)
# Para baixar de perfis privados ou contornar limites, você precisaria de login.
# Ex: L = instaloader.Instaloader(login="seu_usuario", password="sua_senha")
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
        # Pega o Post pelo shortcode
        post = instaloader.Post.from_shortcode(L.context, shortcode)

        # Verifica se é um vídeo
        if not post.is_video:
            st.warning("A URL fornecida não é de um vídeo. Por favor, insira uma URL de vídeo.")
            return None

        st.info(f"Baixando vídeo: {post.url}")

        # Define o diretório de destino para o download
        L.dirname_pattern = DOWNLOAD_DIR
        # Define o padrão do nome do arquivo (ex: username_shortcode.mp4)
        L.filename_pattern = "{profile}_{shortcode}"

        # Baixa o post. Instaloader cria os arquivos no dirname_pattern.
        # Ele baixa o vídeo, a imagem de capa, e o arquivo de metadados.
        L.download_post(post, target=DOWNLOAD_DIR)

        # Encontra o arquivo de vídeo baixado (pode ser .mp4 ou .mov)
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
        # Obter tamanho do arquivo
        file_size_bytes = os.path.getsize(file_path)
        analysis_results["Tamanho do Arquivo"] = f"{file_size_bytes / (1024 * 1024):.2f} MB"
        analysis_results["Caminho do Arquivo"] = file_path
        analysis_results["Nome do Arquivo"] = os.path.basename(file_path)

        # --- Análise de IA com Gemini ---
        st.info("Realizando análise de IA com Gemini... Isso pode levar um tempo.")

        # Verificar o tamanho do arquivo para a análise inline (limite ~20MB)
        if file_size_bytes > 20 * 1024 * 1024: # 20 MB
            st.warning("O vídeo é muito grande para análise inline com a API Gemini (limite ~20MB). A análise de IA pode falhar ou ser incompleta.")
            analysis_results["Análise de IA"] = "Vídeo muito grande para análise inline com Gemini. Considere usar a File API para vídeos maiores."
            return analysis_results

        # Ler o arquivo de vídeo e codificá-lo em base64
        with open(file_path, "rb") as video_file:
            encoded_video = base64.b64encode(video_file.read()).decode("utf-8")

        # Determinar o MIME type do vídeo
        mime_type = "video/mp4"
        if file_path.lower().endswith(".mov"):
            mime_type = "video/quicktime"
        elif file_path.lower().endswith(".flv"):
            mime_type = "video/x-flv"
        elif file_path.lower().endswith(".mpeg"):
            mime_type = "video/mpeg"
        elif file_path.lower().endswith(".mpegps"):
            mime_type = "video/mpegps"

        # Construir o prompt para Gemini
        prompt_parts = [
            {"text": """
             #### *Instruções Gerais*  
Você é um *analista especialista em compliance eleitoral e comunicação pública no Brasil. Sua tarefa é analisar vídeos de candidatos, gestores ou instituições públicas e **avaliar sua conformidade com as leis eleitorais brasileiras*, incluindo:  
- *Lei 9.504/1997* (condutas vedadas em período eleitoral).  
- *Constituição Federal, Art. 37, §1º* (vedação à promoção pessoal).  
- *LGPD* e *LAI* (transparência e proteção de dados).  

Siga estas etapas rigorosamente:  

---

### *1. Coletar Informações do Vídeo*  
Antes de analisar, pergunte ao usuário (ou extraia dos metadados):  
- *Tipo de canal*: Oficial da instituição / Pessoal do gestor / Colab entre ambos / WhatsApp.  
- *Período de publicação: Está dentro dos **3 meses anteriores à eleição*? (Se sim, aplique restrições extras do Art. 73 da Lei 9.504/97).  
- *Conteúdo principal*: O vídeo fala de obras, serviços públicos, ou tem tom eleitoral?  

---

### *2. Análise de Conformidade*  
Verifique os itens abaixo e classifique cada um como *✅ Conforme, **⚠ Parcialmente Conforme* ou *❌ Não Conforme*:  

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
- *Perfil oficial: Deve ser **100% impessoal* (foco em serviços públicos).  
- *Perfil pessoal: Pode mostrar bastidores, mas **sem uso de verba pública* ou apelo eleitoral.  
- *Colab (oficial + pessoal): Risco altíssimo de violar a **CF/88, Art. 37*.  

#### *C. Período Eleitoral*  
Se o vídeo será publicado nos *3 meses antes da eleição*:  
- *Vedação total* a publicidade institucional (exceto em emergências autorizadas pela Justiça Eleitoral).  
- *Proibição* de qualquer conteúdo que beneficie candidatos.  
-apelo partidário ou eleitoral.
---

### *3. Modelo de Resposta*  
Entregue o resultado *em tabelas claras*, como no exemplo abaixo:  

#### *Tabela 1: Conformidade por Item*  
| *Item Analisado*       | *Status*       | *Risco* | *Fundamento Legal*       |  
|--------------------------|------------------|-----------|----------------------------|  
| Promoção pessoal         | ❌ Não conforme  | Alto      | CF/88, Art. 37, §1º        |  
 Uso de símbolos partidários | ✅ Conforme   | Baixo     | Lei 9.504/97, Art. 73      |  

#### *Tabela 2: Recomendações*  
| *Ação Necessária*               | *Prazo*       |  
|-----------------------------------|-----------------|  
| Remover cenas com o gestor        | Imediato        |  
| Alterar canal para perfil pessoal | Antes da publicação |  

---

### *4. Exemplos Práticos*  
*Caso 1: Vídeo da prefeitura mostrando uma obra com a frase *"Gestão do Prefeito João".  
- *Problema: Viola a **CF/88, Art. 37* (promoção pessoal).  
- *Solução: Substituir por *"Prefeitura de São Paulo entrega nova obra".  

*Caso 2: Candidato em perfil pessoal diz *"Preciso do seu voto!" fora do período eleitoral.  
- *Problema: **Lei 9.504/97* só permite campanha em datas específicas.  
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
- *Nunca* invente interpretações legais.  

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

        # Chamar a API Gemini
        api_key = "AIzaSyAjv5HJvMRa-CSebtdkCYfqNTYhhl-05b4" # Placeholder for the API key, will be filled by Canvas runtime or user's secrets.toml
        if not api_key:
            if "gemini_api_key" in st.secrets:
                api_key = st.secrets["gemini_api_key"]
            else:
                st.warning("Chave da API Gemini não configurada. A análise de IA não será realizada. Por favor, adicione 'gemini_api_key' aos seus segredos do Streamlit (arquivo .streamlit/secrets.toml).")
                analysis_results["Análise de IA"] = "Chave da API Gemini não configurada."
                return analysis_results

        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
        payload = {"contents": [{"role": "user", "parts": prompt_parts}]}

        response = requests.post(api_url, headers={'Content-Type': 'application/json'}, json=payload)
        response.raise_for_status() # Lança uma exceção para erros HTTP
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
    for f in os.listdir(DOWNLOAD_DIR):
        if f.endswith(".mp4") or f.endswith(".mov"):
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
st.set_page_config(page_title="Cypher's Instagram Video Downloader", layout="wide")

# --- Tela de Login ---
if not st.session_state['logged_in']:
    st.title("Bem-vindo ao Cypher's Instagram Video Downloader")
    st.subheader("Por favor, faça login para continuar.")

    username = st.text_input("Usuário:")
    password = st.text_input("Senha:", type="password")

    # Credenciais de exemplo (você pode alterar ou usar um método mais seguro)
    CORRECT_USERNAME = "riquelme"
    CORRECT_PASSWORD = "cypherpassword" # Altere para uma senha mais segura!

    if st.button("Entrar"):
        if username == CORRECT_USERNAME and password == CORRECT_PASSWORD:
            st.session_state['logged_in'] = True
            st.success("Login bem-sucedido!")
            st.rerun() # Força a atualização para exibir o app principal
        else:
            st.error("Usuário ou senha incorretos.")
else:
    # --- App Principal (exibido após o login) ---
    st.title("🤖 Cypher's Instagram Video Downloader e Analisador")
    st.markdown("Seja bem-vindo, Riquelme! Use este app para baixar e analisar vídeos do Instagram.")

    # Botão de Logout
    if st.sidebar.button("Sair"):
        st.session_state['logged_in'] = False
        st.session_state['downloaded_videos'] = [] # Opcional: Limpar dados ao sair
        st.session_state['analysis_history'] = [] # Opcional: Limpar dados ao sair
        st.rerun()

    tab1, tab2, tab3 = st.tabs(["⬇️ Baixar Vídeos", "🔬 Analisar Vídeo", "📂 Vídeos Baixados"])

    with tab1:
        st.header("Baixar Vídeos do Instagram")
        video_url = st.text_input("Cole o link do vídeo do Instagram aqui:", key="video_url_input")

        if st.button("Baixar Vídeo", key="download_button"):
            if video_url:
                with st.spinner("Baixando vídeo... Isso pode levar um tempo dependendo do tamanho do vídeo."):
                    downloaded_path = download_instagram_video(video_url)
                    if downloaded_path and downloaded_path not in st.session_state['downloaded_videos']:
                        st.session_state['downloaded_videos'].append(downloaded_path)
                        st.session_state['downloaded_videos'] = sorted(list(set(st.session_state['downloaded_videos']))) # Remove duplicatas e ordena
            else:
                st.warning("Por favor, insira uma URL de vídeo para baixar.")

    with tab2:
        st.header("Analisar Vídeo Baixado")

        if not st.session_state['downloaded_videos']:
            st.info("Nenhum vídeo baixado ainda. Por favor, baixe um vídeo na aba 'Baixar Vídeos' primeiro.")
        else:
            # Cria uma lista de nomes de arquivos para o selectbox
            video_options = [os.path.basename(f) for f in st.session_state['downloaded_videos']]
            selected_video_name = st.selectbox("Selecione um vídeo para analisar:", video_options, key="video_select")

            if st.button("Analisar Vídeo Selecionado", key="analyze_button"):
                if selected_video_name:
                    # Encontra o caminho completo do arquivo selecionado
                    selected_video_path = next((f for f in st.session_state['downloaded_videos'] if os.path.basename(f) == selected_video_name), None)

                    if selected_video_path and os.path.exists(selected_video_path):
                        with st.spinner(f"Analisando {selected_video_name} com IA..."): # Texto do spinner atualizado
                            analysis_results = get_video_analysis(selected_video_path)
                            if analysis_results:
                                analysis_text = f"--- Análise de: {analysis_results.get('Nome do Arquivo', 'N/A')} ({datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) ---\n"
                                analysis_text += "**Análise Básica:**\n"
                                for key, value in analysis_results.items():
                                    # Exclui a análise de IA e chaves internas. Duração e Resolução não são mais obtidas aqui.
                                    if key not in ["Análise de IA", "Erro", "Caminho do Arquivo", "Nome do Arquivo"]:
                                        analysis_text += f"- {key}: {value}\n"
                                if "Análise de IA" in analysis_results:
                                    analysis_text += "\n**Análise de IA (Gemini):**\n"
                                    analysis_text += f"{analysis_results['Análise de IA']}\n"
                                if "Erro" in analysis_results:
                                    analysis_text += f"\n**Erro na Análise:**\n{analysis_results['Erro']}\n"
                                analysis_text += "\n"
                                st.session_state['analysis_history'].append(analysis_text)
                                st.success("Análise concluída e adicionada ao histórico!")
                                st.rerun() # Força a atualização para mostrar o histórico
                            else:
                                st.error("Não foi possível obter a análise do vídeo.")
                    else:
                        st.error("Vídeo selecionado não encontrado. Pode ter sido movido ou excluído.")
                else:
                    st.warning("Por favor, selecione um vídeo para analisar.")

        st.subheader("Histórico de Análises")
        if st.session_state['analysis_history']:
            # Exibe o histórico em ordem reversa (mais recente primeiro)
            st.text_area("Histórico de Análises:", value="".join(st.session_state['analysis_history'][::-1]), height=300, key="analysis_history_display")
        else:
            st.info("O histórico de análises está vazio.")

    with tab3:
        st.header("Vídeos Baixados")
        if not st.session_state['downloaded_videos']:
            st.info("Nenhum vídeo baixado ainda.")
        else:
            st.write(f"Total de vídeos baixados: {len(st.session_state['downloaded_videos'])}")
            for i, video_path in enumerate(st.session_state['downloaded_videos']):
                video_name = os.path.basename(video_path)
                try:
                    file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
                    st.markdown(f"**{i+1}. {video_name}** ({file_size_mb:.2f} MB)")
                    # O Streamlit pode exibir vídeos diretamente
                    st.video(video_path)
                except FileNotFoundError:
                    st.warning(f"Arquivo não encontrado: {video_name}. Pode ter sido movido ou excluído.")
                except Exception as e:
                    st.error(f"Erro ao carregar o vídeo {video_name}: {e}")

