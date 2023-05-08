import os 
import dotenv
import shutil
import gradio as gr
from typing import Union
from os import getenv

from src.utils.logger import get_logger
from src.utils.file_helper import get_filename 
from src.LlamaIndex.index import save_index, get_embeddings_from_pdf
from src.LlamaIndex.graph import build_graph_from_indices, save_graph
from src.Agent.LLamaIndexAgent.agent import build_graph_chat_agent_executor 
from langchain.agents import AgentExecutor
from src.ChatWrapper.ChatWrapper import ChatWrapper
from src.constants import KNOWLEDGE_GRAPH_FOLDER, SAVE_DIR, SUMMARY_PROMPT_FOR_EACH_INDEX
from src.utils.prepare_project import prepare_project_dir


dotenv.load_dotenv()
assert getenv("OPENAI_API_KEY") is not None, "OPENAI_API_KEY not set in .env"


def load_agent(index_name: str = None) -> AgentExecutor:
    logger.info(
        f"======================Using Llama-Index (GPT-Index) Agent======================")
    agent_executor = build_graph_chat_agent_executor(graph_name=index_name)
    logger.info(f"Agent has access to following tools {agent_executor.tools}")
    logger.info(
        f"Agent used temperature: {agent_executor.agent.llm_chain.llm.temperature}")
    return agent_executor


def upload_file_handler(files) -> list[str]:
    global UPLOADED_FILES  
    UPLOADED_FILES = []

    file_paths = [file.name for file in files]

    # create destination directory if it doesn't exist
    if not os.path.exists(SAVE_DIR):
        os.makedirs(SAVE_DIR)

    # loop over all files in the source directory
    uploads_filepath = []
    for path in file_paths:
        filename = get_filename(path)
        destination_path = os.path.join(SAVE_DIR, filename)

        # copy file from source to destination
        shutil.copy(path, destination_path)
        uploads_filepath.append(destination_path)

    UPLOADED_FILES = uploads_filepath
    return uploads_filepath

def multi_pdf_documents_indexing_handler(
    chunk_size: int,
    overlap_chunk: int,
    graph_name: str,
    progress=gr.Progress()
) -> str: 
    global UPLOADED_FILES  
    logger.info(
        f"{chunk_size},{overlap_chunk}, {UPLOADED_FILES}, {graph_name}")

    # indexing multiple documents 
    all_indices = []
    index_summaries = []
    for idx, file in enumerate(UPLOADED_FILES): 
        progress(0.1, "Verify Documents....")
        filename = get_filename(UPLOADED_FILES[idx])
        index_name = os.path.splitext(filename)[0]

        progress(0.3, "Analyzing & Indexing Documents....")
        index = get_embeddings_from_pdf(
            filepath=UPLOADED_FILES[idx])
        summary = index.query(SUMMARY_PROMPT_FOR_EACH_INDEX)                    
        summary = summary.response # NOTE: convert response to str
        all_indices.append(index)
        index_summaries.append(summary)

        progress(0.3, "Saving index...")
        save_index(index, saved_path=index_name)
        logger.info(f"Indexing complete & saving {index_name}....")

    # construct graph from indices
    progress(0.3, "Constructing knowledge from from multiple indices...")
    graph = build_graph_from_indices(all_indices=all_indices, index_summaries=index_summaries) 
    save_graph(graph, graph_name) 
    return "!!! DONE !!!"


# NOTE: un-used
# def single_pdf_documents_indexing_handler(
#         chunk_size: int,
#         overlap_chunk: int,
#         index_name: str,
#         progress=gr.Progress()) -> str:
#     global UPLOADED_FILES  
#     logger.info(
#         f"{chunk_size},{overlap_chunk}, {UPLOADED_FILES}, {index_name}")

#     progress(0.2, "Verify Documents....")
#     if not index_name:
#         filename = get_filename(UPLOADED_FILES[0])
#         index_name = os.path.splitext(filename)[0]

#     progress(0.5, "Analyzing & Indexing Documents....")
#     index = get_embeddings_from_pdf(
#         filepath=UPLOADED_FILES[0])

#     progress(0.3, "Saving index...")
#     save_index(index, index_name=index_name)
#     logger.info(f"Indexing complete & saving {index}....")
#     return "Done!"


