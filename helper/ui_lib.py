import os
import json
import streamlit as st 
from annotated_text import annotated_text
from jinja2 import Template
import boto3
import requests
from io import BytesIO

TRANSCRIBE_TOXICITY_THRESHOLD = 0.4
COMPREHEND_TOXICITY_THRESHOLD = 0.6

s3 = boto3.client('s3')

def get_toxicity_threshold(toxicity_source):
    if toxicity_source is not None:
        return COMPREHEND_TOXICITY_THRESHOLD if toxicity_source == "comprehend" else TRANSCRIBE_TOXICITY_THRESHOLD
    return TRANSCRIBE_TOXICITY_THRESHOLD


def display_toxicity_analysis(toxicity_data):
    st.subheader("Segement transcription and toxicity analysis")

    col1, col2 = st.columns(2)

    if "toxicity" in toxicity_data:
        col1.text("Toxicity Score:")
        col1.caption(f'{toxicity_data["toxicity"]}')

    col1.text("Message:")
    col1.caption(f'{toxicity_data["text"]}')

    if "categories" in toxicity_data:
        col2.text("Toxicity analysis")
        col2.bar_chart(toxicity_data["categories"])

def display_llm(response):
    reference = response.get("references")

    st.subheader("Policy Evaluation")
    st.text(f'Violation:')
    if response.get("answer") == "Y":
        annotated_text((response["answer"], "violation", "#faa"))
    elif response["answer"] is not None:
        annotated_text((response["answer"], "safe", "#afa"))

    if "analysis" in response and len(response["analysis"]) > 0:
        st.text("LLM Analysis:")
        st.caption(f'{response["analysis"]}')

    if reference is not None and len(reference) > 0:
        st.table(reference)

def plot_audio_eval_report(data, show_audio=True):
    threshold = get_toxicity_threshold(data.get("toxicity_source"))

    if show_audio and "s3_path" in data:
        s3_presigned_url = s3.generate_presigned_url('get_object',
                                                        Params={'Bucket': data["s3_path"]["s3_bucket"],
                                                                'Key':  data["s3_path"]["s3_key"]},
                                                        ExpiresIn=3600)

        st.audio(s3_presigned_url)

    # Plot UI
    toxic_max = data.get("toxic_max")
    if toxic_max is not None and toxic_max >= threshold:
        st.markdown(f'***Max toxicity score:*** :red[{data["toxic_max"]}]')
    else:
        st.markdown(f'***Max toxicity score:*** :green[{data["toxic_max"]}]')
    if data["violation"] == True:
        st.markdown(f'***Violation:*** :red[{data["violation"]}]')
    else:
        st.markdown(f'***Violation:*** :green[{data["violation"]}]')
    
    st.markdown('***Full transcription:***')
    st.caption(data["full_transcription"])

    strans = data.get('transcriptions')
    if strans is not None:
        for tran in strans:
            llm = tran.get("llm_response")
            title = f'{tran["transcription"]["text"]} - toxicity score: {tran["transcription"].get("toxicity")}, violation: { llm["answer"] if llm else None}'
            if "start_time" in tran["transcription"] and "end_time"in tran["transcription"]:
                title = f'[{tran["transcription"]["start_time"]} - {tran["transcription"]["end_time"]}] ' + title
            violation = llm["answer"] if llm else None
            toxicity_score = tran["transcription"].get("toxicity")
            if llm is not None and llm["answer"] == "Y" and (toxicity_score is None or toxicity_score >= threshold):
                title = f':heavy_exclamation_mark: :red[{title}]'
            elif violation == "Y" or (toxicity_score is not None and toxicity_score >= threshold):
                title = f':warning: :orange[{title}]'
            with st.expander(title, expanded=False):
                if "transcription" in tran and "toxicity" in tran["transcription"]:
                    display_toxicity_analysis(tran["transcription"])
                if llm is not None:
                    display_llm(llm)

def plot_text_eval_report(data):
    threshold = get_toxicity_threshold(data.get("toxicity_source"))

    # Plot UI
    evaluations = data.get('evaluations')
    if evaluations is not None:
        for item in evaluations:
            plot_text_eval_item(item)

def plot_text_eval_item(item, threshold=0.6, index=None):
    if item is None:
        return

    violation = item["llm"]["answer"] if "llm" in item and item["llm"] is not None else None
    toxicity_score = item["toxicity"].get("toxicity")
    title = f'{item["raw_text"]} - toxicity score: {toxicity_score}, violation: {violation}'

    if violation == "Y" and (toxicity_score is None or toxicity_score >= threshold):
        title = f':heavy_exclamation_mark: :red[{title}]'
    elif violation == "Y" or (toxicity_score is not None and toxicity_score >= threshold):
        title = f':warning: :orange[{title}]'
    if index:
        title = f'{index} - {title}'

    with st.expander(title, expanded=False):
        if "raw_language_code" in item:
            st.text(f"Original language code: {item['raw_language_code']}")
        if "translated_text" in item and item["translated_text"] is not None:
            st.text("Translated text: " + item["translated_text"])

        if "toxicity" in item and "toxicity" in item["toxicity"]:
            display_toxicity_analysis(item["toxicity"])
        if "llm" in item and item["llm"] is not None:
            display_llm(item["llm"])

