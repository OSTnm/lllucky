"""lllucky companion. Controls arrive exclusively from the game's custom CVars."""
import ctypes as C
from ctypes import wintypes as W
import json
import logging
import math
import os
from pathlib import Path
import queue
import re
import sys
import time
from worker import Worker
from memory_backend import ROOT, GAME, MAX_PERCENT, Memory, processes

CONFIG = GAME.parent/'benilla-config'/'config.toml'
STOP = ROOT/'stop-backend.request'
STATE = ROOT/'headless-state.json'
TIMEOUT = 20
logging.basicConfig(filename=ROOT/'lllucky.log', level=logging.INFO,
                    format='%(asctime)s %(levelname)s %(message)s', encoding='utf-8')

def parse_values(text):
    result={}
    for match in re.finditer(r'^\s*"?(lllucky(?:schema|enabled|percent|beat))"?\s*=\s*"([^"\r\n]*)"\s*$',text,re.I|re.M):
        result[match.group(1).lower()]=match.group(2)
    return result

class Channel:
    def __init__(self):
        self.beat=None;self.last_seen=0;self.last_good=None

    def read(self,path,created_unix,now=None,wall=None):
        now=time.monotonic() if now is None else now
        wall=time.time() if wall is None else wall
        try:
            st=path.stat();v=parse_values(path.read_text(encoding='utf-8-sig'))
        except OSError:
            return {'enabled':False,'percent':300,'live':False,'reason':'等待插件配置'}
        try:
            beat=float(v.get('llluckybeat','0'));percent=float(v.get('llluckypercent','0'))
        except ValueError:
            return {'enabled':False,'percent':300,'live':False,'reason':'插件配置无效'}
        valid=(v.get('llluckyschema')=='1' and math.isfinite(beat) and beat>0
               and math.isfinite(percent) and 0<=percent<=MAX_PERCENT
               and st.st_mtime>=created_unix-2)
        if valid and beat!=self.beat:
            self.beat=beat
            if wall-st.st_mtime<=TIMEOUT:self.last_seen=now
        live=valid and self.last_seen>0 and now-self.last_seen<=TIMEOUT
        return {'enabled':live and v.get('llluckyenabled','0')=='1','percent':percent if valid else 300,
                'live':live,'reason':'游戏内面板' if live else '等待 lllucky 插件心跳'}

def write_state(data):
    temp=STATE.with_suffix('.tmp')
    temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    temp.replace(STATE)

def main():
    kernel=C.windll.kernel32
    kernel.CreateMutexW.argtypes=[C.c_void_p,W.BOOL,W.LPCWSTR];kernel.CreateMutexW.restype=W.HANDLE
    kernel.CloseHandle.argtypes=[W.HANDLE]
    mutex=kernel.CreateMutexW(None,False,'Local\\AzerothSurvivorsLuckyControl')
    if kernel.GetLastError()==183:
        logging.info('Another luck controller is already active');return
    worker=None;probe=None
    try:
        if STOP.exists():STOP.unlink()
        (ROOT/'headless.pid').write_text(str(os.getpid()),encoding='ascii')
        q=queue.Queue();worker=Worker(q);worker.configure(False,300);worker.start()
        start=time.monotonic();missing_since=None;channel=Channel();status='等待游戏启动';last_state=0;ever_attached=False
        while not STOP.exists():
            pids=processes()
            if probe and not probe.alive():probe.close();probe=None;channel=Channel()
            if probe is None and len(pids)==1:
                try:probe=Memory(pids[0]);channel=Channel();missing_since=None;ever_attached=True
                except Exception:logging.exception('Could not attach to game')
            if probe:
                created=(probe.creation-116444736000000000)/10_000_000
                command=channel.read(CONFIG,created)
                worker.configure(command['enabled'],command['percent'])
                missing_since=None
            else:
                command={'enabled':False,'percent':300,'live':False,'reason':'等待游戏启动'}
                worker.configure(False,300)
                if missing_since is None:missing_since=time.monotonic()
                if (ever_attached and time.monotonic()-missing_since>5) or (not ever_attached and time.monotonic()-start>45):break
            try:
                while True:
                    kind,text=q.get_nowait()
                    if kind=='status':status=text
            except queue.Empty:pass
            if time.monotonic()-last_state>=1:
                write_state({'backend_pid':os.getpid(),'game_pid':probe.pid if probe else None,
                             'enabled':command['enabled'],'percent':command['percent'],'channel_live':command['live'],
                             'channel_status':command['reason'],'status':status,
                             'worker':worker.diagnostic_snapshot(),'time':time.time()})
                last_state=time.monotonic()
            time.sleep(.25)
    finally:
        if worker:
            worker.stopping.set();worker.join(15)
            if worker.is_alive():logging.error('Worker did not stop promptly')
        if probe:probe.close()
        if STOP.exists():STOP.unlink()
        write_state({'backend_pid':os.getpid(),'stopped':True,'time':time.time()})
        if mutex:kernel.CloseHandle(mutex)

if __name__=='__main__':main()