def change_temperature_gpt_index_llm_handler(temperature: float) -> gr.Slider:
    global chat_gpt_index_agent
    agent_executor = chat_gpt_index_agent.agent
    agent_executor.agent.llm_chain.llm.temperature = temperature
    logger.info(
        f"Change LLM temperature to {agent_executor.agent.llm_chain.llm.temperature}")


def change_agent_handler(index_name: str, chatbot: gr.Chatbot) -> Union[gr.Chatbot, None, None, gr.Slider]:
    logger.info(f"Change GPTIndex Agent to use collection: {index_name}")

    global chat_gpt_index_agent   
    chat_gpt_index_agent = None

    agent_executor = load_agent(index_name=index_name)
    chat_gpt_index_agent = ChatWrapper(agent_executor)

    return gr.Chatbot.update(value=[]), None, None, gr.Slider.update(value=agent_executor.agent.llm_chain.llm.temperature)


def chat_with_agent_handler(message_txt_box, state, agent_state) -> Union[gr.Chatbot, gr.State]:
    global chat_gpt_index_agent
    if not chat_gpt_index_agent: 
        return [("There is no available document to chat with, you must indexing one before chatting","")], state 

    chatbot, state = chat_gpt_index_agent(message_txt_box, state, agent_state)
    return chatbot, state


def refresh_collection_list_handler() -> gr.Dropdown:
    global GPT_INDEX_LIST_COLLECTIONS  
    GPT_INDEX_LIST_COLLECTIONS = os.listdir(KNOWLEDGE_GRAPH_FOLDER)
    return gr.Dropdown.update(choices=GPT_INDEX_LIST_COLLECTIONS)



def clear_chat_history_handler() -> Union[gr.Chatbot, None, None]:
    global chat_gpt_index_agent  
    if chat_gpt_index_agent: 
        chat_gpt_index_agent.clear_agent_memory()
        logger.info(f"Clear agent memory...")
    logger.info(f"Clear chat history...")
    return gr.Chatbot.update(value=[]), None, None




def app() -> gr.Blocks:
    block = gr.Blocks(css=".gradio-container {background-color: lightgray}")

    with block:
        with gr.Tab("Chat GPT_Index"):
            with gr.Row():
                gr.Markdown("<h3><center>GPTIndex + LangChain Demo</center></h3>")

            with gr.Row():
                llama_index_dropdown_btn = gr.Dropdown(
                    value=GPT_INDEX_LIST_COLLECTIONS[0] if GPT_INDEX_LIST_COLLECTIONS else None, 
                    label="Index/Collection to chat with",
                    choices=GPT_INDEX_LIST_COLLECTIONS)

                llama_refresh_btn = gr.Button("⟳ Refresh Collections").style(full_width=False)

            temperature_llm_slider = gr.Slider(0, 2, step=0.2, value=0.1, label="Temperature")
            temperature_llm_slider.change(
                change_temperature_gpt_index_llm_handler,
                inputs=temperature_llm_slider 
            )

            llama_chatbot = gr.Chatbot()
            with gr.Row():
                llama_message_txt_box = gr.Textbox(
                    label="What's your question?",
                    placeholder="What's the answer to life, the universe, and everything?",
                    lines=1,
                ).style(full_width=True)

                llama_submit_chat_msg_btn = gr.Button(
                    value="Send", 
                    variant="primary").style(full_width=False)

                llama_clear_chat_history_btn = gr.Button(
                    value="Clear chat history (will clear chatbot memory)",
                    variant="stop").style(full_width=False)

            gr.Examples(
                examples=[
                    "Hi! How's it going?",
                    "What should I do tonight?",
                    "Whats 2 + 2?",
                ],
                inputs=llama_message_txt_box,
            )

            gr.HTML("Demo application of a LangChain chain.")
            gr.HTML(
                "<center>Powered by <a href='https://github.com/hwchase17/langchain'>LangChain 🦜️🔗</a></center>"
            )

        css = "footer {display: none !important;} .gradio-container {min-height: 0px !important;}"
        with gr.Tab(css=css, label="Upload & Index"):
            file_output = gr.File()
            gpt_upload_button = gr.UploadButton(
                "Click to upload *.pdf, *.txt files",
                file_types=[".txt", ".pdf"],
                file_count="multiple"
            )
            gpt_upload_button.upload(upload_file_handler, gpt_upload_button,
                                 file_output, api_name="upload_files")
            with gr.Row():
                gpt_chunk_slider = gr.Slider(
                    0, 3500, step=250, value=1000, label="Document Chunk Size")

                gpt_overlap_chunk_slider = gr.Slider(
                    0, 1500, step=20, value=40, label="Overlap Document Chunk Size")

            gpt_index_name = gr.Textbox(
                label="Collection/Index Name",
                placeholder="What's the name for this index? Eg: Document_ABC",
                lines=1)
            gpt_index_doc_btn = gr.Button(
                value="Index!", variant="secondary").style(full_width=False)

            gpt_status_text = gr.Textbox(label="Indexing Status")

            gpt_index_doc_btn.click(multi_pdf_documents_indexing_handler,
                                inputs=[gpt_chunk_slider,
                                        gpt_overlap_chunk_slider, gpt_index_name],
                                outputs=gpt_status_text)

        # NOTE: Llama Index
        llama_state = gr.State()
        llama_agent_state = gr.State()

        llama_index_dropdown_btn.change(change_agent_handler,
                                  inputs=llama_index_dropdown_btn,
                                  outputs=[llama_chatbot, llama_state, llama_agent_state, temperature_llm_slider])


        llama_submit_chat_msg_btn.click(chat_with_agent_handler,
                                      inputs=[llama_message_txt_box,
                                              llama_state, llama_agent_state],
                                      outputs=[llama_chatbot, llama_state])

        llama_message_txt_box.submit(chat_with_agent_handler,
                                   inputs=[llama_message_txt_box,
                                           llama_state, llama_agent_state],
                                   outputs=[llama_chatbot, llama_state],
                                   api_name="chats_gpt_index")

        llama_refresh_btn.click(fn=refresh_collection_list_handler,
                          outputs=llama_index_dropdown_btn)


        llama_clear_chat_history_btn.click(
            clear_chat_history_handler,
            outputs=[llama_chatbot, llama_state, llama_agent_state]
        )

    return block

