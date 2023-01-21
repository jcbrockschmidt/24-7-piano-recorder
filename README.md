# 24/7 Piano Recorder

24/7 program that starts recording when a piano is playing.

## Setup

```bash
sudo apt install portaudio19-dev
pip install -r requirements.txt
```

## Use

### Find input device

To find the index of the desired input device, run

```bash
python list_devices.py
```

### Listen for recordings

In `listen.py`, set `DEVICE_INDEX` to the desired input device index. Then to start listening for recordings, run

```bash
python listen.py
```

To stop listening for recordings, simply kill the script.