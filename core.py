import os
import json
import hashlib
import shutil
from datetime import datetime

class VersionControl:
    def __init__(self, work_dir):
        self.work_dir = os.path.abspath(work_dir)
        self.vcs_dir = os.path.join(self.work_dir, '.vcs')
        self.versions_dir = os.path.join(self.vcs_dir, 'versions')
        self.manifest_path = os.path.join(self.vcs_dir, 'manifest.json')
        self.cache_path = os.path.join(self.vcs_dir, 'cache.json')
        self.exclude = ['.vcs', '.git', 'node_modules', '__pycache__', '*.tmp', '*.log']
        self._init_vcs()

    def _init_vcs(self):
        os.makedirs(self.vcs_dir, exist_ok=True)
        os.makedirs(self.versions_dir, exist_ok=True)
        if not os.path.exists(self.manifest_path):
            with open(self.manifest_path, 'w', encoding='utf-8') as f:
                json.dump({'versions': [], 'next_version': 1}, f, indent=2)
        if not os.path.exists(self.cache_path):
            with open(self.cache_path, 'w', encoding='utf-8') as f:
                json.dump({}, f, indent=2)

    def _is_excluded(self, path):
        rel_path = os.path.relpath(path, self.work_dir)
        for ex in self.exclude:
            if ex.startswith('*'):
                if rel_path.endswith(ex[1:]):
                    return True
            else:
                if rel_path.startswith(ex) or ex in rel_path.split(os.sep):
                    return True
        return False

    def _get_file_hash(self, file_path):
        hash_md5 = hashlib.md5()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except:
            return None

    def scan_files(self):
        files = {}
        for root, _, filenames in os.walk(self.work_dir):
            for filename in filenames:
                full_path = os.path.join(root, filename)
                if self._is_excluded(full_path):
                    continue
                rel_path = os.path.relpath(full_path, self.work_dir)
                file_hash = self._get_file_hash(full_path)
                if file_hash:
                    files[rel_path] = {
                        'hash': file_hash,
                        'mtime': os.path.getmtime(full_path),
                        'size': os.path.getsize(full_path)
                    }
        return files

    def get_diff(self):
        with open(self.cache_path, 'r', encoding='utf-8') as f:
            old_cache = json.load(f)
        current_files = self.scan_files()
        diff = {
            'modified': [],
            'added': [],
            'deleted': [],
            'unchanged': []
        }
        for path, info in current_files.items():
            if path not in old_cache:
                diff['added'].append(path)
            elif info['hash'] != old_cache[path]['hash']:
                diff['modified'].append(path)
            else:
                diff['unchanged'].append(path)
        for path in old_cache:
            if path not in current_files:
                diff['deleted'].append(path)
        return diff, current_files

    def create_archive(self, description=""):
        diff, current_files = self.get_diff()
        total_changes = len(diff['modified']) + len(diff['added']) + len(diff['deleted'])
        if total_changes == 0:
            return None, "没有文件变更，无需存档"
        
        with open(self.manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
        
        version = manifest['next_version']
        version_dir = os.path.join(self.versions_dir, str(version))
        os.makedirs(version_dir, exist_ok=True)

        for path in current_files:
            src = os.path.join(self.work_dir, path)
            dest = os.path.join(version_dir, path)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            try:
                if os.name == 'nt':
                    shutil.copy2(src, dest)
                else:
                    os.link(src, dest)
            except:
                shutil.copy2(src, dest)

        version_info = {
            'version': version,
            'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'description': description,
            'diff': diff,
            'files': current_files
        }
        manifest['versions'].append(version_info)
        manifest['next_version'] += 1

        with open(self.manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        with open(self.cache_path, 'w', encoding='utf-8') as f:
            json.dump(current_files, f, indent=2)
        
        return version_info, f"版本 {version} 存档成功，共 {total_changes} 个变更"

    def get_versions(self):
        with open(self.manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
        return sorted(manifest['versions'], key=lambda x: x['version'], reverse=True)

    def restore_version(self, version):
        with open(self.manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
        version_info = next((v for v in manifest['versions'] if v['version'] == version), None)
        if not version_info:
            return False, "版本不存在"
        
        version_dir = os.path.join(self.versions_dir, str(version))
        for root, _, filenames in os.walk(self.work_dir):
            for filename in filenames:
                full_path = os.path.join(root, filename)
                if not self._is_excluded(full_path):
                    os.remove(full_path)
        
        for path in version_info['files']:
            src = os.path.join(version_dir, path)
            dest = os.path.join(self.work_dir, path)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(src, dest)
        
        with open(self.cache_path, 'w', encoding='utf-8') as f:
            json.dump(version_info['files'], f, indent=2)
        
        return True, f"版本 {version} 恢复成功"