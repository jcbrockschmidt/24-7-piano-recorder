#!/usr/bin/env python

import audioop
from datetime import datetime
from math import log10
import numpy as np
import pyaudio
import time
import wave

DEVICE_INDEX = 6
FORMAT = pyaudio.paInt16
CHANNELS = 3
# WARNING: 176400 and 192000 causes distortion and frame skipping?
RATE = 96000
CHUNK_SIZE = 512

# TODO: use later if necessary
# HZ_LOWPASS = 27.5
# HZ_HIGHPASS = 4186

# Which channel triggers recording
DETECT_CHANNEL = 3
# Decibel above which to trigger a recording
DB_THRES = 6
# Duration of moving window for computing decibels, in milliseconds.
DB_SAMPLE_WINDOW_MS = 5000
# How long the decibel threshold needs to be passes before recording is triggered, in milliseconds.
DB_SUSTAIN_MS = 5000

REWIND_MS = 10000
MS_UNTIL_STOP = 30000

def get_save_path(dt):
    return dt.strftime('%Y-%m-%d %H:%M:%S.wav')

def get_rms_db_for_chunk(data, width):
    rms = audioop.rms(data, width)
    return 0 if rms == 0 else 20 * log10(rms)

def save_frames(frames, save_path):
    audio = pyaudio.PyAudio()
    with wave.open(save_path, 'wb') as f:
        f.setnchannels(CHANNELS)
        f.setsampwidth(audio.get_sample_size(FORMAT))
        f.setframerate(RATE)
        f.writeframes(frames)

def listen():
    audio = pyaudio.PyAudio()

    device_name = audio.get_device_info_by_index(DEVICE_INDEX).get('name')
    print(f'Using device "{device_name}"')

    stream = audio.open(
        input=True,
        input_device_index=DEVICE_INDEX,
        format=FORMAT,
        channels=CHANNELS,
        rate=RATE,
        frames_per_buffer=CHUNK_SIZE,
    )

    width = audio.get_sample_size(FORMAT)
    buffer = np.empty((CHANNELS, 0), np.int16)
    db_samples = np.empty((CHANNELS, 0), np.double)
    is_listening = False
    is_recording = False
    recording_start = None
    recording_frames = None
    rewind_buffer_size = int((RATE * REWIND_MS / 1000) / CHUNK_SIZE) * CHUNK_SIZE
    db_sample_size = int((RATE * DB_SAMPLE_WINDOW_MS / 1000) / CHUNK_SIZE) * CHUNK_SIZE
    full_buffer_size = max(rewind_buffer_size, db_sample_size)
    chunk_ms = CHUNK_SIZE * width * 1000 / RATE
    time_loud = 0
    time_quiet = 0

    print(f'Buffering...')
    while True:
        raw_data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
        data = np.frombuffer(raw_data, dtype=np.int16).reshape((CHANNELS, CHUNK_SIZE), order='F')
        cur_buffer_size = len(buffer[0])
        if cur_buffer_size >= full_buffer_size:
            buffer = buffer[:, -full_buffer_size+CHUNK_SIZE:]
            if not is_listening:
                print(f'Listening...')
                is_listening = True
        buffer = np.append(buffer, data, axis=1)

        if cur_buffer_size == full_buffer_size:
            db = get_rms_db_for_chunk(buffer[DETECT_CHANNEL - 1][-db_sample_size:], width)
            if is_recording:
                recording_frames += raw_data
            if db > DB_THRES:
                time_loud += chunk_ms
                time_quiet = 0

                if (not is_recording) and time_loud >= DB_SUSTAIN_MS:
                    print('Recording...')
                    is_recording = True
                    recording_start = datetime.utcnow()
                    recording_frames = bytearray(buffer[:, -rewind_buffer_size:].flatten('F'))

            if db < DB_THRES and is_recording:
                time_loud = 0
                time_quiet += chunk_ms
                if time_quiet >= MS_UNTIL_STOP:
                    print('Done recording. Saving...')
                    is_recording = False
                    save_path = get_save_path(recording_start)
                    save_frames(recording_frames, save_path)
                    recording_frames = None
                    print(f'Saved to {save_path}')

    print('Done listening')

    stream.stop_stream()
    stream.close()
    audio.terminate()

if __name__ == '__main__':
    listen()
