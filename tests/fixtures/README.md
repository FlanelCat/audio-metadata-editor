These fixtures contain 0.1 seconds of generated silence, with title `Original`.
They contain no audiobook content. Tests copy them to temporary directories
before writing metadata. FFmpeg is only needed to regenerate the fixtures,
not to run tests:

```sh
ffmpeg -f lavfi -i anullsrc=r=44100:cl=mono -t 0.1 -c:a libmp3lame -metadata title=Original silence.mp3
ffmpeg -f lavfi -i anullsrc=r=44100:cl=mono -t 0.1 -c:a aac -metadata title=Original -f mp4 silence.m4b
```

Install test dependencies with `pip install -e '.[test]'`. For headless testing:

```sh
QT_QPA_PLATFORM=offscreen python -m pytest
```