def generate_video_eval_html(data, file_name):
    threshold = get_toxicity_threshold(data.get("toxicity_source"))

    segments = ""
    # Add extra fileds for UI display
    trans = data["transcriptions"]
    idx = -1
    for t in trans:
        idx += 1
        image_class = "safe"
        if t["transcription"]["toxicity"] >= threshold and t["llm_response"]["answer"] == "Y":
            image_class = "alert"
        elif t["transcription"]["toxicity"] >= threshold or t["llm_response"]["answer"] == "Y":
            image_class = "warn"
        
        cates, refs = "", ""
        for key, value in t["transcription"]["categories"].items():
            cates += f"<li>{ key }: { value }</li>"
        for r in t["llm_response"]["references"]:
            refs += f'<li>{ r["text"] } - <a href="{r["s3_location"] }">Link</a></li>'

        title = t["transcription"]["text"]
        if "start_time" in t["transcription"] and "end_time" in t["transcription"]:
            title = f'[{t["transcription"]["start_time"]} - {t["transcription"]["end_time"]}] ' + title
    
        segments += f'''
            <div class="container">
                <button id="btntoogle_{idx}" class="toggle-btn" onclick="toggleContent({idx})">&or;</button> 
                <div class="title" onclick="toggleContent({idx})">
                    <div class="{image_class}">{title}</div>
                </div>
                <div id="content_{idx}" class="content">
                <div>
                    <div>
                        <h3>Toxicity score: {t["transcription"]["toxicity"] }</h3>
                        <h3>Toxicity categories</h3>
                        <ul>{cates}</ul>
                    </div>
                    <div>
                        <h3>LLM Response</h3>
                        <p>Answer: { t["llm_response"]["answer"] }</p>
                        <p>Analysis: {t["llm_response"]["analysis"] }</p>
                        <h3>References</h3>
                        <ul>{refs}</ul>
                    </div>
                </div>
                </div>
                </div>
        '''

    html_template = '''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta http-equiv="X-UA-Compatible" content="IE=edge">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Transcription Report</title>
        <style>
            html, body, [class*="css"] {
                font-family: 'Roboto', sans-serif; 
                font-size: 18px;
                font-weight: 500;
                color: #091747;
                padding: 15px;
            }
            .subtitle {
                font-size: 16px;
                color:gray;
                padding-bottom: 20px;
                margin:0px;
            }
            .transcription {
                font-size: 16px;
                color:gray;
                margin: 20px;
            }
            /* Style for the toggle button */
            .toggle-btn {
                cursor: pointer;
                padding: 15px;
                border: none;
                border-radius: 5px;
                float:right;
                background-color: transparent;
                font-size: large;
            }
    
            /* Style for the content div */
            .content {
                display:none;
                padding: 10px;
                border-radius: 5px;
                width: 100%;
            }
            .container {
                display: inline-block;
                width: 100%;
                border: 1px solid gray;
                border-radius: 5px;
                margin-bottom: 10px;
            }
            .container .title {
                display: inline-block;
                font-size: large;
                padding: 15px;
                cursor: pointer;
                width: 90%;
            }
            .container .title .alert {
                width: 100%;
                margin:0px;
                padding: 0px;
                color: red;
            }
            .container .title .warn {
                width: 100%;
                margin:0px;
                padding: 0px;
                color: orange;
            }
            .container .title .safe {
                width: 100%;
                margin:0px;
                padding: 0px;
            }
        </style>
    </head>
    <body>
        <script>
            // JavaScript function to toggle content visibility
            function toggleContent(idx) {
                var contentDiv = document.getElementById('content_' + idx);
                var btntoogle = document.getElementById('btntoogle_' + idx);
                if (contentDiv.style.display === 'block') {
                    contentDiv.style.display = 'none';
                    btntoogle.innerHTML = "&or;";
                }
                else  {
                    contentDiv.style.display = 'block';
                    btntoogle.innerHTML = "&and;";
                } 
            }
        </script>
        <div>
            <h2>Audio file: ##file_name##</h2>
        </div>
        <div>
            <h4>Toxicity Max: ##toxicity_max##</h3>
        </div>
        <div>
            <h4>Violation: ##violation##</h3>
        </div>        
        <div>
            <h3>Full Transcription</h3>
            <p class="transcription">##full_transcription##</p>
        </div>
        
        <h3>Policy evaluation by segment</h3>
        <div class="subtitle">Toxicity analysis (##toxicity_source##) and policy evalution (Bedrock LLMs) on the audio segment level</div>
        ##segments##
    </body>
    </html>
    '''

    # Create Jinja2 template object
    #template = Template(html_template)
    output_html = html_template.replace("##file_name##", file_name)
    output_html = output_html.replace("##toxicity_max##", str(data["toxic_max"]))
    output_html = output_html.replace("##violation##", str(data["violation"]))
    output_html = output_html.replace("##full_transcription##", data.get("full_transcription"))
    output_html = output_html.replace("##toxicity_source##", data["toxicity_source"])
    output_html = output_html.replace("##segments##", segments)

    return output_html

