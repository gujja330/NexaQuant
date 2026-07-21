"""Enable `python -m backend.replay backfill --from ... --to ... --market ...`."""
import sys
from .controller import main

sys.exit(main())
