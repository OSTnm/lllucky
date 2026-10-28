"""Local, reversible Mark of the Chosen bonus adjustment. Windows x64 only."""
import ctypes as C
from ctypes import wintypes as W
import json
import math
import os
from pathlib import Path
import struct
import time

ROOT = Path(__file__).resolve().parent
GAME = Path(os.environ.get('LLLUCKY_GAME_DIR', str(ROOT.parents[1]))).resolve() / 'AzerothSurvivors.exe'
if C.sizeof(C.c_void_p) != 8:
    raise RuntimeError('lllucky requires 64-bit Python on Windows')
MAX_PERCENT = 1_000_000
K = C.WinDLL('kernel32', use_last_error=True)

class MBI(C.Structure):
    _fields_ = [('base', C.c_void_p), ('allocation', C.c_void_p), ('allocation_protect', W.DWORD),
                ('size', C.c_size_t), ('state', W.DWORD), ('protect', W.DWORD), ('type', W.DWORD)]

class PROCESSENTRY(C.Structure):
    _fields_ = [('size', W.DWORD), ('usage', W.DWORD), ('pid', W.DWORD), ('heap', C.c_size_t),
                ('module', W.DWORD), ('threads', W.DWORD), ('parent', W.DWORD), ('priority', W.LONG),
                ('flags', W.DWORD), ('exe', W.WCHAR * 260)]

class MODULEENTRY(C.Structure):
    _fields_ = [('size', W.DWORD), ('id', W.DWORD), ('pid', W.DWORD), ('global_usage', W.DWORD),
                ('process_usage', W.DWORD), ('base', C.c_void_p), ('image_size', W.DWORD),
                ('module', W.HMODULE), ('name', W.WCHAR * 256), ('path', W.WCHAR * 260)]

def api(name, args, result):
    f = getattr(K, name); f.argtypes = args; f.restype = result
    return f

api('OpenProcess', [W.DWORD, W.BOOL, W.DWORD], W.HANDLE)
api('CloseHandle', [W.HANDLE], W.BOOL)
api('ReadProcessMemory', [W.HANDLE, C.c_void_p, C.c_void_p, C.c_size_t, C.POINTER(C.c_size_t)], W.BOOL)
api('WriteProcessMemory', [W.HANDLE, C.c_void_p, C.c_void_p, C.c_size_t, C.POINTER(C.c_size_t)], W.BOOL)
api('VirtualQueryEx', [W.HANDLE, C.c_void_p, C.POINTER(MBI), C.c_size_t], C.c_size_t)
api('CreateToolhelp32Snapshot', [W.DWORD, W.DWORD], W.HANDLE)
api('Process32FirstW', [W.HANDLE, C.POINTER(PROCESSENTRY)], W.BOOL)
api('Process32NextW', [W.HANDLE, C.POINTER(PROCESSENTRY)], W.BOOL)
api('Module32FirstW', [W.HANDLE, C.POINTER(MODULEENTRY)], W.BOOL)
api('GetProcessTimes', [W.HANDLE, C.POINTER(W.FILETIME), C.POINTER(W.FILETIME), C.POINTER(W.FILETIME), C.POINTER(W.FILETIME)], W.BOOL)
api('GetExitCodeProcess', [W.HANDLE, C.POINTER(W.DWORD)], W.BOOL)
api('QueryFullProcessImageNameW', [W.HANDLE, W.DWORD, W.LPWSTR, C.POINTER(W.DWORD)], W.BOOL)

def processes():
    snap = K.CreateToolhelp32Snapshot(2, 0)
    if snap == C.c_void_p(-1).value: raise C.WinError(C.get_last_error())
    result = []
    try:
        entry = PROCESSENTRY(); entry.size = C.sizeof(entry)
        ok = K.Process32FirstW(snap, C.byref(entry))
        while ok:
            if entry.exe.lower() == 'azerothsurvivors.exe': result.append(entry.pid)
            ok = K.Process32NextW(snap, C.byref(entry))
    finally: K.CloseHandle(snap)
    return result

