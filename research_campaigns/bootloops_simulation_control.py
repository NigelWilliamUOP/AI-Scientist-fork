"""BootLoops simulation arithmetic control (synthetic, no empirical claim)."""
import json
import os
import sys
from pathlib import Path
root = Path(os.environ["BOOTLOOPS_ROOT"]).resolve()
sys.path[:0] = [str(root/"tools"), str(root/"tools"/"baller")]
import baller

def recurrence(previous, current):
    return 111 - 1130/current + 3000/(current*previous)

def main():
    baller.verify()
    previous, current = 2.0, -4.0
    for _ in range(2,101):
        previous, current = current, recurrence(previous,current)
    low = baller.run(recurrence, x0=(2,-4), n=100, dps=50)
    checked = baller.solve(recurrence,16,x0=(2,-4),n=100)
    assert current == 100.0
    assert "UNCERTIFIED" in low.render()
    assert checked.certified_digits >= 16
    print(json.dumps({"fixture":"Muller recurrence, synthetic numerical control",
                      "float_result":current,"low_precision_ball":low.render(),
                      "certified_result":checked.render(16,strict=True),
                      "certified_digits":checked.certified_digits,
                      "working_decimal_precision":checked.dps,
                      "attempts":checked.attempts,
                      "scientific_validity":"not_evaluated"},indent=2))
if __name__=="__main__":
    main()
