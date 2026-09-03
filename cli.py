import os
import sys
import subprocess

# Ensure UTF-8 console output on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, DownloadColumn, TransferSpeedColumn, TimeRemainingColumn

from core.cookie_manager import CookieManager
from core.downloader import TikTokDownloader
from core.profile_scraper import ProfileScraper

console = Console()


def _cli_friendly_error(exc: Exception) -> str:
    """Convert technical exceptions into user-friendly Vietnamese messages."""
    msg = str(exc).lower()
    if "invalid url" in msg or "not a valid" in msg or "unsupported url" in msg:
        return "Link không hợp lệ. Kiểm tra lại đường dẫn TikTok hoặc Douyin."
    if "private" in msg or "login" in msg or "403" in msg:
        return "Video ở chế độ riêng tư hoặc yêu cầu đăng nhập."
    if "not found" in msg or "404" in msg:
        return "Video không tồn tại hoặc đã bị xóa."
    if "timeout" in msg or "timed out" in msg:
        return "Kết nối quá chậm. Thử lại sau."
    if "connection" in msg or "network" in msg:
        return "Không thể kết nối mạng. Kiểm tra internet."
    if "rate limit" in msg or "429" in msg:
        return "Tải quá nhanh. Chờ vài giây rồi thử lại."
    return str(exc)

def print_banner():
    banner_text = r"""[bold cyan]
  _______ _ _   _______    _      _____                      _                 _
 |__   __(_) | |__   __|  | |    |  __ \                    | |               | |
    | |   _| | __ | | ___ | | __ | |  | | _____      ___ __ | | ___   __ _  __| | ___ _ __
    | |  | | |/ / | |/ _ \| |/ / | |  | |/ _ \ \ /\ / / '_ \| |/ _ \ / _` |/ _` |/ _ \ '__|
    | |  | |   <  | | (_) |   <  | |__| | (_) \ V  V /| | | | | (_) | (_| | (_| |  __/ |
    |_|  |_|_|\_\ |_|\___/|_|\_\ |_____/ \___/ \_/\_/ |_| |_|_|\___/ \__,_|\__,_|\___|_|
[/bold cyan]
[dim]⚡ 100% Direct Official Engine (No 3rd Party APIs) • TikTok & Douyin Support[/dim]
"""
    console.print(Panel.fit(
        banner_text + "[bold green][+][/bold green] [bold white]INFRABASES[/bold white]\n[dim]TikTok & Douyin Downloader[/dim]",
        border_style="green",
        padding=(1, 5),
    ))

def show_config(cookie_mgr: CookieManager):
    cfg = cookie_mgr.config
    table = Table(title="[bold green]Cấu Hình Hiện Tại[/bold green]")
    table.add_column("Tham số", style="cyan")
    table.add_column("Giá trị", style="yellow")

    table.add_row("Thư mục lưu trữ", cfg.get("download_dir", "./downloads"))
    table.add_row("Chất lượng video", cfg.get("video_quality", "hd").upper())
    table.add_row("Lưu Metadata JSON", str(cfg.get("save_metadata", True)))
    table.add_row("Cookie thủ công", "Đã thiết lập" if cfg.get("custom_cookie_string") else "Trống")

    console.print(table)

def handle_single_download(downloader: TikTokDownloader):
    url = Prompt.ask("\n[bold cyan]Nhập liên kết video TikTok hoặc Douyin[/bold cyan]")
    if not url.strip():
        console.print("[red]Liên kết không được để trống![/red]")
        return

    with console.status("[bold green]Đang phân tích thông tin video từ TikTok/Douyin...[/bold green]"):
        try:
            info = downloader.get_video_info(url)
        except Exception as e:
            console.print(f"[bold red]Lỗi phân tích:[/bold red] {_cli_friendly_error(e)}")
            return

    console.print(Panel.fit(
        f"[bold]Nền tảng:[/bold] {info.get('platform', 'tiktok').upper()}\n"
        f"[bold]Tiêu đề:[/bold] {info.get('title')}\n"
        f"[bold]Tác giả:[/bold] @{info.get('uploader')} ({info.get('nickname')})\n"
        f"[bold]Thời lượng:[/bold] {info.get('duration')}s",
        title="[bold green]✔ Thông tin Video[/bold green]"
    ))

    if not Confirm.ask("Bắt đầu tải video?", default=True):
        return

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=console
    ) as progress:
        task_id = progress.add_task("[cyan]Đang tải video...", total=None)

        def update_progress(downloaded, total, percent):
            if total > 0:
                progress.update(task_id, total=total, completed=downloaded)

        try:
            res = downloader.download_video(url, progress_callback=update_progress)
            console.print(f"\n[bold green]✔ Tải thành công![/bold green] Đã lưu tại:\n[yellow]{res['saved_path']}[/yellow]")
        except Exception as e:
            console.print(f"\n[bold red]✖ Lỗi khi tải video:[/bold red] {_cli_friendly_error(e)}")

