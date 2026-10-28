import os
from pathlib import Path
import tempfile
import unittest
from headless import Channel,parse_values

class Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'config.toml';self.channel=Channel()
    def tearDown(self):self.temp.cleanup()
    def config(self,body):
        self.path.write_text('[cvars]\n'+body,encoding='utf-8');os.utime(self.path,(1000,1000))
    def test_custom_settings_are_case_insensitive(self):
        self.config('llluckySchema = "1"\nllluckyEnabled = "1"\nllluckyPercent = "1000"\nllluckyBeat = "100"\n')
        result=self.channel.read(self.path,900,now=10,wall=1000)
        self.assertTrue(result['enabled']);self.assertEqual(result['percent'],1000)
    def test_omitted_default_enabled_means_off(self):
        self.config('llluckySchema = "1"\nllluckyPercent = "300"\nllluckyBeat = "100"\n')
        result=self.channel.read(self.path,900,now=10,wall=1000)
        self.assertTrue(result['live']);self.assertFalse(result['enabled'])
    def test_dead_addon_is_automatically_disabled(self):
        self.config('llluckySchema = "1"\nllluckyEnabled = "1"\nllluckyPercent = "300"\nllluckyBeat = "100"\n')
        self.assertTrue(self.channel.read(self.path,900,now=10,wall=1000)['enabled'])
        self.assertFalse(self.channel.read(self.path,900,now=31,wall=1021)['enabled'])
    def test_previous_game_config_cannot_enable_new_process(self):
        self.config('llluckySchema = "1"\nllluckyEnabled = "1"\nllluckyPercent = "300"\nllluckyBeat = "100"\n')
        self.assertFalse(self.channel.read(self.path,1100,now=10,wall=1000)['enabled'])
    def test_nonfinite_setting_is_rejected(self):
        self.config('llluckySchema = "1"\nllluckyEnabled = "1"\nllluckyPercent = "nan"\nllluckyBeat = "100"\n')
        self.assertFalse(self.channel.read(self.path,900,now=10,wall=1000)['enabled'])

if __name__=='__main__':unittest.main()
