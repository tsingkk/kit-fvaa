import os
import json
import hashlib
import shutil
from datetime import datetime

class VersionControl:
    def __init__(self, work_dir):
        self.work_dir = os.path.abspath(work_dir)
        # 兼容性迁移：如果存在旧的 .vcs 目录，则将其重命名为 .fvaa
        old_fvaa_dir = os.path.join(self.work_dir, '.vcs')
        new_fvaa_dir = os.path.join(self.work_dir, '.fvaa')
        if os.path.exists(old_fvaa_dir) and not os.path.exists(new_fvaa_dir):
            try:
                os.rename(old_fvaa_dir, new_fvaa_dir)
            except:
                pass
        
        self.fvaa_dir = new_fvaa_dir
        self.versions_dir = os.path.join(self.fvaa_dir, 'versions')
        self.manifest_path = os.path.join(self.fvaa_dir, 'manifest.json')
        self.cache_path = os.path.join(self.fvaa_dir, 'cache.json')
        self.default_exclude = ['.fvaa', '.git', 'node_modules', '__pycache__', '*.tmp', '*.log']
        self._init_fvaa()

    def _init_fvaa(self):
        os.makedirs(self.fvaa_dir, exist_ok=True)
        os.makedirs(self.versions_dir, exist_ok=True)
        if not os.path.exists(self.manifest_path):
            with open(self.manifest_path, 'w', encoding='utf-8') as f:
                json.dump({'versions': [], 'next_version': 1, 'tags': {}, 'operation_log': [], 'pending_desc': ''}, f, indent=2, ensure_ascii=False)
        if not os.path.exists(self.cache_path):
            with open(self.cache_path, 'w', encoding='utf-8') as f:
                json.dump({}, f, indent=2)

    def get_pending_desc(self):
        """获取暂存的存档说明"""
        try:
            with open(self.manifest_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('pending_desc', '')
        except:
            return ''

    def save_pending_desc(self, desc):
        """保存暂存的存档说明"""
        try:
            with open(self.manifest_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            data['pending_desc'] = desc
            with open(self.manifest_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except:
            return False

    def get_excludes(self):
        excludes = list(self.default_exclude)
        ignore_file = os.path.join(self.fvaa_dir, '.fvaaignore')
        if os.path.exists(ignore_file):
            try:
                with open(ignore_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            excludes.append(line)
            except:
                pass
        return excludes

    def _is_excluded(self, path):
        rel_path = os.path.relpath(path, self.work_dir)
        # Normalize slashes for generic matching
        rel_path_norm = rel_path.replace('\\', '/')
        excludes = self.get_excludes()
        for ex in excludes:
            ex_norm = ex.replace('\\', '/').rstrip('/') # Remove trailing slash for matching
            if ex_norm.startswith('*'):
                if rel_path_norm.endswith(ex_norm[1:]):
                    return True
            else:
                if rel_path_norm.startswith(ex_norm + '/') or rel_path_norm == ex_norm or ex_norm in rel_path_norm.split('/'):
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
        for root, dirs, filenames in os.walk(self.work_dir):
            # Prune excluded directories to avoid unnecessary recursion
            dirs[:] = [d for d in dirs if not self._is_excluded(os.path.join(root, d))]
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
                # Do not report as deleted if it's currently excluded
                if not self._is_excluded(os.path.join(self.work_dir, path)):
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
        # 先删除当前所有非排除文件，优化目录遍历避免进入巨大的忽略目录
        deleted_count = 0
        dirs_to_check = []
        for root, dirs, filenames in os.walk(self.work_dir, topdown=True):
            # Prune excluded directories
            dirs[:] = [d for d in dirs if not self._is_excluded(os.path.join(root, d))]
            dirs_to_check.append(root)
            for filename in filenames:
                full_path = os.path.join(root, filename)
                if not self._is_excluded(full_path):
                    try:
                        os.remove(full_path)
                        deleted_count +=1
                    except:
                        return False, f"删除文件失败：{full_path}，请关闭占用该文件的程序后重试"
        
        # 倒序删除空文件夹
        for d in reversed(dirs_to_check):
            try:
                if d != self.work_dir and not os.listdir(d) and not self._is_excluded(d):
                    os.rmdir(d)
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