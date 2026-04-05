import typer
from rich.console import Console

console = Console()
app = typer.Typer(help="Start the local web dashboard")


@app.callback(invoke_without_command=True)
def web(
    port: int = typer.Option(7730, "--port", "-p", help="Port to listen on"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Don't open browser automatically"),
):
    import uvicorn
    import webbrowser
    import threading
    from brain.web.app import app as fastapi_app

    url = f"http://localhost:{port}"
    console.print(f"[bold cyan]🧠 brain dashboard[/bold cyan] → [underline]{url}[/underline]")
    console.print("[dim]Ctrl+C to stop[/dim]")

    if not no_browser:
        # Open browser after a short delay so server starts first
        def _open():
            import time
            time.sleep(0.8)
            webbrowser.open(url)
        threading.Thread(target=_open, daemon=True).start()

    uvicorn.run(fastapi_app, host="127.0.0.1", port=port, log_level="warning")
