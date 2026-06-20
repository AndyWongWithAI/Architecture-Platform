"""Import scripts — 把 docs/components/*.md 导入 SQLite"""
import sys
import os

# 让脚本能从 backend/ 目录运行
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal, init_db
from app.services import MarkdownImporter


COMPONENTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "docs",
    "components",
)


def main():
    print(f"Components dir: {COMPONENTS_DIR}")
    print("Initializing DB schema...")
    init_db()

    print("Importing components...")
    db = SessionLocal()
    try:
        importer = MarkdownImporter(db, COMPONENTS_DIR)
        result = importer.import_all()
        print(f"\n{result}")
        if result.errors:
            print("\nErrors:")
            for err in result.errors:
                print(f"  - {err}")
    finally:
        db.close()


if __name__ == "__main__":
    main()