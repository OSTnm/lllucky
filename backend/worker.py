"""Shared headless game-memory worker; no windowing toolkit dependency."""
import json
import logging
import queue
import threading
import time
from memory_backend import Memory, Adjustment, ROOT, processes, definitions, validate_owner, locate, inspect_owner

class Worker(threading.Thread):
    def __init__(self, messages):
        super().__init__(daemon=False)
        self.messages = messages; self.lock = threading.Lock()
        self.enabled = True; self.percent = 300; self.stopping = threading.Event()
        self.rescan = threading.Event(); self.mem = None; self.adjustment = None
        self.error = None; self.last_status = None
        self._diagnostic = {}; self._diagnostic_after = 0; self._target_signature = None

    def diagnostic_snapshot(self):
        with self.lock:return dict(self._diagnostic)

    def capture_diagnostic(self, defs):
        now=time.monotonic()
        vector=self.adjustment.vector if self.adjustment else None
        signature=(self.mem.pid if self.mem else None,vector,tuple(defs))
        if now<self._diagnostic_after and signature==self._target_signature:return
        snapshot=inspect_owner(self.mem,vector,defs) if self.mem else {'pid':None,'vector':None}
        snapshot['captured_at']=time.time()
        with self.lock:self._diagnostic=snapshot
        self._diagnostic_after=now+2
        if signature!=self._target_signature:
            logging.info('Worker target: %s',json.dumps(snapshot,ensure_ascii=False))
            self._target_signature=signature

    def status(self, text):
        if text != self.last_status:
            self.messages.put(('status',text)); self.last_status = text

    def configure(self, enabled, percent):
        with self.lock: self.enabled, self.percent = enabled, percent

    def detach(self):
        if self.mem:
            try:
                if self.mem.alive() and self.adjustment: self.adjustment.restore()
            finally:
                self.mem.close(); self.mem = None; self.adjustment = None
                with self.lock:self._diagnostic={}

    def cached_vector(self):
        try:
            saved = json.loads((ROOT/'runtime-state.json').read_text(encoding='utf-8'))
            if saved.get('pid') == self.mem.pid and saved.get('creation') == self.mem.creation:
                return int(saved['vector'])
        except (OSError,ValueError,KeyError): pass
        return None

    def cancel_scan(self):
        with self.lock:
            return self.stopping.is_set() or not self.enabled or self.rescan.is_set()

    def run(self):
        defs = []; scan_after = 0
        try:
            while not self.stopping.is_set():
                try:
                    with self.lock: enabled, percent = self.enabled,self.percent
                    if self.mem and not self.mem.alive():
                        self.mem.close(); self.mem = None; self.adjustment = None; defs = []; scan_after = 0
                        self.capture_diagnostic(defs)
                    if not self.mem:
                        pids = processes()
                        if not pids:
                            self.status('等待游戏启动…'); self.stopping.wait(1); continue
                        if len(pids)>1:
                            self.status('发现多个游戏实例，请只保留一个'); self.stopping.wait(2); continue
                        self.mem = Memory(pids[0]); defs = definitions(self.mem)
                        if not defs: raise RuntimeError('当前版本未识别到印记数据，未进行修改')
                        vector = self.cached_vector()
                        if vector and validate_owner(self.mem,vector,defs):
                            self.adjustment = Adjustment(self.mem,defs,vector)
                        self.capture_diagnostic(defs)
                    if self.rescan.is_set():
                        # Restore before dropping ownership tracking.
                        if self.adjustment: self.adjustment.restore()
                        self.adjustment = None; scan_after = 0; self.rescan.clear()
                        self.capture_diagnostic(defs)
                    if not self.adjustment:
                        if not enabled:
                            self.status('已关闭 · 不修改游戏'); self.stopping.wait(.3); continue
                        if time.monotonic()>=scan_after:
                            self.capture_diagnostic(defs)
                            vector = locate(self.mem,defs,self.cancel_scan,self.status)
                            if vector: self.adjustment = Adjustment(self.mem,defs,vector)
                            else:
                                scan_after = time.monotonic()+30
                                self.status('等待装备印记或幸运项链 · 可点“重新查找”')
                            self.capture_diagnostic(defs)
                        self.stopping.wait(.3); continue
                    result = self.adjustment.tick(enabled,percent)
                    self.capture_diagnostic(defs)
                    if result is None:
                        self.adjustment = None; scan_after = time.monotonic()+2
                        self.capture_diagnostic(defs)
                        self.status('等待进入下一局…')
                    elif not result['has_item']:
                        self.status('已连接 · 等待天选者印记或南海海带')
                    elif enabled:
                        self.status(f'已启用 · 每件 {percent:,.0f}% · 角色总幸运 {result["hero_percent"]:,.0f}%')
                    else:
                        self.status(f'已关闭 · 已恢复原加成 · 总幸运 {result["hero_percent"]:,.0f}%')
                    self.stopping.wait(.35)
                except Exception as exc:
                    logging.exception('Controller error')
                    self.status('暂未修改：'+str(exc))
                    try: self.detach()
                    except Exception: logging.exception('Could not restore during error recovery')
                    self.stopping.wait(2)
        finally:
            try: self.detach()
            except Exception as exc:
                self.error = str(exc); logging.exception('Could not restore on close')
            self.messages.put(('closed',self.error))