if __name__ == "__main__":

    import argparse

    parser = argparse.ArgumentParser(
        description="Launch block queue with authentication and server details")

    parser.add_argument("--username", dest="username",
                        default="admin", help="Authentication username")
    parser.add_argument("--password", dest="password",
                        default="1234@abcezIJK1", help="Authentication password")
    parser.add_argument("--concurrency", dest="concurrency", default=1,
                        type=int, help="Number of concurrent blocks to process")
    parser.add_argument("--debug", dest="debug",
                        action="store_true", help="Enable debug mode")
    parser.add_argument("--port", dest="port", default=8000,
                        type=int, help="Server port")
    parser.add_argument("--show-api", dest="show_api",
                        action="store_true", help="Show API details")
    parser.add_argument("--verbose", dest="verbose",
                        action="store_true", help="Agent's verbosity")


    args = parser.parse_args()

    # Usage:
    # python script.py --username admin --password 1234@abcezIJK1 --concurrency 10 --debug --port 8000 --show-api
    # or
    # python script.py -u admin -p 1234@abcezIJK1 -c 10 -d -o 8000 -s

    n_concurrency = args.concurrency
    username = args.username
    password = args.password
    debug = args.debug
    server_port = args.port
    is_show_api = args.show_api
    agent_verbose = args.show_api # TODO: set this to constant.py 

    logger = get_logger()
    logger.info(f"Starting server with config: {args}")

    prepare_project_dir(logger)
    
    # Declared global variable scope
    UPLOADED_FILES = []
    GPT_INDEX_LIST_COLLECTIONS = os.listdir(KNOWLEDGE_GRAPH_FOLDER)

    gpt_index_agent_executor = None 
    chat_gpt_index_agent = None
    if GPT_INDEX_LIST_COLLECTIONS:  
        gpt_index_agent_executor = load_agent(GPT_INDEX_LIST_COLLECTIONS[0])
        chat_gpt_index_agent = ChatWrapper(gpt_index_agent_executor) 


    block = app()
    block.queue(concurrency_count=n_concurrency).launch(
        auth=(username, password),
        debug=debug,
        server_port=server_port,
        show_api=is_show_api
    )