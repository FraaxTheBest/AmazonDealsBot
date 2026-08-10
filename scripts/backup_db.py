from datetime import datetime
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import get_settings


def sqlite_path(url: str) -> Path | None:
    prefix = "sqlite+aiosqlite:///"
    if not url.startswith(prefix):
        return None
    raw = url[len(prefix):]
    return Path(raw).expanduser().resolve()


def main() -> int:
    settings = get_settings()
    backup_dir = Path(settings.backup_dir).expanduser().resolve()
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    source = sqlite_path(settings.database_url)
    if source is not None:
        if not source.exists():
            print(f"ERRORE: database SQLite non trovato: {source}")
            return 1
        destination = backup_dir / f"amazondealsbot_{stamp}.db"
        shutil.copy2(source, destination)
        print(f"Backup SQLite creato: {destination}")
        return 0

    if settings.database_url.startswith("postgresql"):
        destination = backup_dir / f"amazondealsbot_{stamp}.dump"
        url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
        try:
            subprocess.run(
                ["pg_dump", url, "--format=custom", "--file", str(destination)],
                check=True,
            )
        except FileNotFoundError:
            print("ERRORE: pg_dump non trovato nel PATH.")
            return 1
        except subprocess.CalledProcessError:
            print("ERRORE: pg_dump non è riuscito. Le credenziali non vengono stampate.")
            return 1
        print(f"Backup PostgreSQL creato: {destination}")
        return 0

    print("ERRORE: DATABASE_URL non supportato dal backup automatico.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
