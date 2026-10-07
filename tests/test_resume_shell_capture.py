import json
import shlex
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
import kittymux_resume as R

class ShellCaptureTests(unittest.TestCase):
    def test_embedded_foreground_agent_asks_once_and_keeps_layout_identity(self):
        agents=R.load_agents(str(Path(__file__).resolve().parents[1]/'assets/resume-agents.json'))
        sid='0a1b2c3d-0000-4000-8000-000000000001'
        payload={'id':7,'cmd_at_shell_startup':['/usr/bin/claude','--model','opus']}
        line=shlex.join(['launch',R.UNSERIALIZE+json.dumps(payload),'--var=kittymux_agent=claude','--var=kittymux_resume=exact','--var=kittymux_sid='+sid,'/usr/bin/zsh'])+'\n'
        text,report=R.rewrite_session(line,agents,wrapper=['/synthetic/kittymux','resume-prompt'])
        tokens=shlex.split(text)
        self.assertIn('resume-prompt',tokens)
        info=R.parse_info(tokens[-1]);self.assertEqual(info['orig'],payload['cmd_at_shell_startup'])
        native=json.loads(next(t[len(R.UNSERIALIZE):] for t in tokens if t.startswith(R.UNSERIALIZE)))
        self.assertEqual(native,{'id':7})
        self.assertEqual(len(report),1)
        self.assertEqual(R.rewrite_session(text,agents,wrapper=['/synthetic/kittymux','resume-prompt'])[0],text)
