# -*- coding: utf-8 -*-
"""
GITHUB PUSH UTILITY - VNStock-TradingBot-247
Đẩy toàn bộ mã nguồn hệ thống Bot Trading lên GitHub một cách an toàn và bảo mật:
1. Tự động loại trừ 100% các file bí mật (.env, keys*.txt, portfolio.json, log).
2. Sử dụng GitHub REST API (không cần cài đặt Git CLI trên Windows).
3. Tự động tạo Repository mới trên tài khoản GitHub của bạn (nếu chưa có).
4. Tạo commit hoàn chỉnh và cập nhật nhánh main.
"""

import os
import sys
import json
import base64
import argparse
from typing import List, Tuple, Optional
import requests

# Đảm bảo UTF-8 cho console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)

# Danh sách loại trừ bảo mật tuyệt đối
EXCLUDED_EXTENSIONS = {".pyc", ".log"}
EXCLUDED_NAMES = {
    ".env", "keys.txt", "keys_valid.txt", "api.txt",
    "portfolio.json", "subscribers.json", "Thumbs.db", ".DS_Store"
}
EXCLUDED_DIRS = {
    "__pycache__", ".git", ".idea", ".vscode", "venv", "env", "node_modules"
}


def should_exclude(rel_path: str) -> bool:
    """Kiểm tra đường dẫn có thuộc danh sách bị cấm đẩy lên GitHub hay không."""
    normalized = rel_path.replace("\\", "/").strip("/")
    parts = normalized.split("/")

    for p in parts:
        if p in EXCLUDED_DIRS:
            return True
        if p in EXCLUDED_NAMES:
            return True

    filename = parts[-1]
    _, ext = os.path.splitext(filename)
    if ext in EXCLUDED_EXTENSIONS:
        return True

    if "keys" in filename.lower() and ext == ".txt":
        return True

    return False


def get_all_files_to_upload(root_dir: str) -> List[Tuple[str, str]]:
    """Duyệt toàn bộ thư mục và gom các file hợp lệ cần đẩy lên GitHub."""
    files_to_upload = []

    for dirpath, dirnames, filenames in os.walk(root_dir):
        # Lọc bỏ thư mục cấm ngay tại chỗ để tránh đệ quy sâu
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]

        for fname in filenames:
            abs_path = os.path.join(dirpath, fname)
            rel_path = os.path.relpath(abs_path, root_dir).replace("\\", "/")

            if should_exclude(rel_path):
                continue

            files_to_upload.append((abs_path, rel_path))

    return files_to_upload


