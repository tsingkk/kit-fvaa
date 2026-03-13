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
                json.dump({'versions': [], 'next_version': 1, 'tags': {}, 'operation_log': []}, f, indent=2)
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

        # 获取上一个版本，复用未修改文件的硬链接
        prev_version = manifest['versions'][-1] if manifest['versions'] else None
        for path, info in current_files.items():
            dest = os.path.join(version_dir, path)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            # 仅在存档目录内部使用硬链接：优先链接上一个版本的相同文件
            linked = False
            if prev_version and path in prev_version['files'] and prev_version['files'][path]['hash'] == info['hash']:
                try:
                    prev_path = os.path.join(self.versions_dir, str(prev_version['version']), path)
                    os.link(prev_path, dest)
                    linked = True
                except:
                    pass
            # 存档和工作目录之间永远使用复制，禁止硬链接，避免修改当前文件影响存档
            if not linked:
                src = os.path.join(self.work_dir, path)
                shutil.copy2(src, dest)

        version_info = {
            'version': version,
            'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'description': description,
            'diff': diff,
            'files': current_files,
            'tags': []
        }
        manifest['versions'].append(version_info)
        manifest['next_version'] += 1

        with open(self.manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        with open(self.cache_path, 'w', encoding='utf-8') as f:
            json.dump(current_files, f, indent=2)
        
        # 记录操作历史
        self.record_operation('archive', version)
        
        return version_info, f"版本 {version} 存档成功，共 {total_changes} 个变更"

    def record_operation(self, op_type, version):
        """记录操作历史"""
        with open(self.manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
        op_text = f"存档<版本{version}>" if op_type == 'archive' else f"恢复<版本{version}>"
        log_item = {
            'time': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'op': op_text
        }
        # 最新操作插入到最前面
        manifest['operation_log'].insert(0, log_item)
        with open(self.manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
    
    def get_operation_log(self):
        """获取操作历史"""
        with open(self.manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
        return manifest.get('operation_log', [])

    def add_tag(self, version, tag_name):
        """给指定版本添加标签"""
        with open(self.manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
        # 标签不能重复
        if tag_name in manifest['tags']:
            return False, "标签已存在"
        # 查找对应版本
        version_info = next((v for v in manifest['versions'] if v['version'] == version), None)
        if not version_info:
            return False, "版本不存在"
        # 添加标签
        manifest['tags'][tag_name] = version
        if 'tags' not in version_info:
            version_info['tags'] = []
        version_info['tags'].append(tag_name)
        # 保存
        with open(self.manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        return True, f"标签 {tag_name} 添加成功"

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
        # 先删除当前所有非排除文件
        deleted_count = 0
        for root, _, filenames in os.walk(self.work_dir, topdown=False):
            for filename in filenames:
                full_path = os.path.join(root, filename)
                if not self._is_excluded(full_path):
                    try:
                        os.remove(full_path)
                        deleted_count +=1
                    except:
                        return False, f"删除文件失败：{full_path}，请关闭占用该文件的程序后重试"
            # 删除空文件夹
            try:
                if not os.listdir(root) and not self._is_excluded(root):
                    os.rmdir(root)
            except:
                pass
        
        # 复制所有版本文件到工作目录
        restored_count = 0
        for path in version_info['files']:
            src = os.path.join(version_dir, path)
            dest = os.path.join(self.work_dir, path)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            try:
                shutil.copy2(src, dest)
                restored_count +=1
            except Exception as e:
                return False, f"恢复文件失败：{path}，错误：{str(e)}"
        
        with open(self.cache_path, 'w', encoding='utf-8') as f:
            json.dump(version_info['files'], f, indent=2)
        
        # 记录操作历史
        self.record_operation('restore', version)
        
        return True, f"版本 {version} 恢复成功，共恢复 {restored_count} 个文件"