class Memory:
    def __init__(self, pid):
        self.pid = pid
        self.handle = K.OpenProcess(0x438, False, pid)
        if not self.handle: raise C.WinError(C.get_last_error())
        try:
            path = C.create_unicode_buffer(32768); size = W.DWORD(len(path))
            if not K.QueryFullProcessImageNameW(self.handle, 0, path, C.byref(size)):
                raise C.WinError(C.get_last_error())
            if Path(path.value).resolve() != GAME.resolve(): raise ValueError('游戏路径不匹配')
            times = [W.FILETIME() for _ in range(4)]
            if not K.GetProcessTimes(self.handle, *(C.byref(t) for t in times)):
                raise C.WinError(C.get_last_error())
            self.creation = times[0].dwLowDateTime | (times[0].dwHighDateTime << 32)
        except Exception:
            self.close(); raise

    def close(self):
        if self.handle: K.CloseHandle(self.handle); self.handle = None

    def alive(self):
        code = W.DWORD()
        return bool(self.handle and K.GetExitCodeProcess(self.handle, C.byref(code)) and code.value == 259)

    def read(self, address, size):
        buf = C.create_string_buffer(size); got = C.c_size_t()
        K.ReadProcessMemory(self.handle, address, buf, size, C.byref(got))
        return buf.raw[:got.value]

    def write_float(self, address, value):
        data = struct.pack('<f', value); done = C.c_size_t(); buf = C.create_string_buffer(data)
        if not K.WriteProcessMemory(self.handle, address, buf, 4, C.byref(done)) or done.value != 4:
            raise C.WinError(C.get_last_error())
        if self.read(address, 4) != data: raise RuntimeError('数值写入校验失败')

    def regions(self):
        address = 0
        while address < 0x7fffffffffff:
            m = MBI()
            if not K.VirtualQueryEx(self.handle, address, C.byref(m), C.sizeof(m)): break
            base = m.base or 0
            if m.state == 0x1000 and m.type == 0x20000 and m.protect & 0xff in (4,8,0x40,0x80) and not m.protect & 0x100:
                yield base, m.size
            if base + m.size <= address: break
            address = base + m.size

    def chunks(self, stop):
        for base, size in self.regions():
            for off in range(0, size, 4*1024*1024):
                if stop(): return
                data = self.read(base + off, min(4*1024*1024 + 64, size-off))
                if data: yield base+off, data

    def image_sections(self):
        snap = K.CreateToolhelp32Snapshot(0x18, self.pid)
        if snap == C.c_void_p(-1).value: raise C.WinError(C.get_last_error())
        try:
            entry = MODULEENTRY(); entry.size = C.sizeof(entry)
            if not K.Module32FirstW(snap, C.byref(entry)): raise C.WinError(C.get_last_error())
            base = entry.base
        finally: K.CloseHandle(snap)
        header = self.read(base, 4096)
        if header[:2] != b'MZ': raise RuntimeError('游戏模块格式不匹配')
        pe = struct.unpack_from('<I', header, 0x3c)[0]
        if header[pe:pe+4] != b'PE\0\0': raise RuntimeError('游戏 PE 标头无效')
        count = struct.unpack_from('<H', header, pe+6)[0]
        opt = struct.unpack_from('<H', header, pe+20)[0]
        for i in range(count):
            pos = pe+24+opt+i*40
            name = header[pos:pos+8].rstrip(b'\0')
            virtual_size, rva = struct.unpack_from('<II', header, pos+8)
            if name == b'.rdata': yield base+rva, self.read(base+rva, virtual_size)

def definition_ok(mem, definition):
    data = mem.read(definition, 64)
    if len(data) != 64: return False
    kp, kl, np, nl, ip, il, dp, dl = struct.unpack('<8Q', data)
    return (kl == 6 and nl == 18 and dl == 10 and mem.read(kp, kl) == b'chosen'
            and mem.read(np, nl) == b'Mark of the Chosen' and mem.read(dp, dl) == b'+{v}% luck')

def definitions(mem):
    found = []
    racials = set()
    for base, data in mem.image_sections():
        # A native racial ability sits beside the run's stats. Locate it before
        # searching every inventory reference across the entire heap.
        for name in (b'Perception',b'Blood Fury',b'War Stomp',b'Stoneform',b'Berserking',
                     b'Escape Artist',b'Shadowmeld',b'Will of the Forsaken'):
            start=0
            while True:
                pos=data.find(name,start)
                if pos<0:break
                needle=struct.pack('<QQ',base+pos,len(name));at=0
                while True:
                    match=data.find(needle,at)
                    if match<0:break
                    address=base+match-16;raw=mem.read(address,48)
                    if len(raw)==48:
                        kp,kl,np,nl,ip,il=struct.unpack('<6Q',raw)
                        if 0<kl<40 and 0<il<100:
                            key=mem.read(kp,kl);icon=mem.read(ip,il)
                            if key.replace(b'_',b'').isalnum() and len(icon)==il and all(32<=x<127 for x in icon):
                                racials.add(address)
                    at=match+1
                start=pos+1
        # The necklace stores mutable effects rather than a trinket value.
        name = b'Pristine Enchanted South Seas Kelp'
        name_at = data.find(name)
        if name_at >= 0:
            reference = data.find(struct.pack('<QQ',base+name_at,len(name)))
            if reference >= 16:
                definition = base+reference-16
                block = mem.read(definition,64)
                if len(block)==64:
                    kp,kl,np,nl,ip,il,ep,el = struct.unpack('<8Q',block)
                    effects = mem.read(ep,128)
                    if (kl==15 and mem.read(kp,kl)==b'south_seas_kelp' and il==23
                            and mem.read(ip,il)==b'INV_Jewelry_Necklace_26' and el==2 and len(effects)==128
                            and struct.unpack_from('<I',effects,0)[0]==37
                            and struct.unpack_from('<I',effects,8)[0]==12
                            and struct.unpack_from('<I',effects,64)[0]==37
                            and struct.unpack_from('<I',effects,72)[0]==11):
                        mem.kelp_icon = ip
        start = 0
        while True:
            pos = data.find(b'Mark of the Chosen', start)
            if pos < 0: break
            needle = struct.pack('<QQ', base+pos, 18); at = 0
            while True:
                match = data.find(needle, at)
                if match < 0: break
                definition = base+match-16
                if definition_ok(mem, definition): found.append(definition)
                at = match+1
            start = pos+1
    mem.racial_defs=sorted(racials)
    return sorted(set(found))