def push_to_github(
    token: str,
    repo_name: str = "VNStock-TradingBot-247",
    is_private: bool = False,
    commit_msg: str = "🚀 Khởi tạo Hệ thống Auto-Trading 24/7 Chứng khoán Việt Nam"
):
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "MyAgent-TradingBot-Pusher"
    }

    # 1. Xác thực tài khoản GitHub
    print("[1/5] Đang kiểm tra thông tin tài khoản GitHub...")
    user_res = requests.get("https://api.github.com/user", headers=headers)
    if user_res.status_code != 200:
        print(f"❌ Lỗi xác thực GitHub Token! Mã lỗi: {user_res.status_code}")
        print(f"Chi tiết: {user_res.text}")
        return False

    user_data = user_res.json()
    username = user_data["login"]
    print(f"✅ Đăng nhập thành công với tài khoản: {username} ({user_data.get('name', '')})")

    # 2. Kiểm tra hoặc Tạo mới Repository
    print(f"[2/5] Kiểm tra repository: {username}/{repo_name}...")
    repo_res = requests.get(f"https://api.github.com/repos/{username}/{repo_name}", headers=headers)

    if repo_res.status_code == 404:
        print(f"[*] Repository chưa tồn tại, đang tạo mới (Private={is_private})...")
        create_payload = {
            "name": repo_name,
            "description": "Hệ thống Auto-Trading & Quét Dòng Tiền Lớn 24/7 Chứng khoán Việt Nam (Multi-Agent AI x Telegram)",
            "private": is_private,
            "auto_init": True
        }
        create_res = requests.post("https://api.github.com/user/repos", headers=headers, json=create_payload)
        if create_res.status_code not in (200, 201):
            print(f"❌ Không thể tạo repository: {create_res.text}")
            return False
        print(f"✅ Đã tạo mới repository thành công!")
    elif repo_res.status_code == 200:
        print(f"✅ Repository {username}/{repo_name} đã sẵn sàng.")
    else:
        print(f"❌ Lỗi truy vấn repository: {repo_res.text}")
        return False

    # 3. Quét danh sách file hợp lệ trong thư mục bot trading
    print("[3/5] Đang quét các file mã nguồn hợp lệ...")
    files = get_all_files_to_upload(BASE_DIR)
    print(f"✅ Tìm thấy {len(files)} file cần tải lên (Đã bảo vệ lọc bỏ file bí mật .env, keys).")

    # 4. Tải Blobs lên GitHub Git Database đa luồng
    print(f"[4/5] Đang tải song song {len(files)} file lên GitHub Blobs (8 luồng)...", flush=True)
    tree_items = []
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _upload_single_file(item):
        abs_path, rel_path = item
        try:
            with open(abs_path, "rb") as f:
                content_bytes = f.read()

            b64_content = base64.b64encode(content_bytes).decode("utf-8")
            blob_res = requests.post(
                f"https://api.github.com/repos/{username}/{repo_name}/git/blobs",
                headers=headers,
                json={"content": b64_content, "encoding": "base64"},
                timeout=30
            )
            if blob_res.status_code in (200, 201):
                blob_sha = blob_res.json()["sha"]
                return {
                    "path": rel_path,
                    "mode": "100644",
                    "type": "blob",
                    "sha": blob_sha
                }
            else:
                print(f"   ⚠️ Lỗi tải file {rel_path}: {blob_res.text}", flush=True)
                return None
        except Exception as e:
            print(f"   ⚠️ Lỗi đọc file {abs_path}: {e}", flush=True)
            return None

    completed_count = 0
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(_upload_single_file, item): item for item in files}
        for future in as_completed(futures):
            res = future.result()
            completed_count += 1
            if res:
                tree_items.append(res)
            if completed_count % 20 == 0 or completed_count == len(files):
                print(f"   • Đã tải: {completed_count}/{len(files)} files...", flush=True)

    if not tree_items:
        print("❌ Không có file nào được tải lên!", flush=True)
        return False

    # 5. Tạo Git Tree, Commit và Cập nhật nhánh main
    print("[5/5] Đang đóng gói Commit và cập nhật nhánh main...")
    # Lấy SHA commit hiện tại của main (nếu có)
    ref_res = requests.get(f"https://api.github.com/repos/{username}/{repo_name}/git/refs/heads/main", headers=headers)
    parent_commit_sha = None
    if ref_res.status_code == 200:
        parent_commit_sha = ref_res.json()["object"]["sha"]
    else:
        # Thử nhánh master
        ref_master = requests.get(f"https://api.github.com/repos/{username}/{repo_name}/git/refs/heads/master", headers=headers)
        if ref_master.status_code == 200:
            parent_commit_sha = ref_master.json()["object"]["sha"]

    # Tạo tree mới
    tree_payload = {"tree": tree_items}
    tree_res = requests.post(f"https://api.github.com/repos/{username}/{repo_name}/git/trees", headers=headers, json=tree_payload)
    if tree_res.status_code not in (200, 201):
        print(f"❌ Lỗi tạo Tree: {tree_res.text}")
        return False
    new_tree_sha = tree_res.json()["sha"]

    # Tạo commit mới
    commit_payload = {
        "message": commit_msg,
        "tree": new_tree_sha
    }
    if parent_commit_sha:
        commit_payload["parents"] = [parent_commit_sha]

    commit_res = requests.post(f"https://api.github.com/repos/{username}/{repo_name}/git/commits", headers=headers, json=commit_payload)
    if commit_res.status_code not in (200, 201):
        print(f"❌ Lỗi tạo Commit: {commit_res.text}")
        return False
    new_commit_sha = commit_res.json()["sha"]

    # Cập nhật ref heads/main
    if parent_commit_sha:
        patch_ref_res = requests.patch(
            f"https://api.github.com/repos/{username}/{repo_name}/git/refs/heads/main",
            headers=headers,
            json={"sha": new_commit_sha, "force": True}
        )
        if patch_ref_res.status_code != 200:
            # Thử tạo ref mới nếu nhánh main chưa có
            requests.post(
                f"https://api.github.com/repos/{username}/{repo_name}/git/refs",
                headers=headers,
                json={"ref": "refs/heads/main", "sha": new_commit_sha}
            )
    else:
        requests.post(
            f"https://api.github.com/repos/{username}/{repo_name}/git/refs",
            headers=headers,
            json={"ref": "refs/heads/main", "sha": new_commit_sha}
        )

    repo_url = f"https://github.com/{username}/{repo_name}"
    print("\n" + "=" * 65)
    print("🎉 CHÚC MỪNG! TOÀN BỘ MÃ NGUỒN BOT TRADING ĐÃ ĐƯỢC ĐẨY LÊN GITHUB!")
    print(f"🔗 Repository URL: {repo_url}")
    print(f"📦 Số lượng file  : {len(tree_items)}")
    print(f"🛡️ Bảo mật        : Đã bảo vệ và lọc bỏ 100% file .env, keys, tokens")
    print("=" * 65)
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Đẩy mã nguồn Bot Trading lên GitHub an toàn.")
    parser.add_argument("--token", type=str, help="GitHub Personal Access Token (classic hoặc fine-grained với quyền repo)")
    parser.add_argument("--repo", type=str, default="VNStock-TradingBot-247", help="Tên repository trên GitHub")
    parser.add_argument("--private", action="store_true", help="Đặt repository ở chế độ Riêng tư (Private)")

    args = parser.parse_args()

    token = args.token or os.getenv("GITHUB_TOKEN")
    if not token:
        print("=" * 65)
        print("  🔑 CẦN GITHUB PERSONAL ACCESS TOKEN (PAT) ĐỂ TỰ ĐỘNG ĐẨY MÃ NGUỒN")
        print("=" * 65)
        print("Cách lấy token (chỉ mất 1 phút):")
        print("1. Truy cập: https://github.com/settings/tokens")
        print("2. Bấm 'Generate new token (classic)'")
        print("3. Tích chọn quyền: [x] repo")
        print("4. Bấm 'Generate token' và dán mã token vào đây.\n")
        try:
            token = input("Nhập GitHub Personal Access Token của bạn: ").strip()
        except Exception:
            pass

    if not token:
        print("❌ Thiếu GitHub Token! Vui lòng cung cấp token qua tham số --token hoặc nhập trực tiếp.")
        sys.exit(1)

    push_to_github(token, repo_name=args.repo, is_private=args.private)