def handle_profile_download(scraper: ProfileScraper):
    target = Prompt.ask("\n[bold cyan]Nhập @username kênh hoặc đường dẫn file danh sách URL[/bold cyan]")
    if not target.strip():
        console.print("[red]Không được để trống mục tiêu![/red]")
        return

    max_videos_str = Prompt.ask("[bold cyan]Số lượng video tối đa muốn tải[/bold cyan] (0 = tất cả)", default="0")
    try:
        max_videos = int(max_videos_str)
    except ValueError:
        max_videos = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console
    ) as progress:
        task = progress.add_task("[yellow]Đang tải danh sách/kênh...", total=100)

        def batch_callback(current, total, msg):
            if total > 0:
                progress.update(task, total=total, completed=current, description=f"[cyan]{msg}")
            else:
                progress.update(task, description=f"[cyan]{msg}")

        try:
            res = scraper.download_profile_or_list(target, max_videos=max_videos, progress_callback=batch_callback)
            console.print(Panel.fit(
                f"[bold]Tổng số video:[/bold] {res.get('total', 0)}\n"
                f"[bold green]Thành công:[/bold green] {res.get('downloaded', 0)}\n"
                f"[bold yellow]Bỏ qua (đã tải trước đó):[/bold yellow] {res.get('skipped', 0)}\n"
                f"[bold red]Thất bại:[/bold red] {res.get('failed', 0)}",
                title="[bold green]Kết Quả Tải Hàng Loạt[/bold green]"
            ))
            errors = res.get("errors", [])
            if errors:
                console.print("\n[bold red]Chi tiết lỗi:[/bold red]")
                for i, err in enumerate(errors, 1):
                    url_short = err["url"][-60:] if len(err["url"]) > 60 else err["url"]
                    console.print(f"  {i}. [yellow]{url_short}[/yellow]")
                    console.print(f"     [red]{err['error']}[/red]")
        except Exception as e:
            console.print(f"\n[bold red]✖ Lỗi tiến trình hàng loạt:[/bold red] {_cli_friendly_error(e)}")

def handle_settings(cookie_mgr: CookieManager):
    show_config(cookie_mgr)
    console.print("\n[bold]Tùy chọn cấu hình:[/bold]")
    console.print("1. Nhập cookie thủ công")
    console.print("2. Đổi thư mục tải về")
    console.print("3. Quay lại menu chính")

    choice = Prompt.ask("\nChọn chức năng", choices=["1", "2", "3"], default="3")

    if choice == "1":
        c = Prompt.ask("Dán chuỗi cookie (để trống để xóa)")
        cookie_mgr.save_config({"custom_cookie_string": c.strip()})
        console.print("[green]✔ Đã cập nhật chuỗi cookie![/green]")
    elif choice == "2":
        d = Prompt.ask("Đường dẫn thư mục lưu trữ mới")
        if d.strip():
            cookie_mgr.save_config({"download_dir": d.strip()})
            console.print("[green]✔ Đã cập nhật thư mục lưu trữ![/green]")

def main():
    cookie_mgr = CookieManager()
    downloader = TikTokDownloader(cookie_mgr)
    scraper = ProfileScraper(cookie_mgr)

    while True:
        os.system("cls" if os.name == "nt" else "clear")
        print_banner()
        console.print("[bold cyan]=== MENU ĐIỀU KHIỂN ===[/bold cyan]")
        console.print("1. [bold white]Tải video đơn[/bold white] (TikTok / Douyin)")
        console.print("2. [bold white]Tải hàng loạt[/bold white] (Kênh / danh sách URL)")
        console.print("3. [bold white]Cấu hình[/bold white] (Cookie / thư mục lưu)")
        console.print("4. [bold white]Mở Web Dashboard[/bold white]")
        console.print("5. [bold red]Thoát[/bold red]")

        choice = Prompt.ask("\nNhập lựa chọn của bạn", choices=["1", "2", "3", "4", "5"], default="1")

        if choice == "1":
            handle_single_download(downloader)
            Prompt.ask("\n[dim]Nhấn Enter để tiếp tục...[/dim]")
        elif choice == "2":
            handle_profile_download(scraper)
            Prompt.ask("\n[dim]Nhấn Enter để tiếp tục...[/dim]")
        elif choice == "3":
            handle_settings(cookie_mgr)
            Prompt.ask("\n[dim]Nhấn Enter để tiếp tục...[/dim]")
        elif choice == "4":
            console.print("[bold green]Đang khởi động Web Dashboard tại http://127.0.0.1:8080 ...[/bold green]")
            console.print("[dim]Nhấn Ctrl+C trong terminal này để dừng server.[/dim]")
            try:
                proc = subprocess.Popen(
                    [sys.executable, "-m", "uvicorn", "web.app:app",
                     "--host", "127.0.0.1", "--port", "8080"],
                    cwd=os.path.dirname(os.path.abspath(__file__)),
                )
                proc.wait()
            except KeyboardInterrupt:
                proc.terminate()
                console.print("\n[yellow]Đã dừng Web Dashboard.[/yellow]")
        elif choice == "5":
            console.print("[yellow]Tạm biệt![/yellow]")
            break

if __name__ == "__main__":
    main()