def necklace_items(mem, vector):
    # Current shipped Amulet: key String, name String, effects Vec, icon &str.
    key = mem.read(vector+0x60,24)
    if len(key)!=24: return []
    cap,ptr,length = struct.unpack('<3Q',key)
    if length!=15 or not 15<=cap<=256 or mem.read(ptr,length)!=b'south_seas_kelp': return []
    icon = mem.read(vector+0xa8,16)
    if len(icon)!=16:return []
    ip,il = struct.unpack('<2Q',icon)
    if il!=23 or mem.read(ip,il)!=b'INV_Jewelry_Necklace_26':return []
    if getattr(mem,'kelp_icon',ip)!=ip:return []
    effect_vec = mem.read(vector+0x90,24)
    if len(effect_vec)!=24:return []
    capacity,effects,count = struct.unpack('<3Q',effect_vec)
    if not 2<=count<=capacity<=16:return []
    result=[];gold_seen=False
    for index in range(count):
        address=effects+64*index;raw=mem.read(address,64)
        if len(raw)!=64:return []
        tag=struct.unpack_from('<I',raw)[0]
        if tag!=37:continue
        value=struct.unpack_from('<f',raw,4)[0];stat=struct.unpack_from('<I',raw,8)[0]
        if not math.isfinite(value) or not 0<=value<=1e6:return []
        if stat==11:gold_seen=True
        if stat==12:
            identity=struct.pack('<IIQQ',tag,stat,ip,effects).hex()
            result.append({'address':address,'bonus_address':address+4,'definition':0,
                           'identity':identity,'value':value,'kind':'necklace','label':'南海海带'})
    return result if gold_seen and len(result)==1 else []

def validate_owner(mem, vector, allowed_definitions):
    data = mem.read(vector, 24)
    if len(data) != 24: return None
    cap, ptr, length = struct.unpack('<3Q', data)
    if cap not in (0,1,2,4,8,16) or length > min(cap,8) or not ptr or ptr % 8: return None
    # Current shipped run layout: trinket vector -> character stat block.
    raw = mem.read(vector+0x140, 104)
    if len(raw) != 104: return None
    s = struct.unpack('<26f', raw)
    if not all(math.isfinite(x) for x in s): return None
    if not (20 <= s[0] <= 1e7 and .1 <= s[1] <= 1e7 and .00001 <= s[2] <= 2
            and 0 <= s[3] <= 1e4 and 1 <= s[4] <= 1e5 and .1 <= s[5] <= 100
            and 1 <= s[6] <= 1e5 and .1 <= s[7] <= 1e4 and 0 <= s[8] <= 1
            and 0 <= s[9] <= 1e6 and .1 <= s[10] <= 1e4 and 0 <= s[11] <= 1e6
            and .1 <= s[12] <= 1e5): return None
    items = []
    for index in range(length):
        address = ptr+index*24; record = mem.read(address, 24)
        if len(record) != 24: return None
        definition = struct.unpack_from('<Q', record)[0]
        value = struct.unpack_from('<f', record, 16)[0]
        if not math.isfinite(value) or not 0 <= value <= 1e6: return None
        if definition in allowed_definitions and definition_ok(mem, definition):
            items.append({'address':address, 'bonus_address':address+16, 'definition':definition,
                          'identity':(record[:16]+record[20:24]).hex(), 'value':value,
                          'kind':'trinket','label':'天选者印记'})
    items.extend(necklace_items(mem,vector))
    return {'vector':vector, 'stat':vector+0x16c, 'luck':s[11], 'items':items}

