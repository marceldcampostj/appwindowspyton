import tkinter as tk
from tkinter import scrolledtext, ttk, messagebox
import asyncio
import threading
import aiomysql
from datetime import datetime
from tkinter import font as tkfont
import platform
import pystray
from PIL import Image, ImageDraw
import json
import os
import sys

CONFIG_FILE = os.path.join(os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else __file__), "config.json")

DEFAULT_DB_LOCAL = {
    "host": "localhost",
    "port": 3306,
    "user": "root",
    "password": "mca144000",
    "db": "bdloja7pedra90",
    "charset": "latin1",
    "use_unicode": True,
}
DEFAULT_DB_REMOTO = {
    "host": "148.230.72.38",
    "port": 3306,
    "user": "root",
    "password": "mca144000",
    "db": "bdloja7pedra90",
    "charset": "latin1",
    "use_unicode": True,
}

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
            db_local = {**DEFAULT_DB_LOCAL, **data.get("db_local", {})}
            db_remoto = {**DEFAULT_DB_REMOTO, **data.get("db_remoto", {})}
            db_local["port"] = int(db_local["port"])
            db_remoto["port"] = int(db_remoto["port"])
            db_local["use_unicode"] = bool(db_local.get("use_unicode", True))
            db_remoto["use_unicode"] = bool(db_remoto.get("use_unicode", True))
            auto_start = bool(data.get("auto_start_tray", False))
            return db_local, db_remoto, auto_start
        except Exception:
            pass
    return dict(DEFAULT_DB_LOCAL), dict(DEFAULT_DB_REMOTO), False

def save_config(db_local, db_remoto, auto_start_tray=False):
    with open(CONFIG_FILE, "w") as f:
        json.dump({"db_local": db_local, "db_remoto": db_remoto, "auto_start_tray": auto_start_tray}, f, indent=2)

DB_LOCAL, DB_REMOTO, AUTO_START_TRAY = load_config()

