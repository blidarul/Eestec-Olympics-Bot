import json, os, sys, tempfile
sys.path.insert(0, os.path.dirname(__file__))
import drive, fake_gateway, msgs
log="out/f1/probe.jsonl"; open(log,"w").close()
gw=fake_gateway.GW(log,"fixed",json.dumps({"action":"a1","chat":"hi"}))
llm={"base_url":gw.url,"api_key":"k-p","model":"haiku"}
prep,start,turn,g=msgs.build(sys.argv[1],0,0,1,llm)
mem=tempfile.mkdtemp(prefix="am_")
r=drive.run([prep,start,turn(),{"type":"end","game_index":1,"result":"win"},{"type":"shutdown"}],memory_dir=mem)
print(drive.summarize(r)); open("out/f1/probe.err","w",encoding="utf8").write(r["stderr_full"])
for a in r["answers"]: print(a["for"],a["latency"],a["line"][:150])
for r_ in map(json.loads,open(log)): print(r_["n_msgs"],r_["chars"],r_["has_tools"],r_["thinking"],r_["max_tokens"])
for root,d,f in os.walk(mem):
    for x in f: print(os.path.relpath(os.path.join(root,x),mem), os.path.getsize(os.path.join(root,x)))
