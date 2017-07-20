# TODO

## Progress
0. Use a GUI
1. Transform file by FFmpeg
2. Split audio by webrtcvad √
3. Recognize speech by speech_recognition √
4. (Optional) Use Google Cloud API for better performance
5. Write srt file by module or from scratch

## Memo
* ffmpeg: `ffmpeg -i input.mp4 -vn -acodec pcm_s16le -ar 44100 -ac 2 output.wav`
* Use memory to save temp file,see: http://docs.pyfilesystem.org/en/latest/openers.html
