import os
from celery import Celery
from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
from flask_cors import CORS
import openai
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file

UPLOAD_FOLDER = './audio'
TRANSCRIPTS_FOLDER = './transcripts'
ALLOWED_EXTENSIONS = set(['mp3', 'mp4', 'mpeg', 'mpga', 'm4a', 'wav', 'webm'])

app = Flask(__name__)
CORS(app)  # This will enable CORS for all routes
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 25 * 1024 * 1024  # 25 MB

# Configure Celery
celery = Celery(app.name, broker='redis://localhost:6379/0', backend='redis://localhost:6379/0')
celery.conf.update(result_extended=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@celery.task(bind=True)
def transcribe_file(self, filename):
    print(f"Transcribing {filename}...")
    self.update_state(state='PENDING', meta={'current': 0, 'total': 100, 'status': 'Transcribing...', 'result': ''})

    try:
        with open(filename, "rb") as audio_file:
            transcript = openai.Audio.transcribe("whisper-1", audio_file)
            print(f"Transcript: {transcript['transcript']}")
    except Exception as e:
        print(f"Error transcribing file {filename}: {str(e)}")
        self.update_state(state='FAILURE', meta={'current': 100, 'total': 100, 'status': 'Transcription failed!', 'result': ''})
        return {'current': 100, 'total': 100, 'status': 'Transcription failed!', 'result': ''}

    # Create the transcripts directory if it doesn't exist
    if not os.path.exists(TRANSCRIPTS_FOLDER):
        os.makedirs(TRANSCRIPTS_FOLDER)

    # Save the transcript to a file
    transcript_text = transcript['transcript']
    transcript_filename = f"transcript-{self.request.id}.txt"
    transcript_filepath = os.path.join(TRANSCRIPTS_FOLDER, transcript_filename)
    with open(transcript_filepath, 'w') as transcript_file:
        transcript_file.write(transcript_text)

    self.update_state(state='COMPLETED', meta={'current': 100, 'total': 100, 'status': 'Transcription completed!', 'result': transcript_filepath})
    return {'current': 100, 'total': 100, 'status': 'Transcription completed!', 'result': transcript_filepath}

@app.route('/api/transcribe', methods=['POST'])
def transcribe_audio():
    files = request.files.getlist('file')
    tasks = []

    for file in files:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            task = transcribe_file.apply_async(args=[os.path.join(app.config['UPLOAD_FOLDER'], filename)])
            tasks.append(task)

    results = []
    for task in tasks:
        task_result = task.wait()  # Wait for the task to complete and get the result
        results.append(task_result)

    return jsonify(results), 200


@app.route('/api/transcribe/status/<task_id>')
def taskstatus(task_id):
    task = transcribe_file.AsyncResult(task_id)
    if task.state == 'PENDING':
        # job did not start yet
        response = {
            'state': task.state,
            'current': 0,
            'total': 1,
            'status': 'Pending...'
        }
    elif task.state != 'FAILURE':
        response = {
            'state': task.state,
            'current': task.info.get('current', 0),
            'total': task.info.get('total', 1),
            'status': task.info.get('status', '')
        }
        if 'result' in task.info:
            response['result'] = task.info['result']
    else:
        # something went wrong in the background job
        response = {
            'state': task.state,
            'current': 1,
            'total': 1,
            'status': str(task.info),  # this is the exception raised
        }
    return jsonify(response)

if __name__ == '__main__':
    app.run(debug=True)
