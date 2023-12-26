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

NUM_FRAMES = 512

BIT_DEPTH_TO_FORMAT = {
    8: pyaudio.paInt8,
    16: pyaudio.paInt16,
    32: pyaudio.paInt32,
}

BIT_DEPTH_TO_NP_DTYPE = {
    8: np.int8,
    16: np.int16,
    # We exclude 24 bits because numpy does not have a dtype for it.
    32: np.int32
}

# TODO: use later if necessary
# HZ_LOWPASS = 27.5
# HZ_HIGHPASS = 4186

def read_config(config_path):
    with open(config_path, 'r') as f:
        return toml.load(f)

def get_save_path(dt, parent_dir):
    save_name = dt.astimezone().strftime('%Y-%m-%d %H:%M:%S %Z.wav')
    return path.join(path.realpath(parent_dir), save_name)

def get_rms_dbfs_for_chunk(data, width):
    rms = audioop.rms(data, width)
    # If rms is 0, the dBFS value is undefined.
    rms = 1 if rms == 0 else rms
    max_signal = 2 ** (8 * width - 1) - 1
    # https://dsp.stackexchange.com/questions/8785/how-to-compute-dbfs
    return 20 * log10(abs(rms) / max_signal)

def save_frames(frames, channels, sample_rate, format, save_path):
    audio = pyaudio.PyAudio()
    with wave.open(save_path, 'wb') as f:
        f.setnchannels(channels)
        f.setsampwidth(audio.get_sample_size(format))
        f.setframerate(sample_rate)
        f.writeframes(frames)

def listen(config):
    input_cfg = config['input']
    detect_cfg = config['detection']
    rec_cfg = config['recording']
    output_cfg = config['output']

    bit_depth = input_cfg['bit_depth']
    pyaudio_format = BIT_DEPTH_TO_FORMAT[bit_depth]
    bit_depth_dtype = BIT_DEPTH_TO_NP_DTYPE[bit_depth]
    channels = input_cfg['channels']
    sample_rate = input_cfg['sample_rate']

    audio = pyaudio.PyAudio()

    device_name = audio.get_device_info_by_index(input_cfg['device_index']).get('name')
    print(f'Using device "{device_name}"')
    print(f'Sample rate {sample_rate} Hz')
    print(f'Bit depth {bit_depth}')
    print(f'{channels} channels')
    print()


    stream = audio.open(
        input=True,
        input_device_index=input_cfg['device_index'],
        format=pyaudio_format,
        channels=channels,
        rate=sample_rate,
        frames_per_buffer=NUM_FRAMES,
    )

    width = audio.get_sample_size(pyaudio_format)
    buffer = np.empty((channels, 0), bit_depth_dtype)
    db_samples = np.empty((channels, 0), np.double)
    is_listening = False
    is_recording = False
    recording_start = None
    recording_frames = None
    rewind_buffer_size = int((sample_rate * rec_cfg['rewind_ms'] / 1000) / NUM_FRAMES) * NUM_FRAMES
    db_sample_size = int((sample_rate * detect_cfg['db_sample_window_ms'] / 1000) / NUM_FRAMES) * NUM_FRAMES
    full_buffer_size = max(rewind_buffer_size, db_sample_size)
    chunk_ms = NUM_FRAMES / sample_rate * 1000
    time_loud = 0
    time_quiet = 0

    print(f'Buffering...')
    while True:
        raw_data = stream.read(NUM_FRAMES, exception_on_overflow=False)
        data = np.frombuffer(raw_data, dtype=bit_depth_dtype).reshape((channels, NUM_FRAMES), order='F')
        cur_buffer_size = len(buffer[0])
        if cur_buffer_size >= full_buffer_size:
            buffer = buffer[:, -full_buffer_size+NUM_FRAMES:]
            if not is_listening:
                print(f'Listening...')
                is_listening = True
        buffer = np.append(buffer, data, axis=1)

        if cur_buffer_size == full_buffer_size:
            db = get_rms_dbfs_for_chunk(buffer[detect_cfg['detect_channel'] - 1][-db_sample_size:].tobytes(), width)
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
                    save_frames(recording_frames, channels, sample_rate, pyaudio_format, save_path)
                    recording_dur = timedelta(
                        milliseconds=len(recording_frames) / (sample_rate * width * channels) * 1000
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
