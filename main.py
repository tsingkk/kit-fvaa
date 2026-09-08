import ttkbootstrap as ttk
import tkinter as tk
from tkinter import filedialog, messagebox, Toplevel, Text
from tkhtmlview import HTMLLabel, HTMLScrolledText
import tkhtmlview.html_parser as _html_parser
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

# ---------------- 界面主题：柔和低饱和深色 ----------------
PALETTE = {
    # 基础背景
    "bg":          "#1E2228",  # 主窗口/弹窗背景
    "panel":       "#20242B",  # 面板/表格内容区背景
    "header":      "#2A2F38",  # 表头背景
    "separator":   "#3A3F48",  # 分隔线/滚动条
    # 文字
    "text":        "#C8CCD2",  # 正文
    "header_text": "#D8DCE2",  # 表头文字
    "text_dim":    "#8A8F98",  # 次要文字
    "link":        "#6FA8DC",  # 可交互链接
    "title":       "#B39DDB",  # 标题/当前分支高亮
    # 按钮：(背景色, 文字色)——背景较暗用浅字，较亮用深字
    "btn_blue":    ("#4A7FA5", "#F0F0F0"),
    "btn_teal":    ("#4A8F8C", "#F0F0F0"),
    "btn_red":     ("#B5555A", "#F0F0F0"),
    "btn_gray":    ("#3D4148", "#E0E0E0"),
    "btn_purple":  ("#8A6FA8", "#F0F0F0"),
    "btn_green":   ("#6B9C6E", "#1A1A1A"),
    "btn_orange":  ("#C08A55", "#1A1A1A"),
    # 提示与状态信息
    "hint_bg":     "#332E40",  # 弹窗顶部警示条背景
    "hint_text":   "#E5E0F0",  # 警示条文字
    "msg_success": "#8FBF8F",  # 成功提示
    "msg_neutral": "#A9AEB6",  # 中性说明
    "msg_danger":  "#C97A7A",  # 错误提示
    # 文件状态列
    "st_unchanged": "#8A8F98",
    "st_added":     "#7FBF7F",
    "st_deleted":   "#C97A7A",
    "st_modified":  "#D9B36B",
    # 操作历史行底色（按操作类型）
    "op_archive": "#2E3A32",   # 存档
    "op_switch":  "#2A3440",   # 切换分支
    "op_restore": "#2E3A3A",   # 恢复版本
    "op_create":  "#332E3D",   # 创建分支
}

