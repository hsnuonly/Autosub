import tkinter as tk
from tkinter import filedialog
import wave
import webrtcvad
import collections
import contextlib
import sys
import speech_recognition as sr
import subprocess

AV_FORMAT = ['mp4','avi','mkv','wmv','flac','wav','mp3','aac','ac3','rmvb','flv']
FFMPEG_PATH = 'bin/ffmpeg.exe'

def read_wave(path):
    with contextlib.closing(wave.open(path, 'rb')) as wf:
        num_channels = wf.getnchannels()
        assert num_channels == 1
        sample_width = wf.getsampwidth()
        assert sample_width == 2
        sample_rate = wf.getframerate()
        assert sample_rate in (8000, 16000, 32000)
        pcm_data = wf.readframes(wf.getnframes())
        return pcm_data, sample_rate


def write_wave(path, audio, sample_rate):
    with contextlib.closing(wave.open(path, 'wb')) as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio)


class Frame(object):
    def __init__(self, bytes, timestamp, duration):
        self.bytes = bytes
        self.timestamp = timestamp
        self.duration = duration


def frame_generator(frame_duration_ms, audio, sample_rate):
    n = int(sample_rate * (frame_duration_ms / 1000.0) * 2)
    offset = 0
    timestamp = 0.0
    duration = (float(n) / sample_rate) / 2.0
    while offset + n < len(audio):
        yield Frame(audio[offset:offset + n], timestamp, duration)
        timestamp += duration
        offset += n


def vad_collector(sample_rate, frame_duration_ms,
                  padding_duration_ms, vad, frames):
    num_padding_frames = int(padding_duration_ms / frame_duration_ms)
    ring_buffer = collections.deque(maxlen=num_padding_frames)
    triggered = False
    voiced_frames = []
    for frame in frames:
        #sys.stdout.write(
        #    '1' if vad.is_speech(frame.bytes, sample_rate) else '0')
        if not triggered:
            ring_buffer.append(frame)
            num_voiced = len([f for f in ring_buffer
                              if vad.is_speech(f.bytes, sample_rate)])
            if num_voiced > 0.9 * ring_buffer.maxlen:
                sys.stdout.write('+(%s)' % (ring_buffer[0].timestamp,))
                triggered = True
                voiced_frames.extend(ring_buffer)
                ring_buffer.clear()
        else:
            voiced_frames.append(frame)
            ring_buffer.append(frame)
            num_unvoiced = len([f for f in ring_buffer
                                if not vad.is_speech(f.bytes, sample_rate)])
            if num_unvoiced > 0.9 * ring_buffer.maxlen:
                sys.stdout.write('-(%s)' % (frame.timestamp + frame.duration))
                triggered = False
                yield b''.join([f.bytes for f in voiced_frames])
                ring_buffer.clear()
                voiced_frames = []
    #if triggered:
        #sys.stdout.write('-(%s)' % (frame.timestamp + frame.duration))
    #sys.stdout.write('\n')
    if voiced_frames:
        yield b''.join([f.bytes for f in voiced_frames])

def getFilenameExt(filename):
    s = str(filename).split('.')
    return s[len(s)-1].lower()

def extractAudio(file_path):
    ext = getFilenameExt(file_path)
    if ext in AV_FORMAT:
        subprocess.Popen(
            FFMPEG_PATH+" -y -i \"" + file_path + "\" -c copy -vn -acodec pcm_s16le -ar 32000 -ac 1 buf.wav").wait()
    else:
        print('Not support file')
        sys.exit(1)

def main():
    r = sr.Recognizer()
    root = tk.Tk()
    root.withdraw()
    file_path = filedialog.askopenfilename()


    audio, sample_rate = read_wave('buf.wav')
    vad = webrtcvad.Vad(0)
    frames = frame_generator(30, audio, sample_rate)
    frames = list(frames)
    segments = vad_collector(sample_rate, 30, 300, vad, frames)
    for i, segment in enumerate(segments):
        path = 'buf/chunk.wav'
        #print(' Writing %s' % (path,))
        write_wave(path, segment, sample_rate)
        with sr.AudioFile(path) as source:
            audio = r.record(source)
            try:
                print(r.recognize_google(audio, language="ja-JP"))
            except:
                pass


if __name__ == '__main__':
    main()