def locate(mem, defs, stop=lambda:False, progress=lambda message:None):
    racial_defs=getattr(mem,'racial_defs',[])
    if racial_defs:
        progress('正在快速定位角色…')
        needles=[struct.pack('<Q',p) for p in racial_defs]
        for base,size in mem.regions():
            if stop():return None
            if size>16*1024*1024:continue
            data=mem.read(base,size)
            for needle in needles:
                start=0
                while True:
                    at=data.find(needle,start)
                    if at<0:break
                    vector=base+at-0xd0
                    if vector%8==0 and validate_owner(mem,vector,defs):return vector
                    start=at+1
    progress('正在寻找幸运饰品…')
    candidates = set()
    necklace_vectors = set()
    needles = [struct.pack('<Q', d) for d in defs]
    kelp_icon = getattr(mem,'kelp_icon',None)
    icon_needle = struct.pack('<Q',kelp_icon) if kelp_icon else None
    for base, data in mem.chunks(stop):
        if icon_needle:
            start=0
            while True:
                at=data.find(icon_needle,start)
                if at<0:break
                vector=base+at-0xa8
                if vector%8==0:
                    owner=validate_owner(mem,vector,defs)
                    if owner and any(i['kind']=='necklace' for i in owner['items']):necklace_vectors.add(vector)
                start=at+1
        for needle in needles:
            start = 0
            while True:
                at = data.find(needle, start)
                if at < 0: break
                address = base+at
                if address % 8 == 0:
                    record = mem.read(address,24)
                    if len(record)==24:
                        value = struct.unpack_from('<f',record,16)[0]
                        if math.isfinite(value) and 0 <= value <= 1e6:
                            candidates.update(address-index*24 for index in range(8))
                start = at+1
    if stop(): return None
    if len(necklace_vectors)==1:return necklace_vectors.pop()
    if not candidates: return None
    progress('正在确认当前局装备…')
    vectors = set()
    needles = [struct.pack('<Q', c) for c in candidates]
    for base, data in mem.chunks(stop):
        for needle in needles:
            start = 0
            while True:
                at = data.find(needle,start)
                if at < 0: break
                vector = base+at-8
                if vector%8 == 0:
                    owner = validate_owner(mem,vector,defs)
                    if owner and owner['items']: vectors.add(vector)
                start = at+1
    if len(vectors)==1: return vectors.pop()
    return None

class Adjustment:
    def __init__(self, mem, defs, vector, journal=None):
        self.mem, self.defs, self.vector = mem, defs, vector
        self.journal = journal or ROOT/'runtime-state.json'
        self.records = {}
        try:
            saved = json.loads(self.journal.read_text(encoding='utf-8'))
            if saved.get('pid') == mem.pid and saved.get('creation') == mem.creation:
                self.records = {int(a):r for a,r in saved.get('records',{}).items()}
        except (OSError, ValueError): pass

    def save(self):
        data = {'pid':self.mem.pid,'creation':self.mem.creation,'vector':self.vector,'records':self.records}
        temp = self.journal.with_suffix('.tmp')
        temp.write_text(json.dumps(data,indent=2),encoding='utf-8'); temp.replace(self.journal)

    def tick(self, enabled, percent):
        if not math.isfinite(percent) or not 0 <= percent <= MAX_PERCENT:
            raise ValueError('幸运值超出已验证范围')
        owner = validate_owner(self.mem,self.vector,self.defs)
        if not owner: return None
        active = {i['address']:i for i in owner['items']}
        records_before = json.dumps(self.records, sort_keys=True)
        for address in list(self.records):
            item = active.get(address)
            if not item or self.records[address]['identity'] != item['identity']:
                self.records.pop(address)
        changed = False
        for item in owner['items']:
            address = item['address']; record = self.records.get(address)
            if enabled:
                if record is None:
                    record = {'original':item['value'],'identity':item['identity'],'target':item['value']}
                    self.records[address] = record
                wanted = percent/100
                record['target'] = wanted
            elif record:
                wanted = record['original']
            else: continue
            if abs(item['value']-wanted) > max(1e-7,abs(wanted)*1e-7):
                self.save()  # Preserve original value before the first write.
                # Recheck ownership and identity immediately before the write.
                again = validate_owner(self.mem,self.vector,self.defs)
                if not again: raise RuntimeError('当前局装备已变化，已停止写入')
                match = next((v for v in again['items'] if v['address']==address and v['identity']==item['identity']),None)
                if not match: raise RuntimeError('饰品已变化，已停止写入')
                before = match['value']; hero_before = again['luck']
                self.mem.write_float(match['bonus_address'],wanted)
                now = self.mem.read(again['stat'],4)
                if len(now)==4 and abs(struct.unpack('<f',now)[0]-hero_before)<.00001:
                    self.mem.write_float(again['stat'],max(0,hero_before+wanted-before))
                changed = True
            if not enabled: self.records.pop(address,None)
        if json.dumps(self.records, sort_keys=True) != records_before or changed: self.save()
        latest = validate_owner(self.mem,self.vector,self.defs)
        return {'has_item':bool(active),'hero_percent':latest['luck']*100 if latest else None,'changed':changed}

    def restore(self):
        return self.tick(False,0)