def _shade(hex_color, factor):
    """调整颜色明度：factor > 0 变亮，< 0 变暗"""
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    if factor >= 0:
        r, g, b = (round(c + (255 - c) * factor) for c in (r, g, b))
    else:
        r, g, b = (round(c * (1 + factor)) for c in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"

def _font(size, bold=False):
    """统一界面字体（微软雅黑，pt 单位，随系统 DPI 缩放）"""
    return ("微软雅黑", size, "bold" if bold else "normal")

class ToolTip:
    """轻量悬停提示气泡：provider(x, y) 返回提示文本，为空则不显示"""
    def __init__(self, widget, provider, delay=400):
        self.widget = widget
        self.provider = provider
        self.delay = delay
        self.tip_window = None
        self._after_id = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")
        widget.bind("<Motion>", self._schedule, add="+")

    def _schedule(self, event):
        self._hide()
        x, y, rx, ry = event.x, event.y, event.x_root, event.y_root
        self._after_id = self.widget.after(
            self.delay, lambda: self._show(x, y, rx, ry))

    def _show(self, x, y, rx, ry):
        self._hide()
        text = self.provider(x, y)
        if not text:
            return
        self.tip_window = tip = tk.Toplevel(self.widget)
        tip.wm_overrideredirect(True)
        tip.wm_geometry(f"+{rx + 14}+{ry + 18}")
        tk.Label(tip, text=text, justify="left", wraplength=520,
                 background=PALETTE["header"], foreground=PALETTE["header_text"],
                 relief="solid", borderwidth=1, font=_font(10),
                 padx=8, pady=5).pack()

    def _hide(self, event=None):
        if self._after_id is not None:
            self.widget.after_cancel(self._after_id)
            self._after_id = None
        if self.tip_window is not None:
            self.tip_window.destroy()
            self.tip_window = None

# tkhtmlview 默认把正文渲染成黑色文字，改为主题正文色（模块级默认，随每次解析生效）
_html_parser.DEFAULT_STACK[_html_parser.WCfg.KEY][_html_parser.WCfg.FOREGROUND] = \
    [("__DEFAULT__", PALETTE["text"])]

class VersionControlApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Kit文件存档助手")
        # 系统缩放因子（1080p@100% 为 1.0，2K 高分屏按 DPI 放大）
        self.ui_scale = max(1.0, self.root.winfo_fpixels("1i") / 96.0)
        self.root.geometry(f"{int(1600 * self.ui_scale)}x{int(850 * self.ui_scale)}")
        self.root.minsize(int(1200 * self.ui_scale), int(760 * self.ui_scale))
        
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
        
        # 应用全局深色主题样式
        self.build_styles()
        
        self.vc = None
        self.work_dir = ""
        self.monitoring = False
        self.tag_edit_entry = None  # 版本历史“标签”列的原位输入框
        
        # 标题
        header_frame = ttk.Frame(root)
        header_frame.pack(fill="x", pady=10)
        title_label = ttk.Label(header_frame, text="Kit文件存档助手", font=_font(20, True), foreground=PALETTE["title"])
        title_label.pack()
        copyright_label = ttk.Label(header_frame, text="v1.1 by tsingkk@github under GPLv3 License", font=_font(11), foreground=PALETTE["text_dim"])
        copyright_label.place(relx=1.0, rely=0.5, anchor="e", x=-10)
        
        # 工作目录选择 + 当前分支（同一行，右侧显示分支，形成清晰的状态信息区）
        dir_frame = ttk.Frame(root)
        dir_frame.pack(pady=5, fill="x", padx=10)
        
        ttk.Label(dir_frame, text="工作目录:").pack(side="left", padx=5)
        self.dir_entry = ttk.Combobox(dir_frame, width=80, values=self.recent_dirs)
        self.dir_entry.pack(side="left", padx=5, fill="x", expand=True)
        self.dir_entry.bind("<<ComboboxSelected>>", self.on_combobox_select)
        self.dir_entry.bind("<Return>", self.on_combobox_select)
        ttk.Button(dir_frame, text="选择目录", command=self.select_dir, style="FVAA.Blue.TButton").pack(side="left", padx=5)
        self.branch_label = ttk.Label(dir_frame, text="当前分支：-", font=_font(13, True), foreground=PALETTE["title"])
        self.branch_label.pack(side="right", padx=10)
        
        # 操作按钮栏（统一按钮间距，避免“贴脸排列”）
        btn_frame = ttk.Frame(root)
        btn_frame.pack(pady=5, fill="x", padx=10)
        
        self.refresh_btn = ttk.Button(btn_frame, text="刷新状态", command=self.refresh_status, style="FVAA.Blue.TButton")
        self.refresh_btn.pack(side="left", padx=6)
        
        self.monitor_btn = ttk.Button(btn_frame, text="开始监视", command=self.toggle_monitor, style="FVAA.Teal.TButton")
        self.monitor_btn.pack(side="left", padx=6)
        
        self.ignore_btn = ttk.Button(btn_frame, text="忽视文件", command=self.show_ignore_input, style="FVAA.Gray.TButton")
        self.ignore_btn.pack(side="left", padx=6)
        
        self.desc_btn = ttk.Button(btn_frame, text="编辑存档说明", command=self.show_archive_input, style="FVAA.Purple.TButton")
        self.desc_btn.pack(side="left", padx=6)
        
        self.archive_btn = ttk.Button(btn_frame, text="存档", command=self.create_archive, style="FVAA.Green.TButton")
        self.archive_btn.pack(side="left", padx=6)
        
        self.restore_btn = ttk.Button(btn_frame, text="恢复版本", command=self.restore_version, style="FVAA.Orange.TButton")
        self.restore_btn.pack(side="left", padx=6)
        
        self.branch_create_btn = ttk.Button(btn_frame, text="创建分支", command=self.create_branch, style="FVAA.Blue.TButton")
        self.branch_create_btn.pack(side="left", padx=6)

        self.branch_switch_btn = ttk.Button(btn_frame, text="切换分支", command=self.switch_branch, style="FVAA.Blue.TButton")
        self.branch_switch_btn.pack(side="left", padx=6)

        self.branch_history_btn = ttk.Button(btn_frame, text="分支历史", command=self.show_branch_history, style="FVAA.Blue.TButton")
        self.branch_history_btn.pack(side="left", padx=6)

        self.minimize_to_tray_var = tk.BooleanVar(value=self.config.get('minimize_to_tray', False))
        self.tray_checkbox = ttk.Checkbutton(btn_frame, text="最小化至状态栏", variable=self.minimize_to_tray_var, bootstyle="info-round-toggle", command=self.save_config)
        self.tray_checkbox.pack(side="right", padx=10)
        
        self.root.bind("<Unmap>", self.on_window_unmap)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close_app)
        self.tray_icon_created = False

        
        # 消息提示区（消息靠左，状态摘要靠右）
        msg_frame = ttk.Frame(root)
        msg_frame.pack(pady=2, fill="x", padx=10)
        self.msg_label = ttk.Label(msg_frame, text="", font=_font(12), foreground=PALETTE["msg_neutral"])
        self.msg_label.pack(side="left")
        self.summary_label = ttk.Label(msg_frame, text="", font=_font(12), foreground=PALETTE["msg_neutral"])
        self.summary_label.pack(side="right")
        
        # 分割面板
        paned = ttk.Panedwindow(root, orient="horizontal")
        paned.pack(pady=10, fill="both", expand=True, padx=10)
        
        # 操作历史面板（加宽占比，避免长文本被截断）
        op_frame = ttk.Frame(paned)
        paned.add(op_frame, weight=4)
        
        ttk.Label(op_frame, text="操作历史", font=_font(14, True), foreground=PALETTE["header_text"]).pack(pady=5, anchor="w", padx=6)
        op_inner_frame = ttk.Frame(op_frame)
        op_inner_frame.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        # 单列无边框 Treeview：可设置行高并按操作类型着色
        self.op_tree = ttk.Treeview(op_inner_frame, columns=("log",), show="", selectmode="browse")
        self.op_tree.column("log", anchor="w", stretch=True, width=int(340 * self.ui_scale))
        # 横向+竖向滚动条
        op_yscroll = ttk.Scrollbar(op_inner_frame, orient="vertical", command=self.op_tree.yview, style="Custom.Vertical.TScrollbar")
        op_xscroll = ttk.Scrollbar(op_inner_frame, orient="horizontal", command=self.op_tree.xview, style="Custom.Horizontal.TScrollbar")
        # 绑定滚动
        self.op_tree.configure(yscrollcommand=op_yscroll.set, xscrollcommand=op_xscroll.set)
        self.op_tree.grid(row=0, column=0, sticky="nsew")
        op_yscroll.grid(row=0, column=1, sticky="ns")
        op_xscroll.grid(row=1, column=0, sticky="ew")
        op_inner_frame.grid_rowconfigure(0, weight=1)
        op_inner_frame.grid_columnconfigure(0, weight=1)
        # 按操作类型配置行底色
        for tag, color in (("archive", PALETTE["op_archive"]),
                           ("restore", PALETTE["op_restore"]),
                           ("switch", PALETTE["op_switch"]),
                           ("create", PALETTE["op_create"])):
            self.op_tree.tag_configure(tag, background=color)
        # 悬停提示显示完整记录（配合加宽面板，彻底避免信息丢失）
        self.op_tooltip = ToolTip(self.op_tree, self._op_tip_text)
        
        # 文件状态面板
        status_frame = ttk.Frame(paned)
        paned.add(status_frame, weight=5)
        
        ttk.Label(status_frame, text="文件状态", font=_font(14, True), foreground=PALETTE["header_text"]).pack(pady=5, anchor="w", padx=6)
        status_inner_frame = ttk.Frame(status_frame)
        status_inner_frame.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        # 先创建树控件
        self.status_tree = ttk.Treeview(status_inner_frame, columns=("status", "path"), show="headings", height=25)
        self.status_tree.heading("status", text="状态")
        self.status_tree.heading("path", text="文件路径")
        self.status_tree.column("status", width=int(70 * self.ui_scale), anchor="w", stretch=False)
        self.status_tree.column("path", width=int(380 * self.ui_scale), stretch=True)
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
        
        ttk.Label(version_frame, text="版本历史", font=_font(14, True), foreground=PALETTE["header_text"]).pack(pady=5, anchor="w", padx=6)
        version_inner_frame = ttk.Frame(version_frame)
        version_inner_frame.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        # 先创建树控件
        self.version_tree = ttk.Treeview(version_inner_frame, columns=("version", "time", "desc", "files", "tags"), show="headings", height=25)
        self.version_tree.heading("version", text="版本号", anchor="center")
        self.version_tree.heading("time", text="时间", anchor="center")
        self.version_tree.heading("desc", text="说明", anchor="center")
        self.version_tree.heading("files", text="文件清单", anchor="center")
        self.version_tree.heading("tags", text="标签", anchor="center")
        self.version_tree.column("version", width=int(80 * self.ui_scale), anchor="center", stretch=False)
        self.version_tree.column("time", width=int(180 * self.ui_scale), anchor="center", stretch=False)
        self.version_tree.column("desc", width=int(260 * self.ui_scale), anchor="center", stretch=True)
        self.version_tree.column("files", width=int(90 * self.ui_scale), anchor="center", stretch=False)
        self.version_tree.column("tags", width=int(160 * self.ui_scale), anchor="center", stretch=True)
        # 横向+竖向滚动条（高亮样式）
        version_yscroll = ttk.Scrollbar(version_inner_frame, orient="vertical", command=self.version_tree.yview, style="Custom.Vertical.TScrollbar")
        version_xscroll = ttk.Scrollbar(version_inner_frame, orient="horizontal", command=self.version_tree.xview, style="Custom.Horizontal.TScrollbar")
        # 绑定滚动（滚动时销毁原位标签输入框，避免浮层与单元格错位）
        self._version_yscroll_set = version_yscroll.set
        self._version_xscroll_set = version_xscroll.set
        self.version_tree.configure(yscrollcommand=self._on_tree_yscroll, xscrollcommand=self._on_tree_xscroll)
        self.version_tree.grid(row=0, column=0, sticky="nsew")
        version_yscroll.grid(row=0, column=1, sticky="ns")
        version_xscroll.grid(row=1, column=0, sticky="ew")
        version_inner_frame.grid_rowconfigure(0, weight=1)
        version_inner_frame.grid_columnconfigure(0, weight=1)
        self.version_tree.bind('<ButtonRelease-1>', self.show_version_desc)
        
        # “点击查看”类可交互单元格：悬停时行文字变为链接色 + 手型光标
        self._hover_item = None
        self._link_columns = ("#3", "#4", "#5")
        self.version_tree.tag_configure("linkhover", foreground=PALETTE["link"])
        self.version_tree.bind("<Motion>", self._on_version_motion)
        self.version_tree.bind("<Leave>", lambda e: self._clear_link_hover())
        
        self.status_tags = {
            'modified': ('修改', PALETTE["st_modified"]),
            'added': ('新增', PALETTE["st_added"]),
            'deleted': ('删除', PALETTE["st_deleted"]),
            'unchanged': ('不变', PALETTE["st_unchanged"])
        }
        for tag, (_, color) in self.status_tags.items():
            self.status_tree.tag_configure(tag, foreground=color)
    
    def build_styles(self):
        """按 PALETTE 配置全局 ttk 样式（背景/表格/表头/按钮/滚动条/输入框）"""
        P = PALETTE
        s = self.ui_scale
        style = ttk.Style()

        # Combobox 下拉列表配色（经典 Listbox，走选项数据库）
        self.root.option_add("*TCombobox*Listbox.background", P["panel"])
        self.root.option_add("*TCombobox*Listbox.foreground", P["text"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", P["btn_blue"][0])
        self.root.option_add("*TCombobox*Listbox.selectForeground", "#F0F0F0")

        # 基础控件背景与字体
        style.configure(".", background=P["bg"], foreground=P["text"], font=_font(12))
        style.configure("TFrame", background=P["bg"])
        style.configure("TLabel", background=P["bg"], foreground=P["text"])
        style.configure("TButton", font=_font(11, True))
        style.configure("TPanedwindow", background=P["separator"])
        style.configure("Horizontal.TPanedwindow", background=P["separator"])
        style.configure("Vertical.TPanedwindow", background=P["separator"])
        style.configure("Sash", sashthickness=max(2, int(3 * s)), gripcount=0)
        style.configure("TEntry", fieldbackground=P["panel"], foreground=P["text"],
                        insertcolor=P["text"], bordercolor=P["separator"],
                        lightcolor=P["panel"], darkcolor=P["panel"])
        style.map("TEntry", bordercolor=[("focus", P["btn_blue"][0])])
        style.configure("TCombobox", fieldbackground=P["panel"], foreground=P["text"],
                        insertcolor=P["text"], bordercolor=P["separator"],
                        lightcolor=P["panel"], darkcolor=P["panel"],
                        arrowsize=int(14 * s))
        style.map("TCombobox",
                  fieldbackground=[("readonly", P["panel"])],
                  foreground=[("readonly", P["text"])],
                  bordercolor=[("focus", P["btn_blue"][0])],
                  lightcolor=[("focus", P["btn_blue"][0])],
                  darkcolor=[("focus", P["btn_blue"][0])])

        # 表格：内容区/表头分层，行高约 +28% 并随 DPI 缩放
        rowheight = int(36 * s)
        for name in ("Treeview", "dark.Treeview"):
            style.configure(name, background=P["panel"], fieldbackground=P["panel"],
                            foreground=P["text"], font=_font(12), rowheight=rowheight,
                            borderwidth=0, relief="flat")
            style.map(name,
                      background=[("selected", P["btn_blue"][0])],
                      foreground=[("selected", "#F0F0F0")])
        for name in ("Treeview.Heading", "dark.Treeview.Heading"):
            style.configure(name, background=P["header"], foreground=P["header_text"],
                            font=_font(12, True), padding=(8, 8),
                            borderwidth=1, relief="solid", bordercolor=P["separator"])
            style.map(name, background=[("active", _shade(P["header"], 0.1))])

        # 滚动条
        for name in ("Custom.Vertical.TScrollbar", "Custom.Horizontal.TScrollbar"):
            style.configure(name, background=P["separator"], troughcolor=P["bg"],
                            bordercolor=P["bg"], arrowcolor=P["text"], gripcount=0,
                            lightcolor=P["separator"], darkcolor=P["separator"])
            style.map(name,
                      background=[("active", _shade(P["separator"], 0.15)),
                                  ("pressed", _shade(P["separator"], -0.15))],
                      lightcolor=[("active", _shade(P["separator"], 0.15))],
                      darkcolor=[("active", _shade(P["separator"], 0.15))])

        # 按钮样式：背景较暗统一浅字（#F0F0F0），背景较亮统一深字（#1A1A1A）
        for name, (bg, fg) in {"Blue":   P["btn_blue"],
                               "Teal":   P["btn_teal"],
                               "Red":    P["btn_red"],
                               "Gray":   P["btn_gray"],
                               "Purple": P["btn_purple"],
                               "Green":  P["btn_green"],
                               "Orange": P["btn_orange"]}.items():
            hover = _shade(bg, 0.12)
            pressed = _shade(bg, -0.15)
            disabled_bg = _shade(bg, -0.35)
            stylename = f"FVAA.{name}.TButton"
            style.configure(stylename,
                            background=bg, foreground=fg,
                            bordercolor=_shade(bg, 0.25),
                            lightcolor=bg, darkcolor=bg,
                            relief="raised", borderwidth=1,
                            focusthickness=1, focuscolor=bg,
                            padding=(int(12 * s), int(6 * s)),
                            anchor="center")
            style.map(stylename,
                      background=[("disabled", disabled_bg),
                                  ("pressed !disabled", pressed),
                                  ("hover !disabled", hover)],
                      foreground=[("disabled", P["text_dim"])],
                      bordercolor=[("disabled", disabled_bg),
                                   ("pressed !disabled", pressed),
                                   ("hover !disabled", hover)],
                      lightcolor=[("disabled", disabled_bg),
                                  ("pressed !disabled", pressed),
                                  ("hover !disabled", hover)],
                      darkcolor=[("disabled", disabled_bg),
                                 ("pressed !disabled", pressed),
                                 ("hover !disabled", hover)])

    def _set_message(self, text, kind="neutral"):
        """按语义设置消息栏文字颜色：success 成功 / neutral 中性 / danger 错误 / info 提示"""
        colors = {
            "success": PALETTE["msg_success"],
            "neutral": PALETTE["msg_neutral"],
            "danger": PALETTE["msg_danger"],
            "info": PALETTE["link"],
        }
        self.msg_label.config(text=text, foreground=colors.get(kind, PALETTE["msg_neutral"]))

    def _op_tip_text(self, x, y):
        """操作历史悬停提示：返回所在行的完整记录文本"""
        item = self.op_tree.identify_row(y)
        if not item:
            return None
        values = self.op_tree.item(item, "values")
        return values[0].strip() if values else None

    def _on_version_motion(self, event):
        """版本历史表：鼠标悬停在可交互单元格时高亮整行文字为链接色"""
        item = self.version_tree.identify_row(event.y)
        col = self.version_tree.identify_column(event.x)
        if item and col in self._link_columns and self._cell_is_link(item, col):
            self._set_link_hover(item)
        else:
            self._clear_link_hover()

    def _cell_is_link(self, item, col):
        if col in ("#3", "#4"):
            return True  # 说明/文件清单列均为“点击查看”
        values = self.version_tree.item(item, "values")
        return bool(values) and values[4] == "添加标签"

    def _set_link_hover(self, item):
        if self._hover_item == item:
            return
        self._clear_link_hover()
        tags = list(self.version_tree.item(item, "tags"))
        tags.append("linkhover")
        try:
            self.version_tree.item(item, tags=tags)
        except tk.TclError:
            return
        self._hover_item = item
        self.version_tree.configure(cursor="hand2")

    def _clear_link_hover(self):
        if self._hover_item is None:
            return
        try:
            tags = [t for t in self.version_tree.item(self._hover_item, "tags")
                    if t != "linkhover"]
            self.version_tree.item(self._hover_item, tags=tags)
        except tk.TclError:
            pass
        self._hover_item = None
        self.version_tree.configure(cursor="")

    @staticmethod
    def _style_html_view(view):
        """将 tkhtmlview 渲染视图适配深色主题（容器/滚动条配色、黑色文字/链接色修正）"""
        frame = getattr(view, "frame", None)
        if frame is not None:
            try:
                frame.configure(background=PALETTE["panel"])
            except tk.TclError:
                pass
        for bar in ("vbar", "xscroll"):
            bar_widget = getattr(view, bar, None)
            if bar_widget is not None:
                try:
                    bar_widget.configure(background=PALETTE["separator"],
                                         troughcolor=PALETTE["bg"],
                                         activebackground=_shade(PALETTE["separator"], 0.15),
                                         highlightthickness=0)
                except tk.TclError:
                    pass
        for tag in view.tag_names():
            try:
                fg = str(view.tag_cget(tag, "foreground"))
            except tk.TclError:
                continue
            if fg in ("black", "SystemWindowText"):
                view.tag_configure(tag, foreground=PALETTE["text"])
            elif fg == "blue":
                view.tag_configure(tag, foreground=PALETTE["link"])
    
    STATUS_BLOCK_START = "<!-- FVAA文件状态清单 开始 -->"
    STATUS_BLOCK_END = "<!-- FVAA文件状态清单 结束 -->"
    # 分支历史图谱中各分支列的配色
    GRAPH_COLORS = ("#4fc3f7", "#81c784", "#ffb74d", "#ba68c8", "#f06292", "#4dd0e1", "#aed581", "#ff8a65")

    def build_status_block(self):
        """生成当前目录的文件状态清单（Markdown格式，含删除/新增/修改），无变更时返回空字符串"""
        if not self.vc:
            return ""
        try:
            diff, _ = self.vc.get_diff()
        except Exception:
            return ""
        sections = [
            ("删除", diff.get('deleted', [])),
            ("新增", diff.get('added', [])),
            ("修改", diff.get('modified', [])),
        ]
        if not any(paths for _, paths in sections):
            return ""
        lines = ["## 文件状态清单"]
        for title, paths in sections:
            if not paths:
                continue
            lines.append("")
            lines.append(f"**{title}（{len(paths)} 个）：**")
            for path in sorted(paths):
                lines.append(f"- {path}")
        return "\n".join(lines)

    def strip_status_block(self, desc):
        """剥离说明中的自动生成状态清单块，返回纯用户文字"""
        body = desc or ""
        start = body.find(self.STATUS_BLOCK_START)
        if start != -1:
            end = body.find(self.STATUS_BLOCK_END, start)
            body = body[:start] + (body[end + len(self.STATUS_BLOCK_END):] if end != -1 else "")
            body = body.strip("\n")
        return body

    def merge_status_block(self, desc):
        """将最新的文件状态清单附加到说明顶部（先剥离旧清单块）"""
        block = self.build_status_block()
        body = self.strip_status_block(desc)
        if not block:
            return body
        block = f"{self.STATUS_BLOCK_START}\n{block}\n{self.STATUS_BLOCK_END}"
        return f"{block}\n\n{body}" if body else block

    def show_archive_input(self, archive_mode=False):
        """弹出存档说明编辑窗口；archive_mode 为 True 时（存档流程）点击“保存”后才执行存档。
        上栏只读展示文件状态清单，下方为存档说明输入框（存档模式下再下方为标签输入行）"""
        status_block = self.build_status_block()
        user_desc = self.strip_status_block(self.archive_desc)

        win = Toplevel(self.root)
        win.title("编辑存档说明")
        win.geometry(f"{int(620 * self.ui_scale)}x{int(650 * self.ui_scale)}")
        win.configure(background=PALETTE["bg"])
        win.focus_set()
        win.resizable(True, True)
        if archive_mode:
            win.transient(self.root)
            win.grab_set()
         
        # 顶部提示语（警示条样式，字号与正文一致）
        hint_text = "上方只读显示当前目录的文件状态清单（每次打开自动更新），存档时将自动附加到存档说明顶部随版本保存；请在下方输入存档说明！"
        hint_label = tk.Label(win, text=hint_text, wraplength=int(560 * self.ui_scale), justify="left",
                              font=_font(12), background=PALETTE["hint_bg"], foreground=PALETTE["hint_text"],
                              padx=12, pady=8)
        hint_label.pack(pady=(15, 8), padx=20, fill="x", side="top")

        # 底部按钮栏 (先pack side="bottom" 确保即使窗口缩小也始终可见)
        btn_frame = ttk.Frame(win)
        btn_frame.pack(fill="x", side="bottom", pady=15, padx=20)

        # 标签输入行（仅存档流程显示，位于说明输入框与按钮栏之间）
        tag_entry = None
        if archive_mode:
            tag_frame = ttk.Frame(win)
            tag_frame.pack(fill="x", side="bottom", padx=20, pady=(0, 8))
            ttk.Label(tag_frame, text="标签:").pack(side="left", padx=(0, 5))
            tag_entry = ttk.Entry(tag_frame, width=30)
            tag_entry.pack(side="left", fill="x", expand=True)
            ttk.Label(tag_frame, text="（留空则不添加标签）", foreground=PALETTE["text_dim"]).pack(side="left", padx=5)

        # 上栏：文件状态清单（只读，渲染 Markdown；无变更时显示占位）
        status_frame = ttk.Frame(win)
        status_frame.pack(fill="x", padx=20, pady=(0, 8), side="top")
        ttk.Label(status_frame, text="文件状态清单：").pack(anchor="w", pady=(0, 2))
        status_html = markdown.markdown(status_block or "*当前无文件变更*", extensions=['tables', 'fenced_code', 'nl2br'])
        status_view = HTMLScrolledText(status_frame, html=status_html, height=8, background=PALETTE["panel"])
        status_view.pack(fill="x")
        self._style_html_view(status_view)
        status_view.configure(state="disabled")

        # 中/下栏：存档说明输入框（fill="both" 占用剩余空间）
        desc_frame = ttk.Frame(win)
        desc_frame.pack(fill="both", expand=True, padx=20, pady=(5, 8))
        ttk.Label(desc_frame, text="存档说明：").pack(anchor="w", pady=(0, 2))
        desc_inner = ttk.Frame(desc_frame)
        desc_inner.pack(fill="both", expand=True)
        text = Text(desc_inner, wrap=tk.WORD, font=_font(12), undo=True,
                    background=PALETTE["panel"], foreground=PALETTE["text"],
                    insertbackground=PALETTE["text"], relief="flat", padx=8, pady=6,
                    highlightthickness=1, highlightbackground=PALETTE["separator"],
                    highlightcolor=PALETTE["separator"])
        scroll = ttk.Scrollbar(desc_inner, orient="vertical", command=text.yview, style="Custom.Vertical.TScrollbar")
        text.configure(yscrollcommand=scroll.set)
        text.insert("end", user_desc)
        text.mark_set("insert", "end")
        text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        def save_desc():
            desc_text = text.get("1.0", "end-1c")
            if archive_mode and not desc_text.strip():
                messagebox.showwarning("存档说明", "存档说明不能为空，无法存档，请输入内容后再保存", parent=win)
                return
            tag_name = ""
            if archive_mode and tag_entry is not None:
                tag_name = tag_entry.get().strip()
                if tag_name and self.vc and self.vc.tag_exists(tag_name):
                    messagebox.showwarning("标签已存在", f"标签 “{tag_name}” 在当前分支已存在，请修改标签或清空后再保存", parent=win)
                    return
            self.archive_desc = desc_text
            if self.vc:
                self.vc.save_pending_desc(self.archive_desc)
            win.destroy()
            if archive_mode:
                self._do_archive(tag_name)
            else:
                self._set_message("存档说明已保存", "success")
        
        def cancel():
            win.destroy()
        
        def on_close():
            # 仅在点击右上角关闭(X)时提醒
            if archive_mode:
                confirmed = messagebox.askyesno("保存确认", "是否保存存档说明并执行存档？")
            else:
                confirmed = messagebox.askyesno("保存确认", "是否保存当前编辑的存档说明？")
            if confirmed:
                save_desc()
            else:
                cancel()

        # 按钮逻辑：点击“保存”直接保存，点击“放弃”直接关闭，点击“X”才询问
        ttk.Button(btn_frame, text="保存", command=save_desc, style="FVAA.Blue.TButton", width=12).pack(side="right", padx=10)
        ttk.Button(btn_frame, text="放弃", command=cancel, style="FVAA.Gray.TButton", width=12).pack(side="right", padx=10)
        win.protocol("WM_DELETE_WINDOW", on_close)

    def show_ignore_input(self):
        """弹出忽视文件编辑窗口"""
        if not self.vc:
            self._set_message("请先选择工作目录", "danger")
            return
            
        win = Toplevel(self.root)
        win.title("编辑忽视文件规则")
        win.geometry(f"{int(500 * self.ui_scale)}x{int(600 * self.ui_scale)}")
        win.configure(background=PALETTE["bg"])
        win.transient(self.root)
        win.focus_set()
        
        hint_label = tk.Label(win, text="请输入要忽视的文件或文件夹相对路径（每行一个）。\n支持类似 *.log 的通配符。这些文件将不再被监视、显示状态和存档。",
                              wraplength=int(450 * self.ui_scale), justify="left",
                              font=_font(12), background=PALETTE["hint_bg"], foreground=PALETTE["hint_text"],
                              padx=12, pady=8)
        hint_label.pack(pady=(15, 8), padx=20, fill="x", side="top")

        btn_frame = ttk.Frame(win)
        btn_frame.pack(fill="x", side="bottom", pady=15, padx=20)
        
        ignore_file = os.path.join(self.work_dir, '.fvaa', '.fvaaignore')
        
        def save_ignore():
            content = text.get("1.0", "end-1c")
            try:
                with open(ignore_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                self._set_message("忽视文件规则已保存", "success")
                self.refresh_status()  # 刷新状态以应用新规则
            except Exception as e:
                self._set_message(f"保存失败：{e}", "danger")
            win.destroy()
        
        def cancel():
            win.destroy()

        ttk.Button(btn_frame, text="保存", command=save_ignore, style="FVAA.Blue.TButton", width=12).pack(side="right", padx=10)
        ttk.Button(btn_frame, text="放弃", command=cancel, style="FVAA.Gray.TButton", width=12).pack(side="right", padx=10)

        text_frame = ttk.Frame(win)
        text_frame.pack(fill="both", expand=True, padx=20, pady=(5, 8))
        
        text = Text(text_frame, wrap=tk.NONE, font=_font(12), undo=True,
                    background=PALETTE["panel"], foreground=PALETTE["text"],
                    insertbackground=PALETTE["text"], relief="flat", padx=8, pady=6,
                    highlightthickness=1, highlightbackground=PALETTE["separator"],
                    highlightcolor=PALETTE["separator"])
        scroll_y = ttk.Scrollbar(text_frame, orient="vertical", command=text.yview, style="Custom.Vertical.TScrollbar")
        scroll_x = ttk.Scrollbar(text_frame, orient="horizontal", command=text.xview, style="Custom.Horizontal.TScrollbar")
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
        """点击版本查看说明或文件清单"""
        item = self.version_tree.identify_row(event.y)
        if not item:
            return
        col = self.version_tree.identify_column(event.x)
        if col == "#4":  # 点击文件清单列，弹出文件取回窗口
            version_num = int(self.version_tree.item(item, "values")[0])
            self.show_version_files(version_num)
            return
        if col == "#5":  # 点击标签列，为无标签的版本原位添加标签
            self._start_tag_edit(item)
            return
        if col != "#3": # 仅点击说明列才触发
            return
        version_data = self.version_tree.item(item)
        desc = self.version_tree.item(item, "tags")[0] if self.version_tree.item(item, "tags") else "无说明"
        
        win = Toplevel(self.root)
        win.title(f"版本 {version_data['values'][0]} 存档说明")
        win.geometry(f"{int(600 * self.ui_scale)}x{int(400 * self.ui_scale)}")
        win.configure(background=PALETTE["bg"])
        win.resizable(True, True)
        
        # 渲染markdown格式
        html = markdown.markdown(desc, extensions=['tables', 'fenced_code', 'nl2br'])
        html_view = HTMLLabel(win, html=html, background=PALETTE["panel"])
        self._style_html_view(html_view)
        html_view.fit_height()
        html_view.pack(fill="both", expand=True, padx=10, pady=10)

    @staticmethod
    def format_file_size(size):
        """文件大小人性化显示"""
        if size >= 1024 * 1024:
            return f"{size / 1024 / 1024:.1f} MB"
        if size >= 1024:
            return f"{size / 1024:.1f} KB"
        return f"{size} B"

    def show_version_files(self, version_num):
        """弹窗展示指定版本的归档文件清单，勾选后可取回到当前工作目录"""
        if not self.vc:
            self._set_message("请先选择工作目录", "danger")
            return
        version_info = self.vc.get_version_info(version_num)
        if not version_info:
            self._set_message("版本不存在", "danger")
            return
        files_map = version_info.get('files', {})
        files = sorted(files_map.keys())
        if not files:
            messagebox.showinfo("文件清单", f"版本 {version_num} 的归档为空")
            return

        win = Toplevel(self.root)
        win.title(f"版本 {version_num} 文件清单（{len(files)} 个文件）")
        win.geometry(f"{int(760 * self.ui_scale)}x{int(680 * self.ui_scale)}")
        win.minsize(int(620 * self.ui_scale), int(520 * self.ui_scale))
        win.configure(background=PALETTE["bg"])
        win.transient(self.root)
        win.grab_set()
        win.resizable(True, True) # 可缩放（含最大化按钮）
        win.focus_set()

        # 底部按钮栏先 pack side="bottom"，确保窗口缩小时“取回”等操作按钮始终可见
        btn_frame = ttk.Frame(win)
        btn_frame.pack(fill="x", side="bottom", pady=12, padx=20)

        hint_label = tk.Label(win, text="勾选需要取回的文件，点击“取回”将复制到当前工作目录并自动重命名\n（原文件名-分支名称-版本名称-归档日期），归档中的文件不会被修改。",
                              wraplength=int(720 * self.ui_scale), justify="left",
                              font=_font(12), background=PALETTE["hint_bg"], foreground=PALETTE["hint_text"],
                              padx=12, pady=8)
        hint_label.pack(pady=(12, 8), padx=20, anchor="w", side="top")

        count_label = ttk.Label(win, text="已勾选 0 个文件", foreground=PALETTE["link"])
        count_label.pack(anchor="w", padx=20, side="top")

        tree_frame = ttk.Frame(win)
        tree_frame.pack(fill="both", expand=True, padx=20, pady=(5, 8), side="top")
        tree = ttk.Treeview(tree_frame, columns=("check", "path", "size"), show="headings", height=15)
        tree.heading("check", text="勾选", anchor="center")
        tree.heading("path", text="文件路径", anchor="w")
        tree.heading("size", text="大小", anchor="center")
        tree.column("check", width=int(60 * self.ui_scale), anchor="center", stretch=False)
        tree.column("path", width=int(480 * self.ui_scale), anchor="w", stretch=True)
        tree.column("size", width=int(90 * self.ui_scale), anchor="center", stretch=False)
        yscroll = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview, style="Custom.Vertical.TScrollbar")
        xscroll = ttk.Scrollbar(tree_frame, orient="horizontal", command=tree.xview, style="Custom.Horizontal.TScrollbar")
        tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        checked = set()
        for path in files:
            size_text = self.format_file_size(files_map[path].get('size', 0))
            tree.insert("", "end", iid=path, values=("☐", path, size_text))

        def toggle_item(path):
            if not path:
                return
            if path in checked:
                checked.discard(path)
                tree.set(path, "check", "☐")
            else:
                checked.add(path)
                tree.set(path, "check", "☑")
            count_label.config(text=f"已勾选 {len(checked)} 个文件")

        def select_all():
            checked.update(files)
            for path in files:
                tree.set(path, "check", "☑")
            count_label.config(text=f"已勾选 {len(checked)} 个文件")

        def select_none():
            checked.clear()
            for path in files:
                tree.set(path, "check", "☐")
            count_label.config(text="已勾选 0 个文件")

        tree.bind("<ButtonRelease-1>", lambda e: toggle_item(tree.identify_row(e.y)))

        def do_retrieve():
            if not checked:
                messagebox.showinfo("取回文件", "请先勾选要取回的文件", parent=win)
                return
            if not messagebox.askyesno("确认取回", f"确定要取回勾选的 {len(checked)} 个文件到当前工作目录吗？", parent=win):
                return
            success_count, msg = self.vc.retrieve_files(version_num, sorted(checked))
            self._set_message(msg, "success" if success_count > 0 else "danger")
            if success_count > 0:
                self.refresh_status()
                win.destroy()

        ttk.Button(btn_frame, text="全选", command=select_all, style="FVAA.Gray.TButton", width=8).pack(side="left", padx=10)
        ttk.Button(btn_frame, text="全不选", command=select_none, style="FVAA.Gray.TButton", width=8).pack(side="left", padx=6)
        ttk.Button(btn_frame, text="取回", command=do_retrieve, style="FVAA.Blue.TButton", width=10).pack(side="right", padx=10)
        ttk.Button(btn_frame, text="关闭", command=win.destroy, style="FVAA.Gray.TButton", width=10).pack(side="right", padx=6)

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
            self._set_message("目录不存在！", "danger")

    def load_workspace(self, dir_path):
        self.work_dir = dir_path
        self.dir_entry.set(dir_path)
        self.add_recent_dir(dir_path)
        self.vc = VersionControl(dir_path)
        self.archive_desc = self.strip_status_block(self.vc.get_pending_desc())
        self.refresh_branch_label()
        self.refresh_status()
        self.refresh_versions()
        self.refresh_operation_log()
        
        # 选择目录后默认自动开始监视
        if not self.monitoring:
            self.toggle_monitor()
    
    def refresh_branch_label(self):
        """刷新第4行正中间的分支名称显示"""
        if self.vc:
            self.branch_label.config(text=f"当前分支：{self.vc.get_current_branch()}")
        else:
            self.branch_label.config(text="当前分支：-")

    def refresh_operation_log(self):
        """刷新操作历史列表（仅显示当前分支的记录，按操作类型着色行底）"""
        if not self.vc:
            return
        for item in self.op_tree.get_children():
            self.op_tree.delete(item)
        logs = self.vc.get_operation_log()
        for log in logs:
            op = log['op']
            if op.startswith("存档"):
                tag = "archive"
            elif op.startswith("恢复"):
                tag = "restore"
            elif op.startswith("创建分支"):
                tag = "create"
            else:
                tag = "switch"
            # 行首留白，避免文字紧贴行左边缘
            self.op_tree.insert("", "end", values=(f"  {log['time']}  {op}",), tags=(tag,))
    
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
        self._destroy_tag_edit()
        for item in self.version_tree.get_children():
            self.version_tree.delete(item)
        
        versions = self.vc.get_versions()
        for v in versions:
            tags = ','.join(v.get('tags', [])) or "添加标签"
            desc = v['description'] or "无说明"
            show_desc = "点击查看" if desc.strip() else "无说明"
            self.version_tree.insert("", "end", values=(v['version'], v['time'], show_desc, "点击查看", tags), tags=(desc,))
    
    def create_archive(self):
        """存档：先弹出存档说明编辑窗口，点击弹窗中的“保存”后才执行存档"""
        if not self.vc:
            self._set_message("请先选择工作目录", "danger")
            return
        self.show_archive_input(archive_mode=True)

    def _do_archive(self, tag=""):
        """执行存档并刷新界面（存档说明已在前置弹窗中确认；tag 非空时为该版本打上标签）
        存档时将最新的文件状态清单附加到说明顶部随版本保存"""
        desc = self.merge_status_block(self.archive_desc)
        version, msg = self.vc.create_archive(desc)
        if version and tag:
            tag_ok, tag_msg = self.vc.add_tag(version['version'], tag)
            if not tag_ok:
                msg += f"（标签添加失败：{tag_msg}）"
        self._set_message(msg, "success" if version else "neutral")
        if version:
            self.refresh_versions()
            self.refresh_status()
            self.refresh_operation_log()
            self.archive_desc = ""
            self.vc.save_pending_desc("")

    def restore_version(self):
        if not self.vc:
            self._set_message("请先选择工作目录", "danger")
            return
        selected = self.version_tree.selection()
        if not selected:
            self._set_message("请先选择要恢复的版本", "danger")
            return
        version_num = int(self.version_tree.item(selected[0])['values'][0])
        confirm = messagebox.askyesno("确认恢复", f"确定要恢复到版本 {version_num} 吗？当前文件将被覆盖！")
        if confirm:
            success, msg = self.vc.restore_version(version_num)
            self._set_message(msg, "success" if success else "danger")
            self.refresh_status()
            self.refresh_operation_log()
    
    def _destroy_tag_edit(self):
        """销毁版本历史“标签”列的原位输入框（幂等）"""
        if self.tag_edit_entry is not None:
            try:
                self.tag_edit_entry.destroy()
            except Exception:
                pass
            self.tag_edit_entry = None

    def _on_tree_yscroll(self, first, last):
        self._destroy_tag_edit()
        self._version_yscroll_set(first, last)

    def _on_tree_xscroll(self, first, last):
        self._destroy_tag_edit()
        self._version_xscroll_set(first, last)

    def _start_tag_edit(self, item):
        """在无标签版本的“标签”列单元格原位创建输入框：回车保存并关联版本，Esc/失焦取消"""
        self._destroy_tag_edit()
        if not self.vc:
            return
        version_num = int(self.version_tree.item(item, "values")[0])
        version_info = self.vc.get_version_info(version_num)
        if not version_info or version_info.get('tags'):
            return  # 已有标签的版本直接显示标签，不提供添加入口
        bbox = self.version_tree.bbox(item, column="#5")
        if not bbox:
            return  # 单元格不可见时无法原位编辑
        x, y, width, height = bbox

        entry = ttk.Entry(self.version_tree)
        entry.place(x=x + 2, y=y + 2, width=width - 4, height=height - 4)
        self.tag_edit_entry = entry
        entry.focus_set()

        def confirm(event=None):
            tag_name = entry.get().strip()
            if not tag_name:
                self._destroy_tag_edit()  # 空输入视为取消
                return
            success, msg = self.vc.add_tag(version_num, tag_name)
            if success:
                self._destroy_tag_edit()
                self._set_message(msg, "success")
                self.refresh_versions()
            else:
                # 重名等错误：消息栏提示，输入框保留供修改后重试
                self._set_message(msg, "danger")
                entry.focus_set()

        def cancel(event=None):
            self._destroy_tag_edit()

        entry.bind("<Return>", confirm)
        entry.bind("<Escape>", cancel)
        entry.bind("<FocusOut>", cancel)
    
    def create_branch(self):
        """创建分支：无变更文件时弹窗输入分支名称并创建（自动切换到新分支）"""
        if not self.vc:
            self._set_message("请先选择工作目录", "danger")
            return
        if self.vc.has_changes():
            messagebox.showwarning("创建分支", "创建新分支前需要先归档当前目录")
            return
        
        win = Toplevel(self.root)
        win.title("创建新分支")
        win.geometry(f"{int(460 * self.ui_scale)}x{int(190 * self.ui_scale)}")
        win.configure(background=PALETTE["bg"])
        win.transient(self.root)
        win.grab_set()
        win.resizable(False, False)
        win.focus_set()
        
        hint_label = tk.Label(win, text="以当前分支最新归档为基线创建新分支，新分支版本号从 1 开始独立递增，\n创建后自动切换到新分支。",
                              wraplength=int(420 * self.ui_scale), justify="left",
                              font=_font(12), background=PALETTE["hint_bg"], foreground=PALETTE["hint_text"],
                              padx=12, pady=8)
        hint_label.pack(pady=(15, 8), padx=20)
        
        entry_frame = ttk.Frame(win)
        entry_frame.pack(fill="x", padx=20, pady=(5, 8))
        ttk.Label(entry_frame, text="分支名称:").pack(side="left", padx=5)
        entry = ttk.Entry(entry_frame, width=30)
        entry.pack(side="left", fill="x", expand=True)
        
        err_label = ttk.Label(win, text="", foreground=PALETTE["msg_danger"], wraplength=int(420 * self.ui_scale))
        err_label.pack(fill="x", padx=20)
        
        def confirm(event=None):
            name = entry.get()
            ok, result = self.vc.validate_branch_name(name)
            if not ok:
                err_label.config(text=result)
                return
            success, msg = self.vc.create_branch(result)
            if success:
                win.destroy()
                self._set_message(msg, "success")
                self.refresh_branch_label()
                self.refresh_versions()
                self.refresh_operation_log()
                self.refresh_status()
            else:
                err_label.config(text=msg)
        
        def cancel():
            win.destroy()
        
        btn_frame = ttk.Frame(win)
        btn_frame.pack(side="bottom", pady=12)
        ttk.Button(btn_frame, text="创建", command=confirm, style="FVAA.Blue.TButton", width=10).pack(side="left", padx=10)
        ttk.Button(btn_frame, text="取消", command=cancel, style="FVAA.Gray.TButton", width=10).pack(side="left", padx=10)
        entry.bind("<Return>", confirm)
        entry.focus_set()
    
    def switch_branch(self):
        """切换分支：无变更文件时弹窗选择分支，切换后工作目录恢复为该分支最新归档"""
        if not self.vc:
            self._set_message("请先选择工作目录", "danger")
            return
        if self.vc.has_changes():
            messagebox.showwarning("切换分支", "切换分支前需要先归档当前目录")
            return
        
        branches = self.vc.list_branches()
        if len(branches) <= 1:
            self._set_message("当前只有一个分支，无需切换", "neutral")
            return
        
        win = Toplevel(self.root)
        win.title("切换分支")
        win.geometry(f"{int(560 * self.ui_scale)}x{int(380 * self.ui_scale)}")
        win.configure(background=PALETTE["bg"])
        win.transient(self.root)
        win.grab_set()
        win.focus_set()
        
        hint_label = tk.Label(win, text="请选择要切换到的分支（切换后工作目录文件将恢复为该分支最新归档）：",
                              wraplength=int(520 * self.ui_scale), justify="left",
                              font=_font(12), background=PALETTE["hint_bg"], foreground=PALETTE["hint_text"],
                              padx=12, pady=8)
        hint_label.pack(pady=(15, 8), padx=20, anchor="w", side="top")
        
        tree_frame = ttk.Frame(win)
        tree_frame.pack(fill="both", expand=True, padx=20, pady=(5, 8), side="top")
        tree = ttk.Treeview(tree_frame, columns=("name", "time"), show="headings", height=8)
        tree.heading("name", text="分支名称", anchor="center")
        tree.heading("time", text="最后归档时间", anchor="center")
        tree.column("name", width=int(240 * self.ui_scale), anchor="center", stretch=True)
        tree.column("time", width=int(240 * self.ui_scale), anchor="center", stretch=True)
        yscroll = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview, style="Custom.Vertical.TScrollbar")
        tree.configure(yscrollcommand=yscroll.set)
        tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)
        
        # iid 直接使用分支名，便于选中后取回
        for b in branches:
            display_name = b['name'] + ("（当前分支）" if b['is_current'] else "")
            time_text = b['last_archive_time'] or "尚未归档"
            tree.insert("", "end", iid=b['name'], values=(display_name, time_text))
        
        def confirm():
            selected = tree.selection()
            if not selected:
                messagebox.showinfo("切换分支", "请先选择要切换到的分支", parent=win)
                return
            branch_name = selected[0]
            success, msg = self.vc.switch_branch(branch_name)
            if success:
                win.destroy()
                self._set_message(msg, "success")
                self.refresh_branch_label()
                self.refresh_versions()
                self.refresh_operation_log()
                self.refresh_status()
            else:
                messagebox.showwarning("切换分支", msg, parent=win)
        
        def cancel():
            win.destroy()
        
        btn_frame = ttk.Frame(win)
        btn_frame.pack(side="bottom", pady=12)
        ttk.Button(btn_frame, text="切换", command=confirm, style="FVAA.Blue.TButton", width=10).pack(side="left", padx=10)
        ttk.Button(btn_frame, text="取消", command=cancel, style="FVAA.Gray.TButton", width=10).pack(side="left", padx=10)
        tree.bind("<Double-1>", lambda event: confirm())

    def show_branch_history(self):
        """弹窗展示分支历史图谱（类 Git 分支图：分支按列、版本较新在上、连线按继承关系）"""
        if not self.vc:
            self._set_message("请先选择工作目录", "danger")
            return

        win = Toplevel(self.root)
        win.title("分支历史")
        win.geometry(f"{int(900 * self.ui_scale)}x{int(620 * self.ui_scale)}")
        win.minsize(int(680 * self.ui_scale), int(480 * self.ui_scale))
        win.configure(background=PALETTE["bg"])
        win.transient(self.root)
        win.resizable(True, True)
        win.focus_set()

        def refresh():
            self._draw_branch_graph(canvas)

        # 底部按钮栏 (先pack side="bottom" 确保即使窗口缩小也始终可见)
        btn_frame = ttk.Frame(win)
        btn_frame.pack(fill="x", side="bottom", pady=12, padx=20)
        ttk.Button(btn_frame, text="刷新", command=refresh, style="FVAA.Blue.TButton", width=10).pack(side="right", padx=10)
        ttk.Button(btn_frame, text="关闭", command=win.destroy, style="FVAA.Gray.TButton", width=10).pack(side="right", padx=6)

        hint_label = tk.Label(win, text="每列代表一个分支，节点为该分支的归档版本（空心为尚未归档的分支创建点），较新版本在上、较早版本在下；连线表示版本间的继承关系：同列弧线为恢复旧版本后存档的跳跃继承，跨列曲线为分支分叉来源；当前分支加粗高亮，点击节点可查看版本详情。",
                              wraplength=int(860 * self.ui_scale), justify="left",
                              font=_font(12), background=PALETTE["hint_bg"], foreground=PALETTE["hint_text"],
                              padx=12, pady=8)
        hint_label.pack(pady=(12, 8), padx=20, anchor="w", side="top")

        canvas_frame = ttk.Frame(win)
        canvas_frame.pack(fill="both", expand=True, padx=20, pady=(5, 8), side="top")
        canvas = tk.Canvas(canvas_frame, bg=PALETTE["panel"], highlightthickness=0)
        yscroll = ttk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview, style="Custom.Vertical.TScrollbar")
        xscroll = ttk.Scrollbar(canvas_frame, orient="horizontal", command=canvas.xview, style="Custom.Horizontal.TScrollbar")
        canvas.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        canvas_frame.grid_rowconfigure(0, weight=1)
        canvas_frame.grid_columnconfigure(0, weight=1)

        def on_wheel(event):
            canvas.yview_scroll(-1 * int(event.delta / 120), "units")

        # 仅当鼠标位于图谱上方时响应滚轮
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", on_wheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        refresh()

        def on_destroy(event):
            if event.widget is win:
                canvas.unbind_all("<MouseWheel>")
        win.bind("<Destroy>", on_destroy)

    def _draw_branch_graph(self, canvas):
        """在 Canvas 上绘制类 Git 分支图：分支为列、版本节点较新在上、较早在下；
        连线严格按版本继承关系绘制（同列直线/弧线、跨列平滑曲线）"""
        canvas.delete("all")
        branches = self.vc.get_branch_graph()
        if not branches:
            canvas.create_text(20, 20, text="没有分支数据", fill=PALETTE["text"], font=_font(12), anchor="nw")
            canvas.configure(scrollregion=(0, 0, 400, 80))
            return

        lane_gap = 120
        row_h = 34
        left = 50
        header_y = 26
        top = 60

        lane_of = {b['name']: i for i, b in enumerate(branches)}
        color_of = {b['name']: self.GRAPH_COLORS[i % len(self.GRAPH_COLORS)] for i, b in enumerate(branches)}
        is_current = {b['name']: b['is_current'] for b in branches}
        base_of = {b['name']: b.get('base_ref') for b in branches}

        # 收集节点：各分支版本 + 未归档分支的占位节点（分支创建点），按时间降序（较新在上，缺失时间置底）
        nodes = []
        for b in branches:
            lane = lane_of[b['name']]
            if b['versions']:
                for v in b['versions']:
                    nodes.append({'time': v['time'] or '0000', 'lane': lane, 'version': v['version'],
                                  'branch': b['name'], 'info': v})
            else:
                nodes.append({'time': b['created_time'] or '0000', 'lane': lane, 'version': 0,
                              'branch': b['name'], 'info': None})
        nodes.sort(key=lambda n: (n['time'], n['lane'], n['version']), reverse=True)
        for i, n in enumerate(nodes):
            n['row'] = i
            n['x'] = left + n['lane'] * lane_gap
            n['y'] = top + i * row_h

        node_index = {(n['branch'], n['version']): n for n in nodes}
        rows_by_branch = {}
        for n in nodes:
            rows_by_branch.setdefault(n['branch'], []).append(n['row'])

        # 列表头：分支名称（当前分支高亮）
        for b in branches:
            x = left + lane_of[b['name']] * lane_gap
            name = b['name'] if len(b['name']) <= 10 else b['name'][:9] + "…"
            header = name + ("（当前）" if b['is_current'] else "")
            fill = PALETTE["header_text"] if b['is_current'] else color_of[b['name']]
            canvas.create_text(x, header_y, text=header, fill=fill, font=_font(11, True))

        # 继承连线：父版本节点 → 子版本节点（父在下、子在上）
        def draw_edge(pnode, cnode):
            """同分支相邻版本间为垂直直线；跳跃继承（如恢复旧版本后存档）为向列左侧外拱的弧线；
            跨分支继承（分支分叉）为平滑曲线"""
            color = color_of[cnode['branch']]
            width = 3 if is_current[cnode['branch']] else 2
            if pnode['branch'] == cnode['branch']:
                x = cnode['x']
                # 父子节点行间是否存在同分支的其他版本节点（被跳过的版本）
                skipped = any(cnode['row'] < r < pnode['row'] for r in rows_by_branch[cnode['branch']])
                if not skipped:
                    canvas.create_line(x, pnode['y'], x, cnode['y'], fill=color, width=width)
                else:
                    mid_y = (pnode['y'] + cnode['y']) / 2
                    canvas.create_line(x, pnode['y'], x - 16, mid_y, x, cnode['y'],
                                       smooth=True, fill=color, width=width)
            else:
                mid_y = pnode['y'] + (cnode['y'] - pnode['y']) * 0.5
                canvas.create_line(pnode['x'], pnode['y'], pnode['x'], mid_y, cnode['x'], cnode['y'],
                                   smooth=True, fill=color, width=width)

        for n in nodes:
            if n['info'] is None:
                # 未归档分支的占位节点：从分支基线版本引出连线
                base = base_of.get(n['branch'])
                if not base:
                    continue
                pnode = node_index.get((base.get('branch'), base.get('version')))
            else:
                parent = n['info'].get('parent') or {}
                pnode = node_index.get((parent.get('branch'), parent.get('version')))
            if pnode is None or pnode is n:
                continue
            draw_edge(pnode, n)

        # 版本节点 + 标签
        for n in nodes:
            x, y = n['x'], n['y']
            color = color_of[n['branch']]
            cur = is_current[n['branch']]
            if n['info'] is None:
                canvas.create_oval(x - 5, y - 5, x + 5, y + 5, outline=color, width=2)
                canvas.create_text(x + 12, y, text="尚未归档（分支创建点）", fill=PALETTE["text_dim"],
                                   font=_font(10), anchor="w")
                continue
            v = n['info']
            r = 7 if cur else 6
            oid = canvas.create_oval(x - r, y - r, x + r, y + r, fill=color,
                                     outline=PALETTE["header_text"] if cur else color, width=1)
            label = f"v{v['version']}"
            if v['tags']:
                tag_text = '、'.join(v['tags'])
                if len(tag_text) > 8:
                    tag_text = tag_text[:7] + "…"
                label += f" [{tag_text}]"
            canvas.create_text(x + 14, y, text=label, fill=PALETTE["text"], font=_font(10), anchor="w")
            detail = {'branch': n['branch'], 'version': v['version'], 'time': v['time'],
                      'tags': v['tags'], 'description': v['description']}
            canvas.tag_bind(oid, "<Button-1>", lambda e, d=detail: self._show_graph_node_detail(d))
            canvas.tag_bind(oid, "<Enter>", lambda e: canvas.configure(cursor="hand2"))
            canvas.tag_bind(oid, "<Leave>", lambda e: canvas.configure(cursor=""))

        width = max(left + len(branches) * lane_gap + 30, 700)
        height = max(top + len(nodes) * row_h + 20, 400)
        canvas.configure(scrollregion=(0, 0, width, height))

    def _show_graph_node_detail(self, info):
        """弹窗展示分支图谱中某个版本节点的详情（说明渲染 Markdown）"""
        win = Toplevel(self.root)
        win.title(f"分支 {info['branch']} · 版本 {info['version']} 详情")
        win.geometry(f"{int(620 * self.ui_scale)}x{int(480 * self.ui_scale)}")
        win.configure(background=PALETTE["bg"])
        win.resizable(True, True)
        win.transient(self.root)
        win.focus_set()

        meta = ttk.Frame(win)
        meta.pack(fill="x", padx=20, pady=(15, 0))
        rows = [
            ("分支", info['branch']),
            ("版本号", f"v{info['version']}"),
            ("时间", info['time'] or "-"),
            ("标签", "、".join(info['tags']) if info['tags'] else "无"),
        ]
        for i, (k, val) in enumerate(rows):
            ttk.Label(meta, text=f"{k}：", font=_font(11, True)).grid(row=i, column=0, sticky="ne", padx=(0, 8), pady=2)
            ttk.Label(meta, text=val, font=_font(11)).grid(row=i, column=1, sticky="w", pady=2)

        ttk.Label(win, text="存档说明：", font=_font(11, True)).pack(fill="x", padx=20, pady=(10, 2))
        desc = (info.get('description') or '').strip()
        if desc:
            html = markdown.markdown(desc, extensions=['tables', 'fenced_code', 'nl2br'])
            view = HTMLScrolledText(win, html=html, background=PALETTE["panel"])
            self._style_html_view(view)
            view.pack(fill="both", expand=True, padx=20, pady=(0, 15))
        else:
            ttk.Label(win, text="无说明", foreground=PALETTE["text_dim"]).pack(anchor="w", padx=20)
    
    def monitor_thread(self):
        while self.monitoring:
            self.root.after(0, self.refresh_status)
            time.sleep(2)
    
    def toggle_monitor(self):
        if not self.vc:
            self._set_message("请先选择工作目录", "danger")
            return
        self.monitoring = not self.monitoring
        if self.monitoring:
            self.monitor_btn.configure(text="停止监视", style="FVAA.Red.TButton")
            threading.Thread(target=self.monitor_thread, daemon=True).start()
        else:
            self.monitor_btn.configure(text="开始监视", style="FVAA.Teal.TButton")

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
    # 高分屏适配：按系统 DPI 渲染（2K 下字体与界面元素自动放大）
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_DPI_AWARE
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass
    app = ttk.Window(themename="cyborg", title="Kit文件存档助手")
    # 以系统 DPI 设置 tk 缩放（pt 字号随缩放因子自适应放大）
    try:
        import ctypes
        app.tk.call("tk", "scaling", ctypes.windll.user32.GetDpiForSystem() / 72.0)
    except Exception:
        pass
    VersionControlApp(app)
    app.mainloop()