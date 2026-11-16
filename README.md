# wizcli

wizcli is a unified command-line tool written for experimentation with WiZ lights. It synchronizes your smart lights to audio in real-time or pre-analyzed files, and automatically discovers your bulbs on the network.

## Installation

The easiest way to install wizcli and its dependencies is to use the provided installation script:

```bash
chmod +x install.sh
./install.sh
```

This will create a virtual environment, install all required Python packages, and create a `wizcli` executable in the root directory.

### System Dependencies
Wizcli relies on audio processing libraries that may require system-level packages. On Debian/Ubuntu based systems, you may need:

```bash
sudo apt-get install libportaudio2 portaudio19-dev libaubio-dev
```

## Usage

After installation, you can run the tool directly:

```bash
./wizcli <command> [options]
```

By default, the tool will automatically broadcast to `255.255.255.255` to find your Wiz lightbulbs. If you want to skip discovery to speed up the process, you can provide the IPs manually via `--ips 192.168.1.X 192.168.1.Y`.

### Commands

#### `discover`
Discover and print the IPs of Wiz bulbs on your network.
```bash
python cli.py discover
```

#### `play`
Plays an audio file and syncs the lights to the beats dynamically. (Formerly `wizcli.py`).
```bash
python cli.py play /path/to/song.wav
```

#### `switch`
Listens to an audio input device (like microphone or loopback) and turns the lights ON when the volume exceeds a threshold, and OFF otherwise. (Formerly `wizrealtime.py`).
```bash
python cli.py switch --threshold 50.0
```

#### `party`
Real-time dynamic light controller. Listens to an audio input device (microphone or loopback/monitor) and continuously alters brightness and color based on beat detection and volume. (Formerly `wizrealtime-party.py`).
```bash
# Start with default input (microphone)
python cli.py party

# List all available audio input devices (e.g. microphones, monitor loopbacks)
python cli.py party --list-devices

# Sync with system audio / what you are listening to (using a loopback device or name)
python cli.py party --device pulse
# or match a device name
python cli.py party --device Headphones
```
