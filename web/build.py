import json, os
here = os.path.dirname(os.path.abspath(__file__))
t = open(os.path.join(here, "template.html")).read()
eng = open(os.path.join(here, "engine.js")).read() + "\n" + open(os.path.join(here, "geo.js")).read()
sc = json.load(open(os.path.join(here, "..", "scenarios", "sg_my_modern.json")))
out = t.replace("/*ENGINE*/", eng).replace("/*SCENARIO*/", json.dumps(sc))
open(os.path.join(here, "sg_my_simulator.html"), "w").write(out)
print("built", len(out))
