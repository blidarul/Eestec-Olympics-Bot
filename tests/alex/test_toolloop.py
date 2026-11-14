import json
import time
import unittest

from solvers.toolloop import run_tool_loop, make_openai_llm_call, _first_json

BS = {"lo": 1, "hi": 100}


def R(content=None, calls=None, error=None):
    return {"content": content, "tool_calls": calls or [], "error": error}


def TC(name="binary_search_next", args=None, i="c1"):
    return {"id": i, "name": name, "arguments": json.dumps(BS if args is None else args)}


class Stub:
    def __init__(self, script):
        self.script, self.calls = list(script), []

    def __call__(self, messages, tools, timeout, max_tokens):
        self.calls.append((list(messages), tools, timeout))
        if not self.script:
            return R('{"a": "zz", "c": "x"}')
        s = self.script.pop(0)
        if callable(s):
            return s()
        return s


FINAL = '{"a": "50", "c": "go"}'


class T(unittest.TestCase):
    def run_(self, stub, native=True, rounds=2, secs=20, names=("binary_search_next",)):
        return run_tool_loop(stub, "sys", "user", list(names), time.monotonic() + secs, rounds, native)

    def test_native_one_round_then_final(self):
        s = Stub([R(calls=[TC()]), R(FINAL)])
        r = self.run_(s)
        self.assertEqual(r.final, {"a": "50", "c": "go"})
        self.assertEqual(r.mode, "native")
        self.assertEqual(len(r.trace), 1)
        self.assertTrue(r.trace[0]["ok"])
        self.assertEqual(r.model_calls, 2)
        tool_msgs = [m for m in s.calls[1][0] if m["role"] == "tool"]
        self.assertEqual(len(tool_msgs), 1)
        self.assertLessEqual(len(tool_msgs[0]["content"]), 1024)

    def test_native_two_rounds_then_forced_final(self):
        s = Stub([R(calls=[TC()]), R(calls=[TC(i="c2")]), R(FINAL)])
        r = self.run_(s)
        self.assertEqual(r.final["a"], "50")
        self.assertEqual(len(r.trace), 2)
        self.assertIsNone(s.calls[2][1])  # last call has tools disabled

    def test_direct_final_no_tools(self):
        r = self.run_(Stub([R(FINAL)]))
        self.assertEqual(r.final["a"], "50")
        self.assertEqual(r.model_calls, 1)

    def test_malformed_json_then_none(self):
        r = self.run_(Stub([R("blah {not json"), R("still not")]))
        self.assertIsNone(r.final)

    def test_unknown_tool_no_crash(self):
        r = self.run_(Stub([R(calls=[TC("nope", {})]), R(FINAL)]))
        self.assertEqual(r.final["a"], "50")
        self.assertFalse(r.trace[0]["ok"])

    def test_tool_error(self):
        r = self.run_(Stub([R(calls=[TC(args={})]), R(FINAL)]))
        self.assertFalse(r.trace[0]["ok"])
        self.assertEqual(r.final["a"], "50")

    def test_max_three_calls_per_round(self):
        s = Stub([R(calls=[TC(i="c%d" % i) for i in range(6)]), R(FINAL)])
        r = self.run_(s, rounds=1)
        self.assertEqual(len(r.trace), 3)

    def test_model_never_gives_final(self):
        r = self.run_(Stub([R(calls=[TC()]), R(calls=[TC()]), R("no idea")]))
        self.assertIsNone(r.final)
        self.assertEqual(len(r.trace), 2)

    def test_slow_model_respects_deadline(self):
        t = time.monotonic()
        r = self.run_(Stub([lambda: (time.sleep(5), R(FINAL))[1]]), secs=2.6)
        self.assertLess(time.monotonic() - t, 3.5)
        self.assertIsNone(r.final)

    def test_no_time_left(self):
        s = Stub([R(FINAL)])
        r = self.run_(s, secs=1.0)
        self.assertIsNone(r.final)
        self.assertEqual(s.calls, [])

    def test_text_mode_tool_then_final(self):
        s = Stub([R('```json\n{"tool": "binary_search_next", "args": {"lo": 1, "hi": 10}}\n```'),
                  R('ok {"final": {"a": "5", "c": "hi"}}')])
        r = self.run_(s, native=False)
        self.assertEqual(r.mode, "text")
        self.assertEqual(r.final, {"a": "5", "c": "hi"})
        self.assertTrue(r.trace[0]["ok"])
        self.assertIsNone(s.calls[0][1])
        self.assertIn("binary_search_next", s.calls[0][0][0]["content"])

    def test_native_error_falls_back_to_text(self):
        s = Stub([R(error="tools unsupported"), R('{"final": {"a": "7", "c": ""}}')])
        r = self.run_(s)
        self.assertEqual(r.mode, "text")
        self.assertEqual(r.final["a"], "7")

    def test_llm_raises(self):
        def boom(*a):
            raise RuntimeError("x")
        r = run_tool_loop(boom, "s", "u", ["binary_search_next"], time.monotonic() + 10)
        self.assertIsNone(r.final)

    def test_garbage_args(self):
        r = run_tool_loop(None, None, None, None, "x", "y", None)
        self.assertIsNone(r.final)

    def test_chat_capped_and_parse(self):
        self.assertEqual(len(_first_json('x {"a": 1} y')), 1)
        r = self.run_(Stub([R('{"a": "1", "c": "%s"}' % ("z" * 500))]))
        self.assertEqual(len(r.final["c"]), 200)

    def test_adapter_shape(self):
        class M: content = "hi"; tool_calls = None
        class C: message = M()
        class Resp: choices = [C()]
        class Comp:
            def create(self, **kw):
                self.kw = kw
                return Resp()
        class Ch: completions = Comp()
        class Cl: chat = Ch()
        cl = Cl()
        out = make_openai_llm_call(cl, "haiku")([{"role": "user", "content": "x"}], None, 5, 100)
        self.assertEqual(out["content"], "hi")
        self.assertEqual(cl.chat.completions.kw["extra_body"], {"thinking": {"type": "disabled"}})


if __name__ == "__main__":
    unittest.main()
