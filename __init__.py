import tkinter as tk
from tkinter import filedialog
import wave
import webrtcvad
import collections
import contextlib
import sys
import speech_recognition as sr
import subprocess
import os

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
                  padding_duration_ms, vad, frames,max_frame_duration_ms):
    num_padding_frames = int(padding_duration_ms / frame_duration_ms)
    ring_buffer = collections.deque(maxlen=num_padding_frames)
    max_seg_frame = int(max_frame_duration_ms/frame_duration_ms)
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
                begin = ring_buffer[0].timestamp
                #sys.stdout.write('+(%s)' % (ring_buffer[0].timestamp,))
                triggered = True
                voiced_frames.extend(ring_buffer)
                ring_buffer.clear()
        else:
            voiced_frames.append(frame)
            ring_buffer.append(frame)
            num_unvoiced = len([f for f in ring_buffer
                                if not vad.is_speech(f.bytes, sample_rate)])
            if num_unvoiced > 0.9 * ring_buffer.maxlen or len(voiced_frames) > max_seg_frame:
                end = frame.timestamp + frame.duration
                #sys.stdout.write('-(%s)' % (frame.timestamp + frame.duration))
                triggered = False
                yield b''.join([f.bytes for f in voiced_frames]),begin,end
                ring_buffer.clear()
                voiced_frames = []
    if triggered:
        end = frame.timestamp + frame.duration
        #sys.stdout.write('-(%s)' % (frame.timestamp + frame.duration))
    #sys.stdout.write('\n')
    if voiced_frames:
        yield b''.join([f.bytes for f in voiced_frames]),begin,end

def getFilenameExt(filename):
    s = str(filename).split('.')
    return s[len(s)-1].lower()

def changeFilenameExt(path,newExt):
    path = str(path)
    pos = 0;
    for i in range(0,len(path)):
        if(path[i]=='.'):
            pos = i
    path = path[0:pos+1]
    return path+str(newExt)

class Autosub(object):
    AV_FORMAT = ['mp4', 'avi', 'mkv', 'wmv', 'flac', 'wav', 'mp3', 'aac', 'ac3', 'rmvb', 'flv']
    FFMPEG_PATH = 'bin/ffmpeg.exe'
    SAMPLE_RATE = 32000
    LENGTH_CAP = 10
    FRAME_DURATION = 30
    PADDING_DURATION = 300
    MAX_SEGMENT_DURATION = 10000  # ms


    def __init__(self):
        self.r = sr.Recognizer()

    def getAudio(self,file_path,ffmpeg_path=FFMPEG_PATH,sample_rate=SAMPLE_RATE):
        self.file_path = file_path
        ext = getFilenameExt(self.file_path)
        if ext in self.AV_FORMAT:
            subprocess.Popen("\"%s\" -y -i \"%s\" -c copy -vn -acodec pcm_s16le -ar %d -ac 1 buf.wav"
                             %(ffmpeg_path,self.file_path,sample_rate)).wait()
        else:
            print('Not support file')
            exit(1)
        self.audio, self.sample_rate = read_wave('buf.wav')

    def vad(self,vad_level=1,frame_duration_ms=FRAME_DURATION,padding_duration_ms=PADDING_DURATION,max_segment_duration_ms=MAX_SEGMENT_DURATION):
        self.vad = webrtcvad.Vad(vad_level)
        frames = frame_generator(frame_duration_ms, self.audio, self.sample_rate)
        frames = list(frames)
        self.segments = vad_collector(self.sample_rate, frame_duration_ms, padding_duration_ms, self.vad, frames, max_segment_duration_ms)

    def start(self,display=True,save_buf=False,encoding='utf8',api='google',lang='en-US',key=None):
        srt = open(changeFilenameExt(self.file_path, 'srt'), 'w', encoding=encoding)
        i = 0
        while True:
            try:
                segment, begin, end = next(self.segments)
            except:
                break
            path = 'buf/chunk.wav'
            write_wave(path, segment, self.sample_rate)
            with sr.AudioFile(path) as source:
                audio = self.r.record(source)
                try:
                    if(api=='google'):
                        translation = self.r.recognize_google(audio, language=lang)
                    else:
                        print('Not support api')
                        exit(1)

                    if(display):
                        print('+(%.3f)-(%.3f) %s'%(begin,end,translation))
                    i += 1
                    srt.write("%d\r\n" % (i))
                    srt.write("%d:%d:%d,%d --> %d:%d:%d,%d\r\n" % (
                        begin / 3600, begin / 60, begin % 60, (begin - int(begin)*1000),
                        end / 3600, end / 60, end % 60, (end - int(end))*1000)
                              )
                    srt.write(translation + '\r\n\r\n')
                except:
                    pass
        srt.close()
        if not save_buf:
            os.remove('buf.wav')
        os.remove('buf/chunk.wav')
