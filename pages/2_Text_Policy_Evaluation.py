import streamlit as st 
import json
from io import BytesIO
import os
from pathlib import Path
import sys
sys.path.append(str(Path(__file__).resolve().parent.parent))
from streamlit.components.v1 import html

from helper import lib
from helper import ui_lib as lib_ui
from helper import constants

SAMPLE_DATA_FOLDER = "data/text_eval/"

if 'is_logged_in' not in st.session_state or not st.session_state['is_logged_in']:
    st.text("Please login using the Home page.")
    st.stop()
    
st.set_page_config(page_title="Text Policy Evaluation Demo", layout="wide") 
st.title("Text Moderation Demo") 

text_eval_tab, text_eval_bulk_tab, sample_tab, doc_tab = st.tabs(["Text Policy Evalution", "Text Policy Evaluation - Bulk", "Sample Reports", "Workflow"])

with doc_tab:
    st.image("static/text-moderation.png", caption="Workflow diagram")

def evaluate(text_content, key):    
    if text_content is None or len(text_content) == 0:
        st.warning("Submit a message or upload a file to initiate the evaluation.")
    else:
        prompt_template = constants.TEXT_EVAL_PROMPTS_TEMPLATE
        with st.expander("Modify LLM prompts template", expanded=False):
            prompt_template = st.text_area(
                key=f"{key}_textarea",
                label="You can modify the LLM prompts template, and this will be reflected in the evaluation results. Please ensure to leave the placeholders, as removing them may lead to errors.", 
                value=constants.TEXT_EVAL_PROMPTS_TEMPLATE,
                height=200)

        result = {
            "raw_content": text_content,
            "evaluations": []
        }
        enable_toxicity_dependency = st.toggle(key=f"{key}_toggle",label="Apply LLMs analysis only when toxicity detection returns a toxicity score exceeding the threshold", value=True)

        # Start Policy Evaluation
        # Upload file to S3
        if st.button(key=f"{key}_start", label="Start policy evaluation"):
            # Start evaluation
            rows = text_content.split('\n')
            with st.spinner(f"Analyzing text messages. Total: {len(rows)}"):
                idx = 0
                for txt in rows:
                    idx += 1
                    txt = txt.strip()
                    if len(txt) == 0:
                        continue

                    txt_en = txt
                    item = {
                        "raw_text": txt,
                        "translated_text": None,
                        "raw_language_code": None,
                        "toxicity": None,
                        "llm": None
                    }

                    # Detect language
                    lang_code = lib.detect_language(txt)
                    item["raw_language_code"] = lang_code
                    lcode = lang_code[0:2].lower()

                    # Translate to English
                    if not lcode.startswith('en'):
                        translated_text = lib.translate_text(txt,lcode)
                        item["translated_text"] = translated_text
                        if translated_text is None:
                            st.warning(f'Unsupported language detected: {lang_code}',icon="⚠️")
                            st.text(txt)
                            st.stop()
                        txt_en = translated_text
                        item["translated_text"] = translated_text

                    chunks = lib.chunk_text(txt_en)
                    for chunk in chunks:
                        chunk = chunk.strip()
                        if len(chunk) == 0:
                            continue
                        # Comprehend Toxicity Analysis
                        c_result = lib.detect_toxicity(chunk)
                        if item["toxicity"] is None:
                            item["toxicity"] = c_result
                        elif item["toxicity"]["toxicity"] < c_result["toxicity"]:
                            item["toxicity"] = c_result

                        # Toxicity dependency enabled: only run LLMs when toxicity score greater than threshold
                        if not enable_toxicity_dependency or c_result["toxicity"] >= lib_ui.COMPREHEND_TOXICITY_THRESHOLD:
                            # LLM evaluation
                            response = lib.call_bedrock_knowledge_base(chunk, prompt_template)
                            violation = False
                            if response["answer"] == "Y":
                                violation = True

                            if item["llm"] is None:
                                item["llm"] = response
                            else:
                                if response["answer"] == "Y":
                                    item["llm"]["answer"] = "Y"
                                item["llm"]["analysis"]  += response["analysis"]
                                item["llm"]["references"] = item["llm"]["references"] + response["references"]
                    
                    lib_ui.plot_text_eval_item(item=item, index=idx)

                    result["evaluations"].append(item)

            # store to file
            if uploaded_file:
                print("store result to disk")
                json_data = json.dumps(result, ensure_ascii=False) 
                file_path = f"{SAMPLE_DATA_FOLDER}{uploaded_file.name.split('/')[-1]}.json"
                if not os.path.exists(SAMPLE_DATA_FOLDER):
                    os.makedirs(SAMPLE_DATA_FOLDER)
                with open(file_path, "w") as json_file:
                    json_file.write(json_data)


with text_eval_bulk_tab:
    st.subheader("Upload a audio to start policy evaluation")
    text_content = None
    st.caption("You can submit a TXT or CSV file containing multiple messages in separate rows without a header row. If the CSV file has multiple columns, this app will only consider the content from the first column.")
    st.caption("This app is designed for demo and evaluate sample messages. To prevent UI timeouts, do not upload files containing more than 200 rows.")
    uploaded_file = st.file_uploader(key="uploaded_file", label="Select a file", type=['txt', 'csv'])
    if uploaded_file:
        text_content = uploaded_file.read().decode("utf-8")
        if text_content:
            html(text_content.replace("\n","<br/>"), height=200, scrolling=True)
        else:
            st.warning("Invalid text file")
            st.stop()
        
        evaluate(text_content, "bulk")
    
with text_eval_tab:
    st.subheader("Assess an individual text message")
    text_input = st.text_input("Enter a message and click on anywhere else on the screen")
    if text_input:
        evaluate(text_input, "text")

with sample_tab: 
    st.subheader("Sample policy evaluation report")

    if os.path.exists(SAMPLE_DATA_FOLDER):
        option = st.selectbox("Select a sample report", 
            tuple(file for file in os.listdir(SAMPLE_DATA_FOLDER) if os.path.isfile(os.path.join(SAMPLE_DATA_FOLDER, file)))
        )
        if option and len(option) > 0:
            # Plot UI
            file_path = f"{SAMPLE_DATA_FOLDER}{option}"
            
            data = None
            # Open and read the JSON file
            with open(file_path, "r") as json_file:
                data = json.load(json_file)

                st.text("Raw content:")
                html(data["raw_content"].replace("\n","<br/>"), height=200, scrolling=True)

                lib_ui.plot_text_eval_report(data)

                # Export HTML report
                if st.button("Export report in HTML"):
                    html = lib_ui.generate_text_eval_html(data, option)

                    if html:
                        # Create a BytesIO buffer
                        buffer = BytesIO()
                        # Write the content to the buffer
                        buffer.write(html.encode())
                        # Set the cursor to the beginning of the buffer
                        buffer.seek(0)
                        # Create a link to download the file
                        st.download_button(label="Download File", data=buffer, file_name=f'{option}.html', key="download_button")