def generate_text_eval_html(data, file_name, threshold=0.6):
    segments = ""
    # Add extra fileds for UI display
    trans = data["evaluations"]
    idx = -1
    for t in trans:
        idx += 1
        image_class = "safe"
        if t["toxicity"]["toxicity"] >= threshold and t["llm"]["answer"] == "Y":
            image_class = "alert"
        elif t["toxicity"]["toxicity"] >= threshold or t["llm"]["answer"] == "Y":
            image_class = "warn"
        
        cates, refs = "", ""
        for key, value in t["toxicity"]["categories"].items():
            cates += f"<li>{ key }: { value }</li>"
        for r in t["llm"]["references"]:
            refs += f'<li>{ r["text"] } - <a href="{r["s3_location"] }">Link</a></li>'

        title = t["raw_text"]
    
        segments += f'''
            <div class="container">
                <button id="btntoogle_{idx}" class="toggle-btn" onclick="toggleContent({idx})">&or;</button> 
                <div class="title" onclick="toggleContent({idx})">
                    <div class="{image_class}">{title}</div>
                </div>
                <div id="content_{idx}" class="content">
                <div>
                    <div>
                        <h3>Toxicity score: {t["toxicity"]["toxicity"] }</h3>
                        <h3>Toxicity categories</h3>
                        <ul>{cates}</ul>
                    </div>
                    <div>
                        <h3>LLM Response</h3>
                        <p>Answer: { t["llm"]["answer"] }</p>
                        <p>Analysis: {t["llm"]["analysis"] }</p>
                        <h3>References</h3>
                        <ul>{refs}</ul>
                    </div>
                </div>
                </div>
                </div>
        '''

    html_template = '''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta http-equiv="X-UA-Compatible" content="IE=edge">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Policy Evaluation Report</title>
        <style>
            html, body, [class*="css"] {
                font-family: 'Roboto', sans-serif; 
                font-size: 18px;
                font-weight: 500;
                color: #091747;
                padding: 15px;
            }
            .subtitle {
                font-size: 16px;
                color:gray;
                padding-bottom: 20px;
                margin:0px;
            }
            .transcription {
                font-size: 16px;
                color:gray;
                margin: 20px;
            }
            /* Style for the toggle button */
            .toggle-btn {
                cursor: pointer;
                padding: 15px;
                border: none;
                border-radius: 5px;
                float:right;
                background-color: transparent;
                font-size: large;
            }
    
            /* Style for the content div */
            .content {
                display:none;
                padding: 10px;
                border-radius: 5px;
                width: 100%;
            }
            .container {
                display: inline-block;
                width: 100%;
                border: 1px solid gray;
                border-radius: 5px;
                margin-bottom: 10px;
            }
            .container .title {
                display: inline-block;
                font-size: large;
                padding: 15px;
                cursor: pointer;
                width: 90%;
            }
            .container .title .alert {
                width: 100%;
                margin:0px;
                padding: 0px;
                color: red;
            }
            .container .title .warn {
                width: 100%;
                margin:0px;
                padding: 0px;
                color: orange;
            }
            .container .title .safe {
                width: 100%;
                margin:0px;
                padding: 0px;
            }
        </style>
    </head>
    <body>
        <script>
            // JavaScript function to toggle content visibility
            function toggleContent(idx) {
                var contentDiv = document.getElementById('content_' + idx);
                var btntoogle = document.getElementById('btntoogle_' + idx);
                if (contentDiv.style.display === 'block') {
                    contentDiv.style.display = 'none';
                    btntoogle.innerHTML = "&or;";
                }
                else  {
                    contentDiv.style.display = 'block';
                    btntoogle.innerHTML = "&and;";
                } 
            }
        </script>
        <div>
            <h2>File name: ##file_name##</h2>
        </div>     
        
        <div class="subtitle">Toxicity analysis (Comprehend) and policy evalution (Bedrock LLMs)</div>
        ##segments##
    </body>
    </html>
    '''

    # Create Jinja2 template object
    #template = Template(html_template)
    output_html = html_template.replace("##file_name##", file_name)
    output_html = output_html.replace("##segments##", segments)

    return output_html


