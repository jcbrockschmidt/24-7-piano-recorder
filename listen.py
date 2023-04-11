#!/usr/bin/env python

import audioop
from datetime import datetime, timedelta
from math import log10
import numpy as np
from os import path
import pyaudio
import time
import toml
import wave

CONFIG_PATH = 'config.toml'

FORMAT = pyaudio.paInt16
CHUNK_SIZE = 512

# TODO: use later if necessary
# HZ_LOWPASS = 27.5
# HZ_HIGHPASS = 4186

def read_config(config_path):
    with open(config_path, 'r') as f:
        return toml.load(f)

def get_save_path(dt, parent_dir):
    save_name = dt.astimezone().strftime('%Y-%m-%d %H:%M:%S %Z.wav')
    return path.join(path.realpath(parent_dir), save_name)

def get_rms_db_for_chunk(data, width):
    rms = audioop.rms(data, width)
    return 0 if rms == 0 else 20 * log10(rms)

def save_frames(frames, channels, sample_rate, save_path):
    audio = pyaudio.PyAudio()
    with wave.open(save_path, 'wb') as f:
        f.setnchannels(channels)
        f.setsampwidth(audio.get_sample_size(FORMAT))
        f.setframerate(sample_rate)
        f.writeframes(frames)

def listen(config):
    input_cfg = config['input']
    detect_cfg = config['detection']
    rec_cfg = config['recording']
    output_cfg = config['output']

    audio = pyaudio.PyAudio()

    device_name = audio.get_device_info_by_index(input_cfg['device_index']).get('name')
    print(f'Using device "{device_name}"')

    stream = audio.open(
        input=True,
        input_device_index=input_cfg['device_index'],
        format=FORMAT,
        channels=input_cfg['channels'],
        rate=input_cfg['sample_rate'],
        frames_per_buffer=CHUNK_SIZE,
    )

    width = audio.get_sample_size(FORMAT)
    buffer = np.empty((input_cfg['channels'], 0), np.int16)
    db_samples = np.empty((input_cfg['channels'], 0), np.double)
    is_listening = False
    is_recording = False
    recording_start = None
    recording_frames = None
    rewind_buffer_size = int((input_cfg['sample_rate'] * rec_cfg['rewind_ms'] / 1000) / CHUNK_SIZE) * CHUNK_SIZE
    db_sample_size = int((input_cfg['sample_rate'] * detect_cfg['db_sample_window_ms'] / 1000) / CHUNK_SIZE) * CHUNK_SIZE
    full_buffer_size = max(rewind_buffer_size, db_sample_size)
    chunk_ms = CHUNK_SIZE * width * 1000 / input_cfg['sample_rate']
    time_loud = 0
    time_quiet = 0

    print(f'Buffering...')
    while True:
        raw_data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
        data = np.frombuffer(raw_data, dtype=np.int16).reshape((input_cfg['channels'], CHUNK_SIZE), order='F')
        cur_buffer_size = len(buffer[0])
        if cur_buffer_size >= full_buffer_size:
            buffer = buffer[:, -full_buffer_size+CHUNK_SIZE:]
            if not is_listening:
                print(f'Listening...')
                is_listening = True
        buffer = np.append(buffer, data, axis=1)

        if cur_buffer_size == full_buffer_size:
            db = get_rms_db_for_chunk(buffer[detect_cfg['detect_channel'] - 1][-db_sample_size:], width)
            if is_recording:
                recording_frames += raw_data
            if db > detect_cfg['db_thres']:
                time_loud += chunk_ms
                time_quiet = 0

                if (not is_recording) and time_loud >= detect_cfg['db_sustain_ms']:
                    print('Recording...')
                    is_recording = True
                    recording_start = datetime.now()
                    recording_frames = bytearray(buffer[:, -rewind_buffer_size:].flatten('F'))

            if db < detect_cfg['db_thres'] and is_recording:
                time_loud = 0
                time_quiet += chunk_ms
                if time_quiet >= detect_cfg['time_until_stop_ms']:
                    print('Done recording. Saving...')
                    is_recording = False
                    save_path = get_save_path(recording_start, output_cfg['recordings_dir'])
                    save_frames(recording_frames, input_cfg['channels'], input_cfg['sample_rate'], save_path)
                    recording_dur = timedelta(
                        milliseconds=len(recording_frames) / (input_cfg['sample_rate'] * width * input_cfg['channels']) * 1000
                    )
                    recording_frames = None
                    print(f'Saved to {save_path} with duration of {recording_dur}')

    print('Done listening')

    stream.stop_stream()
    stream.close()
    audio.terminate()

if __name__ == '__main__':
    config = read_config(CONFIG_PATH)
    listen(config)
