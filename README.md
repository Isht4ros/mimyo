# mimyo

![PyPI](https://img.shields.io/pypi/v/mimyo)
![Python](https://img.shields.io/pypi/pyversions/mimyo)
![License](https://img.shields.io/pypi/l/mimyo)
![Downloads](https://img.shields.io/pypi/dm/mimyo)

![pygame-ce](https://img.shields.io/badge/pygame--ce-2.5.7-brightgreen)
![mutagen](https://img.shields.io/badge/mutagen-1.47.0-brightgreen)
![textual](https://img.shields.io/badge/textual-0.50.0+-brightgreen)
![yt-dlp](https://img.shields.io/badge/yt--dlp-latest-brightgreen)
![Pillow](https://img.shields.io/badge/Pillow-10.0.0+-brightgreen)

A simple vibecoded terminal music player that takes inspiration from [rmpc](https://github.com/mierak/rmpc) and runs completely standalone. Built for anyone who just wants to open their terminal, hit play, and lose themselves in their music library 

## What it does

- Plays music straight from your terminal
- Renders album art (sixel support included for compatible terminals)
- Manages playlists and queues
- Play audio from YouTube URL
- Hooks into Discord rich presence if you want it to

<img width="1686" height="799" alt="ss1" src="https://github.com/user-attachments/assets/a8b7894f-4547-4177-b46d-3f4dda3bd673" />
<img width="1685" height="795" alt="ss2" src="https://github.com/user-attachments/assets/846e0a82-f017-46cf-af2e-644c2923ee49" />
<img width="929" height="373" alt="ss3" src="https://github.com/user-attachments/assets/12b7eaaf-65e3-4cb7-827d-dc83b8af5fe1" />

## Installation

```bash
pip install mimyo
```

For album art rendering, install [chafa](https://hpjansson.org/chafa/):
- **Windows:** `winget install -e --id hpjansson.Chafa`
- **macOS:** `brew install chafa`
- **Linux:** `sudo apt install chafa` or your distro's equivalent

Want Discord rich presence too?

```bash
pip install "mimyo[discord]"
```
### Installing from source

```bash
git clone https://github.com/Isht4ros/mimyo.git
cd mimyo
pip install .
```

## Usage

```bash
mimyo
```

Or run it without installing:

```bash
python -m mimyo
```

By default, mimyo looks for a `Music` folder in your home directory. You can point it somewhere else and it'll remember for next time:

```bash
mimyo --path "D:\Music"
# or
mimyo -p "D:\Music"
```

## License

MIT — see [LICENSE](LICENSE).
