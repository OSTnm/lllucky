import json
import math
from pathlib import Path
import struct
import tempfile
import unittest
from memory_backend import Adjustment, MAX_PERCENT, validate_owner, locate

class FakeMemory:
    pid=123
    creation=456
    def __init__(self):
        self.parts={};self.writes=[]
        self.vector=0x1000;self.item=0x3000;self.definition=0x5000
        self.parts[self.vector]=struct.pack('<3Q',4,self.item,1)
        self.parts[self.item]=struct.pack('<QII f I',self.definition,0,0,.225,1)
        self.parts[self.definition]=struct.pack('<8Q',0x6000,6,0x7000,18,0x8000,23,0x9000,10)
        self.parts[0x6000]=b'chosen';self.parts[0x7000]=b'Mark of the Chosen';self.parts[0x9000]=b'+{v}% luck'
        stats=[400,2,.8,.1,2,1.1,18,1.1,.4,2,1.1,1.0,1.3]+[0]*13
        self.parts[self.vector+0x140]=struct.pack('<26f',*stats)
    def read(self,address,size):
        for base,part in self.parts.items():
            if base<=address and address+size<=base+len(part):return part[address-base:address-base+size]
        return b''
    def write_float(self,address,value):
        for base,part in self.parts.items():
            if base<=address and address+4<=base+len(part):
                offset=address-base;self.parts[base]=part[:offset]+struct.pack('<f',value)+part[offset+4:]
                self.writes.append((address,value));return
        raise RuntimeError('Unexpected memory write')

class Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.mem=FakeMemory()
        self.adj=Adjustment(self.mem,[self.mem.definition],self.mem.vector,Path(self.temp.name)/'state.json')
    def tearDown(self):self.temp.cleanup()
    def luck(self):return struct.unpack('<f',self.mem.read(self.mem.vector+0x16c,4))[0]
    def test_toggle_preserves_other_luck(self):
        self.adj.tick(True,300);self.assertAlmostEqual(self.luck(),3.775,places=5)
        self.adj.tick(True,1000);self.assertAlmostEqual(self.luck(),10.775,places=5)
        self.adj.restore();self.assertAlmostEqual(self.luck(),1,places=5)
    def test_recalculation_uses_modified_item(self):
        self.adj.tick(True,300)
        item=struct.unpack('<f',self.mem.read(self.mem.item+16,4))[0]
        self.mem.write_float(self.mem.vector+0x16c,item+.775)
        count=len(self.mem.writes);self.adj.tick(True,300)
        self.assertEqual(count,len(self.mem.writes));self.assertAlmostEqual(self.luck(),3.775,places=5)
    def test_replaced_item_is_never_restored(self):
        self.adj.tick(True,300)
        self.mem.parts[self.mem.item]=struct.pack('<QII f I',0x9999,0,0,.75,1)
        count=len(self.mem.writes);self.adj.restore()
        self.assertEqual(count,len(self.mem.writes))
    def test_bad_layout_prevents_write(self):
        self.mem.write_float(self.mem.vector+0x140+8*4,9)
        count=len(self.mem.writes);self.assertIsNone(self.adj.tick(True,300))
        self.assertEqual(count,len(self.mem.writes))
    def test_restart_recovery_remembers_original(self):
        self.adj.tick(True,300)
        resumed=Adjustment(self.mem,[self.mem.definition],self.mem.vector,self.adj.journal)
        resumed.restore();self.assertAlmostEqual(self.luck(),1,places=5)
    def test_other_process_cannot_inherit_restore_record(self):
        self.adj.tick(True,300);self.mem.creation+=1
        resumed=Adjustment(self.mem,[self.mem.definition],self.mem.vector,self.adj.journal)
        self.assertFalse(resumed.records)
    def test_nonfinite_or_unverified_value_is_rejected(self):
        for value in [math.inf,math.nan,-1,MAX_PERCENT+1]:
            with self.assertRaises(ValueError):self.adj.tick(True,value)
        self.assertFalse(self.mem.writes)

    def add_necklace(self):
        v=self.mem.vector
        self.mem.parts[v+0x60]=struct.pack('<3Q',15,0xa000,15)
        self.mem.parts[0xa000]=b'south_seas_kelp'
        self.mem.parts[v+0xa8]=struct.pack('<2Q',0xb000,23)
        self.mem.parts[0xb000]=b'INV_Jewelry_Necklace_26'
        self.mem.parts[v+0x90]=struct.pack('<3Q',2,0xc000,2)
        luck=struct.pack('<IfI',37,.3,12)+bytes(52)
        gold=struct.pack('<IfI',37,.25,11)+bytes(52)
        self.mem.parts[0xc000]=luck+gold
        self.mem.parts[v+0x530]=struct.pack('<3Q',4,0xd000,3)
        # Padding is unspecified in Rust's compact enum. Only byte 0 is a tag.
        self.mem.parts[0xd000]=(struct.pack('<If',5,.125)
                               +bytes([12,0x96,0x96,0xbe])+struct.pack('<f',.3)
                               +bytes([11,0xfa,0x64,0x7d])+struct.pack('<f',.25))

    def test_necklace_and_mark_stack_without_changing_gold(self):
        self.add_necklace();gold=self.mem.read(0xc040,64)
        self.adj.tick(True,300)
        self.assertAlmostEqual(self.luck(),6.475,places=5)
        self.assertEqual(self.mem.read(0xc040,64),gold)
        self.assertAlmostEqual(struct.unpack('<f',self.mem.read(0xd00c,4))[0],3)
        self.adj.restore();self.assertAlmostEqual(self.luck(),1,places=5)
        self.assertAlmostEqual(struct.unpack('<f',self.mem.read(0xc004,4))[0],.3,places=5)
        self.assertAlmostEqual(struct.unpack('<f',self.mem.read(0xd00c,4))[0],.3,places=5)

    def test_necklace_native_recalculation_uses_source_not_description(self):
        self.add_necklace();self.adj.tick(True,300)
        # Recompute from native sources, then append a normal level-up card.
        sources=self.mem.parts[0xd000]+struct.pack('<If',12,.2)
        self.mem.parts[0xd000]=sources
        self.mem.parts[self.mem.vector+0x530]=struct.pack('<3Q',4,0xd000,4)
        mark=struct.unpack('<f',self.mem.read(self.mem.item+16,4))[0]
        luck=sum(struct.unpack_from('<f',sources,i+4)[0]
                 for i in range(0,len(sources),8) if sources[i]==12)
        self.mem.write_float(self.mem.vector+0x16c,mark+luck+.475)
        count=len(self.mem.writes);self.adj.tick(True,300)
        self.assertEqual(count,len(self.mem.writes))
        self.assertAlmostEqual(self.luck(),6.675,places=5)
        self.assertAlmostEqual(struct.unpack('<f',self.mem.read(0xc004,4))[0],.3,places=5)
        self.assertAlmostEqual(struct.unpack('<f',self.mem.read(0xd014,4))[0],.25,places=5)
        self.adj.restore();self.assertAlmostEqual(self.luck(),1.2,places=5)

    def test_necklace_source_vector_reallocation_and_rebuild(self):
        self.add_necklace();original=self.mem.parts[0xd000]
        self.adj.tick(True,300)
        # A rebuild derives fresh values from the untouched equipped effects.
        self.mem.parts[0xe000]=original
        self.mem.parts[self.mem.vector+0x530]=struct.pack('<3Q',4,0xe000,3)
        self.mem.write_float(self.mem.vector+0x16c,3.775)
        self.adj.tick(True,300);self.assertAlmostEqual(self.luck(),6.475,places=5)
        old=self.mem.read(0xd000,24)
        self.adj.restore();self.assertAlmostEqual(self.luck(),1,places=5)
        self.assertEqual(old,self.mem.read(0xd000,24))

    def test_ambiguous_or_invalid_stat_sources_prevent_necklace_write(self):
        self.add_necklace()
        self.mem.parts[self.mem.vector]=struct.pack('<3Q',0,8,0)
        pair=self.mem.parts[0xd000][8:]
        self.mem.parts[0xd000]=pair+pair
        self.mem.parts[self.mem.vector+0x530]=struct.pack('<3Q',4,0xd000,4)
        self.adj.tick(True,300);self.assertFalse(self.mem.writes)
        self.mem.parts[0xd000]=struct.pack('<If',99,.3)+pair
        self.mem.parts[self.mem.vector+0x530]=struct.pack('<3Q',4,0xd000,3)
        self.adj.tick(True,300);self.assertFalse(self.mem.writes)

    def test_necklace_vector_growth_retains_restore_value(self):
        self.add_necklace();self.adj.tick(True,300)
        self.mem.parts[0xe000]=self.mem.parts[0xd000]+struct.pack('<If',12,.2)
        self.mem.parts[self.mem.vector+0x530]=struct.pack('<3Q',8,0xe000,4)
        self.adj.tick(True,300)
        self.adj=Adjustment(self.mem,[self.mem.definition],self.mem.vector,self.adj.journal)
        self.adj.restore()
        self.assertAlmostEqual(struct.unpack('<f',self.mem.read(0xe00c,4))[0],.3,places=5)
        self.assertAlmostEqual(struct.unpack('<f',self.mem.read(0xe01c,4))[0],.2,places=5)

    def test_necklace_can_disable_immediately_after_vector_growth(self):
        self.add_necklace();self.adj.tick(True,300)
        self.mem.parts[0xe000]=self.mem.parts[0xd000]
        self.mem.parts[self.mem.vector+0x530]=struct.pack('<3Q',8,0xe000,3)
        self.adj.restore()
        self.assertAlmostEqual(struct.unpack('<f',self.mem.read(0xe00c,4))[0],.3,places=5)
        self.assertAlmostEqual(self.luck(),1,places=5)

    def test_necklace_works_without_mark(self):
        self.add_necklace()
        self.mem.parts[self.mem.vector]=struct.pack('<3Q',0,8,0)
        self.adj.tick(True,300);self.assertAlmostEqual(self.luck(),3.7,places=5)
        self.adj.restore();self.assertAlmostEqual(self.luck(),1,places=5)

    def test_unrelated_necklace_effects_are_never_modified(self):
        self.add_necklace()
        data=self.mem.parts[0xc000]
        self.mem.parts[0xc000]=data[:8]+struct.pack('<I',99)+data[12:]
        self.mem.parts[self.mem.vector]=struct.pack('<3Q',0,8,0)
        self.adj.tick(True,300)
        self.assertFalse(self.mem.writes)

    def test_fast_lookup_finds_owner_before_full_heap_scan(self):
        self.mem.racial_defs=[0x12345678]
        original_read=self.mem.read
        def root_read(address,size):
            if address==self.mem.vector and size==0x200:
                data=bytearray(0x200)
                for base,part in self.mem.parts.items():
                    off=base-self.mem.vector
                    if 0<=off and off+len(part)<=len(data):data[off:off+len(part)]=part
                struct.pack_into('<Q',data,0xd0,self.mem.racial_defs[0])
                return bytes(data)
            return original_read(address,size)
        self.mem.read=root_read
        self.mem.regions=lambda:iter([(self.mem.vector,0x200)])
        self.assertEqual(locate(self.mem,[self.mem.definition]),self.mem.vector)

    def test_fast_lookup_can_cache_run_before_luck_item_is_obtained(self):
        self.mem.parts[self.mem.vector]=struct.pack('<3Q',0,8,0)
        self.test_fast_lookup_finds_owner_before_full_heap_scan()

if __name__=='__main__':unittest.main()
