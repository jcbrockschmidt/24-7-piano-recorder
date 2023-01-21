#!/usr/bin/env python

import pyaudio

SAMPLE_RATES = (8000, 11025, 16000, 22050, 32000, 44100, 48000, 88200, 96000, 176400, 192000, 352800, 384000)
FORMAT = pyaudio.paInt16

def get_supported_rates(device_index):
    audio = pyaudio.PyAudio()
    dev_info = audio.get_device_info_by_index(device_index)
    max_input_channels = dev_info['maxInputChannels']
    if max_input_channels == 0:
        return []

    supported = []
    for rate in SAMPLE_RATES:
        try:
            is_supported = audio.is_format_supported(
                rate,
                input_device=device_index,
                input_channels=max_input_channels,
                input_format=FORMAT
            )
            if is_supported:
                supported.append(rate)
        except ValueError:
            pass
    return supported

def list_audio_devices():
    audio = pyaudio.PyAudio()
    for i in range(audio.get_device_count()):
        dev_info = audio.get_device_info_by_index(i)
        name = dev_info['name']
        max_input_channels = dev_info['maxInputChannels']
        if max_input_channels:
            supported_rates = ', '.join(map(str, get_supported_rates(i)))
            print(f'{i} - {name}')
            print(f'  -- max input channels: {max_input_channels}')
            print(f'  -- supported sample rates: {supported_rates}')

if __name__ == '__main__':
    list_audio_devices()
