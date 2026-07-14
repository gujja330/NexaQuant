# india/sheets_sync.py
"""
GOOGLE SHEETS SYNC — push the latest AEGIS workbook to Google Sheets (the free, shareable, mobile
"live view"). Excel stays the authoritative report; Google Sheets is VIEW-ONLY downstream — same data,
no duplicated logic.

Auth: a Google service account, configured in .env.google (git-ignored):
    GOOGLE_SERVICE_ACCOUNT_FILE = path to the service-account .json
    AEGIS_SPREADSHEET_ID        = the target spreadsheet id (falls back to PRISM_SPREADSHEET_ID)
ONE manual setup step (once): create a Google Sheet, Share it with the service account's
client_email (Editor), and put its id in AEGIS_SPREADSHEET_ID. Then this runs unattended.

Run:  python india/sheets_sync.py            # push every sheet of the latest workbook
      python india/sheets_sync.py --check    # validate config only (no network write)
      python india/sheets_sync.py --create   # create a fresh spreadsheet, print its id+url
"""
import os, sys, warnings
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.simplefilter("ignore")
REPORTS = ROOT / "reports"

# ENG002: consolidated env-loader + workbook-glob helpers from nexaquant.lib.
# The two functions below remain in the module ABI as thin wrappers so any
# external caller (grep verifies none as of ENG002) still resolves them.
from nexaquant.lib.env_loader import load_env_files as _load_env_files
from nexaquant.lib.paths import find_latest_workbook as _find_latest_workbook


def load_env():
    """Read .env.google / .env into os.environ (no python-dotenv dependency). Real env vars win.

    ENG002: implementation delegated to `nexaquant.lib.env_loader.load_env_files`.
    Semantics preserved: existing env values win (override=False), quotes stripped,
    comments and blank lines ignored.
    """
    _load_env_files(ROOT / ".env.google", ROOT / ".env")


def latest_workbook():
    """Path (as string) to the newest AEGIS_*.xlsx in reports/, or None.

    ENG002: implementation delegated to `nexaquant.lib.paths.find_latest_workbook`.
    Return type coerced to str for byte-identical downstream behaviour.
    """
    p = _find_latest_workbook(REPORTS)
    return str(p) if p is not None else None


def _creds_path():
    sa = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "")
    p = Path(sa)
    if not p.is_absolute():
        p = ROOT / sa
    return p


def _spreadsheet_id():
    return os.environ.get("AEGIS_SPREADSHEET_ID") or os.environ.get("PRISM_SPREADSHEET_ID")


def check():
    load_env()
    sa, sid, wb = _creds_path(), _spreadsheet_id(), latest_workbook()
    ok = True
    print("  service account file:", sa, "->", "FOUND" if sa.exists() else "MISSING"); ok &= sa.exists()
    print("  spreadsheet id      :", "set" if sid else "MISSING (set AEGIS_SPREADSHEET_ID)"); ok &= bool(sid)
    print("  latest workbook     :", Path(wb).name if wb else "none"); ok &= bool(wb)
    try:
        import gspread  # noqa
        print("  gspread             : OK")
    except Exception:
        print("  gspread             : MISSING (pip install gspread)"); ok = False
    print("  ->", "READY to sync" if ok else "NOT ready — fix the items above")
    return ok


def _client():
    import gspread
    return gspread.service_account(filename=str(_creds_path()))


def create_spreadsheet(title="AEGIS Live"):
    load_env()
    sh = _client().create(title)
    email = os.environ.get("SHARE_WITH_EMAIL")
    if email:
        sh.share(email, perm_type="user", role="writer")
    print(f"  created '{title}'  id={sh.id}")
    print(f"  url: https://docs.google.com/spreadsheets/d/{sh.id}")
    print("  -> put this id in .env.google as AEGIS_SPREADSHEET_ID (and Share the sheet with your "
          "own Google account to see it).")
    return sh.id


def sync(clean=False):
    """Push every sheet of the latest workbook to the target spreadsheet (clear + rewrite each tab).
    clean=True also REMOVES any pre-existing tabs that aren't AEGIS sheets (reuse a sheet entirely)."""
    load_env()
    wb = latest_workbook()
    if not wb:
        print("  no workbook found — run india/recommendation_generator.py first."); return False
    sid = _spreadsheet_id()
    if not _creds_path().exists() or not sid:
        print("  config incomplete — run with --check."); return False
    sh = _client().open_by_key(sid)
    xls = pd.ExcelFile(wb)
    aegis_names = set(xls.sheet_names)
    for name in xls.sheet_names:
        df = pd.read_excel(wb, sheet_name=name).fillna("")
        values = [list(map(str, df.columns))] + df.astype(str).values.tolist()
        try:
            ws = sh.worksheet(name)
            ws.clear()
        except Exception:
            ws = sh.add_worksheet(title=name[:99], rows=max(len(values) + 5, 20),
                                  cols=max(len(df.columns) + 2, 6))
        ws.update(values, value_input_option="USER_ENTERED")
    if clean:                                            # remove leftover non-AEGIS tabs (reuse entirely)
        for ws in sh.worksheets():
            if ws.title not in aegis_names:
                try:
                    sh.del_worksheet(ws)
                except Exception:
                    pass
    print(f"  synced {len(xls.sheet_names)} sheets from {Path(wb).name}"
          + ("  (cleaned old tabs)" if clean else ""))
    print(f"  view: https://docs.google.com/spreadsheets/d/{sid}")
    return True





def main():
    if "--check" in sys.argv:
        check()
    elif "--create" in sys.argv:
        create_spreadsheet()
    else:
        if check():
            sync(clean="--clean" in sys.argv)


if __name__ == "__main__":
    main()
