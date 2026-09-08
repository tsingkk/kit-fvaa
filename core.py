import os
import json
import re
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
            self._save_manifest(self._default_manifest())
        else:
            self._migrate_manifest()
        if not os.path.exists(self.cache_path):
            with open(self.cache_path, 'w', encoding='utf-8') as f:
                json.dump({}, f, indent=2)

    @staticmethod
    def _default_manifest():
        return {
            'branches': {
                'main': {'versions': [], 'next_version': 1, 'tags': {}, 'base_ref': None, 'created_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            },
            'current_branch': 'main',
            'operation_log': [],
            'pending_desc': '',
            'workdir_base': None
        }

    def _load_manifest(self):
        with open(self.manifest_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _save_manifest(self, manifest):
        with open(self.manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

    def _migrate_manifest(self):
        """将 v1（无分支）manifest 迁移为 v2 分支结构：所有历史数据归入 main 分支"""
        try:
            manifest = self._load_manifest()
        except:
            return
        if 'branches' in manifest:
            return
        main_data = {
            'versions': manifest.get('versions', []),
            'next_version': manifest.get('next_version', 1),
            'tags': manifest.get('tags', {}),
            'base_ref': None,
            'created_time': ''
        }
        new_manifest = {
            'branches': {'main': main_data},
            'current_branch': 'main',
            'operation_log': manifest.get('operation_log', []),
            'pending_desc': manifest.get('pending_desc', '')
        }
        for op in new_manifest['operation_log']:
            op['branch'] = 'main'
        # 版本目录由扁平结构 versions/N 迁移为 versions/main/N
        main_dir = os.path.join(self.versions_dir, 'main')
        os.makedirs(main_dir, exist_ok=True)
        for name in os.listdir(self.versions_dir):
            if name == 'main':
                continue
            src = os.path.join(self.versions_dir, name)
            if os.path.isdir(src):
                dest = os.path.join(main_dir, name)
                if not os.path.exists(dest):
                    try:
                        shutil.move(src, dest)
                    except:
                        pass
        self._save_manifest(new_manifest)

    def get_current_branch(self):
        """获取当前分支名称"""
        manifest = self._load_manifest()
        return manifest.get('current_branch', 'main')

    def has_changes(self):
        """判断工作目录相对最近一次状态是否存在变更文件"""
        try:
            diff, _ = self.get_diff()
        except:
            return True
        return bool(diff['modified'] or diff['added'] or diff['deleted'])

    def get_pending_desc(self):
        """获取暂存的存档说明"""
        try:
            manifest = self._load_manifest()
            return manifest.get('pending_desc', '')
        except:
            return ''

    def save_pending_desc(self, desc):
        """保存暂存的存档说明"""
        try:
            manifest = self._load_manifest()
            manifest['pending_desc'] = desc
            self._save_manifest(manifest)
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
        
        # 版本号按分支独立编制，仅在同一分支内递增
        branch = manifest['current_branch']
        branch_data = manifest['branches'][branch]
        version = branch_data['next_version']
        version_dir = os.path.join(self.versions_dir, branch, str(version))
        os.makedirs(version_dir, exist_ok=True)

        # 获取本分支上一个版本，复用未修改文件的硬链接
        prev_version = branch_data['versions'][-1] if branch_data['versions'] else None
        for path, info in current_files.items():
            dest = os.path.join(version_dir, path)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            # 仅在存档目录内部使用硬链接：优先链接上一个版本的相同文件
            linked = False
            if prev_version and path in prev_version['files'] and prev_version['files'][path]['hash'] == info['hash']:
                try:
                    prev_path = os.path.join(self.versions_dir, branch, str(prev_version['version']), path)
                    os.link(prev_path, dest)
                    linked = True
                except:
                    pass
            # 存档和工作目录之间永远使用复制，禁止硬链接，避免修改当前文件影响存档
            if not linked:
                src = os.path.join(self.work_dir, path)
                shutil.copy2(src, dest)

        # 本版本的继承来源：工作目录当前基于的版本快照（存档/恢复/切换分支时更新）
        if 'workdir_base' in manifest:
            parent = manifest['workdir_base']
        elif prev_version:
            # 旧 manifest 无该字段：回退推断为本分支上一版本
            parent = {'branch': branch, 'version': prev_version['version']}
        else:
            # 分支首个版本：继承分支创建时的基线
            parent = branch_data.get('base_ref')

        version_info = {
            'version': version,
            'branch': branch,
            'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'description': description,
            'diff': diff,
            'files': current_files,
            'tags': [],
            'parent': parent
        }
        branch_data['versions'].append(version_info)
        branch_data['next_version'] += 1
        # 存档后工作目录基于新建的版本
        manifest['workdir_base'] = {'branch': branch, 'version': version}

        with open(self.manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        with open(self.cache_path, 'w', encoding='utf-8') as f:
            json.dump(current_files, f, indent=2)
        
        # 记录操作历史
        self.record_operation('archive', version)
        
        return version_info, f"版本 {version} 存档成功，共 {total_changes} 个变更"

    def record_operation(self, op_type, version, branch=None):
        """记录操作历史（带分支标记，用于按分支过滤展示）"""
        manifest = self._load_manifest()
        if op_type == 'archive':
            op_text = f"存档<版本{version}>"
        elif op_type == 'restore':
            op_text = f"恢复<版本{version}>"
        elif op_type == 'create_branch':
            op_text = f"创建分支<{branch}>"
        elif op_type == 'switch_branch':
            op_text = f"切换分支<{branch}>"
        else:
            op_text = str(op_type)
        log_item = {
            'time': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'op': op_text,
            'branch': branch or manifest.get('current_branch', 'main')
        }
        # 最新操作插入到最前面
        manifest['operation_log'].insert(0, log_item)
        self._save_manifest(manifest)
    
    def get_operation_log(self, branch=None):
        """获取操作历史，仅返回指定分支（默认当前分支）的记录"""
        manifest = self._load_manifest()
        branch = branch or manifest.get('current_branch', 'main')
        logs = manifest.get('operation_log', [])
        # 旧版本记录无 branch 字段，视为 main 分支
        return [log for log in logs if log.get('branch', 'main') == branch]

    def tag_exists(self, tag_name):
        """判断标签在当前分支内是否已存在"""
        manifest = self._load_manifest()
        branch = manifest.get('current_branch', 'main')
        branch_data = manifest['branches'].get(branch)
        return bool(branch_data) and tag_name in branch_data.get('tags', {})

    def add_tag(self, version, tag_name):
        """给当前分支的指定版本添加标签"""
        manifest = self._load_manifest()
        branch = manifest.get('current_branch', 'main')
        branch_data = manifest['branches'][branch]
        # 标签在同一分支内不能重复
        if tag_name in branch_data['tags']:
            return False, "标签已存在"
        # 查找对应版本
        version_info = next((v for v in branch_data['versions'] if v['version'] == version), None)
        if not version_info:
            return False, "版本不存在"
        # 添加标签
        branch_data['tags'][tag_name] = version
        if 'tags' not in version_info:
            version_info['tags'] = []
        version_info['tags'].append(tag_name)
        # 保存
        self._save_manifest(manifest)
        return True, f"标签 {tag_name} 添加成功"

    def get_version_info(self, version):
        """获取当前分支指定版本的元数据，不存在时返回 None"""
        manifest = self._load_manifest()
        branch = manifest.get('current_branch', 'main')
        return next((v for v in manifest['branches'][branch]['versions'] if v['version'] == version), None)

    @staticmethod
    def _sanitize_filename_part(text):
        """替换文件名片段中的非法字符，避免重命名失败"""
        return re.sub(r'[\\/:*?"<>|]', '_', (text or '').strip())

    def _build_retrieved_name(self, orig_name, branch, version_info):
        """生成取回文件的重命名：<原文件名>-<分支名称>-<版本名称>-<归档日期>，保留原扩展名；
        版本名称：有标签时为 <版本号>-<第一个标签>，无标签时为 <版本号>"""
        stem, ext = os.path.splitext(orig_name)
        version = version_info['version']
        tags = version_info.get('tags') or []
        tag = self._sanitize_filename_part(tags[0]) if tags else ''
        version_name = f"{version}-{tag}" if tag else str(version)
        parts = [stem, self._sanitize_filename_part(branch), version_name]
        archive_date = (version_info.get('time') or '').strip().split(' ')[0]
        if archive_date:
            parts.append(archive_date)
        return '-'.join(parts) + ext

    def retrieve_files(self, version, rel_paths):
        """从当前分支指定版本的归档中取回文件：复制到工作目录根目录并重命名，归档内原文件保持不变。
        返回 (成功数量, 提示消息)"""
        manifest = self._load_manifest()
        branch = manifest.get('current_branch', 'main')
        version_info = next((v for v in manifest['branches'][branch]['versions'] if v['version'] == version), None)
        if not version_info:
            return 0, "版本不存在"
        version_dir = os.path.join(self.versions_dir, branch, str(version_info['version']))
        files_map = version_info.get('files', {})
        # 仅允许取回归档清单中实际存在的文件，防止路径穿越（兼容正/反斜杠写法）
        normalized = {os.path.normpath(k): k for k in files_map}
        requested = [normalized[os.path.normpath(p)] for p in (rel_paths or []) if os.path.normpath(p) in normalized]
        if not requested:
            return 0, "没有可取回的文件"
        success = 0
        failed = []
        for path in requested:
            src = os.path.join(version_dir, path)
            if not os.path.isfile(src):
                failed.append(path)
                continue
            orig_name = os.path.basename(path)
            new_name = self._build_retrieved_name(orig_name, branch, version_info)
            name_stem, name_ext = os.path.splitext(new_name)
            dest = os.path.join(self.work_dir, new_name)
            # 与工作目录现有文件重名时自动加序号
            counter = 1
            while os.path.exists(dest):
                dest = os.path.join(self.work_dir, f"{name_stem}-{counter}{name_ext}")
                counter += 1
            try:
                shutil.copy2(src, dest)
                success += 1
            except OSError as e:
                failed.append(f"{path}（{str(e) or type(e).__name__}）")
        msg = f"成功取回 {success} 个文件到工作目录"
        if failed:
            shown = '、'.join(failed[:3])
            more = '等' if len(failed) > 3 else ''
            msg += f"，{len(failed)} 个取回失败：{shown}{more}"
        return success, msg

    def get_versions(self):
        """获取当前分支的版本列表，按版本号倒序"""
        manifest = self._load_manifest()
        branch = manifest.get('current_branch', 'main')
        versions = manifest['branches'][branch]['versions']
        return sorted(versions, key=lambda x: x['version'], reverse=True)

    def _clear_workdir(self):
        """删除工作目录中所有未被排除的文件，返回 (删除数量, 失败文件路径或None)"""
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
                        return -1, full_path
        # 倒序删除空文件夹
        for d in reversed(dirs_to_check):
            try:
                if d != self.work_dir and not os.listdir(d) and not self._is_excluded(d):
                    os.rmdir(d)
            except:
                pass
        return deleted_count, None

    def _restore_snapshot(self, version_info, branch):
        """将指定分支的版本快照恢复到工作目录，返回 (success, msg, 文件映射)"""
        version_dir = os.path.join(self.versions_dir, branch, str(version_info['version']))
        # 先删除当前所有非排除文件，优化目录遍历避免进入巨大的忽略目录
        deleted_count, failed_path = self._clear_workdir()
        if deleted_count == -1:
            return False, f"删除文件失败：{failed_path}，请关闭占用该文件的程序后重试", None
        
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
                return False, f"恢复文件失败：{path}，错误：{str(e)}", None
        
        return True, f"共恢复 {restored_count} 个文件", version_info['files']

    def restore_version(self, version):
        manifest = self._load_manifest()
        branch = manifest.get('current_branch', 'main')
        version_info = next((v for v in manifest['branches'][branch]['versions'] if v['version'] == version), None)
        if not version_info:
            return False, "版本不存在"
        
        success, msg, files = self._restore_snapshot(version_info, branch)
        if not success:
            return False, msg
        
        with open(self.cache_path, 'w', encoding='utf-8') as f:
            json.dump(files, f, indent=2)
        
        # 恢复后工作目录基于被恢复的版本快照，之后的存档将继承该版本
        manifest['workdir_base'] = {'branch': branch, 'version': version}
        self._save_manifest(manifest)
        
        # 记录操作历史
        self.record_operation('restore', version)
        
        return True, f"版本 {version} 恢复成功，{msg}"

    def validate_branch_name(self, name):
        """校验分支名称，合法时返回 (True, 去除首尾空白后的名称)，否则返回 (False, 原因)"""
        name = (name or '').strip()
        if not name:
            return False, "分支名称不能为空"
        if len(name) > 50:
            return False, "分支名称过长（最多50个字符）"
        if name in ('.', '..') or any(c in name for c in '\\/:*?"<>|'):
            return False, '分支名称不能包含 \\ / : * ? " < > | 等字符'
        manifest = self._load_manifest()
        if name in manifest['branches']:
            return False, f"分支 {name} 已存在"
        return True, name

    def create_branch(self, name):
        """创建新分支：以当前分支最新归档为基线，版本号从1开始，创建后自动切换到新分支"""
        ok, result = self.validate_branch_name(name)
        if not ok:
            return False, result
        name = result
        if self.has_changes():
            return False, "创建新分支前需要先归档当前目录"
        
        manifest = self._load_manifest()
        cur_branch = manifest.get('current_branch', 'main')
        cur_versions = manifest['branches'][cur_branch]['versions']
        base_ref = {'branch': cur_branch, 'version': cur_versions[-1]['version']} if cur_versions else None
        manifest['branches'][name] = {
            'versions': [],
            'next_version': 1,
            'tags': {},
            'base_ref': base_ref,
            'created_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        manifest['current_branch'] = name
        self._save_manifest(manifest)
        
        # 记录操作历史（归属新分支）
        self.record_operation('create_branch', None, branch=name)
        
        return True, f"分支 {name} 创建成功，已切换至新分支"

    def switch_branch(self, name):
        """切换分支：工作目录恢复为该分支最新归档（尚未归档时恢复其创建时的基线快照）"""
        manifest = self._load_manifest()
        if name not in manifest['branches']:
            return False, f"分支 {name} 不存在"
        if name == manifest.get('current_branch', 'main'):
            return True, f"已位于分支 {name}"
        if self.has_changes():
            return False, "切换分支前需要先归档当前目录"
        
        target = manifest['branches'][name]
        versions = target['versions']
        if versions:
            latest = sorted(versions, key=lambda x: x['version'])[-1]
            success, msg, files = self._restore_snapshot(latest, name)
            if not success:
                return False, msg
            new_base = {'branch': name, 'version': latest['version']}
        else:
            # 尚未归档的分支：恢复创建时的基线快照
            files = {}
            base_ref = target.get('base_ref')
            base_info = None
            if base_ref:
                base_data = manifest['branches'].get(base_ref['branch'])
                if base_data:
                    base_info = next((v for v in base_data['versions'] if v['version'] == base_ref['version']), None)
            if base_info:
                success, msg, files = self._restore_snapshot(base_info, base_ref['branch'])
                if not success:
                    return False, msg
                new_base = dict(base_ref)
            else:
                # 无基线快照时清空工作目录
                deleted_count, failed_path = self._clear_workdir()
                if deleted_count == -1:
                    return False, f"删除文件失败：{failed_path}，请关闭占用该文件的程序后重试"
                new_base = None
        
        with open(self.cache_path, 'w', encoding='utf-8') as f:
            json.dump(files, f, indent=2)
        
        manifest['current_branch'] = name
        # 工作目录已恢复为该分支的状态，其基于的版本快照相应更新
        manifest['workdir_base'] = new_base
        self._save_manifest(manifest)
        
        # 记录操作历史（归属切换后的分支）
        self.record_operation('switch_branch', None, branch=name)
        
        return True, f"已切换到分支 {name}"

    def list_branches(self):
        """列出所有分支及其最后归档时间"""
        manifest = self._load_manifest()
        current = manifest.get('current_branch', 'main')
        result = []
        for name, data in manifest['branches'].items():
            versions = data.get('versions', [])
            last_time = sorted(versions, key=lambda x: x['version'])[-1]['time'] if versions else None
            result.append({
                'name': name,
                'last_archive_time': last_time,
                'version_count': len(versions),
                'is_current': name == current
            })
        return result

    def get_branch_graph(self):
        """获取全部分支的版本图谱数据（用于绘制分支历史图），各分支版本按版本号升序；
        每个版本带 parent（{'branch', 'version'} 或 None）表示其继承来源，
        旧数据无继承记录时按线性回退推断：分支首个版本继承分叉点，其余继承前一版本"""
        manifest = self._load_manifest()
        current = manifest.get('current_branch', 'main')
        branches = []
        for name, data in manifest['branches'].items():
            base_ref = data.get('base_ref')
            graph_versions = []
            prev_version = None
            for v in sorted(data.get('versions', []), key=lambda x: x['version']):
                parent = v.get('parent')
                if not parent:
                    parent = base_ref if prev_version is None else {'branch': name, 'version': prev_version}
                graph_versions.append({
                    'version': v['version'],
                    'time': v.get('time', ''),
                    'tags': list(v.get('tags', [])),
                    'description': v.get('description', '') or '',
                    'parent': parent
                })
                prev_version = v['version']
            branches.append({
                'name': name,
                'is_current': name == current,
                'base_ref': base_ref,
                'created_time': data.get('created_time', ''),
                'versions': graph_versions
            })
        return branches