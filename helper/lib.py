import os
import boto3
import json
from io import BytesIO
import re
import uuid
import time

AWS_REGION = os.environ.get('AWS_REGION','us-east-1')
AWS_BUCKET_NAME = os.environ.get('AWS_BUCKET_NAME')
AWS_S3_PREFIX = os.environ.get('AWS_S3_PREFIX', 'policy-eval-demo')
TRANSCRIBE_OUTPUT_PREFIX = 'policy-eval-demo/transcription/'
TRANSCRIBE_JOB_PREFIX = 'ch-audio-analysis'
SUPPORTED_LANGUAGE = [
        'af', 'sq', 'am', 'ar', 'hy', 'az', 'bn', 'bs', 'bg', 'ca', 'zh', 'zh-TW', 'hr', 'cs', 'da', 'fa-AF',
        'nl', 'en', 'et', 'fa', 'tl', 'fi', 'fr', 'fr-CA', 'ka', 'de', 'el', 'gu', 'ht', 'ha', 'he', 'hi', 'hu',
        'is', 'id', 'ga', 'it', 'ja', 'kn', 'kk', 'ko', 'lv', 'lt', 'mk', 'ms', 'ml', 'mt', 'mr', 'mn', 'no', 'ps',
        'pl', 'pt', 'pt-PT', 'pa', 'ro', 'ru', 'sr', 'si', 'sk', 'sl', 'so', 'es', 'es-MX', 'sw', 'sv', 'ta', 'te',
        'th', 'tr', 'uk', 'ur', 'uz', 'vi', 'cy'
    ]
BEDROCK_MODEL_ID = os.environ.get('BEDROCK_MODEL_ID', "anthropic.claude-v2")
BEDROCK_KNOWLEDGE_BASE_ID = os.environ.get('BEDROCK_KNOWLEDGE_BASE_ID')

s3 = boto3.client('s3')
bedrock_agent_runtime_client = boto3.client("bedrock-agent-runtime")
transcribe = boto3.client('transcribe')
translate = boto3.client('translate')
comprehend = boto3.client('comprehend')
rekognition = boto3.client('rekognition')
bedrock_runtime = boto3.client('bedrock-runtime')

def upload_to_s3(uploaded_audio):
    # upload file
    s3_key = f'{AWS_S3_PREFIX}/{uploaded_audio.name}'
    print(AWS_BUCKET_NAME, s3_key)
    s3.upload_fileobj(uploaded_audio, AWS_BUCKET_NAME, s3_key)
    return AWS_BUCKET_NAME, s3_key

def generate_presigned_url(bucket_name, object_key, expiration_time=3600):
    s3 = boto3.client('s3')

    try:
        url = s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket_name, 'Key': object_key},
            ExpiresIn=expiration_time
        )
        return url

    except NoCredentialsError:
        print("AWS credentials not available. Please set your AWS credentials.")
        return None

def chunk_text(text, sentence_limit=3, char_limit=400):
    if len(text) <= char_limit:
        return [text]
    # Split the text into sentences
    arr = re.split(r'(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\?)\s', text)
    sentences = []
    for sentence in arr:
        csize = len(sentence)
        if csize <= char_limit:
            sentences.append(sentence)
        else:
            for i in range(0,int(csize/char_limit)):
                sentences.append(sentence[i*char_limit:char_limit*(i+1)])

    # Initialize variables
    chunks = []
    current_chunk = ""

    # Iterate through sentences to create chunks
    for sentence in sentences:
        if len(current_chunk) + len(sentence) <= char_limit and len(re.split(r'(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\?)\s', current_chunk)) <= sentence_limit:
            current_chunk += sentence + " "
        else:
            chunks.append(current_chunk.strip())
            current_chunk = sentence + " "

    # Add the last chunk
    if current_chunk:
        chunks.append(current_chunk.strip())

    return chunks

def transcribe_audio(s3_bucket, s3_key, detect_language=False, enable_toxicity=True):
    job_name = f'{TRANSCRIBE_JOB_PREFIX}-{str(uuid.uuid4())[0:5]}'
    if detect_language:
        transcribe.start_transcription_job(
                        TranscriptionJobName = job_name,
                        Media = { 'MediaFileUri': f's3://{s3_bucket}/{s3_key}'},
                        OutputBucketName = s3_bucket,
                        OutputKey = TRANSCRIBE_OUTPUT_PREFIX,
                        IdentifyLanguage=True,
                    )
    elif enable_toxicity:
        transcribe.start_transcription_job(
                        TranscriptionJobName = job_name,
                        Media = { 'MediaFileUri': f's3://{s3_bucket}/{s3_key}'},
                        OutputBucketName = s3_bucket,
                        OutputKey = TRANSCRIBE_OUTPUT_PREFIX,
                        LanguageCode = 'en-US',
                        ToxicityDetection = [{'ToxicityCategories': ['ALL']}]
                    )
    else:
        transcribe.start_transcription_job(
                        TranscriptionJobName = job_name,
                        Media = { 'MediaFileUri': f's3://{s3_bucket}/{s3_key}'},
                        OutputBucketName = s3_bucket,
                        OutputKey = TRANSCRIBE_OUTPUT_PREFIX,
                        LanguageCode = 'en-US'
                    )

    # Wait until job completes
    job = transcribe.get_transcription_job(TranscriptionJobName = job_name)

    print("Transcribing audio. Job name: {0}".format(job_name))
    while(job['TranscriptionJob']['TranscriptionJobStatus'] not in ['COMPLETED', 'FAILED']):
        time.sleep(5)
        print('.', end='')

        job = transcribe.get_transcription_job(TranscriptionJobName = job_name)
    print(job['TranscriptionJob']['TranscriptionJobStatus'])

    # Read transcription file
    s3_clientobj = s3.get_object(Bucket=s3_bucket, Key=f'{TRANSCRIBE_OUTPUT_PREFIX}{job_name}.json')
    s3_clientdata = s3_clientobj["Body"].read().decode("utf-8")
    original = json.loads(s3_clientdata)
    #print(original)
    
    transcriptions = []
    if "toxicity_detection" in original["results"]:
        for item in original["results"]["toxicity_detection"]:
            transcriptions.append(item)
    else:
        transcription = ""
        for t in original["results"]["transcripts"]:
            transcription += t.get("transcript")
        ts = chunk_text(transcription)
        for t in ts:
            transcriptions.append({"text": t})
            
    return original, transcriptions

