# Packages
import argparse
import re
import pandas as pd
from sqlalchemy import create_engine
import whisper
import os
from sklearn.feature_extraction.text import TfidfVectorizer
from rapidfuzz import process, fuzz
from scipy.optimize import linear_sum_assignment
from pydub import AudioSegment

# Initialize the parser
parser = argparse.ArgumentParser(description="Parser to setup params for DAO wav assignments to conversation strings.")

# Add arguments
parser.add_argument('-m', '--module', help="Module UID", required=True)
parser.add_argument('-c', '--conversation', help="Conversation DLG filename", required=True)
parser.add_argument("-f", "--force", action="store_true", help="Force assignment from assignments.csv")
args = parser.parse_args()

# Setup conversation params
MODULE_UID = f"'{args.module}'"
CONV_NAME = f"'{args.conversation}'"

# Check force params
FORCE_ASSIGNMENT = args.force

# Setup file references
INPUT_DIR = 'input'
OUTPUT_DIR = 'output'
STORAGE_DIR = 'storage'
INPUT_BASENAMES = [f for f in os.listdir(INPUT_DIR) if f.endswith('.wav')]
INPUT_PATHNAMES = [os.path.join(INPUT_DIR, f) for f in INPUT_BASENAMES]
ASSIGNMENT_BASENAME = 'assignments.csv'
ASSIGNMENT_OUTPUT_PATHNAME = os.path.join(OUTPUT_DIR, ASSIGNMENT_BASENAME)
ASSIGNMENT_INPUT_PATHNAME = os.path.join(INPUT_DIR, ASSIGNMENT_BASENAME)
SQL_QUERY_PATHNAME = 'line_lookup.sql'

# Functions
def check_settings(df):
    num_wavs = len(INPUT_PATHNAMES)
    len_df = df.shape[0]
    if num_wavs != len_df:
        raise ValueError(f"The number of transcription files does not equal the length of the NPC dialogue. Review these items and make adjustments as needed. Received {num_wavs} wav files while NPC dialogue has {len_df} lines.")

def save_audio_file(infile, outfile):
    # Convert wav to format needed by DAO and export
    sound = AudioSegment.from_file(infile)
    sound = sound.set_frame_rate(24000).set_sample_width(2)
    sound.export(outfile, format='wav')

def clean_text(input_text):
    # Remove non-alphanumeric characters and replace multiple whitespace with a single space
    cleaned_text = re.sub(r'[^A-Za-z0-9\s+]', '', input_text)
    cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip().lower()
    return cleaned_text

def build_conversation_data():
    # Broker connection to dragon age DB
    # You may need to edit your connection string based on your DB settings
    connection_string = (
        f"mssql+pyodbc://./bw_dragonage_content?driver=ODBC+Driver+17+for+SQL+Server&trusted_connection=yes"
    )

    engine = create_engine(connection_string)

    # Setup SQL query
    with open(SQL_QUERY_PATHNAME, 'r') as f:
        sql_statement = ' '.join(f.readlines())
        sql_statement = re.sub("<conversation_name>", CONV_NAME, sql_statement)
        sql_statement = re.sub("<uid_name>", MODULE_UID, sql_statement)

    # Build dataframe and check
    conv_df = pd.read_sql(sql_statement, con=engine)
    check_settings(conv_df)
    conv_df['OUTPUT_WAV_PATHNAME'] =  conv_df.OUTPUT_WAV_FILENAME.apply(lambda x: os.path.join(OUTPUT_DIR, x))
    engine.dispose()
    return conv_df

def transcribe_and_match(df):
    # Load inference model
    turbo_model = whisper.load_model('turbo')
    
    # Run transcriptions
    transcriptions = [turbo_model.transcribe(f)['text'] for f in INPUT_PATHNAMES]
    conv_df = df.copy()

    # Preprocess text and set up dataframes for matching
    conv_df = df.copy()
    conv_df['CONVERSATION_TEXT_PROCESSED'] = conv_df.CONVERSATION_TEXT.apply(clean_text)
    transcription_df = pd.DataFrame({
        'INPUT_WAV_FILENAME': INPUT_BASENAMES,
        'INPUT_WAV_PATHNAME': INPUT_PATHNAMES,
        'INPUT_WAV_TEXT_PROCESSED': list(map(clean_text, transcriptions))
    })

    # Run matching
    costs = -process.cdist(conv_df.CONVERSATION_TEXT_PROCESSED, transcription_df.INPUT_WAV_TEXT_PROCESSED, scorer=fuzz.ratio)
    row_idx, col_idx = linear_sum_assignment(costs)
    match_df_conv = pd.DataFrame({c: conv_df.iloc[row_idx][c].values for c in conv_df.columns})
    match_df_transcription = pd.DataFrame({c: transcription_df.iloc[col_idx][c].values for c in transcription_df.columns})
    match_df = pd.concat([match_df_conv, match_df_transcription], axis=1)
    return match_df

def export_wavs(match_df):
    # Write files
    for row in match_df.iterrows():
        infile = row[1].INPUT_WAV_PATHNAME
        outfile = row[1].OUTPUT_WAV_PATHNAME
        save_audio_file(infile=infile, outfile=outfile)

    # Write assignments
    assignment_df = match_df[['OUTPUT_WAV_PATHNAME','CONVERSATION_TEXT','INPUT_WAV_PATHNAME','INPUT_WAV_TEXT_PROCESSED']]
    assignment_df.to_csv(ASSIGNMENT_OUTPUT_PATHNAME, index=False)
    
def force_assignments():
    assignment_df = pd.read_csv(ASSIGNMENT_INPUT_PATHNAME)
    for row in assignment_df.iterrows():
        infile = row[1].INPUT_WAV_PATHNAME
        outfile = row[1].OUTPUT_WAV_PATHNAME
        save_audio_file(infile=infile, outfile=outfile)
    assignment_df.to_csv(ASSIGNMENT_OUTPUT_PATHNAME, index=False)

def infer_assignments():
    conv_df = build_conversation_data()
    match_df = transcribe_and_match(conv_df)
    export_wavs(match_df)

# Run assignments
try:
    if FORCE_ASSIGNMENT:
        print('Forcing assignments from assignments.csv')
        force_assignments()
    else:
        print('Running inference...')
        infer_assignments()
    print('Assignments complete!')
except Exception as e:
    print(e)
finally:
    print('End of program.')