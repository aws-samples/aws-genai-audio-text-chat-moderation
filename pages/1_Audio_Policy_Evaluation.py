import streamlit as st 
import json
from io import BytesIO
import os
from pathlib import Path
import sys
sys.path.append(str(Path(__file__).resolve().parent.parent))

from helper import lib
from helper import ui_lib as lib_ui
from helper import constants

SAMPLE_DATA_FOLDER = "data/audio_eval/"

if 'is_logged_in' not in st.session_state or not st.session_state['is_logged_in']:
    st.text("Please login using the Home page.")
    st.stop()
    
st.set_page_config(page_title="Video/Audio Policy Evaluation Demo", layout="wide") 
st.title("Audio Moderation Demo") 

audio_eval_tab, audio_sample_tab, doc_tab = st.tabs(["Audio Policy Evalution", "Sample Reports", "Workflow"])

with doc_tab:
    st.image("static/audio-moderation.png", caption="Workflow diagram")

with audio_eval_tab:
    st.subheader("Upload a audio to start policy evaluation")
    
    uploaded_audio = st.file_uploader(key="uploaded_audio", label="Select an video or audio file", type=['mp4', 'mp3', "wav"])
    if uploaded_audio:
        st.audio(uploaded_audio, format='audio/*')
        
        prompt_template = constants.TEXT_EVAL_PROMPTS_TEMPLATE
        with st.expander("Modify LLM prompts template", expanded=False):
            prompt_template = st.text_area(
                key=f"prompts_textarea",
                label="You can modify the LLM prompts template, and this will be reflected in the evaluation results. Please ensure to leave the placeholders, as removing them may lead to errors.", 
                value=constants.TEXT_EVAL_PROMPTS_TEMPLATE,
                height=200)
        enable_toxicity_dependency = st.toggle(label="Apply LLMs analysis only when toxicity detection returns a toxicity score exceeding the threshold", value=True)

        # Start Policy Evaluation
        st.session_state["detect_language"] = False
        if st.toggle("Detect language (If audio is in English, leave it unchecked to enable Transcribe's built-in toxicity analysis.)"):
            st.session_state['detect_language'] = True

        # Upload audio file to S3
        if st.button("Start policy evaluation"):
            st.session_state['audio_eval_result'] = {}
            with st.spinner("Uploading to S3... Please wait."):
                s3_bucket, s3_key = lib.upload_to_s3(uploaded_audio)
                st.session_state['s3_bucket'] = s3_bucket
                st.session_state['s3_key'] = s3_key
                st.session_state['toxicity_source'] = "comprehend"
                st.info(f"Audio file uploaded successfully to S3: s3://{s3_bucket}/{s3_key}")

            # Start evaluation
            with st.spinner("Analyzing audio. This will take a few minutes to complete."):
                # Transcribe audio
                original, transcriptions = lib.transcribe_audio(st.session_state['s3_bucket'], st.session_state['s3_key'], st.session_state['detect_language'])
                full_trans, display_trans, traslated_text = "", "", ""
                for t in original["results"]["transcripts"]:
                    full_trans += t["transcript"]
                display_trans = full_trans
                traslated_text = full_trans
                st.session_state['toxicity_source'] = "comprehend" if "toxicity_detection" not in original else "transcribe"
                
                # Translate transcription if not in english
                if "language_code" in original["results"]:
                    language_code = original["results"]["language_code"][0:2]
                    if language_code != "en":                        
                        traslated_text = lib.translate_text(full_trans,language_code)
                        if traslated_text is None:
                            st.warning(f'Unsupported language detected in the audio: {full_trans,original["results"]["language_code"]}',icon="⚠️")
                            st.text(full_trans)
                            st.stop()
                        display_trans = f'Orginial ({language_code}): {full_trans}  \nTranslation: {traslated_text}'

                    transcriptions = []
                    ts = lib.chunk_text(traslated_text)
                    for t in ts:
                        transcriptions.append(
                            lib.detect_toxicity(t)
                        )


                result = {"transcriptions" : [], "full_transcription": display_trans}

                st.info("Performed audio transcription with toxicity analysis using amazon transcribe")
                st.markdown(f'***Transcription:*** {display_trans}')
                st.info("Evaluating policy using Amazon Bedrock Knowledge Base")
                if transcriptions is None or len(transcriptions) == 0:
                    st.warning('No transcription')
                else:
                    # LLM evaluation for each segments
                    st.subheader("Transcriptions and policy evaluation")
                    toxic_max, violation = 0, False
                    for tran in transcriptions:
                        if "toxicity" in tran and tran["toxicity"] >= toxic_max: 
                            toxic_max = tran["toxicity"]
                        
                        response = None
                        if not enable_toxicity_dependency or tran["toxicity"] > lib_ui.get_toxicity_threshold(st.session_state['toxicity_source']):
                            response = lib.call_bedrock_knowledge_base(tran["text"], prompt_template)
                            if response["answer"] == "Y":
                                violation = True
                        else:
                            violation = None

                        # Store result to session
                        result["transcriptions"].append(
                            {
                                "llm_response": response,
                                "transcription": tran
                            }
                        )

                    result["toxic_max"] = toxic_max
                    result["violation"] = violation
                    result["toxicity_source"] = st.session_state['toxicity_source']
                    result["s3_path"] = {
                        "s3_bucket": st.session_state['s3_bucket'],
                        "s3_key": st.session_state['s3_key']
                    }
                    st.session_state['audio_eval_result'] = result

                    # store to file
                    json_data = json.dumps(result, ensure_ascii=False)  # Optional: indent for pretty formatting
                    if not os.path.exists(SAMPLE_DATA_FOLDER):
                        os.makedirs(SAMPLE_DATA_FOLDER)
                    file_path = f"{SAMPLE_DATA_FOLDER}{st.session_state['s3_key'].split('/')[-1]}.json"
                    with open(file_path, "w") as json_file:
                        json_file.write(json_data)

            # Plot report
            lib_ui.plot_audio_eval_report(st.session_state['audio_eval_result'], False)

with audio_sample_tab: 
    st.subheader("Sample policy evaluation report")

    if os.path.exists(SAMPLE_DATA_FOLDER):
        option = st.selectbox("Select a sample audio", 
            tuple(file for file in os.listdir(SAMPLE_DATA_FOLDER) if os.path.isfile(os.path.join(SAMPLE_DATA_FOLDER, file)))
        )
        if len(option) > 0:
            # Plot UI
            file_path = f"{SAMPLE_DATA_FOLDER}{option}"
            
            data = None
            # Open and read the JSON file
            with open(file_path, "r") as json_file:
                data = json.load(json_file)
                lib_ui.plot_audio_eval_report(data)

                # Export HTML report
                if st.button("Export report in HTML"):
                    html = lib_ui.generate_video_eval_html(data, option)

                    if html:
                        buffer = BytesIO()
                        buffer.write(html.encode())
                        buffer.seek(0)
                        # Create a link to download the file
                        st.download_button(label="Download File", data=buffer, file_name=f'{option}.html', key="download_button")