def translate_text(text, source, target='en-US'):
    if source not in SUPPORTED_LANGUAGE:
        return None
    response = translate.translate_text(Text=text, SourceLanguageCode=source,TargetLanguageCode=target)
    return response.get("TranslatedText")

def detect_toxicity(text):
    response = comprehend.detect_toxic_content(
        TextSegments=[
            {"Text":  text}
        ],
        LanguageCode='en'
    )
    result = {"text": text, "categories": {}}
    if response is not None and "ResultList" in response and len(response["ResultList"]) > 0:
        result["toxicity"] = response["ResultList"][0].get("Toxicity")
        for r in response["ResultList"][0]["Labels"]:
            result["categories"][r["Name"]] = r["Score"]

    return result

def detect_language(text):
    response = comprehend.detect_dominant_language(
        Text=text,
    )
    if response is not None and "Languages" in response and len(response["Languages"]) > 0:
        return response["Languages"][0]["LanguageCode"]

    return None

def parse_value(text, key):
    arr = text.split(f'<{key}>')
    if len(arr) > 1:
        arr2 = arr[-1].split(f'</{key}>')
        if len(arr2) > 1:
            return arr2[0]
    return None

def call_bedrock_knowledge_base(message, prompts_template):
    model_arn = f'arn:aws:bedrock:{AWS_REGION}::foundation-model/{BEDROCK_MODEL_ID}'

    # Call bedrock knowledge base to retrieve references
    response = bedrock_agent_runtime_client.retrieve(
        knowledgeBaseId=BEDROCK_KNOWLEDGE_BASE_ID,
        retrievalQuery={
            'text': message
        },
        retrievalConfiguration={
            "vectorSearchConfiguration": {
                "numberOfResults": 3
            }
        }
    )
    retrieval_results = response.get("retrievalResults",[])
    policy = ""
    for r in retrieval_results:
        policy += f'\n{r["content"]["text"]}'

    # Call Bedrock LLM to evaluate
    prompt = prompts_template.format(message=message, policy=policy)
    analysis,answer = call_bedrock_llm(prompt)

    references = []
    for c in retrieval_results:
        r = {
                'text':c['content']['text'],
                's3_location': c['location']['s3Location']['uri']
            }
        if r not in references:
            references.append(r)

    return {
        "answer":answer,
        "analysis":analysis,
        "references":references
    }

def detect_celebrity_video(s3_bucket, s3_key):
    startCelebrityRekognition = rekognition.start_celebrity_recognition(
        Video={
            'S3Object': {
                'Bucket': s3_bucket,
                'Name': s3_key,
            }
        },
    )

    celebrityJobId = startCelebrityRekognition['JobId']
    print("Detecting celebrities. Job Id: {0}".format(celebrityJobId))

    getCelebrityRecognition = rekognition.get_celebrity_recognition(
        JobId=celebrityJobId,
        SortBy='TIMESTAMP'
    )

    while(getCelebrityRecognition['JobStatus'] == 'IN_PROGRESS'):
        time.sleep(5)
        print('.', end='')

        getCelebrityRecognition = rekognition.get_celebrity_recognition(
            JobId=celebrityJobId,
            SortBy='TIMESTAMP')
    print(getCelebrityRecognition['JobStatus'])

    result = []
    # Celebrities detected in each frame
    for celebrity in getCelebrityRecognition['Celebrities']:
        if 'Celebrity' in celebrity :
            cconfidence = celebrity["Celebrity"]["Confidence"]
            if(cconfidence > 90):
                cname = celebrity["Celebrity"]["Name"]
                if cname not in result:
                    result.append(cname)

    return result

def call_bedrock_llm(prompt):
    body = json.dumps({
            "prompt": prompt,
            "max_tokens_to_sample": 300,
            "temperature": 0,
            "top_k": 250,
            "top_p": 0.999
            })
    response = bedrock_runtime.invoke_model(
        body=body,
        contentType='application/json',
        accept='application/json',
        modelId=BEDROCK_MODEL_ID
    )

    response_text = json.loads(response.get('body').read()).get("completion")
    analysis = parse_value(response_text,"analysis")
    answer = parse_value(response_text,"answer")

    return analysis,answer
