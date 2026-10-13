"""``python -m labelcheck`` 入口（与 console_scripts ``labelcheck`` 同一 main）。"""

import sys

from .cli.main import main

if __name__ == "__main__":
    sys.exit(main())