class SincronizadorApp:
    def __init__(self, root):
        self.root = root
        self.sync_active = False
        self.tray_icon = None
        self.tray_thread = None
        self.produto_sync_last = None
        self.setup_ui()
        self.setup_tray_icon()
        self.root.protocol('WM_DELETE_WINDOW', self.minimize_to_tray)

        if AUTO_START_TRAY:
            self.root.after(500, self._auto_start_and_tray)

    def _auto_start_and_tray(self):
        self.start_sync()
        self.minimize_to_tray()

    def _load_tray_image(self):
        ico_path = os.path.join(
            getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__))),
            '788.ico'
        )
        try:
            img = Image.open(ico_path).convert('RGBA').resize((64, 64))
            return img
        except Exception:
            color = (76, 175, 80) if self.sync_active else (244, 67, 54)
            img = Image.new('RGBA', (64, 64), color)
            return img

    def setup_tray_icon(self):
        image = self._load_tray_image()
        menu = pystray.Menu(
            pystray.MenuItem('Abrir', self.restore_from_tray),
            pystray.MenuItem(
                lambda item: 'Parar Sincronização' if self.sync_active else 'Iniciar Sincronização',
                self._tray_toggle_sync
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Sair', self.quit_application)
        )
        if self.tray_icon:
            self.tray_icon.stop()
        tooltip = "Sincronizador — Ativo" if self.sync_active else "Sincronizador — Parado"
        self.tray_icon = pystray.Icon("sync_app", image, tooltip, menu)

    def _tray_toggle_sync(self, icon=None, item=None):
        if self.sync_active:
            self.root.after(0, self.stop_sync)
        else:
            self.root.after(0, self.start_sync)
        self.root.after(200, self.setup_tray_icon)

    def minimize_to_tray(self):
        self.root.withdraw()
        self.setup_tray_icon()
        if self.tray_thread and self.tray_thread.is_alive():
            self.tray_thread.join()
        self.tray_thread = threading.Thread(target=self.run_tray_icon, daemon=True)
        self.tray_thread.start()

    def run_tray_icon(self):
        if self.tray_icon:
            self.tray_icon.run()

    def restore_from_tray(self, icon=None, item=None):
        if self.tray_icon:
            self.tray_icon.stop()
        self.root.after(0, self.root.deiconify)
        self.root.after(0, self.root.lift)

    def quit_application(self, icon=None, item=None):
        self.sync_active = False
        if self.tray_icon:
            self.tray_icon.stop()
        self.root.after(0, self.root.destroy)

    def setup_ui(self):
        self.root.title("Sincronizador de Bancos de Dados")
        self.root.configure(bg="#f5f5f5")
        if platform.system() == "Windows":
            try:
                self.root.iconbitmap('788.ico')
            except:
                pass
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.setup_styles()
        self.setup_geometry()
        self.create_header()
        self.create_log_area()
        self.create_progress_bar()
        self.create_buttons()
        self.create_footer()

    def setup_styles(self):
        self.colors = {
            "primary": "#2196F3",
            "success": "#4CAF50",
            "danger": "#F44336",
            "warning": "#FFC107",
            "info": "#00BCD4",
            "dark": "#212121",
            "light": "#f5f5f5",
            "text": "#333333"
        }
        self.title_font = tkfont.Font(family="Segoe UI", size=12, weight="bold")
        self.text_font = tkfont.Font(family="Segoe UI", size=10)
        self.style.configure('Accent.TButton', foreground='white', background=self.colors["primary"], font=self.text_font, padding=6)
        self.style.map('Accent.TButton', background=[('active', self.colors["primary"]), ('pressed', '#0D47A1')])
        self.style.configure('danger.TButton', foreground='white', background=self.colors["danger"], font=self.text_font, padding=6)
        self.style.map('danger.TButton', background=[('active', self.colors["danger"]), ('pressed', '#B71C1C')])
        self.style.configure('TLabelFrame', background=self.colors["light"], bordercolor="#ddd", relief=tk.GROOVE)
        self.style.configure('TFrame', background=self.colors["light"])

    def setup_geometry(self):
        window_width = 1000
        window_height = 700
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width // 2) - (window_width // 2)
        y = (screen_height // 2) - (window_height // 2)
        self.root.geometry(f'{window_width}x{window_height}+{x}+{y}')
        self.root.minsize(800, 600)

    def create_header(self):
        header_frame = ttk.Frame(self.root)
        header_frame.pack(fill=tk.X, padx=10, pady=(10, 5))
        title_label = ttk.Label(header_frame, text="🔄 Sincronizador de Bancos de Dados", font=self.title_font, foreground=self.colors["dark"])
        title_label.pack(side=tk.LEFT)
        self.status_label = ttk.Label(header_frame, text="🔴 Sincronização Parada", background=self.colors["danger"], foreground="white", font=self.text_font, padding=(10, 5), anchor=tk.CENTER, borderwidth=1, relief=tk.SOLID)
        self.status_label.pack(side=tk.RIGHT, padx=(10, 0))

    def create_log_area(self):
        log_frame = ttk.LabelFrame(self.root, text=" Log de Atividades ", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.memo = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, font=self.text_font, padx=10, pady=10, bg="#ffffff", insertbackground=self.colors["dark"], foreground=self.colors["text"])
        self.memo.pack(fill=tk.BOTH, expand=True)
        self.setup_text_tags()

    def setup_text_tags(self):
        tags_config = {
            "info": {"foreground": self.colors["info"]},
            "success": {"foreground": self.colors["success"]},
            "error": {"foreground": self.colors["danger"], "background": "#FFEBEE"},
            "warning": {"foreground": self.colors["warning"]},
            "process": {"foreground": self.colors["primary"]},
            "update": {"foreground": "#FF9800"},
            "insert": {"foreground": "#9C27B0"},
            "header": {"font": (self.text_font.actual("family"), self.text_font.actual("size"), "bold")}
        }
        for tag, config in tags_config.items():
            self.memo.tag_config(tag, **config)

    def create_progress_bar(self):
        progress_frame = ttk.Frame(self.root)
        progress_frame.pack(fill=tk.X, padx=10, pady=(5, 0))
        self.progress_bar = ttk.Progressbar(progress_frame, orient=tk.HORIZONTAL, mode='determinate', length=100, style='green.Horizontal.TProgressbar' if platform.system() == 'Windows' else '')
        self.progress_bar.pack(fill=tk.X, expand=True)
        self.progress_label = ttk.Label(progress_frame, text="Pronto para iniciar", foreground=self.colors["dark"], font=(self.text_font.actual("family"), 8))
        self.progress_label.pack(side=tk.TOP, anchor=tk.W)

    def create_buttons(self):
        buttons_frame = ttk.Frame(self.root)
        buttons_frame.pack(fill=tk.X, padx=10, pady=(10, 5))
        self.start_btn = ttk.Button(buttons_frame, text="🚀 Iniciar Sincronização", command=self.start_sync, style="Accent.TButton")
        self.start_btn.pack(side=tk.LEFT, padx=(0, 10), fill=tk.X, expand=True)
        self.stop_btn = ttk.Button(buttons_frame, text="⏹ Parar Sincronização", command=self.stop_sync, style="danger.TButton")
        self.stop_btn.pack(side=tk.LEFT, fill=tk.X, expand=True)
        clear_btn = ttk.Button(buttons_frame, text="🧹 Limpar Log", command=self.clear_log)
        clear_btn.pack(side=tk.LEFT, padx=(10, 0), fill=tk.X, expand=True)
        config_btn = ttk.Button(buttons_frame, text="⚙️ Configurações", command=self.open_config_window)
        config_btn.pack(side=tk.LEFT, padx=(10, 0), fill=tk.X, expand=True)

    def open_config_window(self):
        win = tk.Toplevel(self.root)
        win.title("Configurações")
        win.resizable(False, False)
        win.grab_set()
        win_w, win_h = 520, 540
        sx = self.root.winfo_x() + (self.root.winfo_width() // 2) - (win_w // 2)
        sy = self.root.winfo_y() + (self.root.winfo_height() // 2) - (win_h // 2)
        win.geometry(f"{win_w}x{win_h}+{sx}+{sy}")
        win.configure(bg="#f5f5f5")

        fields_local = {}
        fields_remoto = {}

        def make_db_frame(parent, title, db_dict, fields_out):
            frame = ttk.LabelFrame(parent, text=f" {title} ", padding=10)
            frame.pack(fill=tk.X, padx=10, pady=5)
            labels = [("Host", "host"), ("Porta", "port"), ("Usuário", "user"),
                      ("Senha", "password"), ("Banco", "db"), ("Charset", "charset")]
            for label, key in labels:
                row = ttk.Frame(frame)
                row.pack(fill=tk.X, pady=2)
                ttk.Label(row, text=label + ":", width=10, anchor=tk.W).pack(side=tk.LEFT)
                show = "*" if key == "password" else ""
                var = tk.StringVar(value=str(db_dict.get(key, "")))
                entry = ttk.Entry(row, textvariable=var, show=show, width=35)
                entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
                fields_out[key] = var

        make_db_frame(win, "Banco Local", DB_LOCAL, fields_local)
        make_db_frame(win, "Banco Remoto", DB_REMOTO, fields_remoto)

        startup_frame = ttk.LabelFrame(win, text=" Inicialização ", padding=10)
        startup_frame.pack(fill=tk.X, padx=10, pady=5)
        auto_start_var = tk.BooleanVar(value=AUTO_START_TRAY)
        ttk.Checkbutton(
            startup_frame,
            text="Iniciar sincronizando automaticamente e minimizar para a bandeja",
            variable=auto_start_var
        ).pack(anchor=tk.W)

        def on_save():
            global DB_LOCAL, DB_REMOTO, AUTO_START_TRAY
            try:
                new_local = {
                    "host": fields_local["host"].get().strip(),
                    "port": int(fields_local["port"].get().strip()),
                    "user": fields_local["user"].get().strip(),
                    "password": fields_local["password"].get(),
                    "db": fields_local["db"].get().strip(),
                    "charset": fields_local["charset"].get().strip(),
                    "use_unicode": True,
                }
                new_remoto = {
                    "host": fields_remoto["host"].get().strip(),
                    "port": int(fields_remoto["port"].get().strip()),
                    "user": fields_remoto["user"].get().strip(),
                    "password": fields_remoto["password"].get(),
                    "db": fields_remoto["db"].get().strip(),
                    "charset": fields_remoto["charset"].get().strip(),
                    "use_unicode": True,
                }
                AUTO_START_TRAY = auto_start_var.get()
                save_config(new_local, new_remoto, AUTO_START_TRAY)
                DB_LOCAL.update(new_local)
                DB_REMOTO.update(new_remoto)
                messagebox.showinfo("Configurações", "Configurações salvas com sucesso!", parent=win)
                win.destroy()
            except ValueError:
                messagebox.showerror("Erro", "Porta deve ser um número inteiro.", parent=win)

        btn_frame = ttk.Frame(win)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
        ttk.Button(btn_frame, text="Salvar", command=on_save, style="Accent.TButton").pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(btn_frame, text="Cancelar", command=win.destroy).pack(side=tk.RIGHT)

    def create_footer(self):
        footer_frame = ttk.Frame(self.root)
        footer_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        version_label = ttk.Label(footer_frame, text="Versão 2.1 © 2025 - DynamicApps Solutions", foreground=self.colors["dark"], font=(self.text_font.actual("family"), 8))
        version_label.pack(side=tk.RIGHT)

    def clear_log(self):
        self.memo.delete(1.0, tk.END)

    def start_sync(self):
        if not self.sync_active:
            self.sync_active = True
            threading.Thread(target=lambda: asyncio.run(self.run_async_sync()), daemon=True).start()

    def stop_sync(self):
        if self.sync_active:
            self.sync_active = False
            self.log_message("Sincronização sendo parada...", "warning")

    async def run_async_sync(self):
        self.produto_sync_last = datetime.now()
        while self.sync_active:
            try:
                pool_local, pool_remoto = await self.create_pool_with_retry()
                now = datetime.now()
                if (now - self.produto_sync_last).total_seconds() >= 180 or self.produto_sync_last is None:
                    await self.sincronizar_produtos(pool_local, pool_remoto)
                    self.produto_sync_last = now
                await self.sincronizar_lancamentos_caixa(pool_local, pool_remoto)
                await self.sincronizar_vendas(pool_local, pool_remoto)
            except Exception as e:
                self.log_message(f"❌ Erro crítico: {str(e)}. Tentando novamente em 30 segundos...", "error")
                await asyncio.sleep(30)
                continue
            if self.sync_active:
                await asyncio.sleep(60)
        if pool_local:
            pool_local.close()
            await pool_local.wait_closed()
        if pool_remoto:
            pool_remoto.close()
            await pool_remoto.wait_closed()
        self.update_ui_status(False)

    async def create_pool_with_retry(self):
        max_attempts = 5
        attempt = 0
        wait_time = 5
        while attempt < max_attempts and self.sync_active:
            try:
                pool_local = await aiomysql.create_pool(
                    host=DB_LOCAL['host'],
                    port=DB_LOCAL['port'],
                    user=DB_LOCAL['user'],
                    password=DB_LOCAL['password'],
                    db=DB_LOCAL['db'],
                    charset=DB_LOCAL['charset'],
                    use_unicode=DB_LOCAL['use_unicode'],
                    minsize=1, maxsize=10
                )
                pool_remoto = await aiomysql.create_pool(
                    host=DB_REMOTO['host'],
                    port=DB_REMOTO['port'],
                    user=DB_REMOTO['user'],
                    password=DB_REMOTO['password'],
                    db=DB_REMOTO['db'],
                    charset=DB_REMOTO['charset'],
                    use_unicode=DB_REMOTO['use_unicode'],
                    minsize=1, maxsize=10
                )
                self.log_message(
                    f"✅ Conexão estabelecida | Local: {DB_LOCAL['host']}:{DB_LOCAL['port']}/{DB_LOCAL['db']} | "
                    f"Remoto: {DB_REMOTO['host']}:{DB_REMOTO['port']}/{DB_REMOTO['db']}",
                    "success"
                )
                return pool_local, pool_remoto
            except Exception as e:
                attempt += 1
                self.log_message(f"⚠️ Tentativa {attempt} de {max_attempts}: Falha ao conectar - {str(e)}", "warning")
                if attempt < max_attempts:
                    self.log_message(f"⏳ Aguardando {wait_time} segundos antes de tentar novamente...", "info")
                    await asyncio.sleep(wait_time)
                    wait_time *= 2
        raise Exception("Não foi possível estabelecer conexão com os bancos de dados após várias tentativas")

    # ========== PRODUTO ==========
    async def sincronizar_produtos(self, pool_local, pool_remoto):
        self.log_message("🔄 Iniciando sincronização de produtos...", "header")
        async with pool_local.acquire() as conn_check:
            async with conn_check.cursor(aiomysql.DictCursor) as cursor_check:
                await cursor_check.execute("SELECT COUNT(*) as total FROM produto WHERE enviado = 'N' OR enviado IS NULL")
                result = await cursor_check.fetchone()
                self.log_message(f"🔎 Verificação: Existem {result['total']} produtos não enviados", "info")
        async with pool_local.acquire() as conn_local, pool_remoto.acquire() as conn_remoto:
            async with conn_local.cursor(aiomysql.DictCursor) as cursor_local, conn_remoto.cursor(aiomysql.DictCursor) as cursor_remoto:
                await cursor_local.execute("SET NAMES latin1;")
                await cursor_remoto.execute("SET NAMES latin1;")
                self.log_message("🔍 Buscando produtos para sincronizar do banco local...", "info")
                await cursor_local.execute("""
                    SELECT * FROM produto 
                    WHERE enviado = 'N' OR enviado IS NULL
                    ORDER BY id DESC 
                    LIMIT 100
                """)
                produtos = await cursor_local.fetchall()
                total_produtos = len(produtos)
                self.log_message(f"📊 Total de produtos encontrados para sincronizar: {total_produtos}", "info")
                if total_produtos == 0:
                    self.log_message("ℹ️ Nenhum produto novo encontrado.", "info")
                    return
                self.update_progress_bar(0, total_produtos)
                for i, produto in enumerate(produtos, 1):
                    if not self.sync_active:
                        break
                    id_produto = produto["id"]
                    self.log_message(f"📦 Processando produto Nº {id_produto} ({i}/{total_produtos})...", "process")
                    self.update_progress_bar(i)
                    try:
                        await cursor_remoto.execute("SELECT id FROM produto WHERE id = %s", (id_produto,))
                        existe = await cursor_remoto.fetchone()
                        if existe:
                            self.log_message("🔄 Atualizando produto existente...", "update")
                            await self.atualizar_produto(cursor_remoto, produto)
                        else:
                            self.log_message("⬆️ Enviando novo produto...", "insert")
                            await self.inserir_produto(cursor_remoto, produto)
                        await conn_remoto.commit()
                        self.log_message(f"✅ Produto Nº {id_produto} sincronizado com sucesso!", "success")
                        await self.marcar_como_enviado(cursor_local, id_produto)
                    except Exception as e:
                        await conn_remoto.rollback()
                        self.log_message(f"❌ Erro no produto {id_produto}: {str(e)}", "error")
                        continue
                    await asyncio.sleep(0.5)
                self.log_message("🏁 Sincronização de produtos concluída!", "success")

    async def marcar_como_enviado(self, cursor, id_produto):
        try:
            await cursor.execute("""
                UPDATE produto 
                SET enviado = 'S' 
                WHERE id = %s AND (enviado = 'N' OR enviado IS NULL)
            """, (id_produto,))
            rows_affected = cursor.rowcount
            if rows_affected == 0:
                self.log_message(f"⚠️ Produto {id_produto} não foi marcado como enviado (já estava marcado?)", "warning")
            else:
                await cursor.connection.commit()
                self.log_message(f"✓ Produto {id_produto} marcado como enviado", "success")
        except Exception as e:
            self.log_message(f"❌ Erro ao marcar produto {id_produto} como enviado: {str(e)}", "error")
            raise

    async def inserir_produto(self, cursor, produto):
        fields = list(produto.keys())
        fields_str = ", ".join(fields)
        values_str = ", ".join([f"%({k})s" for k in fields])
        await cursor.execute(
            f"INSERT INTO produto ({fields_str}) VALUES ({values_str})",
            produto
        )

    async def atualizar_produto(self, cursor, produto):
        fields = [f"{field} = %({field})s" for field in produto if field != "id"]
        update_str = ", ".join(fields)
        await cursor.execute(
            f"UPDATE produto SET {update_str} WHERE id = %(id)s",
            produto
        )

    # ========== LANCAMENTOS CAIXA ==========
    async def sincronizar_lancamentos_caixa(self, pool_local, pool_remoto):
        self.log_message("🔄 Iniciando sincronização de lançamentos de caixa...", "header")
        async with pool_local.acquire() as conn_check:
            async with conn_check.cursor(aiomysql.DictCursor) as cursor_check:
                await cursor_check.execute("SELECT COUNT(*) as total FROM lancamentoscaixa WHERE transferido = 'N' OR transferido IS NULL")
                result = await cursor_check.fetchone()
                self.log_message(f"🔎 Verificação: Existem {result['total']} lançamentos não transferidos", "info")
        async with pool_local.acquire() as conn_local, pool_remoto.acquire() as conn_remoto:
            async with conn_local.cursor(aiomysql.DictCursor) as cursor_local, conn_remoto.cursor(aiomysql.DictCursor) as cursor_remoto:
                await cursor_local.execute("SET NAMES latin1;")
                await cursor_remoto.execute("SET NAMES latin1;")
                self.log_message("🔍 Buscando lançamentos para sincronizar do banco local...", "info")
                await cursor_local.execute("""
                    SELECT id, idusuario, idcaixa, dataemissao, tipomovimento, ndoc, valor, cadastro,
                    observacoes, parcela, id_origem, sigla_origem, hora, situacao, descricao_recebimento,
                    id_plano_contas, id_movimento, vencimento, id_pagto, desc_tipo, valor_pago, data_pagamento,
                    taxa_cartao 
                    FROM lancamentoscaixa 
                    WHERE transferido = 'N' OR transferido IS NULL
                    ORDER BY id DESC 
                    LIMIT 100
                """)
                dados_locais = await cursor_local.fetchall()
                total_registros = len(dados_locais)
                self.log_message(f"📊 Total de lançamentos encontrados para sincronizar: {total_registros}", "info")
                if total_registros == 0:
                    self.log_message("ℹ️ Nenhum lançamento novo encontrado.", "info")
                    return
                self.update_progress_bar(0, total_registros)
                for i, registro in enumerate(dados_locais, 1):
                    if not self.sync_active:
                        break
                    id_registro = registro["id"]
                    self.log_message(f"📦 Processando lançamento Nº {id_registro} ({i}/{total_registros})...", "process")
                    self.update_progress_bar(i)
                    try:
                        await cursor_remoto.execute("SELECT id FROM lancamentoscaixa WHERE id = %s", (id_registro,))
                        existe = await cursor_remoto.fetchone()
                        if existe:
                            self.log_message("🔄 Atualizando lançamento existente...", "update")
                            await self.atualizar_lancamento(cursor_remoto, registro)
                        else:
                            self.log_message("⬆️ Enviando novo lançamento...", "insert")
                            await self.inserir_lancamento(cursor_remoto, registro)
                        await conn_remoto.commit()
                        self.log_message(f"✅ Lançamento Nº {id_registro} sincronizado com sucesso!", "success")
                        await self.marcar_como_transferido(cursor_local, id_registro, 'lancamentoscaixa')
                    except Exception as e:
                        await conn_remoto.rollback()
                        self.log_message(f"❌ Erro no lançamento {id_registro}: {str(e)}", "error")
                        continue
                    await asyncio.sleep(0.5)
                self.log_message("🏁 Sincronização de lançamentos concluída!", "success")

    async def marcar_como_transferido(self, cursor, id_registro, tabela):
        try:
            await cursor.execute(f"""
                UPDATE {tabela} 
                SET transferido = 'S' 
                WHERE id = %s AND (transferido = 'N' OR transferido IS NULL)
            """, (id_registro,))
            rows_affected = cursor.rowcount
            if rows_affected == 0:
                self.log_message(f"⚠️ Registro {id_registro} da tabela {tabela} não foi marcado como transferido (já estava marcado?)", "warning")
            else:
                await cursor.connection.commit()
                self.log_message(f"✓ Registro {id_registro} da tabela {tabela} marcado como transferido", "success")
        except Exception as e:
            self.log_message(f"❌ Erro ao marcar registro {id_registro} da tabela {tabela} como transferido: {str(e)}", "error")
            raise

    async def inserir_lancamento(self, cursor, registro):
        await cursor.execute("""
            INSERT INTO lancamentoscaixa(
                id, idusuario, idcaixa, dataemissao, tipomovimento, ndoc, valor, cadastro,
                observacoes, parcela, id_origem, sigla_origem, hora, situacao, descricao_recebimento,
                id_plano_contas, id_movimento, vencimento, id_pagto, desc_tipo, valor_pago, data_pagamento,
                taxa_cartao
            ) VALUES (
                %(id)s, %(idusuario)s, %(idcaixa)s, %(dataemissao)s, %(tipomovimento)s, %(ndoc)s, %(valor)s, %(cadastro)s,
                %(observacoes)s, %(parcela)s, %(id_origem)s, %(sigla_origem)s, %(hora)s, %(situacao)s, %(descricao_recebimento)s,
                %(id_plano_contas)s, %(id_movimento)s, %(vencimento)s, %(id_pagto)s, %(desc_tipo)s, %(valor_pago)s, %(data_pagamento)s,
                %(taxa_cartao)s
            )
        """, registro)

    async def atualizar_lancamento(self, cursor, registro):
        await cursor.execute("""
            UPDATE lancamentoscaixa SET
                idusuario = %(idusuario)s,
                idcaixa = %(idcaixa)s,
                dataemissao = %(dataemissao)s,
                tipomovimento = %(tipomovimento)s,
                ndoc = %(ndoc)s,
                valor = %(valor)s,
                cadastro = %(cadastro)s,
                observacoes = %(observacoes)s,
                parcela = %(parcela)s,
                id_origem = %(id_origem)s,
                sigla_origem = %(sigla_origem)s,
                hora = %(hora)s,
                situacao = %(situacao)s,
                descricao_recebimento = %(descricao_recebimento)s,
                id_plano_contas = %(id_plano_contas)s,
                id_movimento = %(id_movimento)s,
                vencimento = %(vencimento)s,
                id_pagto = %(id_pagto)s,
                desc_tipo = %(desc_tipo)s,
                valor_pago = %(valor_pago)s,
                data_pagamento = %(data_pagamento)s,
                taxa_cartao = %(taxa_cartao)s
            WHERE id = %(id)s
        """, registro)

    # ========== VENDAS ==========
    async def sincronizar_vendas(self, pool_local, pool_remoto):
        self.log_message("🔄 Iniciando sincronização de vendas...", "header")
        async with pool_local.acquire() as conn_check:
            async with conn_check.cursor(aiomysql.DictCursor) as cursor_check:
                await cursor_check.execute("SELECT COUNT(*) as total FROM venda WHERE transferido = 'N' OR transferido IS NULL")
                result = await cursor_check.fetchone()
                self.log_message(f"🔎 Verificação: Existem {result['total']} vendas não transferidas", "info")
        async with pool_local.acquire() as conn_local, pool_remoto.acquire() as conn_remoto:
            async with conn_local.cursor(aiomysql.DictCursor) as cursor_local, conn_remoto.cursor(aiomysql.DictCursor) as cursor_remoto:
                await cursor_local.execute("SET NAMES latin1;")
                await cursor_remoto.execute("SET NAMES latin1;")
                self.log_message("🔍 Buscando vendas para sincronizar do banco local...", "info")
                await cursor_local.execute("""
                    SELECT * FROM venda 
                    WHERE transferido = 'N' OR transferido IS NULL
                    ORDER BY id DESC 
                    LIMIT 50
                """)
                vendas = await cursor_local.fetchall()
                total_vendas = len(vendas)
                self.log_message(f"📊 Total de vendas encontradas para sincronizar: {total_vendas}", "info")
                if total_vendas == 0:
                    self.log_message("ℹ️ Nenhuma venda nova encontrada.", "info")
                    return
                self.update_progress_bar(0, total_vendas)
                for i, venda in enumerate(vendas, 1):
                    if not self.sync_active:
                        break
                    id_venda = venda["id"]
                    self.log_message(f"📦 Processando venda Nº {id_venda} ({i}/{total_vendas})...", "process")
                    self.update_progress_bar(i)
                    try:
                        await cursor_remoto.execute("SELECT id FROM venda WHERE id = %s", (id_venda,))
                        existe = await cursor_remoto.fetchone()
                        if existe:
                            self.log_message("🔄 Atualizando venda existente...", "update")
                            await self.atualizar_venda(cursor_remoto, venda)
                        else:
                            self.log_message("⬆️ Enviando nova venda...", "insert")
                            await self.inserir_venda(cursor_remoto, venda)
                        await self.sincronizar_itens_venda(cursor_local, cursor_remoto, id_venda)
                        await conn_remoto.commit()
                        self.log_message(f"✅ Venda Nº {id_venda} sincronizada com sucesso!", "success")
                        await self.marcar_como_transferido(cursor_local, id_venda, 'venda')
                    except Exception as e:
                        await conn_remoto.rollback()
                        self.log_message(f"❌ Erro na venda {id_venda}: {str(e)}", "error")
                        continue
                    await asyncio.sleep(0.5)
                self.log_message("🏁 Sincronização de vendas concluída!", "success")

    async def inserir_venda(self, cursor, venda):
        await cursor.execute("""
            INSERT INTO venda(
                id, idcliente, data, hora, subtotal, desconto, total, idatendente,
                aliqicms, vlbcicms, valoricms, aliqipi, vlipi, vlfrete, vlseguro,
                vloutras, desctotitens, tipo, situacao, troco, aliqicmsst, vlbcicmsst,
                vlicmsst, idempresa, vlPagto, numeromesa, agrupada, npessoas,
                pagtoparcial, servico, identregador, idcaixa, nota, tipooperacaovenda,
                mesa_agrupada, tipo_nota, numero_nf, nome_cliente_sem_cadastro
            ) VALUES (
                %(id)s, %(idcliente)s, %(data)s, %(hora)s, %(subtotal)s, %(desconto)s, %(total)s, %(idatendente)s,
                %(aliqicms)s, %(vlbcicms)s, %(valoricms)s, %(aliqipi)s, %(vlipi)s, %(vlfrete)s, %(vlseguro)s,
                %(vloutras)s, %(desctotitens)s, %(tipo)s, %(situacao)s, %(troco)s, %(aliqicmsst)s, %(vlbcicmsst)s,
                %(vlicmsst)s, %(idempresa)s, %(vlPagto)s, %(numeromesa)s, %(agrupada)s, %(npessoas)s,
                %(pagtoparcial)s, %(servico)s, %(identregador)s, %(idcaixa)s, %(nota)s, %(tipooperacaovenda)s,
                %(mesa_agrupada)s, %(tipo_nota)s, %(numero_nf)s, %(nome_cliente_sem_cadastro)s
            )
        """, venda)    

    async def atualizar_venda(self, cursor, venda):
        await cursor.execute("""
            UPDATE venda SET
                idcliente = %(idcliente)s,
                data = %(data)s,
                hora = %(hora)s,
                subtotal = %(subtotal)s,
                desconto = %(desconto)s,
                total = %(total)s,
                idatendente = %(idatendente)s,
                aliqicms = %(aliqicms)s,
                vlbcicms = %(vlbcicms)s,
                valoricms = %(valoricms)s,
                aliqipi = %(aliqipi)s,
                vlipi = %(vlipi)s,
                vlfrete = %(vlfrete)s,
                vlseguro = %(vlseguro)s,
                vloutras = %(vloutras)s,
                desctotitens = %(desctotitens)s,
                tipo = %(tipo)s,
                situacao = %(situacao)s,
                troco = %(troco)s,
                aliqicmsst = %(aliqicmsst)s,
                vlbcicmsst = %(vlbcicmsst)s,
                vlicmsst = %(vlicmsst)s,
                idempresa = %(idempresa)s,
                vlPagto = %(vlPagto)s,
                numeromesa = %(numeromesa)s,
                agrupada = %(agrupada)s,
                npessoas = %(npessoas)s,
                pagtoparcial = %(pagtoparcial)s,
                servico = %(servico)s,
                identregador = %(identregador)s,
                idcaixa = %(idcaixa)s,
                nota = %(nota)s,
                tipooperacaovenda = %(tipooperacaovenda)s,
                mesa_agrupada = %(mesa_agrupada)s,
                tipo_nota = %(tipo_nota)s,
                numero_nf = %(numero_nf)s,
                nome_cliente_sem_cadastro = %(nome_cliente_sem_cadastro)s
            WHERE id = %(id)s
        """, venda)

    async def sincronizar_itens_venda(self, cursor_local, cursor_remoto, id_venda):
        self.log_message(f"🔍 Buscando itens para a venda Nº {id_venda}...", "info")
        await cursor_local.execute("""
            SELECT * FROM vendaitens 
            WHERE idvenda = %s
            ORDER BY id
        """, (id_venda,))
        itens = await cursor_local.fetchall()
        total_itens = len(itens)
        self.log_message(f"📦 Encontrados {total_itens} itens para a venda Nº {id_venda}", "info")
        for item in itens:
            id_item = item["id"]
            try:
                await cursor_remoto.execute("SELECT id FROM vendaitens WHERE id = %s", (id_item,))
                existe = await cursor_remoto.fetchone()
                if existe:
                    self.log_message(f"🔄 Atualizando item {id_item} da venda {id_venda}...", "update")
                    await self.atualizar_item_venda(cursor_remoto, item)
                else:
                    self.log_message(f"⬆️ Enviando novo item {id_item} para venda {id_venda}...", "insert")
                    await self.inserir_item_venda(cursor_remoto, item)
            except Exception as e:
                self.log_message(f"❌ Erro no item {id_item} da venda {id_venda}: {str(e)}", "error")
                raise

    async def inserir_item_venda(self, cursor, item):
        await cursor.execute("""
            INSERT INTO vendaitens(
                id, idvenda, idproduto, desconto, quantidade, descvaloritens, estornado,
                observacoes, pagto_parcial, cancelado, parcial, impresso, desconto_porcento,
                descricao_item, id_atendente, preco_custo, custo_medio, hora, largura,
                altura, unidade_venda, micra, peso, qtde_cx, tamanho, fracionada,
                densidade, total_producao, qtde_entregue, peso_cx, peso_total, producao,
                contador, acrescimo, qtde_recebida, impressao_extra, valor_real, vlunitario,
                precovenda_cadastro
            ) VALUES (
                %(id)s, %(idvenda)s, %(idproduto)s, %(desconto)s, %(quantidade)s, %(descvaloritens)s, %(estornado)s,
                %(observacoes)s, %(pagto_parcial)s, %(cancelado)s, %(parcial)s, %(impresso)s, %(desconto_porcento)s,
                %(descricao_item)s, %(id_atendente)s, %(preco_custo)s, %(custo_medio)s, %(hora)s, %(largura)s,
                %(altura)s, %(unidade_venda)s, %(micra)s, %(peso)s, %(qtde_cx)s, %(tamanho)s, %(fracionada)s,
                %(densidade)s, %(total_producao)s, %(qtde_entregue)s, %(peso_cx)s, %(peso_total)s, %(producao)s,
                %(contador)s, %(acrescimo)s, %(qtde_recebida)s, %(impressao_extra)s, %(valor_real)s, %(vlunitario)s,
                %(precovenda_cadastro)s
            )
        """, item)

    async def atualizar_item_venda(self, cursor, item):
        await cursor.execute("""
            UPDATE vendaitens SET
                idvenda = %(idvenda)s,
                idproduto = %(idproduto)s,
                desconto = %(desconto)s,
                quantidade = %(quantidade)s,
                descvaloritens = %(descvaloritens)s,
                estornado = %(estornado)s,
                observacoes = %(observacoes)s,
                pagto_parcial = %(pagto_parcial)s,
                cancelado = %(cancelado)s,
                parcial = %(parcial)s,
                impresso = %(impresso)s,
                desconto_porcento = %(desconto_porcento)s,
                descricao_item = %(descricao_item)s,
                id_atendente = %(id_atendente)s,
                preco_custo = %(preco_custo)s,
                custo_medio = %(custo_medio)s,
                hora = %(hora)s,
                largura = %(largura)s,
                altura = %(altura)s,
                unidade_venda = %(unidade_venda)s,
                micra = %(micra)s,
                peso = %(peso)s,
                qtde_cx = %(qtde_cx)s,
                tamanho = %(tamanho)s,
                fracionada = %(fracionada)s,
                densidade = %(densidade)s,
                total_producao = %(total_producao)s,
                qtde_entregue = %(qtde_entregue)s,
                peso_cx = %(peso_cx)s,
                peso_total = %(peso_total)s,
                producao = %(producao)s,
                contador = %(contador)s,
                acrescimo = %(acrescimo)s,
                qtde_recebida = %(qtde_recebida)s,
                impressao_extra = %(impressao_extra)s,
                valor_real = %(valor_real)s,
                precovenda_cadastro = %(precovenda_cadastro)s
            WHERE id = %(id)s
        """, item)

    def log_message(self, message, tag="info"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.memo.insert(tk.END, f"{timestamp} - {message}\n", tag)
        self.memo.see(tk.END)
        self.root.update()

    def update_progress_bar(self, value, maximum=None):
        if maximum:
            self.progress_bar["maximum"] = maximum
        self.progress_bar["value"] = value
        percent = int((value / self.progress_bar["maximum"]) * 100)
        self.progress_label.config(text=f"Progresso: {percent}%")
        self.root.update()

    def update_ui_status(self, active):
        if active:
            self.status_label.config(text="🟢 Sincronização Ativa - Vs 2.0", background=self.colors["success"])
            self.progress_bar.start()
        else:
            self.status_label.config(text="🔴 Sincronização Parada", background=self.colors["danger"])
            self.progress_bar.stop()
            self.progress_bar["value"] = 0
            self.progress_label.config(text="Pronto para iniciar")
        self.start_btn["state"] = "disabled" if active else "normal"
        self.stop_btn["state"] = "normal" if active else "disabled"
        self.root.update()

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        root = tk.Tk()
        app = SincronizadorApp(root)
        root.state('zoomed')
        root.mainloop()
    except Exception as e:
        with open('error_log.txt', 'w') as f:
            f.write(str(e))
        print(f"An error occurred: {e}")
