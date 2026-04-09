import ttkbootstrap as ttk
import tkinter as tk
from tkinter import filedialog, messagebox, Toplevel, Text, Scrollbar
from tkhtmlview import HTMLLabel
import markdown
import os
import sys
from core import VersionControl
import threading
import time
import json
import win32gui
import win32api
import win32con

class VersionControlApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Kit文件存档助手")
        self.root.geometry("1600x850")
        self.root.minsize(1200, 760)
        
        if "__compiled__" in globals():
            application_path = os.path.dirname(sys.argv[0])
        elif getattr(sys, 'frozen', False):
            application_path = os.path.dirname(sys.executable)
        else:
            application_path = os.path.dirname(os.path.abspath(__file__))
            
        self.config_file = os.path.join(application_path, "fvaa_config.json")
        self.config = self.load_config()
        self.recent_dirs = self.config.get('recent_dirs', [])
        self.archive_desc = ""
        
        # 自定义高亮滚动条样式和按钮字体
        style = ttk.Style()
        style.configure("TButton", font=("微软雅黑", 11, "bold"))
        style.configure("Treeview", font=("微软雅黑", 12), rowheight=28)
        style.configure("dark.Treeview", font=("微软雅黑", 12), rowheight=28)
        style.configure("Treeview.Heading", font=("微软雅黑", 12, "bold"))
        style.configure("dark.Treeview.Heading", font=("微软雅黑", 12, "bold"))
        
        # Add light gray separator lines for headings
        style.configure("Treeview.Heading", borderwidth=1, relief="solid", bordercolor="#d3d3d3")
        style.configure("dark.Treeview.Heading", borderwidth=1, relief="solid", bordercolor="#d3d3d3")

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
        header_frame = ttk.Frame(root)
        header_frame.pack(fill="x", pady=10)
        title_label = ttk.Label(header_frame, text="Kit文件存档助手", font=("微软雅黑", 20, "bold"), bootstyle="info")
        title_label.pack()
        copyright_label = ttk.Label(header_frame, text="by tsingkk under GPLv3 License", font=("微软雅黑", 12), foreground="grey")
        copyright_label.place(relx=1.0, rely=0.5, anchor="e", x=-10)
        
        # 工作目录选择
        dir_frame = ttk.Frame(root)
        dir_frame.pack(pady=5, fill="x", padx=10)
        
        ttk.Label(dir_frame, text="工作目录:").pack(side="left", padx=5)
        self.dir_entry = ttk.Combobox(dir_frame, width=80, values=self.recent_dirs)
        self.dir_entry.pack(side="left", padx=5, fill="x", expand=True)
        self.dir_entry.bind("<<ComboboxSelected>>", self.on_combobox_select)
        self.dir_entry.bind("<Return>", self.on_combobox_select)
        ttk.Button(dir_frame, text="选择目录", command=self.select_dir, bootstyle="primary").pack(side="left", padx=5)
        
        # 操作按钮栏
        btn_frame = ttk.Frame(root)
        btn_frame.pack(pady=5, fill="x", padx=10)
        
        self.refresh_btn = ttk.Button(btn_frame, text="刷新状态", command=self.refresh_status, bootstyle="primary")
        self.refresh_btn.pack(side="left", padx=5)
        
        self.monitor_btn = ttk.Button(btn_frame, text="开始监视", command=self.toggle_monitor, bootstyle="success")
        self.monitor_btn.pack(side="left", padx=5)
        
        self.ignore_btn = ttk.Button(btn_frame, text="忽视文件", command=self.show_ignore_input, bootstyle="secondary")
        self.ignore_btn.pack(side="left", padx=5)
        
        self.desc_btn = ttk.Button(btn_frame, text="编辑存档说明", command=self.show_archive_input, bootstyle="info", width=12)
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

        self.minimize_to_tray_var = tk.BooleanVar(value=self.config.get('minimize_to_tray', False))
        self.tray_checkbox = ttk.Checkbutton(btn_frame, text="最小化至状态栏", variable=self.minimize_to_tray_var, bootstyle="info-round-toggle", command=self.save_config)
        self.tray_checkbox.pack(side="right", padx=10)
        
        self.tag_msg_label = ttk.Label(btn_frame, text="", bootstyle="danger", font=("微软雅黑", 10, "bold"))
        self.tag_msg_label.pack(side="left", padx=5)

        self.root.bind("<Unmap>", self.on_window_unmap)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close_app)
        self.tray_icon_created = False

        
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
        paned.add(op_frame, weight=3)
        
        ttk.Label(op_frame, text="操作历史", font=("微软雅黑", 14, "bold")).pack(pady=5)
        op_inner_frame = ttk.Frame(op_frame)
        op_inner_frame.pack(fill="both", expand=True)
        # 先创建列表控件
        self.op_list = tk.Listbox(op_inner_frame, font=("微软雅黑", 12), bg="#3c3f41", fg="#f0f0f0", selectbackground="#4682b4")
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
        paned.add(status_frame, weight=5)
        
        ttk.Label(status_frame, text="文件状态", font=("微软雅黑", 14, "bold")).pack(pady=5)
        status_inner_frame = ttk.Frame(status_frame)
        status_inner_frame.pack(fill="both", expand=True)
        # 先创建树控件
        self.status_tree = ttk.Treeview(status_inner_frame, columns=("status", "path"), show="headings", height=25, bootstyle="dark")
        self.status_tree.heading("status", text="状态")
        self.status_tree.heading("path", text="文件路径")
        self.status_tree.column("status", width=60, anchor="center", stretch=False)
        self.status_tree.column("path", width=380, stretch=True)
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
        paned.add(version_frame, weight=7)
        
        ttk.Label(version_frame, text="版本历史", font=("微软雅黑", 14, "bold")).pack(pady=5)
        version_inner_frame = ttk.Frame(version_frame)
        version_inner_frame.pack(fill="both", expand=True)
        # 先创建树控件
        self.version_tree = ttk.Treeview(version_inner_frame, columns=("version", "time", "desc", "tags"), show="headings", height=25, bootstyle="dark")
        self.version_tree.heading("version", text="版本号", anchor="center")
        self.version_tree.heading("time", text="时间", anchor="center")
        self.version_tree.heading("desc", text="说明", anchor="center")
        self.version_tree.heading("tags", text="标签", anchor="center")
        self.version_tree.column("version", width=80, anchor="center", stretch=False)
        self.version_tree.column("time", width=180, anchor="center", stretch=False)
        self.version_tree.column("desc", width=220, anchor="center", stretch=True)
        self.version_tree.column("tags", width=160, anchor="center", stretch=True)
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
        win.geometry("600x500")
        win.focus_set()
        win.resizable(True, True)
        
        # 顶部提示语
        hint_label = ttk.Label(win, text="请记录当前目录中的文件修改情况，一键存档时将与存档版本绑定，方便后期查阅！", bootstyle="info", wraplength=550)
        hint_label.pack(pady=(15, 5), padx=20, fill="x", side="top")

        # 底部按钮栏 (先pack side="bottom" 确保即使窗口缩小也始终可见)
        btn_frame = ttk.Frame(win)
        btn_frame.pack(fill="x", side="bottom", pady=15, padx=20)
        
        def save_desc():
            self.archive_desc = text.get("1.0", "end-1c")
            if self.vc:
                self.vc.save_pending_desc(self.archive_desc)
            win.destroy()
            self.msg_label.config(text="存档说明已保存")
        
        def cancel():
            win.destroy()
        
        def on_close():
            # 仅在点击右上角关闭(X)时提醒
            if messagebox.askyesno("保存确认", "是否保存当前编辑的存档说明？"):
                save_desc()
            else:
                cancel()

        # 按钮逻辑：点击“保存”直接保存，点击“放弃”直接关闭，点击“X”才询问
        ttk.Button(btn_frame, text="保存", command=save_desc, bootstyle="primary", width=12).pack(side="right", padx=10)
        ttk.Button(btn_frame, text="放弃", command=cancel, bootstyle="secondary", width=12).pack(side="right", padx=10)
        win.protocol("WM_DELETE_WINDOW", on_close)

        # 中间文本输入框 (最后pack fill="both" 占用剩余空间)
        text_frame = ttk.Frame(win)
        text_frame.pack(fill="both", expand=True, padx=20, pady=5)
        
        text = Text(text_frame, wrap=tk.WORD, font=("微软雅黑", 12), undo=True)
        scroll = Scrollbar(text_frame, command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.insert("end", self.archive_desc)
        
        text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
    
    def show_ignore_input(self):
        """弹出忽视文件编辑窗口"""
        if not self.vc:
            self.msg_label.config(text="请先选择工作目录")
            return
            
        win = Toplevel(self.root)
        win.title("编辑忽视文件规则")
        win.geometry("500x600")
        win.transient(self.root)
        win.focus_set()
        
        hint_label = ttk.Label(win, text="请输入要忽视的文件或文件夹相对路径（每行一个）。\n支持类似 *.log 的通配符。这些文件将不再被监视、显示状态和存档。", bootstyle="info", wraplength=450)
        hint_label.pack(pady=(15, 5), padx=20, fill="x", side="top")

        btn_frame = ttk.Frame(win)
        btn_frame.pack(fill="x", side="bottom", pady=15, padx=20)
        
        ignore_file = os.path.join(self.work_dir, '.fvaa', '.fvaaignore')
        
        def save_ignore():
            content = text.get("1.0", "end-1c")
            try:
                with open(ignore_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                self.msg_label.config(text="忽视文件规则已保存")
                self.refresh_status()  # 刷新状态以应用新规则
            except Exception as e:
                self.msg_label.config(text=f"保存失败：{e}")
            win.destroy()
        
        def cancel():
            win.destroy()

        ttk.Button(btn_frame, text="保存", command=save_ignore, bootstyle="primary", width=12).pack(side="right", padx=10)
        ttk.Button(btn_frame, text="放弃", command=cancel, bootstyle="secondary", width=12).pack(side="right", padx=10)

        text_frame = ttk.Frame(win)
        text_frame.pack(fill="both", expand=True, padx=20, pady=5)
        
        text = Text(text_frame, wrap=tk.NONE, font=("微软雅黑", 12), undo=True)
        scroll_y = Scrollbar(text_frame, command=text.yview)
        scroll_x = Scrollbar(text_frame, orient="horizontal", command=text.xview)
        text.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        
        existing_content = ""
        if os.path.exists(ignore_file):
            try:
                with open(ignore_file, 'r', encoding='utf-8') as f:
                    existing_content = f.read()
            except:
                pass
        text.insert("end", existing_content)
        
        text.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")
        text_frame.grid_rowconfigure(0, weight=1)
        text_frame.grid_columnconfigure(0, weight=1)
    
    def show_version_desc(self, event):
        """点击版本查看说明"""
        item = self.version_tree.identify_row(event.y)
        if not item:
            return
        col = self.version_tree.identify_column(event.x)
        if col != "#3": # 仅点击说明列才触发
            return
        version_data = self.version_tree.item(item)
        desc = self.version_tree.item(item, "tags")[0] if self.version_tree.item(item, "tags") else "无说明"
        
        win = Toplevel(self.root)
        win.title(f"版本 {version_data['values'][0]} 存档说明")
        win.geometry("600x400")
        win.resizable(True, True)
        
        # 渲染markdown格式
        html = markdown.markdown(desc, extensions=['tables', 'fenced_code', 'nl2br'])
        html_view = HTMLLabel(win, html=html)
        html_view.fit_height()
        html_view.pack(fill="both", expand=True, padx=5, pady=5)

    def load_config(self):
        config = {'recent_dirs': [], 'archive_desc': '', 'minimize_to_tray': False}
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    config.update(data)
        except:
            pass
        return config

    def save_config(self):
        config = {
            'recent_dirs': self.recent_dirs,
            'minimize_to_tray': self.minimize_to_tray_var.get()
        }
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False)
        except:
            pass
            
    def add_recent_dir(self, d):
        d = os.path.abspath(d)
        if d in self.recent_dirs:
            self.recent_dirs.remove(d)
        self.recent_dirs.insert(0, d)
        self.recent_dirs = self.recent_dirs[:5]
        self.save_config()
        self.dir_entry['values'] = self.recent_dirs

    def select_dir(self):
        dir_path = filedialog.askdirectory()
        if dir_path:
            self.load_workspace(dir_path)

    def on_combobox_select(self, event=None):
        dir_path = self.dir_entry.get().strip()
        if os.path.isdir(dir_path):
            self.load_workspace(dir_path)
        else:
            self.msg_label.config(text="目录不存在！")

    def load_workspace(self, dir_path):
        self.work_dir = dir_path
        self.dir_entry.set(dir_path)
        self.add_recent_dir(dir_path)
        self.vc = VersionControl(dir_path)
        self.archive_desc = self.vc.get_pending_desc()
        self.refresh_status()
        self.refresh_versions()
        self.refresh_operation_log()
        
        # 选择目录后默认自动开始监视
        if not self.monitoring:
            self.toggle_monitor()

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
        
        if not self.archive_desc.strip():
            if not messagebox.askyesno("未编辑存档说明", "未编辑存档说明，是否存档？\n\n点击“是”直接存档，点击“否”去编辑说明。"):
                self.show_archive_input()
                return

        desc = self.archive_desc
        version, msg = self.vc.create_archive(desc)
        self.msg_label.config(text=msg)
        if version:
            self.refresh_versions()
            self.refresh_status()
            self.refresh_operation_log()
            self.archive_desc = ""
            self.vc.save_pending_desc("")
    
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
        self.tag_msg_label.config(text="")
        if not self.vc:
            self.msg_label.config(text="请先选择工作目录")
            return
        selected = self.version_tree.selection()
        if not selected:
            self.tag_msg_label.config(text="请现在版本历史中选择要打标签的版本！")
            self.root.after(3000, lambda: self.tag_msg_label.config(text=""))
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
            self.monitor_btn.configure(text="停止监视", bootstyle="danger")
            threading.Thread(target=self.monitor_thread, daemon=True).start()
        else:
            self.monitor_btn.configure(text="开始监视", bootstyle="success")

    def on_window_unmap(self, event):
        if event.widget == self.root and self.root.state() == 'iconic':
            if self.minimize_to_tray_var.get():
                self.minimize_to_tray()

    def minimize_to_tray(self):
        self.root.withdraw()
        if not self.tray_icon_created:
            self.create_tray_icon()
            self.tray_icon_created = True
        else:
            self.show_tray_icon()

    def tray_wnd_proc(self, hwnd, msg, wparam, lparam):
        if msg == win32con.WM_USER + 20:
            if lparam == win32con.WM_LBUTTONDBLCLK or lparam == win32con.WM_LBUTTONUP:
                self.root.after(0, self.restore_from_tray)
            elif lparam == win32con.WM_RBUTTONUP:
                menu = win32gui.CreatePopupMenu()
                win32gui.AppendMenu(menu, win32con.MF_STRING, 1023, "打开主窗口")
                win32gui.AppendMenu(menu, win32con.MF_STRING, 1024, "退出")
                pos = win32api.GetCursorPos()
                win32gui.SetForegroundWindow(hwnd)
                win32gui.TrackPopupMenu(menu, win32con.TPM_LEFTALIGN, pos[0], pos[1], 0, hwnd, None)
                win32gui.PostMessage(hwnd, win32con.WM_NULL, 0, 0)
        elif msg == win32con.WM_COMMAND:
            cmd_id = win32api.LOWORD(wparam)
            if cmd_id == 1023:
                self.root.after(0, self.restore_from_tray)
            elif cmd_id == 1024:
                self.root.after(0, self.on_close_app)
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

    def create_tray_icon(self):
        def tray_loop():
            wc = win32gui.WNDCLASS()
            hinst = wc.hInstance = win32api.GetModuleHandle(None)
            wc.lpszClassName = "KitFVAA_Tray"
            wc.lpfnWndProc = self.tray_wnd_proc
            try:
                classAtom = win32gui.RegisterClass(wc)
            except:
                classAtom = win32gui.GetModuleHandle(None) # Already registered or similar
            
            style = win32con.WS_OVERLAPPED | win32con.WS_SYSMENU
            self.hwnd = win32gui.CreateWindow("KitFVAA_Tray", "KitFVAA_Tray", style, 0, 0, win32con.CW_USEDEFAULT, win32con.CW_USEDEFAULT, 0, 0, hinst, None)
            win32gui.UpdateWindow(self.hwnd)
            
            hicon = win32gui.LoadIcon(0, win32con.IDI_APPLICATION)
            win32gui.Shell_NotifyIcon(win32gui.NIM_ADD, (self.hwnd, 0, win32gui.NIF_ICON | win32gui.NIF_MESSAGE | win32gui.NIF_TIP, win32con.WM_USER + 20, hicon, "Kit文件存档助手"))
            win32gui.PumpMessages()
        
        threading.Thread(target=tray_loop, daemon=True).start()

    def show_tray_icon(self):
        # The NIM_MODIFY is only needed if we want to change something, 
        # but since we create it once and keep it, NIM_ADD in tray_loop is enough.
        # However, we can use NIM_MODIFY to ensure it's visible.
        try:
            hicon = win32gui.LoadIcon(0, win32con.IDI_APPLICATION)
            win32gui.Shell_NotifyIcon(win32gui.NIM_MODIFY, (self.hwnd, 0, win32gui.NIF_ICON | win32gui.NIF_MESSAGE | win32gui.NIF_TIP, win32con.WM_USER + 20, hicon, "Kit文件存档助手"))
        except:
            pass

    def restore_from_tray(self):
        self.root.deiconify()
        self.root.state('normal')
        self.root.focus_force()

    def on_close_app(self):
        if self.tray_icon_created:
            try:
                win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, (self.hwnd, 0))
            except:
                pass
        self.root.destroy()
        os._exit(0) # Use os._exit to kill all threads immediately

if __name__ == "__main__":
    app = ttk.Window(themename="cyborg", title="Kit文件存档助手")
    VersionControlApp(app)
    app.mainloop()