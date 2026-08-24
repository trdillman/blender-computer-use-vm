"""
Release Packaging & Checksum Generator for Blender Computer-Use VM & MCP Server.
Creates a clean, reproducible distribution bundle (.zip) and SHA256 checksum manifest.
"""

from __future__ import annotations

import hashlib
import os
import zipfile


def get_file_sha256(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def build_release_package():
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dist_dir = os.path.join(root_dir, "dist")
    os.makedirs(dist_dir, exist_ok=True)

    release_zip_path = os.path.join(dist_dir, "blender-computer-use-vm-v1.1.1.zip")
    checksum_file_path = os.path.join(dist_dir, "CHECKSUMS.txt")

    # Files and directories to include in release
    include_dirs = ["host", "guest", "blender", "scripts", "skills", "tests", ".claude-plugin"]
    include_files = ["package.json", "marketplace.json", "mcp-config.json", "README.md", ".gitignore", "install.bat", "install.ps1", "install.py"]

    print(f"Building Release Bundle: {release_zip_path}...")

    manifest_entries = []

    with zipfile.ZipFile(release_zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Include top-level files
        for fname in include_files:
            fpath = os.path.join(root_dir, fname)
            if os.path.exists(fpath):
                arcname = fname
                zf.write(fpath, arcname=arcname)
                sha = get_file_sha256(fpath)
                manifest_entries.append((arcname, sha))

        # Include directories
        for dname in include_dirs:
            dir_path = os.path.join(root_dir, dname)
            if not os.path.exists(dir_path):
                continue
            for r, _, files in os.walk(dir_path):
                if "__pycache__" in r or "staging" in r:
                    continue
                for f in files:
                    if f.endswith((".pyc", ".mp4", ".zip", ".vhdx")):
                        continue
                    full_fpath = os.path.join(r, f)
                    rel_arc = os.path.relpath(full_fpath, root_dir)
                    zf.write(full_fpath, arcname=rel_arc)
                    sha = get_file_sha256(full_fpath)
                    manifest_entries.append((rel_arc, sha))

    # Write Checksums
    zip_sha = get_file_sha256(release_zip_path)
    zip_size_kb = os.path.getsize(release_zip_path) / 1024

    with open(checksum_file_path, "w", encoding="utf-8") as f:
        f.write(f"# SHA256 Checksums for blender-computer-use-vm v1.1.1\n")
        f.write(f"{zip_sha}  blender-computer-use-vm-v1.1.1.zip\n\n")
        f.write(f"# Component File Manifest\n")
        for arcname, sha in sorted(manifest_entries):
            f.write(f"{sha}  {arcname}\n")

    print(f"Package created successfully! Size: {zip_size_kb:.1f} KB")
    print(f"Zip SHA256: {zip_sha}")
    print(f"Checksum manifest saved to: {checksum_file_path}")


if __name__ == "__main__":
    build_release_package()
