import tkinter as tk
from tkinter import ttk,filedialog
import wave
import webrtcvad
import collections
import contextlib
import sys
import speech_recognition as sr
import subprocess
import os
import threading

AV_FORMAT = ['mp4','avi','mkv','wmv','flac','wav','mp3','aac','ac3','rmvb','flv']
FFMPEG_PATH = 'bin/ffmpeg.exe'
SAMPLE_RATE = 32000
LENGTH_CAP = 10
FRAME_DURATION = 30
PADDING_DURATION = 300
MAX_SEGMENT_DURATION = 5000 #ms
LANG = 'zh-TW'

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

class ffmpegProcess(threading.Thread):
    def __init__(self,file_path):
        threading.Thread.__init__(self)
        self.file_path=file_path
    def run(self):
        sp = subprocess.Popen(
            FFMPEG_PATH+" -y -i \"%s\" -c copy -vn -acodec pcm_s16le -ar %d -ac 1 \"%s\""%
            (self.file_path,SAMPLE_RATE,changeFilenameExt(self.file_path,'wav')))
        self.stdout, self.stderr = sp.communicate()


def extractAudio(file_path):
    ext = getFilenameExt(file_path)
    if ext in AV_FORMAT:
        pFFmepg = ffmpegProcess(file_path)
        pFFmepg.start()
        pFFmepg.join()
    else:
        print('Not support file')
        sys.exit(1)

class APIProcess(threading.Thread):
    def __init__(self,lang,samprate,maxlength,sensetive,progress):
        threading.Thread.__init__(self)
        self.lang = lang
        self.samprate = int(samprate)
        self.maxlength = int(maxlength)
        self.sensetive = int(sensetive)
        self.progress = progress
    def run(self):
        samprate=self.samprate
        maxlength=self.maxlength
        sensetive=self.sensetive
        LANG=self.lang
        progress=self.progress
        SAMPLE_RATE=samprate
        MAX_SEGMENT_DURATION=maxlength
        r = sr.Recognizer()
        file_list = filedialog.askopenfilenames()
        for file_path in file_list:
            progress.set('Extracting audio...')
            extractAudio(file_path)
            progress.set('Generating subtitles...')
            tmp_path = changeFilenameExt(file_path, 'wav')
            buf_path = file_path + '.buf'

            audio, sample_rate = read_wave(tmp_path)
            vad = webrtcvad.Vad(sensetive)
            frames = frame_generator(FRAME_DURATION, audio, sample_rate)
            frames = list(frames)
            segments = vad_collector(sample_rate, FRAME_DURATION, PADDING_DURATION, vad, frames, MAX_SEGMENT_DURATION)
            srt = open(changeFilenameExt(file_path, 'srt'), 'w', encoding='utf8')
            i = 0
            half = len(frames)*FRAME_DURATION
            while True:
                try:
                    segment, begin, end = next(segments)
                except:
                    break
                # print(' Writing %s' % (path,))
                print(end - begin)
                write_wave(buf_path, segment, sample_rate)
                with sr.AudioFile(buf_path) as source:
                    audio = r.record(source)
                    try:
                        translation = r.recognize_google(audio, language=LANG)
                        i += 1
                        srt.write("%d\r\n" % (i))
                        srt.write("%d:%d:%d,%d --> %d:%d:%d,%d\r\n" % (
                            begin / 3600, begin / 60, begin % 60, (begin - int(begin)) * 1000,
                            end / 3600, end / 60, end % 60, (end - int(end)) * 1000)
                                  )
                        print(translation)
                        srt.write(translation + '\r\n')
                        srt.write('\r\n')
                    except:
                        pass
            os.remove(buf_path)
            os.remove(tmp_path)
            srt.close()
        progress.set('Complete!')


def main():
    root = tk.Tk()
    root.title('Autosub')
    labelLang = ttk.Label(root,text='Language : ')
    labelLang.grid(column=0,row=0)
    comboLang = ttk.Combobox(root)
    comboLang['values']=('zh-TW','en-US','ja-JP')
    comboLang.current(0)
    comboLang.grid(column=1,row=0)
    labelSample = ttk.Label(root,text='Sampling Rate : ')
    labelSample.grid(column=0,row=1)
    comboSample = ttk.Combobox(root)
    comboSample['values']=(8000,16000,32000)
    comboSample.current(1)
    comboSample.grid(column=1,row=1)
    labelMaxLen = ttk.Label(root,text='Max Segment Length(ms) : ')
    labelMaxLen.grid(column=0,row=2)
    entryMaxLen = ttk.Entry(root)
    entryMaxLen.insert(0,'5000')
    entryMaxLen.grid(column=1,row=2)
    labelSense = ttk.Label(root,text='Sensitive')
    labelSense.grid(column=0,row=3)
    comboSense = ttk.Combobox(root)
    comboSense['values']=(0,1,2,3)
    comboSense.grid(column=1,row=3)
    comboSense.current(1)

    stringVar = tk.StringVar()
    labelProgress = ttk.Label(root,textvariable=stringVar)
    labelProgress.grid(column=0,row=4)
    #progressbar = ttk.Progressbar(root,length=400,maximum=100,mode='determinate')
    #progressbar.grid(column=0,row=5,columnspan=2)
    startButton = ttk.Button(root,text='start',command=lambda:
        APIProcess(comboLang.get(),comboSample.get(),entryMaxLen.get(),comboSense.get(),stringVar).run())
    startButton.grid(column=1,row=4)
    root.mainloop()


if __name__ == '__main__':
    main()