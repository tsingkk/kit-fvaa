import ttkbootstrap as ttk
from tkinter import filedialog, messagebox
import os
from core import VersionControl
import threading
import time

class VersionControlApp:
    def __init__(self, root):
        self.root = root
        self.root.title("文件版本管理工具")
        self.root.geometry("1000x700")
        
        self.vc = None
        self.work_dir = ""
        self.monitoring = False
        
        # 标题
        title_label = ttk.Label(root, text="文件版本管理工具", font=("微软雅黑", 20, "bold"), bootstyle="info")
        title_label.pack(pady=10)
        
        # 工作目录选择
        dir_frame = ttk.Frame(root)
        dir_frame.pack(pady=5, fill="x", padx=10)
        
        ttk.Label(dir_frame, text="工作目录:").pack(side="left", padx=5)
        self.dir_entry = ttk.Entry(dir_frame, width=80)
        self.dir_entry.pack(side="left", padx=5, fill="x", expand=True)
        ttk.Button(dir_frame, text="选择目录", command=self.select_dir, bootstyle="primary").pack(side="left", padx=5)
        
        # 操作按钮栏
        btn_frame = ttk.Frame(root)
        btn_frame.pack(pady=5, fill="x", padx=10)
        
        self.refresh_btn = ttk.Button(btn_frame, text="刷新状态", command=self.refresh_status, bootstyle="secondary")
        self.refresh_btn.pack(side="left", padx=5)
        
        self.monitor_btn = ttk.Button(btn_frame, text="开始监视", command=self.toggle_monitor, bootstyle="secondary")
        self.monitor_btn.pack(side="left", padx=5)
        
        ttk.Label(btn_frame, text="存档说明:").pack(side="left", padx=5)
        self.desc_entry = ttk.Entry(btn_frame, width=30)
        self.desc_entry.pack(side="left", padx=5)
        
        self.archive_btn = ttk.Button(btn_frame, text="一键存档", command=self.create_archive, bootstyle="success")
        self.archive_btn.pack(side="left", padx=5)
        
        self.restore_btn = ttk.Button(btn_frame, text="恢复选中版本", command=self.restore_version, bootstyle="warning")
        self.restore_btn.pack(side="left", padx=5)
        
        ttk.Label(btn_frame, text="添加标签:").pack(side="left", padx=5)
        self.tag_entry = ttk.Entry(btn_frame, width=15)
        self.tag_entry.pack(side="left", padx=5)
        self.tag_btn = ttk.Button(btn_frame, text="添加标签", command=self.add_tag, bootstyle="info")
        self.tag_btn.pack(side="left", padx=5)
        
        # 消息提示
        self.msg_label = ttk.Label(root, text="", bootstyle="warning")
        self.msg_label.pack(pady=2, fill="x", padx=10)
        
        # 状态摘要
        self.summary_label = ttk.Label(root, text="")
        self.summary_label.pack(pady=2, fill="x", padx=10)
        
        # 分割面板
        paned = ttk.Panedwindow(root, orient="horizontal")
        paned.pack(pady=10, fill="both", expand=True, padx=10)
        
        # 文件状态面板
        status_frame = ttk.Frame(paned)
        paned.add(status_frame, weight=6)
        
        ttk.Label(status_frame, text="文件状态", font=("微软雅黑", 14, "bold")).pack(pady=5)
        self.status_tree = ttk.Treeview(status_frame, columns=("status", "path"), show="headings", height=25, bootstyle="dark")
        self.status_tree.heading("status", text="状态")
        self.status_tree.heading("path", text="文件路径")
        self.status_tree.column("status", width=80, anchor="center")
        self.status_tree.column("path", width=500)
        self.status_tree.pack(fill="both", expand=True)
        
        # 版本历史面板
        version_frame = ttk.Frame(paned)
        paned.add(version_frame, weight=4)
        
        ttk.Label(version_frame, text="版本历史", font=("微软雅黑", 14, "bold")).pack(pady=5)
        self.version_tree = ttk.Treeview(version_frame, columns=("version", "time", "desc", "tags"), show="headings", height=25, bootstyle="dark")
        self.version_tree.heading("version", text="版本号", anchor="center")
        self.version_tree.heading("time", text="时间", anchor="center")
        self.version_tree.heading("desc", text="说明", anchor="center")
        self.version_tree.heading("tags", text="标签", anchor="center")
        self.version_tree.column("version", width=60, anchor="center")
        self.version_tree.column("time", width=150, anchor="center")
        self.version_tree.column("desc", width=140)
        self.version_tree.column("tags", width=80, anchor="center")
        self.version_tree.pack(fill="both", expand=True)
        
        self.status_tags = {
            'modified': ('修改', '#ffc107'),
            'added': ('新增', '#28a745'),
            'deleted': ('删除', '#dc3545'),
            'unchanged': ('不变', '#6c757d')
        }
        for tag, (_, color) in self.status_tags.items():
            self.status_tree.tag_configure(tag, foreground=color)
    
    def select_dir(self):
        dir_path = filedialog.askdirectory()
        if dir_path:
            self.work_dir = dir_path
            self.dir_entry.delete(0, "end")
            self.dir_entry.insert(0, dir_path)
            self.vc = VersionControl(dir_path)
            self.refresh_status()
            self.refresh_versions()
    
    def refresh_status(self):
        if not self.vc:
            return
        for item in self.status_tree.get_children():
            self.status_tree.delete(item)
        
        diff, _ = self.vc.get_diff()
        total_changes = 0
        for status, paths in diff.items():
            total_changes += len(paths) if status != 'unchanged' else 0
            for path in paths:
                self.status_tree.insert("", "end", values=(self.status_tags[status][0], path), tags=(status,))
        
        self.summary_label.config(text=f"共 {total_changes} 个变更，{len(diff['unchanged'])} 个文件未变更")
    
    def refresh_versions(self):
        if not self.vc:
            return
        for item in self.version_tree.get_children():
            self.version_tree.delete(item)
        
        versions = self.vc.get_versions()
        for v in versions:
            tags = ','.join(v.get('tags', []))
            self.version_tree.insert("", "end", values=(v['version'], v['time'], v['description'] or '无说明', tags))
    
    def create_archive(self):
        if not self.vc:
            self.msg_label.config(text="请先选择工作目录")
            return
        desc = self.desc_entry.get()
        version, msg = self.vc.create_archive(desc)
        self.msg_label.config(text=msg)
        if version:
            self.refresh_versions()
            self.refresh_status()
            self.desc_entry.delete(0, "end")
    
    def restore_version(self):
        if not self.vc:
            self.msg_label.config(text="请先选择工作目录")
            return
        selected = self.version_tree.selection()
        if not selected:
            self.msg_label.config(text="请先选择要恢复的版本")
            return
        version_num = int(self.version_tree.item(selected[0])['values'][0])
        confirm = messagebox.askyesno("确认恢复", f"确定要恢复到版本 {version_num} 吗？当前文件将被覆盖！")
        if confirm:
            success, msg = self.vc.restore_version(version_num)
            self.msg_label.config(text=msg)
            self.refresh_status()
    
    def add_tag(self):
        if not self.vc:
            self.msg_label.config(text="请先选择工作目录")
            return
        selected = self.version_tree.selection()
        if not selected:
            self.msg_label.config(text="请先选择要打标签的版本")
            return
        tag_name = self.tag_entry.get().strip()
        if not tag_name:
            self.msg_label.config(text="请输入标签名称")
            return
        version_num = int(self.version_tree.item(selected[0])['values'][0])
        success, msg = self.vc.add_tag(version_num, tag_name)
        self.msg_label.config(text=msg)
        if success:
            self.refresh_versions()
            self.tag_entry.delete(0, "end")
    
    def monitor_thread(self):
        while self.monitoring:
            self.root.after(0, self.refresh_status)
            time.sleep(2)
    
    def toggle_monitor(self):
        if not self.vc:
            self.msg_label.config(text="请先选择工作目录")
            return
        self.monitoring = not self.monitoring
        if self.monitoring:
            self.monitor_btn.config(text="停止监视")
            threading.Thread(target=self.monitor_thread, daemon=True).start()
        else:
            self.monitor_btn.config(text="开始监视")

if __name__ == "__main__":
    app = ttk.Window(themename="cyborg", title="文件版本管理工具")
    VersionControlApp(app)
    app.mainloop()