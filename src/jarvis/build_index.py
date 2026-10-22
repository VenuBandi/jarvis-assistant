"""Build the Jarvis J1 index from the allowlisted project files.

Run from the project root:  python3 -I src/jarvis/build_index.py
Writes data/jarvis/index.json and data/jarvis/index_manifest.json.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jarvis_core as jc  # noqa: E402


def main():
    index, manifest = jc.build_index(jc.ROOT)
    jc.INDEX_DIR.mkdir(parents=True, exist_ok=True)
    jc.INDEX_FILE.write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    jc.MANIFEST_FILE.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"files indexed: {manifest['files_indexed']}")
    print(f"chunks: {manifest['chunk_count']}")
    print(f"skipped secret chunks: {manifest['skipped_secret_chunks']}")
    print(f"skipped large files: {len(manifest['skipped_large_files'])}")
    print(f"parse errors: {len(manifest['parse_errors'])}")
    for e in manifest["parse_errors"]:
        print(f"  {e['path']}: {e['error']}")
    print(f"built_at: {manifest['built_at']}")
    print(f"wrote: {jc.INDEX_FILE.relative_to(jc.ROOT)}, {jc.MANIFEST_FILE.relative_to(jc.ROOT)}")


if __name__ == "__main__":
    main()
