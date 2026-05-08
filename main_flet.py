import flet as ft
import asyncio
import threading
import aiomysql
from datetime import datetime
try:
    import pystray
    from PIL import Image
    TRAY_AVAILABLE = True
except Exception:
    TRAY_AVAILABLE = False
import json
import os
import sys

CONFIG_FILE = os.path.join(os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else __file__), "config.json")

DEFAULT_DB_LOCAL = {
    "host": "localhost",
    "port": 3306,
    "user": "root",
    "password": "",
    "db": "",
    "charset": "latin1",
    "use_unicode": True,
}
DEFAULT_DB_REMOTO = {
    "host": "",
    "port": 3306,
    "user": "root",
    "password": "",
    "db": "",
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

LOG_COLORS = {
    "info":    "#00BCD4",
    "success": "#4CAF50",
    "error":   "#F44336",
    "warning": "#FFC107",
    "process": "#2196F3",
    "update":  "#FF9800",
    "insert":  "#9C27B0",
    "header":  "#212121",
}


class SincronizadorApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.sync_active = False
        self.tray_icon = None
        self.tray_thread = None
        self.produto_sync_last = None
        self._progress_max = 100
        self.log_list = ft.ListView(expand=True, auto_scroll=True, spacing=1, padding=4)
        self._setup_ui()
        self._setup_tray_icon()
        self.page.window.prevent_close = True
        self.page.on_window_event = self._handle_window_event
        if AUTO_START_TRAY:
            threading.Timer(0.5, self._auto_start_and_tray).start()

    def _handle_window_event(self, e):
        if e.data == "close":
            self._minimize_to_tray()

    def _auto_start_and_tray(self):
        self.start_sync()
        self._minimize_to_tray()

    # ── tray ──────────────────────────────────────────────────────────────────

    def _load_tray_image(self):
        if not TRAY_AVAILABLE:
            return None
        ico_path = os.path.join(
            getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__))),
            '788.ico'
        )
        try:
            return Image.open(ico_path).convert('RGBA').resize((64, 64))
        except Exception:
            color = (76, 175, 80) if self.sync_active else (244, 67, 54)
            return Image.new('RGBA', (64, 64), color)

    def _setup_tray_icon(self):
        if not TRAY_AVAILABLE:
            return
        image = self._load_tray_image()
        menu = pystray.Menu(
            pystray.MenuItem('Abrir', self._restore_from_tray),
            pystray.MenuItem(
                lambda item: 'Parar Sincronização' if self.sync_active else 'Iniciar Sincronização',
                self._tray_toggle_sync,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Sair', self._quit_application),
        )
        if self.tray_icon:
            self.tray_icon.stop()
        tooltip = "Sincronizador — Ativo" if self.sync_active else "Sincronizador — Parado"
        self.tray_icon = pystray.Icon("sync_app", image, tooltip, menu)

    def _tray_toggle_sync(self, icon=None, item=None):
        if self.sync_active:
            self.stop_sync()
        else:
            self.start_sync()
        threading.Timer(0.2, self._setup_tray_icon).start()

    def _minimize_to_tray(self):
        if not TRAY_AVAILABLE:
            self.page.window.visible = False
            self.page.update()
            return
        self.page.window.visible = False
        self.page.update()
        self._setup_tray_icon()
        self.tray_thread = threading.Thread(target=lambda: self.tray_icon.run(), daemon=True)
        self.tray_thread.start()

    def _restore_from_tray(self, icon=None, item=None):
        if self.tray_icon:
            self.tray_icon.stop()
        self.page.window.visible = True
        self.page.window.bring_to_front()
        self.page.update()

    def _quit_application(self, icon=None, item=None):
        self.sync_active = False
        if self.tray_icon:
            self.tray_icon.stop()
        self.page.window.destroy()

    # ── UI setup ──────────────────────────────────────────────────────────────

    def _setup_ui(self):
        self.page.title = "Sincronizador de Bancos de Dados"
        self.page.bgcolor = "#f5f5f5"
        self.page.padding = 10
        self.page.window.width = 1000
        self.page.window.height = 700
        self.page.window.min_width = 800
        self.page.window.min_height = 600
        self.page.window.center()

        # status badge
        self.status_text = ft.Text("🔴 Sincronização Parada", color="white", size=12)
        self.status_badge = ft.Container(
            content=self.status_text,
            bgcolor="#F44336",
            padding=ft.padding.symmetric(horizontal=10, vertical=5),
            border_radius=4,
        )

        header = ft.Row(
            controls=[
                ft.Text(
                    "🔄 Sincronizador de Bancos de Dados",
                    size=16,
                    weight=ft.FontWeight.BOLD,
                    color="#212121",
                ),
                ft.Container(expand=True),
                self.status_badge,
            ],
        )

        log_area = ft.Container(
            content=ft.Column(
                [
                    ft.Container(
                        content=ft.Text(" Log de Atividades ", size=11, color="#555555"),
                        padding=ft.padding.only(bottom=4),
                    ),
                    ft.Container(
                        content=self.log_list,
                        bgcolor="white",
                        border=ft.border.all(1, "#cccccc"),
                        border_radius=4,
                        expand=True,
                    ),
                ],
                spacing=0,
                expand=True,
            ),
            border=ft.border.all(1, "#dddddd"),
            border_radius=6,
            padding=8,
            expand=True,
        )

        self.progress_label = ft.Text("Pronto para iniciar", size=9, color="#555555")
        self.progress_bar = ft.ProgressBar(value=0, color="#4CAF50", bgcolor="#e0e0e0")
        progress_section = ft.Column([self.progress_label, self.progress_bar], spacing=2)

        self.start_btn = ft.ElevatedButton(
            "🚀 Iniciar Sincronização",
            on_click=lambda _: self.start_sync(),
            style=ft.ButtonStyle(bgcolor="#2196F3", color="white"),
            expand=True,
        )
        self.stop_btn = ft.ElevatedButton(
            "⏹ Parar Sincronização",
            on_click=lambda _: self.stop_sync(),
            style=ft.ButtonStyle(bgcolor="#F44336", color="white"),
            expand=True,
            disabled=True,
        )
        clear_btn = ft.ElevatedButton(
            "🧹 Limpar Log",
            on_click=lambda _: self.clear_log(),
            expand=True,
        )
        config_btn = ft.ElevatedButton(
            "⚙️ Configurações",
            on_click=lambda _: self._open_config_dialog(),
            expand=True,
        )

        buttons_row = ft.Row([self.start_btn, self.stop_btn, clear_btn, config_btn], spacing=8)

        footer = ft.Row(
            [
                ft.Container(expand=True),
                ft.Text("Versão 2.1 © 2025 - DynamicApps Solutions", size=9, color="#777777"),
            ]
        )

        self.page.add(
            ft.Column(
                [header, log_area, progress_section, buttons_row, footer],
                expand=True,
                spacing=8,
            )
        )

    # ── config dialog ─────────────────────────────────────────────────────────

    def _open_config_dialog(self):
        FIELD_LABELS = [
            ("Host",    "host"),
            ("Porta",   "port"),
            ("Usuário", "user"),
            ("Senha",   "password"),
            ("Banco",   "db"),
            ("Charset", "charset"),
        ]

        def make_fields(source):
            return {
                key: ft.TextField(
                    value=str(source.get(key, "")),
                    password=(key == "password"),
                    can_reveal_password=(key == "password"),
                    expand=True,
                    height=42,
                    text_size=12,
                    content_padding=ft.padding.symmetric(horizontal=8, vertical=4),
                )
                for _, key in FIELD_LABELS
            }

        local_fields  = make_fields(DB_LOCAL)
        remoto_fields = make_fields(DB_REMOTO)
        auto_cb = ft.Checkbox(
            label="Iniciar sincronizando automaticamente e minimizar para a bandeja",
            value=AUTO_START_TRAY,
        )

        def section(title, fields):
            rows = [ft.Text(title, size=13, weight=ft.FontWeight.BOLD, color="#212121")]
            for label, key in FIELD_LABELS:
                rows.append(ft.Row([
                    ft.Text(f"{label}:", width=80, size=12),
                    fields[key],
                ], spacing=6))
            return ft.Container(
                content=ft.Column(rows, spacing=4),
                border=ft.border.all(1, "#dddddd"),
                border_radius=6,
                padding=10,
            )

        def on_save(e):
            global DB_LOCAL, DB_REMOTO, AUTO_START_TRAY
            try:
                new_local = {
                    "host":        local_fields["host"].value.strip(),
                    "port":        int(local_fields["port"].value.strip()),
                    "user":        local_fields["user"].value.strip(),
                    "password":    local_fields["password"].value,
                    "db":          local_fields["db"].value.strip(),
                    "charset":     local_fields["charset"].value.strip(),
                    "use_unicode": True,
                }
                new_remoto = {
                    "host":        remoto_fields["host"].value.strip(),
                    "port":        int(remoto_fields["port"].value.strip()),
                    "user":        remoto_fields["user"].value.strip(),
                    "password":    remoto_fields["password"].value,
                    "db":          remoto_fields["db"].value.strip(),
                    "charset":     remoto_fields["charset"].value.strip(),
                    "use_unicode": True,
                }
                AUTO_START_TRAY = auto_cb.value
                save_config(new_local, new_remoto, AUTO_START_TRAY)
                DB_LOCAL.update(new_local)
                DB_REMOTO.update(new_remoto)
                dlg.open = False
                self.page.update()
                self._show_snack("Configurações salvas com sucesso!", "#4CAF50")
            except ValueError:
                self._show_snack("Porta deve ser um número inteiro.", "#F44336")

        def on_cancel(e):
            dlg.open = False
            self.page.update()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Configurações", weight=ft.FontWeight.BOLD),
            content=ft.Container(
                width=500,
                height=520,
                content=ft.Column(
                    [
                        section("Banco Local", local_fields),
                        section("Banco Remoto", remoto_fields),
                        ft.Container(
                            content=ft.Column([
                                ft.Text("Inicialização", size=13, weight=ft.FontWeight.BOLD),
                                auto_cb,
                            ], spacing=4),
                            border=ft.border.all(1, "#dddddd"),
                            border_radius=6,
                            padding=10,
                        ),
                    ],
                    scroll=ft.ScrollMode.AUTO,
                    spacing=10,
                ),
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=on_cancel),
                ft.ElevatedButton(
                    "Salvar",
                    on_click=on_save,
                    style=ft.ButtonStyle(bgcolor="#2196F3", color="white"),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.overlay.append(dlg)
        dlg.open = True
        self.page.update()

    # ── UI helpers ────────────────────────────────────────────────────────────

    def _show_snack(self, message, bgcolor="#4CAF50"):
        snack = ft.SnackBar(ft.Text(message, color="white"), bgcolor=bgcolor)
        self.page.overlay.append(snack)
        snack.open = True
        self.page.update()

    def clear_log(self):
        self.log_list.controls.clear()
        self.page.update()

    def log_message(self, message, tag="info"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        color = LOG_COLORS.get(tag, "#333333")
        bold  = tag == "header"
        text  = ft.Text(
            f"{timestamp} - {message}",
            color=color,
            size=11,
            weight=ft.FontWeight.BOLD if bold else ft.FontWeight.NORMAL,
        )
        item = ft.Container(content=text, bgcolor="#FFEBEE", padding=2) if tag == "error" else text
        self.log_list.controls.append(item)
        self.page.update()

    def update_progress_bar(self, value, maximum=None):
        if maximum:
            self._progress_max = maximum
        pct = int((value / self._progress_max) * 100) if self._progress_max else 0
        self.progress_bar.value = value / self._progress_max if self._progress_max else 0
        self.progress_label.value = f"Progresso: {pct}%"
        self.page.update()

    def update_ui_status(self, active):
        if active:
            self.status_text.value = "🟢 Sincronização Ativa - Vs 2.0"
            self.status_badge.bgcolor = "#4CAF50"
        else:
            self.status_text.value = "🔴 Sincronização Parada"
            self.status_badge.bgcolor = "#F44336"
            self.progress_bar.value = 0
            self.progress_label.value = "Pronto para iniciar"
        self.start_btn.disabled = active
        self.stop_btn.disabled  = not active
        self.page.update()

    # ── sync control ──────────────────────────────────────────────────────────

    def start_sync(self):
        if not self.sync_active:
            self.sync_active = True
            self.update_ui_status(True)
            threading.Thread(
                target=lambda: asyncio.run(self.run_async_sync()), daemon=True
            ).start()

    def stop_sync(self):
        if self.sync_active:
            self.sync_active = False
            self.log_message("Sincronização sendo parada...", "warning")

    # ── async sync (unchanged from original) ─────────────────────────────────

    async def run_async_sync(self):
        self.produto_sync_last = datetime.now()
        pool_local = pool_remoto = None
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
                    host=DB_LOCAL['host'], port=DB_LOCAL['port'],
                    user=DB_LOCAL['user'], password=DB_LOCAL['password'],
                    db=DB_LOCAL['db'], charset=DB_LOCAL['charset'],
                    use_unicode=DB_LOCAL['use_unicode'], minsize=1, maxsize=10,
                )
                pool_remoto = await aiomysql.create_pool(
                    host=DB_REMOTO['host'], port=DB_REMOTO['port'],
                    user=DB_REMOTO['user'], password=DB_REMOTO['password'],
                    db=DB_REMOTO['db'], charset=DB_REMOTO['charset'],
                    use_unicode=DB_REMOTO['use_unicode'], minsize=1, maxsize=10,
                )
                self.log_message(
                    f"✅ Conexão estabelecida | Local: {DB_LOCAL['host']}:{DB_LOCAL['port']}/{DB_LOCAL['db']} | "
                    f"Remoto: {DB_REMOTO['host']}:{DB_REMOTO['port']}/{DB_REMOTO['db']}",
                    "success",
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

    # ── produtos ──────────────────────────────────────────────────────────────

    async def sincronizar_produtos(self, pool_local, pool_remoto):
        self.log_message("🔄 Iniciando sincronização de produtos...", "header")
        async with pool_local.acquire() as conn_check:
            async with conn_check.cursor(aiomysql.DictCursor) as cursor_check:
                await cursor_check.execute("SELECT COUNT(*) as total FROM produto WHERE enviado = 'N' OR enviado IS NULL")
                result = await cursor_check.fetchone()
                self.log_message(f"🔎 Verificação: Existem {result['total']} produtos não enviados", "info")
        async with pool_local.acquire() as conn_local, pool_remoto.acquire() as conn_remoto:
            async with conn_local.cursor(aiomysql.DictCursor) as cursor_local, \
                       conn_remoto.cursor(aiomysql.DictCursor) as cursor_remoto:
                await cursor_local.execute("SET NAMES latin1;")
                await cursor_remoto.execute("SET NAMES latin1;")
                self.log_message("🔍 Buscando produtos para sincronizar do banco local...", "info")
                await cursor_local.execute("""
                    SELECT * FROM produto
                    WHERE enviado = 'N' OR enviado IS NULL
                    ORDER BY id DESC LIMIT 100
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
                        if await cursor_remoto.fetchone():
                            self.log_message("🔄 Atualizando produto existente...", "update")
                            await self._atualizar_produto(cursor_remoto, produto)
                        else:
                            self.log_message("⬆️ Enviando novo produto...", "insert")
                            await self._inserir_produto(cursor_remoto, produto)
                        await conn_remoto.commit()
                        self.log_message(f"✅ Produto Nº {id_produto} sincronizado com sucesso!", "success")
                        await self._marcar_como_enviado(cursor_local, id_produto)
                    except Exception as e:
                        await conn_remoto.rollback()
                        self.log_message(f"❌ Erro no produto {id_produto}: {str(e)}", "error")
                    await asyncio.sleep(0.5)
                self.log_message("🏁 Sincronização de produtos concluída!", "success")

    async def _marcar_como_enviado(self, cursor, id_produto):
        try:
            await cursor.execute("""
                UPDATE produto SET enviado = 'S'
                WHERE id = %s AND (enviado = 'N' OR enviado IS NULL)
            """, (id_produto,))
            if cursor.rowcount == 0:
                self.log_message(f"⚠️ Produto {id_produto} não foi marcado como enviado (já estava marcado?)", "warning")
            else:
                await cursor.connection.commit()
                self.log_message(f"✓ Produto {id_produto} marcado como enviado", "success")
        except Exception as e:
            self.log_message(f"❌ Erro ao marcar produto {id_produto} como enviado: {str(e)}", "error")
            raise

    async def _inserir_produto(self, cursor, produto):
        fields = list(produto.keys())
        await cursor.execute(
            f"INSERT INTO produto ({', '.join(fields)}) VALUES ({', '.join(f'%({k})s' for k in fields)})",
            produto,
        )

    async def _atualizar_produto(self, cursor, produto):
        sets = ", ".join(f"{f} = %({f})s" for f in produto if f != "id")
        await cursor.execute(f"UPDATE produto SET {sets} WHERE id = %(id)s", produto)

    # ── lançamentos caixa ─────────────────────────────────────────────────────

    async def sincronizar_lancamentos_caixa(self, pool_local, pool_remoto):
        self.log_message("🔄 Iniciando sincronização de lançamentos de caixa...", "header")
        async with pool_local.acquire() as conn_check:
            async with conn_check.cursor(aiomysql.DictCursor) as cursor_check:
                await cursor_check.execute("SELECT COUNT(*) as total FROM lancamentoscaixa WHERE transferido = 'N' OR transferido IS NULL")
                result = await cursor_check.fetchone()
                self.log_message(f"🔎 Verificação: Existem {result['total']} lançamentos não transferidos", "info")
        async with pool_local.acquire() as conn_local, pool_remoto.acquire() as conn_remoto:
            async with conn_local.cursor(aiomysql.DictCursor) as cursor_local, \
                       conn_remoto.cursor(aiomysql.DictCursor) as cursor_remoto:
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
                    ORDER BY id DESC LIMIT 100
                """)
                dados_locais = await cursor_local.fetchall()
                total = len(dados_locais)
                self.log_message(f"📊 Total de lançamentos encontrados para sincronizar: {total}", "info")
                if total == 0:
                    self.log_message("ℹ️ Nenhum lançamento novo encontrado.", "info")
                    return
                self.update_progress_bar(0, total)
                for i, registro in enumerate(dados_locais, 1):
                    if not self.sync_active:
                        break
                    id_r = registro["id"]
                    self.log_message(f"📦 Processando lançamento Nº {id_r} ({i}/{total})...", "process")
                    self.update_progress_bar(i)
                    try:
                        await cursor_remoto.execute("SELECT id FROM lancamentoscaixa WHERE id = %s", (id_r,))
                        if await cursor_remoto.fetchone():
                            self.log_message("🔄 Atualizando lançamento existente...", "update")
                            await self._atualizar_lancamento(cursor_remoto, registro)
                        else:
                            self.log_message("⬆️ Enviando novo lançamento...", "insert")
                            await self._inserir_lancamento(cursor_remoto, registro)
                        await conn_remoto.commit()
                        self.log_message(f"✅ Lançamento Nº {id_r} sincronizado com sucesso!", "success")
                        await self._marcar_como_transferido(cursor_local, id_r, 'lancamentoscaixa')
                    except Exception as e:
                        await conn_remoto.rollback()
                        self.log_message(f"❌ Erro no lançamento {id_r}: {str(e)}", "error")
                    await asyncio.sleep(0.5)
                self.log_message("🏁 Sincronização de lançamentos concluída!", "success")

    async def _marcar_como_transferido(self, cursor, id_registro, tabela):
        try:
            await cursor.execute(
                f"UPDATE {tabela} SET transferido = 'S' WHERE id = %s AND (transferido = 'N' OR transferido IS NULL)",
                (id_registro,),
            )
            if cursor.rowcount == 0:
                self.log_message(f"⚠️ Registro {id_registro} da tabela {tabela} não foi marcado como transferido", "warning")
            else:
                await cursor.connection.commit()
                self.log_message(f"✓ Registro {id_registro} da tabela {tabela} marcado como transferido", "success")
        except Exception as e:
            self.log_message(f"❌ Erro ao marcar registro {id_registro} da tabela {tabela} como transferido: {str(e)}", "error")
            raise

    async def _inserir_lancamento(self, cursor, registro):
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

    async def _atualizar_lancamento(self, cursor, registro):
        await cursor.execute("""
            UPDATE lancamentoscaixa SET
                idusuario=%(idusuario)s, idcaixa=%(idcaixa)s, dataemissao=%(dataemissao)s,
                tipomovimento=%(tipomovimento)s, ndoc=%(ndoc)s, valor=%(valor)s, cadastro=%(cadastro)s,
                observacoes=%(observacoes)s, parcela=%(parcela)s, id_origem=%(id_origem)s,
                sigla_origem=%(sigla_origem)s, hora=%(hora)s, situacao=%(situacao)s,
                descricao_recebimento=%(descricao_recebimento)s, id_plano_contas=%(id_plano_contas)s,
                id_movimento=%(id_movimento)s, vencimento=%(vencimento)s, id_pagto=%(id_pagto)s,
                desc_tipo=%(desc_tipo)s, valor_pago=%(valor_pago)s, data_pagamento=%(data_pagamento)s,
                taxa_cartao=%(taxa_cartao)s
            WHERE id=%(id)s
        """, registro)

    # ── vendas ────────────────────────────────────────────────────────────────

    async def sincronizar_vendas(self, pool_local, pool_remoto):
        self.log_message("🔄 Iniciando sincronização de vendas...", "header")
        async with pool_local.acquire() as conn_check:
            async with conn_check.cursor(aiomysql.DictCursor) as cursor_check:
                await cursor_check.execute("SELECT COUNT(*) as total FROM venda WHERE transferido = 'N' OR transferido IS NULL")
                result = await cursor_check.fetchone()
                self.log_message(f"🔎 Verificação: Existem {result['total']} vendas não transferidas", "info")
        async with pool_local.acquire() as conn_local, pool_remoto.acquire() as conn_remoto:
            async with conn_local.cursor(aiomysql.DictCursor) as cursor_local, \
                       conn_remoto.cursor(aiomysql.DictCursor) as cursor_remoto:
                await cursor_local.execute("SET NAMES latin1;")
                await cursor_remoto.execute("SET NAMES latin1;")
                self.log_message("🔍 Buscando vendas para sincronizar do banco local...", "info")
                await cursor_local.execute("""
                    SELECT * FROM venda
                    WHERE transferido = 'N' OR transferido IS NULL
                    ORDER BY id DESC LIMIT 50
                """)
                vendas = await cursor_local.fetchall()
                total = len(vendas)
                self.log_message(f"📊 Total de vendas encontradas para sincronizar: {total}", "info")
                if total == 0:
                    self.log_message("ℹ️ Nenhuma venda nova encontrada.", "info")
                    return
                self.update_progress_bar(0, total)
                for i, venda in enumerate(vendas, 1):
                    if not self.sync_active:
                        break
                    id_venda = venda["id"]
                    self.log_message(f"📦 Processando venda Nº {id_venda} ({i}/{total})...", "process")
                    self.update_progress_bar(i)
                    try:
                        await cursor_remoto.execute("SELECT id FROM venda WHERE id = %s", (id_venda,))
                        if await cursor_remoto.fetchone():
                            self.log_message("🔄 Atualizando venda existente...", "update")
                            await self._atualizar_venda(cursor_remoto, venda)
                        else:
                            self.log_message("⬆️ Enviando nova venda...", "insert")
                            await self._inserir_venda(cursor_remoto, venda)
                        await self._sincronizar_itens_venda(cursor_local, cursor_remoto, id_venda)
                        await conn_remoto.commit()
                        self.log_message(f"✅ Venda Nº {id_venda} sincronizada com sucesso!", "success")
                        await self._marcar_como_transferido(cursor_local, id_venda, 'venda')
                    except Exception as e:
                        await conn_remoto.rollback()
                        self.log_message(f"❌ Erro na venda {id_venda}: {str(e)}", "error")
                    await asyncio.sleep(0.5)
                self.log_message("🏁 Sincronização de vendas concluída!", "success")

    async def _inserir_venda(self, cursor, venda):
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

    async def _atualizar_venda(self, cursor, venda):
        await cursor.execute("""
            UPDATE venda SET
                idcliente=%(idcliente)s, data=%(data)s, hora=%(hora)s, subtotal=%(subtotal)s,
                desconto=%(desconto)s, total=%(total)s, idatendente=%(idatendente)s,
                aliqicms=%(aliqicms)s, vlbcicms=%(vlbcicms)s, valoricms=%(valoricms)s,
                aliqipi=%(aliqipi)s, vlipi=%(vlipi)s, vlfrete=%(vlfrete)s, vlseguro=%(vlseguro)s,
                vloutras=%(vloutras)s, desctotitens=%(desctotitens)s, tipo=%(tipo)s,
                situacao=%(situacao)s, troco=%(troco)s, aliqicmsst=%(aliqicmsst)s,
                vlbcicmsst=%(vlbcicmsst)s, vlicmsst=%(vlicmsst)s, idempresa=%(idempresa)s,
                vlPagto=%(vlPagto)s, numeromesa=%(numeromesa)s, agrupada=%(agrupada)s,
                npessoas=%(npessoas)s, pagtoparcial=%(pagtoparcial)s, servico=%(servico)s,
                identregador=%(identregador)s, idcaixa=%(idcaixa)s, nota=%(nota)s,
                tipooperacaovenda=%(tipooperacaovenda)s, mesa_agrupada=%(mesa_agrupada)s,
                tipo_nota=%(tipo_nota)s, numero_nf=%(numero_nf)s,
                nome_cliente_sem_cadastro=%(nome_cliente_sem_cadastro)s
            WHERE id=%(id)s
        """, venda)

    async def _sincronizar_itens_venda(self, cursor_local, cursor_remoto, id_venda):
        self.log_message(f"🔍 Buscando itens para a venda Nº {id_venda}...", "info")
        await cursor_local.execute("SELECT * FROM vendaitens WHERE idvenda = %s ORDER BY id", (id_venda,))
        itens = await cursor_local.fetchall()
        self.log_message(f"📦 Encontrados {len(itens)} itens para a venda Nº {id_venda}", "info")
        for item in itens:
            id_item = item["id"]
            try:
                await cursor_remoto.execute("SELECT id FROM vendaitens WHERE id = %s", (id_item,))
                if await cursor_remoto.fetchone():
                    self.log_message(f"🔄 Atualizando item {id_item} da venda {id_venda}...", "update")
                    await self._atualizar_item_venda(cursor_remoto, item)
                else:
                    self.log_message(f"⬆️ Enviando novo item {id_item} para venda {id_venda}...", "insert")
                    await self._inserir_item_venda(cursor_remoto, item)
            except Exception as e:
                self.log_message(f"❌ Erro no item {id_item} da venda {id_venda}: {str(e)}", "error")
                raise

    async def _inserir_item_venda(self, cursor, item):
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

    async def _atualizar_item_venda(self, cursor, item):
        await cursor.execute("""
            UPDATE vendaitens SET
                idvenda=%(idvenda)s, idproduto=%(idproduto)s, desconto=%(desconto)s,
                quantidade=%(quantidade)s, descvaloritens=%(descvaloritens)s, estornado=%(estornado)s,
                observacoes=%(observacoes)s, pagto_parcial=%(pagto_parcial)s, cancelado=%(cancelado)s,
                parcial=%(parcial)s, impresso=%(impresso)s, desconto_porcento=%(desconto_porcento)s,
                descricao_item=%(descricao_item)s, id_atendente=%(id_atendente)s,
                preco_custo=%(preco_custo)s, custo_medio=%(custo_medio)s, hora=%(hora)s,
                largura=%(largura)s, altura=%(altura)s, unidade_venda=%(unidade_venda)s,
                micra=%(micra)s, peso=%(peso)s, qtde_cx=%(qtde_cx)s, tamanho=%(tamanho)s,
                fracionada=%(fracionada)s, densidade=%(densidade)s, total_producao=%(total_producao)s,
                qtde_entregue=%(qtde_entregue)s, peso_cx=%(peso_cx)s, peso_total=%(peso_total)s,
                producao=%(producao)s, contador=%(contador)s, acrescimo=%(acrescimo)s,
                qtde_recebida=%(qtde_recebida)s, impressao_extra=%(impressao_extra)s,
                valor_real=%(valor_real)s, precovenda_cadastro=%(precovenda_cadastro)s
            WHERE id=%(id)s
        """, item)


def main(page: ft.Page):
    SincronizadorApp(page)


if __name__ == "__main__":
    ft.app(target=main)
