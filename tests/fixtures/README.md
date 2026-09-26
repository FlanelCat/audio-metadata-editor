`audio/silence.mp3` and `audio/silence.m4b` contain 0.1 seconds of generated silence, with title `Original`.
They contain no audiobook content. Tests copy them to temporary directories
before writing metadata. FFmpeg is only needed to regenerate the fixtures,
not to run tests. Run these commands from `tests/fixtures/`:

```sh
ffmpeg -f lavfi -i anullsrc=r=44100:cl=mono -t 0.1 -c:a libmp3lame -metadata title=Original audio/silence.mp3
ffmpeg -f lavfi -i anullsrc=r=44100:cl=mono -t 0.1 -c:a aac -metadata title=Original -f mp4 audio/silence.m4b
```

Install test dependencies with `pip install -e '.[test]'`. For headless testing:

```sh
QT_QPA_PLATFORM=offscreen python -m pytest
```

The shared `audio_fixture_dir` fixture in `tests/conftest.py` supplies the source
directory. Select named silence samples and copy them into `tmp_path`; never
write to source media or scan local media in this directory during tests.
Generated images and modified audio belong in temporary directories.
