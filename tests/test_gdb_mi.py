import os
import shutil
import subprocess
import tempfile
import unittest

from ogmkdev.debug import Exited, GdbMiDebugger, Output, Stopped
from ogmkdev.debug.gdb_mi import MiParseError, parse_record

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


class MiParserTests(unittest.TestCase):
    def test_result_tuple_and_repeated_keys(self):
        rec = parse_record('^done,bkpt={number="1",type="breakpoint",line="5",fullname="/a b/c.c"}')
        self.assertEqual(rec.cls, "done")
        self.assertEqual(rec.payload["bkpt"]["number"], "1")
        self.assertEqual(rec.payload["bkpt"]["fullname"], "/a b/c.c")

    def test_list_of_named_results_becomes_list_of_values(self):
        rec = parse_record('^done,stack=[frame={level="0",func="f"},frame={level="1",func="main"}]')
        self.assertEqual([f["func"] for f in rec.payload["stack"]], ["f", "main"])

    def test_async_stopped_record(self):
        rec = parse_record('*stopped,reason="breakpoint-hit",disp="keep",bkptno="2",'
                           'frame={func="main",line="7",fullname="/p/x.c"},thread-id="1"')
        self.assertEqual(rec.kind, "exec")
        self.assertEqual(rec.cls, "stopped")
        self.assertEqual(rec.payload["frame"]["line"], "7")

    def test_c_string_escapes_and_utf8_octal_bytes(self):
        self.assertEqual(parse_record('~"a\\tb\\n"').text, "a\tb\n")
        self.assertEqual(parse_record('~"caf\\303\\251 \\"q\\""').text, 'café "q"')

    def test_error_result_and_notify(self):
        rec = parse_record('^error,msg="No symbol \\"x\\" in current context."')
        self.assertEqual(rec.cls, "error")
        self.assertEqual(rec.payload["msg"], 'No symbol "x" in current context.')
        notify = parse_record('=thread-group-exited,id="i1",exit-code="03"')
        self.assertEqual(notify.payload["exit-code"], "03")

    def test_prompt_and_unknown_lines(self):
        self.assertEqual(parse_record("(gdb)").kind, "prompt")
        self.assertIsNone(parse_record("garbage"))
        with self.assertRaises(MiParseError):
            parse_record('^done,x="unterminated')


def _line_of(path, marker):
    with open(path, encoding="utf-8") as handle:
        for number, text in enumerate(handle, 1):
            if marker in text:
                return number
    raise AssertionError(marker)


@unittest.skipUnless(shutil.which("gdb") and shutil.which("gcc"), "gdb and gcc are required")
class GdbIntegrationTests(unittest.TestCase):
    def test_breakpoint_watch_step_and_exit(self):
        source = os.path.join(FIXTURES, "gdb_target.c")
        with tempfile.TemporaryDirectory() as tmp:
            binary = os.path.join(tmp, "target")
            subprocess.run(["gcc", "-g", "-O0", "-o", binary, source], check=True)
            events = []
            dbg = GdbMiDebugger(binary, cwd=tmp, timeout=30)
            dbg.on_event(events.append)
            dbg.start()
            try:
                bp_line = _line_of(source, "@bp-square")
                bp = dbg.add_breakpoint(source, bp_line)
                dbg.run()
                stop = dbg.wait_event(lambda e: isinstance(e, Stopped), 30)
                self.assertEqual(stop.reason, "breakpoint")
                self.assertEqual(stop.breakpoint_id, bp.id)
                self.assertEqual(stop.location.line, bp_line)
                self.assertEqual(stop.location.function, "square")
                self.assertEqual(dbg.evaluate("v"), "1")

                watch = dbg.add_watch("v")
                self.assertEqual(dbg.watch_values(), {"v": "1"})
                dbg.remove_watch(watch.id)
                self.assertEqual(dbg.watches, ())

                dbg.step_over()
                step = dbg.wait_event(lambda e: isinstance(e, Stopped), 30)
                self.assertEqual(step.reason, "step")
                self.assertEqual(step.location.line, _line_of(source, "@bp-return"))
                self.assertEqual(dbg.evaluate("result"), "1")
                self.assertEqual(dict(dbg.variables()).get("result"), "1")

                dbg.remove_breakpoint(bp.id)
                dbg.run()
                done = dbg.wait_event(lambda e: isinstance(e, Exited), 30)
                self.assertEqual(done.code, 0)
                self.assertIn("total=14", "".join(e.text for e in events if isinstance(e, Output)))
            finally:
                dbg.stop()

    def test_evaluate_error_is_reported(self):
        source = os.path.join(FIXTURES, "gdb_target.c")
        with tempfile.TemporaryDirectory() as tmp:
            binary = os.path.join(tmp, "target")
            subprocess.run(["gcc", "-g", "-O0", "-o", binary, source], check=True)
            dbg = GdbMiDebugger(binary, cwd=tmp, timeout=30)
            dbg.start()
            try:
                dbg.add_watch("no_such_symbol")
                self.assertTrue(dbg.watch_values()["no_such_symbol"].startswith("<error:"))
            finally:
                dbg.stop()


if __name__ == "__main__":
    unittest.main()
