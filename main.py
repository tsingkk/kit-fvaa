import ttkbootstrap as ttk
import tkinter as tk
from tkinter import filedialog, messagebox, Toplevel, Text, Scrollbar
from tkhtmlview import HTMLLabel
import markdown
import os
from core import VersionControl
import threading
import time

class VersionControlApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Kit文件存档助手")
        self.root.geometry("1100x760")
        self.root.minsize(1100, 760)
        
        # 自定义高亮滚动条样式
        style = ttk.Style()
        style.configure("Custom.Vertical.TScrollbar", 
                        background="#e0e0e0", 
                        troughcolor="#888888",
                        bordercolor="#2b2b2b",
                        arrowcolor="#ffffff",
                        gripcount=0)
        style.configure("Custom.Horizontal.TScrollbar", 
                        background="#e0e0e0", 
                        troughcolor="#888888",
                        bordercolor="#2b2b2b",
                        arrowcolor="#ffffff",
                        gripcount=0)
        style.map("Custom.Vertical.TScrollbar",
                  background=[('active', '#f0f0f0'), ('pressed', '#cccccc')])
        style.map("Custom.Horizontal.TScrollbar",
                  background=[('active', '#f0f0f0'), ('pressed', '#cccccc')])
        
        self.vc = None
        self.work_dir = ""
        self.monitoring = False
        
        # 标题
        title_label = ttk.Label(root, text="Kit文件存档助手", font=("微软雅黑", 20, "bold"), bootstyle="info")
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
        
        self.archive_desc = ""
        self.desc_btn = ttk.Button(btn_frame, text="编辑存档说明", command=self.show_archive_input, bootstyle="secondary", width=12)
        self.desc_btn.pack(side="left", padx=2)
        
        self.archive_btn = ttk.Button(btn_frame, text="一键存档", command=self.create_archive, bootstyle="success", width=8)
        self.archive_btn.pack(side="left", padx=2)
        
        self.restore_btn = ttk.Button(btn_frame, text="恢复版本", command=self.restore_version, bootstyle="warning", width=8)
        self.restore_btn.pack(side="left", padx=2)
        
        ttk.Label(btn_frame, text="标签:").pack(side="left", padx=2)
        self.tag_entry = ttk.Entry(btn_frame, width=10)
        self.tag_entry.pack(side="left", padx=2)
        self.tag_btn = ttk.Button(btn_frame, text="添加标签", command=self.add_tag, bootstyle="info", width=8)
        self.tag_btn.pack(side="left", padx=2)
        
        # 消息提示
        self.msg_label = ttk.Label(root, text="", bootstyle="warning")
        self.msg_label.pack(pady=2, fill="x", padx=10)
        
        # 状态摘要
        self.summary_label = ttk.Label(root, text="")
        self.summary_label.pack(pady=2, fill="x", padx=10)
        
        # 分割面板
        paned = ttk.Panedwindow(root, orient="horizontal")
        paned.pack(pady=10, fill="both", expand=True, padx=10)
        
        # 操作历史面板
        op_frame = ttk.Frame(paned)
        paned.add(op_frame, weight=2)
        
        ttk.Label(op_frame, text="操作历史", font=("微软雅黑", 14, "bold")).pack(pady=5)
        op_inner_frame = ttk.Frame(op_frame)
        op_inner_frame.pack(fill="both", expand=True)
        # 先创建列表控件
        self.op_list = tk.Listbox(op_inner_frame, font=("微软雅黑", 11), bg="#3c3f41", fg="#f0f0f0", selectbackground="#4682b4")
        # 横向+竖向滚动条（高亮样式）
        op_yscroll = ttk.Scrollbar(op_inner_frame, orient="vertical", command=self.op_list.yview, style="Custom.Vertical.TScrollbar")
        op_xscroll = ttk.Scrollbar(op_inner_frame, orient="horizontal", command=self.op_list.xview, style="Custom.Horizontal.TScrollbar")
        # 绑定滚动
        self.op_list.configure(yscrollcommand=op_yscroll.set, xscrollcommand=op_xscroll.set)
        self.op_list.grid(row=0, column=0, sticky="nsew")
        op_yscroll.grid(row=0, column=1, sticky="ns")
        op_xscroll.grid(row=1, column=0, sticky="ew")
        op_inner_frame.grid_rowconfigure(0, weight=1)
        op_inner_frame.grid_columnconfigure(0, weight=1)
        
        # 文件状态面板
        status_frame = ttk.Frame(paned)
        paned.add(status_frame, weight=4)
        
        ttk.Label(status_frame, text="文件状态", font=("微软雅黑", 14, "bold")).pack(pady=5)
        status_inner_frame = ttk.Frame(status_frame)
        status_inner_frame.pack(fill="both", expand=True)
        # 先创建树控件
        self.status_tree = ttk.Treeview(status_inner_frame, columns=("status", "path"), show="headings", height=25, bootstyle="dark")
        self.status_tree.heading("status", text="状态")
        self.status_tree.heading("path", text="文件路径")
        self.status_tree.column("status", width=80, anchor="center", stretch=False)
        self.status_tree.column("path", width=600, stretch=False)
        # 横向+竖向滚动条（高亮样式）
        status_yscroll = ttk.Scrollbar(status_inner_frame, orient="vertical", command=self.status_tree.yview, style="Custom.Vertical.TScrollbar")
        status_xscroll = ttk.Scrollbar(status_inner_frame, orient="horizontal", command=self.status_tree.xview, style="Custom.Horizontal.TScrollbar")
        # 绑定滚动
        self.status_tree.configure(yscrollcommand=status_yscroll.set, xscrollcommand=status_xscroll.set)
        self.status_tree.grid(row=0, column=0, sticky="nsew")
        status_yscroll.grid(row=0, column=1, sticky="ns")
        status_xscroll.grid(row=1, column=0, sticky="ew")
        status_inner_frame.grid_rowconfigure(0, weight=1)
        status_inner_frame.grid_columnconfigure(0, weight=1)
        
        # 版本历史面板
        version_frame = ttk.Frame(paned)
        paned.add(version_frame, weight=5)
        
        ttk.Label(version_frame, text="版本历史", font=("微软雅黑", 14, "bold")).pack(pady=5)
        version_inner_frame = ttk.Frame(version_frame)
        version_inner_frame.pack(fill="both", expand=True)
        # 先创建树控件
        self.version_tree = ttk.Treeview(version_inner_frame, columns=("version", "time", "desc", "tags"), show="headings", height=25, bootstyle="dark")
        self.version_tree.heading("version", text="版本号", anchor="center")
        self.version_tree.heading("time", text="时间", anchor="center")
        self.version_tree.heading("desc", text="说明", anchor="center")
        self.version_tree.heading("tags", text="标签", anchor="center")
        self.version_tree.column("version", width=60, anchor="center", stretch=False)
        self.version_tree.column("time", width=130, anchor="center", stretch=False)
        self.version_tree.column("desc", width=120, anchor="center", stretch=False)
        self.version_tree.column("tags", width=80, anchor="center", stretch=False)
        # 横向+竖向滚动条（高亮样式）
        version_yscroll = ttk.Scrollbar(version_inner_frame, orient="vertical", command=self.version_tree.yview, style="Custom.Vertical.TScrollbar")
        version_xscroll = ttk.Scrollbar(version_inner_frame, orient="horizontal", command=self.version_tree.xview, style="Custom.Horizontal.TScrollbar")
        # 绑定滚动
        self.version_tree.configure(yscrollcommand=version_yscroll.set, xscrollcommand=version_xscroll.set)
        self.version_tree.grid(row=0, column=0, sticky="nsew")
        version_yscroll.grid(row=0, column=1, sticky="ns")
        version_xscroll.grid(row=1, column=0, sticky="ew")
        version_inner_frame.grid_rowconfigure(0, weight=1)
        version_inner_frame.grid_columnconfigure(0, weight=1)
        self.version_tree.bind('<ButtonRelease-1>', self.show_version_desc)
        
        self.status_tags = {
            'modified': ('修改', '#ffc107'),
            'added': ('新增', '#28a745'),
            'deleted': ('删除', '#dc3545'),
            'unchanged': ('不变', '#6c757d')
        }
        for tag, (_, color) in self.status_tags.items():
            self.status_tree.tag_configure(tag, foreground=color)
    
    def show_archive_input(self):
        """弹出存档说明编辑窗口"""
        win = Toplevel(self.root)
        win.title("编辑存档说明")
        win.geometry("600x400")
        win.transient(self.root)
        
        text = Text(win, wrap=tk.WORD, font=("微软雅黑", 12))
        scroll = Scrollbar(win, command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.insert("end", self.archive_desc)
        
        text.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        scroll.pack(side="right", fill="y", pady=5)
        
        btn_frame = ttk.Frame(win)
        btn_frame.pack(fill="x", pady=5, padx=5)
        
        def save_desc():
            self.archive_desc = text.get("1.0", "end-1c")
            win.destroy()
            self.msg_label.config(text="存档说明已保存")
        
        def cancel():
            win.destroy()
        
        def on_close():
            if messagebox.askyesno("保存确认", "是否保存当前编辑的存档说明？"):
                save_desc()
            else:
                cancel()
        
        ttk.Button(btn_frame, text="保存", command=save_desc, bootstyle="primary", width=10).pack(side="right", padx=5)
        ttk.Button(btn_frame, text="取消", command=cancel, bootstyle="secondary", width=10).pack(side="right", padx=5)
        win.protocol("WM_DELETE_WINDOW", on_close)
    
    def show_version_desc(self, event):
        """点击版本查看说明"""
        item = self.version_tree.identify_row(event.y)
        if not item:
            return
        col = self.version_tree.identify_column(event.x)
        if col != "#3": # 仅点击说明列才触发
            return
        version_data = self.version_tree.item(item)
        desc = version_data['tags'][0] if version_data['tags'] else "无说明"
        
        win = Toplevel(self.root)
        win.title(f"版本 {version_data['values'][0]} 存档说明")
        win.geometry("600x400")
        win.transient(self.root)
        
        # 渲染markdown格式
        html = markdown.markdown(desc, extensions=['tables', 'fenced_code', 'nl2br'])
        html_view = HTMLLabel(win, html=html)
        html_view.fit_height()
        html_view.pack(fill="both", expand=True, padx=5, pady=5)

    def select_dir(self):
        dir_path = filedialog.askdirectory()
        if dir_path:
            self.work_dir = dir_path
            self.dir_entry.delete(0, "end")
            self.dir_entry.insert(0, dir_path)
            self.vc = VersionControl(dir_path)
            self.archive_desc = ""
            self.refresh_status()
            self.refresh_versions()
            self.refresh_operation_log()

    def refresh_operation_log(self):
        """刷新操作历史列表"""
        if not self.vc:
            return
        self.op_list.delete(0, "end")
        logs = self.vc.get_operation_log()
        for idx, log in enumerate(logs):
            tag = "archive" if "存档" in log['op'] else "restore"
            self.op_list.insert("end", f"{log['time']} {log['op']}")
            self.op_list.itemconfig(idx, {'bg': '#2d5033' if tag == 'archive' else '#5a4a20'})
    
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
            desc = v['description'] or "无说明"
            show_desc = "点击查看" if desc.strip() else "无说明"
            self.version_tree.insert("", "end", values=(v['version'], v['time'], show_desc, tags), tags=(desc,))
    
    def create_archive(self):
        if not self.vc:
            self.msg_label.config(text="请先选择工作目录")
            return
        desc = self.archive_desc
        version, msg = self.vc.create_archive(desc)
        self.msg_label.config(text=msg)
        if version:
            self.refresh_versions()
            self.refresh_status()
            self.refresh_operation_log()
            self.archive_desc = ""
    
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
            self.refresh_operation_log()
    
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
    app = ttk.Window(themename="cyborg", title="Kit文件存档助手")
    VersionControlApp(app)
    app.mainloop()